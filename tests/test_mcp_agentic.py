"""Tests for the opt-in high-level graph MCP adapter."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

pytest.importorskip("lasio")

try:
    from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
except ModuleNotFoundError:  # pragma: no cover - unittest discovery mode
    from _mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
from wellplot.agent.code_mode.enrichment import SemanticEnricher
from wellplot.agent.code_mode.facade import CodeModeCompileFacade
from wellplot.agent.code_mode.planner import ReportTask, SemanticPlan, SemanticPlanner
from wellplot.agent.code_mode.program_worker import ProgramSectionCompiler
from wellplot.agent.code_mode.report_worker import ReportProgramCompiler
from wellplot.agent.code_mode.source_loader import LogfileSourceLoader
from wellplot.agent.code_mode.workflow import CodeModeGraphDependencies
from wellplot.agent.execution_trace import read_agent_trace
from wellplot.agent.providers.base import (
    ProgramGenerationResult,
    ProviderMetrics,
    StructuredGenerationResult,
)
from wellplot.agent.session import (
    AgentDiagnostic,
    AgentMetrics,
    AgentSession,
    AgentSessionResult,
    AgentWorkerEvidence,
    AgentWorkerMetrics,
)
from wellplot.authoring_service import AuthoringService
from wellplot.capabilities import create_builtin_registry
from wellplot.mcp import service
from wellplot.mcp.agentic import (
    GraphAuthoringMcpOperations,
    GraphAuthoringToolResult,
    _request_context,
    register_agentic_tools,
)


class _ToolCollector:
    """Minimal FastMCP-compatible collector for registration tests."""

    def __init__(self) -> None:
        self.tools: list[dict[str, object]] = []

    def add_tool(self, function: object, **metadata: object) -> None:
        self.tools.append({"function": function, **metadata})


class _Session:
    """Deterministic direct-session substitute for adapter tests."""

    def __init__(self, *, intent: dict[str, object], mode: str) -> None:
        self.intent = intent
        self.mode = mode
        self.states: list[dict[str, object]] = []

    async def build(self, *, request: str, document: object, sources: object) -> object:
        """Return one deterministic reconstruction result."""
        self.states.append({"mode": "reconstruct", "request": request, "sources": sources})
        return _session_result("reconstruct", self.intent)

    async def revise(self, *, request: str, document: object, sources: object) -> object:
        """Return one deterministic revision result."""
        self.states.append({"mode": "revise", "request": request, "sources": sources})
        return _session_result("revise", self.intent)


class _ProviderFailureSession:
    """Return one bounded provider failure from the direct session boundary."""

    def __init__(self) -> None:
        self.calls = 0

    async def build(self, **_: object) -> object:
        """Return a bounded failed result without raising through MCP."""
        self.calls += 1
        return _session_failure("reconstruct")

    async def revise(self, **_: object) -> object:
        """Return a bounded failed revision result without raising through MCP."""
        self.calls += 1
        return _session_failure("revise")


class _FacadeBackend:
    """Fake provider proving the real session/facade/graph integration path."""

    async def generate_structured(self, _request: object, *, response_model: object) -> object:
        """Return one static report plan through the provider contract."""
        return StructuredGenerationResult(
            value=SemanticPlan(
                summary="report integration",
                report_task=ReportTask(
                    goal="Set the report title.",
                    capability_ids=("report.standard",),
                ),
            ),
            metrics=ProviderMetrics(),
        )

    async def generate_program(self, _request: object) -> ProgramGenerationResult:
        """Return one executable report program through the provider contract."""
        return ProgramGenerationResult(
            text="report = wp.report(title='Facade integration')",
            metrics=ProviderMetrics(),
        )


def _session_result(mode: str, intent: dict[str, object]) -> AgentSessionResult:
    """Build a successful public session result for edge tests."""
    worker = AgentWorkerEvidence(
        kind="report",
        plan_order=0,
        success=True,
        diagnostics=(),
        metrics=AgentWorkerMetrics(
            program_chars=1,
            program_ast_nodes=1,
            program_statements=1,
            program_calls=1,
            program_repairs=0,
            program_loop_iterations=0,
            program_nesting_depth=0,
            created_objects=1,
        ),
    )
    return AgentSessionResult(
        mode=mode,
        success=True,
        intent=intent,
        workers=(worker,),
        metrics=AgentMetrics(
            worker_count=1,
            successful_workers=1,
            failed_workers=0,
            total_program_chars=1,
            total_ast_nodes=1,
            total_statements=1,
            total_calls=1,
            total_repairs=0,
            total_loop_iterations=0,
            total_created_objects=1,
            max_nesting_depth=0,
        ),
    )


def _session_failure(mode: str) -> AgentSessionResult:
    """Build a failed public session result with safe diagnostic evidence."""
    diagnostic = AgentDiagnostic(
        stage="provider",
        code="provider.transport",
        message="The configured provider request failed.",
    )
    return AgentSessionResult(
        mode=mode,
        success=False,
        diagnostics=(diagnostic,),
        metrics=AgentMetrics(
            worker_count=0,
            successful_workers=0,
            failed_workers=0,
            total_program_chars=0,
            total_ast_nodes=0,
            total_statements=0,
            total_calls=0,
            total_repairs=0,
            total_loop_iterations=0,
            total_created_objects=0,
            max_nesting_depth=0,
        ),
    )


def _canonical_document(path: Path) -> dict[str, object]:
    """Read one persisted logfile through the canonical authoring projection."""
    spec = service.load_logfile(path, allowed_root=REPO_ROOT)
    return AuthoringService.from_mapping(service.report_to_dict(spec)).document.model_dump(
        mode="json"
    )


def test_agentic_tools_persist_successful_build_and_revision() -> None:
    """High-level tools use one graph transaction and persist verified output."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
        build_graph = _Session(intent={"title": "Graph reconstruction"}, mode="reconstruct")
        build_operations = GraphAuthoringMcpOperations.create(
            session=build_graph,  # type: ignore[arg-type]
            root=REPO_ROOT,
        )
        collector = _ToolCollector()
        assert register_agentic_tools(collector, operations=build_operations) == (
            "build_plot_from_request",
            "revise_plot_from_request",
        )

        build_tool = next(
            item["function"]
            for item in collector.tools
            if item["name"] == "build_plot_from_request"
        )
        build_result = asyncio.run(
            build_tool(
                logfile_path=str(fixture_paths.single_logfile),
                request="Set the report title.",
            )
        )

        revision_graph = _Session(
            intent={
                "sections": [
                    {"section_id": "main", "subtitle": "Graph revision"},
                ]
            },
            mode="revise",
        )
        revision_operations = GraphAuthoringMcpOperations.create(
            session=revision_graph,  # type: ignore[arg-type]
            root=REPO_ROOT,
        )
        revision_result = asyncio.run(
            revision_operations.revise(
                logfile_path=str(fixture_paths.single_logfile),
                request="Set the main subtitle.",
            )
        )

        persisted = _canonical_document(fixture_paths.single_logfile)
        build_events = read_agent_trace(build_result.trace_path or "")

    assert build_result.success is True, build_result.errors
    assert build_result.changed is True
    assert build_result.mode == "reconstruct"
    assert build_result.trace_path is not None
    assert build_result.trace_event_count >= 3
    assert revision_result.success is True, revision_result.errors
    assert revision_result.changed is True
    assert revision_result.mode == "revise"
    assert build_graph.states[0]["mode"] == "reconstruct"
    assert revision_graph.states[0]["mode"] == "revise"
    assert persisted["title"] == "Graph reconstruction"
    assert persisted["sections"][0]["subtitle"] == "Graph revision"
    assert any(event.event == "run_finished" for event in build_events)


def test_agentic_tool_contract_and_declared_source_candidates_are_stable() -> None:
    """MCP arguments stay stable and only logfile-declared sources cross the edge."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
        (fixture_paths.fixture_dir / "undeclared.las").write_text("not declared", encoding="utf-8")
        context = _request_context(str(fixture_paths.multi_logfile), root=REPO_ROOT)
        session = _Session(intent={"title": "No-op"}, mode="reconstruct")
        operations = GraphAuthoringMcpOperations.create(
            session=session,  # type: ignore[arg-type]
            root=REPO_ROOT,
        )
        collector = _ToolCollector()
        register_agentic_tools(collector, operations=operations)

    assert list(inspect.signature(collector.tools[0]["function"]).parameters) == [
        "logfile_path",
        "request",
    ]
    assert list(inspect.signature(collector.tools[1]["function"]).parameters) == [
        "logfile_path",
        "request",
    ]
    assert [candidate.candidate_id for candidate in context.source_candidates] == ["source-1"]
    assert context.source_candidates[0].path == str(fixture_paths.las_path.resolve())
    assert context.source_candidates[0].labels == (
        fixture_paths.las_path.name,
        fixture_paths.las_path.stem,
        "las",
    )
    assert set(GraphAuthoringToolResult.model_fields) == {
        "logfile_path",
        "mode",
        "success",
        "changed",
        "rolled_back",
        "plan_summary",
        "section_ids",
        "errors",
        "trace_path",
        "trace_event_count",
    }


def test_agentic_operations_use_real_v2_facade_with_fake_provider() -> None:
    """The MCP edge reaches AgentSession, facade, graph, and canonical apply."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
        backend = _FacadeBackend()
        registry = create_builtin_registry()
        dependencies = CodeModeGraphDependencies(
            planner=SemanticPlanner(backend=backend, registry=registry),
            enricher=SemanticEnricher(
                loader=object(),
                allowed_roots={"server": REPO_ROOT},
            ),
            report_compiler=ReportProgramCompiler(backend=backend, registry=registry),
            section_compiler=ProgramSectionCompiler(backend=backend, registry=registry),
        )
        operations = GraphAuthoringMcpOperations.create(
            session=AgentSession(compiler=CodeModeCompileFacade(dependencies)),
            root=REPO_ROOT,
        )

        result = asyncio.run(
            operations.build(
                logfile_path=str(fixture_paths.single_logfile),
                request="Set the report title.",
            )
        )

        persisted = _canonical_document(fixture_paths.single_logfile)

    assert result.success is True, result.errors
    assert result.changed is True
    assert persisted["title"] == "Facade integration"


def test_agentic_source_loader_projects_neutral_channel_facts() -> None:
    """The host loader reads explicit LAS metadata without exposing samples."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
        loaded = LogfileSourceLoader().load(fixture_paths.las_path, "las")

    assert loaded.dataset_name
    assert {channel.mnemonic for channel in loaded.channels} >= {"CBL", "VDL"}
    assert all(channel.shape for channel in loaded.channels)
    assert all(not hasattr(channel, "values") for channel in loaded.channels)


def test_agentic_execution_failure_discards_private_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed neutral executor cannot persist a partial private document."""
    from wellplot.mcp import agentic as agentic_module

    def fail_execution(*_args: object, **_kwargs: object) -> object:
        return SimpleNamespace(success=False, errors=("executor failed",))

    monkeypatch.setattr(agentic_module, "execute_authoring_plan", fail_execution)
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
        before = fixture_paths.single_logfile.read_text(encoding="utf-8")
        operations = GraphAuthoringMcpOperations.create(
            session=_Session(intent={"title": "Discarded"}, mode="reconstruct"),
            root=REPO_ROOT,  # type: ignore[arg-type]
        )
        result = asyncio.run(
            operations.build(
                logfile_path=str(fixture_paths.single_logfile),
                request="Set the title.",
            )
        )
        after = fixture_paths.single_logfile.read_text(encoding="utf-8")

    assert result.success is False
    assert result.changed is False
    assert result.rolled_back is True
    assert result.errors == ["executor failed"]
    assert before == after


def test_agentic_trace_contains_bounded_evidence_without_source_paths() -> None:
    """Trace details contain result evidence, not canonical source locations."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
        operations = GraphAuthoringMcpOperations.create(
            session=_ProviderFailureSession(),  # type: ignore[arg-type]
            root=REPO_ROOT,
        )
        result = asyncio.run(
            operations.build(
                logfile_path=str(fixture_paths.multi_logfile),
                request="Build the plot.",
            )
        )
        events = read_agent_trace(result.trace_path or "")

    serialized = json.dumps([event.model_dump(mode="json") for event in events])
    assert str(fixture_paths.las_path.resolve()) not in serialized
    assert "provider.transport" in serialized


def test_agentic_tools_do_not_persist_blocked_execution() -> None:
    """A blocked graph transaction leaves the logfile text untouched."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
        before = fixture_paths.single_logfile.read_text(encoding="utf-8")
        session = _Session(
            intent={
                "sections": [
                    {
                        "section_id": "main",
                        "tracks": [
                            {
                                "track_id": "missing_curve",
                                "title": "Missing curve",
                                "kind": "normal",
                                "width_mm": 20,
                                "bindings": [
                                    {
                                        "kind": "curve",
                                        "binding_id": "main.missing_curve.UNKNOWN.1",
                                        "channel": "UNKNOWN",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
            mode="reconstruct",
        )
        operations = GraphAuthoringMcpOperations.create(
            session=session,  # type: ignore[arg-type]
            root=REPO_ROOT,
        )

        result = asyncio.run(
            operations.build(
                logfile_path=str(fixture_paths.single_logfile),
                request="Add an unavailable curve.",
            )
        )

        after = fixture_paths.single_logfile.read_text(encoding="utf-8")

    assert result.success is False
    assert result.changed is False
    assert result.errors
    assert before == after


def test_agentic_tools_return_structured_provider_failure_without_persistence() -> None:
    """Provider interruptions are graph results rather than MCP protocol errors."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
        before = fixture_paths.single_logfile.read_text(encoding="utf-8")
        operations = GraphAuthoringMcpOperations.create(
            session=_ProviderFailureSession(),  # type: ignore[arg-type]
            root=REPO_ROOT,
        )

        result = asyncio.run(
            operations.build(
                logfile_path=str(fixture_paths.single_logfile),
                request="Build the plot.",
            )
        )

        after = fixture_paths.single_logfile.read_text(encoding="utf-8")
        trace_events = read_agent_trace(result.trace_path or "")

    assert result.success is False
    assert result.changed is False
    assert result.rolled_back is False
    assert result.errors == ["provider.transport: The configured provider request failed."]
    assert result.trace_path is not None
    assert any(event.event == "compile_finished" for event in trace_events)
    assert before == after
