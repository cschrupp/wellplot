"""Tests for the direct Code Mode v2 notebook authoring adapter."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest import mock

import pytest

pytest.importorskip("lasio")

try:
    from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
except ModuleNotFoundError:  # pragma: no cover - unittest discovery mode
    from _mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
from wellplot.agent import (
    AuthoringResult,
    AuthoringSession,
    ProjectPaths,
    ProjectSession,
    display_authoring_result,
)
from wellplot.agent import notebook as notebook_module
from wellplot.agent.code_mode.enrichment import EnrichedSemanticContext, ReportContext
from wellplot.agent.code_mode.facade import CodeModeCompileFacade
from wellplot.agent.code_mode.planner import ReportTask, SemanticPlan
from wellplot.agent.code_mode.workflow import CodeModeGraphDependencies
from wellplot.agent.direct_notebook import DirectNotebookSession
from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2
from wellplot.agent.providers.openai_v2 import OpenAIBackendV2
from wellplot.agent.session import (
    AgentMetrics,
    AgentSession,
    AgentSessionConfig,
    AgentSessionResult,
    AgentWorkerEvidence,
    AgentWorkerMetrics,
)
from wellplot.authoring_program.models import (
    AuthoringProgram,
    ProgramArtifact,
    ProgramExecutionResult,
    ProgramMetrics,
    ProgramSource,
)
from wellplot.model.intent import AuthoringDocumentIntent


def _result(*, success: bool, intent: AuthoringDocumentIntent | None = None) -> AgentSessionResult:
    """Build one bounded fake v2 session result."""
    worker = AgentWorkerEvidence(
        kind="report",
        plan_order=0,
        success=success,
        diagnostics=(),
        metrics=AgentWorkerMetrics(
            program_chars=12,
            program_ast_nodes=2,
            program_statements=1,
            program_calls=1,
            program_repairs=0,
            program_loop_iterations=0,
            program_nesting_depth=1,
            created_objects=1,
        ),
    )
    return AgentSessionResult(
        mode="reconstruct",
        success=success,
        intent=intent,
        workers=(worker,),
        metrics=AgentMetrics(
            worker_count=1,
            successful_workers=1 if success else 0,
            failed_workers=0 if success else 1,
            total_program_chars=12,
            total_ast_nodes=2,
            total_statements=1,
            total_calls=1,
            total_repairs=0,
            total_loop_iterations=0,
            total_created_objects=1,
            max_nesting_depth=1,
        ),
    )


class _FakeDirectSession:
    """Fake AgentSession proving the adapter's host-owned transaction."""

    def __init__(self, *, success: bool = True) -> None:
        self.success = success
        self.calls: list[tuple[str, int]] = []
        self.sources: tuple[object, ...] = ()

    async def build(self, *, request: str, document: object, sources: object) -> AgentSessionResult:
        """Return one bounded build result without provider or MCP calls."""
        del document
        self.sources = tuple(sources)
        self.calls.append((request, 1))
        return _result(
            success=self.success,
            intent=AuthoringDocumentIntent(title="Direct notebook build") if self.success else None,
        )

    async def revise(
        self, *, request: str, document: object, sources: object
    ) -> AgentSessionResult:
        """Return one bounded revision result without provider or MCP calls."""
        del document
        self.sources = tuple(sources)
        self.calls.append((request, 1))
        return _result(
            success=self.success,
            intent=AuthoringDocumentIntent(subtitle="Direct notebook revision")
            if self.success
            else None,
        )

    async def call_tool(self, *_args: object, **_kwargs: object) -> object:
        """Fail if the direct path accidentally uses an MCP session."""
        raise AssertionError("direct notebook path must not call MCP tools")


class _DeterministicPlanner:
    """Planner fixture for the real v2 graph integration test."""

    async def plan(self, **_kwargs: object) -> SemanticPlan:
        """Return one report-only semantic task without a provider call."""
        return SemanticPlan(
            summary="deterministic notebook report",
            report_task=ReportTask(goal="Deterministic notebook report"),
        )


class _DeterministicEnricher:
    """Enricher fixture that preserves the real graph boundary."""

    def enrich(self, *, plan: SemanticPlan, **_kwargs: object) -> EnrichedSemanticContext:
        """Return a bounded report context for the real graph."""
        return EnrichedSemanticContext(plan=plan, sections=(), report=ReportContext())


def _deterministic_program_result() -> ProgramExecutionResult:
    """Build one successful report program result for the graph fixture."""
    return ProgramExecutionResult(
        program=AuthoringProgram(
            source=ProgramSource(
                text="report = wp.report(title='Deterministic notebook report')",
                logical_name="cm52-test.wpa",
            )
        ),
        success=True,
        artifact=ProgramArtifact(
            intent_fragment=AuthoringDocumentIntent(title="Deterministic notebook report")
        ),
        metrics=ProgramMetrics(
            program_chars=58,
            program_ast_nodes=2,
            program_statements=1,
            program_calls=1,
            program_repairs=0,
            program_loop_iterations=0,
            program_nesting_depth=1,
            created_objects=1,
        ),
    )


class _DeterministicReportCompiler:
    """Report worker fixture used behind the real v2 graph."""

    async def compile(self, **_kwargs: object) -> ProgramExecutionResult:
        """Return one successful report program result."""
        return _deterministic_program_result()


class _UnusedSectionCompiler:
    """Section worker fixture that must not run in the report-only case."""

    async def compile(self, **_kwargs: object) -> ProgramExecutionResult:
        """Fail if the graph dispatches an unexpected section task."""
        raise AssertionError("report-only notebook fixture dispatched a section")


def _direct_adapter(fake_session: _FakeDirectSession, root: Path) -> DirectNotebookSession:
    """Wrap a fake v2 session with notebook metadata."""
    return DirectNotebookSession(
        session=fake_session,  # type: ignore[arg-type]
        provider="openai",
        model="fake-model",
        credential_source="test",
        server_root=root,
    )


def _real_graph_adapter(root: Path) -> DirectNotebookSession:
    """Wrap a real AgentSession and CodeMode facade with deterministic workers."""
    dependencies = CodeModeGraphDependencies(
        planner=_DeterministicPlanner(),  # type: ignore[arg-type]
        enricher=_DeterministicEnricher(),  # type: ignore[arg-type]
        report_compiler=_DeterministicReportCompiler(),  # type: ignore[arg-type]
        section_compiler=_UnusedSectionCompiler(),  # type: ignore[arg-type]
    )
    return DirectNotebookSession(
        session=AgentSession(
            compiler=CodeModeCompileFacade(dependencies),
            config=AgentSessionConfig(timeout_seconds=5.0),
        ),
        provider="deterministic",
        model="fixture-model",
        credential_source="test",
        server_root=root,
    )


def test_project_session_uses_direct_v2_build_and_compatibility_result() -> None:
    """Build preserves AuthoringResult while bypassing MCP and legacy loops."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture = create_mcp_fixture_paths(Path(temporary_directory))
        fake_session = _FakeDirectSession()
        adapter = _direct_adapter(fake_session, REPO_ROOT)
        project = ProjectSession(
            authoring_session=adapter,  # type: ignore[arg-type]
            paths=ProjectPaths.under_root(REPO_ROOT, fixture.fixture_dir),
        )

        result = asyncio.run(
            project.run(
                goal="Build the direct notebook draft.",
                source_logfile_path=fixture.single_logfile,
                output_logfile=fixture.fixture_dir / "draft.log.yaml",
                max_rounds=50,
            )
        )

        persisted = fixture.fixture_dir / "draft.log.yaml"
        text = persisted.read_text(encoding="utf-8")

    assert isinstance(result, AuthoringResult)
    assert result.submitted_intent == {"title": "Direct notebook build"}
    assert result.plan is None
    assert result.phase_summaries == ()
    assert result.tool_trace == ()
    assert result.validation["valid"] is True
    assert result.report_preview_png
    assert result.section_preview_png
    assert result.report_facts["engine"] == "v2"
    assert "fixture.las" not in json.dumps(result.report_facts)
    assert "Direct notebook build" in text
    assert fake_session.calls == [("Build the direct notebook draft.", 1)]


def test_project_session_runs_real_v2_graph_with_deterministic_workers() -> None:
    """Exercise AgentSession through CodeModeCompileFacade and the v2 graph."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture = create_mcp_fixture_paths(Path(temporary_directory))
        adapter = _real_graph_adapter(REPO_ROOT)
        project = ProjectSession(
            authoring_session=adapter,  # type: ignore[arg-type]
            paths=ProjectPaths.under_root(REPO_ROOT, fixture.fixture_dir),
        )

        result = asyncio.run(
            project.run(
                goal="Build through the real deterministic v2 graph.",
                source_logfile_path=fixture.single_logfile,
                output_logfile=fixture.fixture_dir / "real-v2-draft.log.yaml",
            )
        )

    assert result.report_facts["engine"] == "v2"
    assert result.report_facts["success"] is True
    assert result.submitted_intent == {"title": "Deterministic notebook report"}


def test_project_session_uses_example_seed_and_declared_sources_only() -> None:
    """Example seeds and source candidates stay host-owned and bounded."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture = create_mcp_fixture_paths(Path(temporary_directory))
        (fixture.fixture_dir / "neighbor.las").write_text(
            fixture.las_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        fake_session = _FakeDirectSession()
        adapter = _direct_adapter(fake_session, REPO_ROOT)
        project = ProjectSession(
            authoring_session=adapter,  # type: ignore[arg-type]
            paths=ProjectPaths.under_root(REPO_ROOT, fixture.fixture_dir),
        )

        source_result = asyncio.run(
            project.run(
                goal="Build the source-seeded direct notebook draft.",
                source_logfile_path=fixture.single_logfile,
                output_logfile=fixture.fixture_dir / "source-draft.log.yaml",
            )
        )
        source_candidates = fake_session.sources
        persisted = (fixture.fixture_dir / "source-draft.log.yaml").read_text(encoding="utf-8")
        example_result = asyncio.run(
            project.run(
                goal="Build the example-seeded direct notebook draft.",
                example_id="forge16b_porosity_example",
                output_logfile=fixture.fixture_dir / "example-draft.log.yaml",
            )
        )

    assert source_result.source_logfile_path == str(fixture.single_logfile)
    assert example_result.example_id == "forge16b_porosity_example"
    assert example_result.source_logfile_path is None
    assert [source.candidate_id for source in source_candidates] == ["source-1"]
    assert "neighbor.las" not in str(source_candidates)
    assert "source_path: fixture.las" in persisted


def test_project_session_failed_build_preserves_deterministic_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed initial compile leaves the newly seeded draft unchanged."""
    from wellplot.agent import direct_notebook

    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture = create_mcp_fixture_paths(Path(temporary_directory))
        output = fixture.fixture_dir / "seeded.log.yaml"
        seed_text = fixture.single_logfile.read_text(encoding="utf-8")

        def seed_output(path: str, **_kwargs: object) -> object:
            Path(path).write_text(seed_text, encoding="utf-8")
            return SimpleNamespace(logfile_path=path)

        monkeypatch.setattr(direct_notebook.mcp_service, "create_logfile_draft", seed_output)
        adapter = _direct_adapter(_FakeDirectSession(success=False), REPO_ROOT)
        project = ProjectSession(
            authoring_session=adapter,  # type: ignore[arg-type]
            paths=ProjectPaths.under_root(REPO_ROOT, fixture.fixture_dir),
        )

        result = asyncio.run(
            project.run(
                goal="Fail after deterministic seed.",
                source_logfile_path=fixture.single_logfile,
                output_logfile=output,
            )
        )
        persisted = output.read_text(encoding="utf-8")

    assert result.report_facts["success"] is False
    assert persisted == seed_text


def test_direct_render_and_header_helpers_use_service_without_mcp() -> None:
    """Rendering and heading helpers remain direct deterministic service calls."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture = create_mcp_fixture_paths(Path(temporary_directory))
        adapter = _direct_adapter(_FakeDirectSession(), REPO_ROOT)
        output = fixture.fixture_dir / "direct-render.pdf"

        render_result = asyncio.run(
            adapter.render_logfile_to_file(
                logfile_path=fixture.single_logfile,
                output_path=output,
                overwrite=True,
            )
        )
        slots = asyncio.run(adapter.inspect_heading_slots(logfile_path=fixture.single_logfile))
        preview = asyncio.run(
            adapter.preview_header_mapping(
                logfile_path=fixture.single_logfile,
                values={"company": "CM52 Direct"},
            )
        )
        applied = asyncio.run(
            adapter.apply_header_values(
                logfile_path=fixture.single_logfile,
                values={"company": "CM52 Direct"},
            )
        )
        output_exists = output.exists()

    assert output_exists
    assert render_result["output_path"].endswith("direct-render.pdf")
    assert slots["target_kind"] == "logfile"
    assert "resolved_assignments" in preview
    assert applied["logfile_path"].endswith("single.log.yaml")
    assert not hasattr(adapter, "call_tool")


def test_display_consumes_actual_v2_projected_result() -> None:
    """The public display helper accepts the direct adapter's real result envelope."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture = create_mcp_fixture_paths(Path(temporary_directory))
        adapter = _direct_adapter(_FakeDirectSession(), REPO_ROOT)
        project = ProjectSession(
            authoring_session=adapter,  # type: ignore[arg-type]
            paths=ProjectPaths.under_root(REPO_ROOT, fixture.fixture_dir),
        )
        result = asyncio.run(
            project.run(
                goal="Create a displayable direct result.",
                source_logfile_path=fixture.single_logfile,
                output_logfile=fixture.fixture_dir / "display-draft.log.yaml",
            )
        )

    display_calls: list[object] = []

    class FakeImage:
        def __init__(self, *, data: bytes) -> None:
            self.data = data

    fake_display_module = ModuleType("IPython.display")
    fake_display_module.Image = FakeImage
    fake_display_module.display = display_calls.append
    with mock.patch.dict(sys.modules, {"IPython.display": fake_display_module}):
        displayed = display_authoring_result("CM-52", result, preview="report", return_image=True)

    assert isinstance(displayed, FakeImage)
    assert display_calls == [displayed]


def test_project_session_revision_failure_preserves_existing_logfile() -> None:
    """A failed direct revision leaves the existing draft unchanged."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture = create_mcp_fixture_paths(Path(temporary_directory))
        before = fixture.single_logfile.read_text(encoding="utf-8")
        adapter = _direct_adapter(_FakeDirectSession(success=False), REPO_ROOT)
        project = ProjectSession(
            authoring_session=adapter,  # type: ignore[arg-type]
            paths=ProjectPaths.under_root(REPO_ROOT, fixture.fixture_dir),
        )

        result = asyncio.run(
            project.revise(
                feedback="Make a failed direct revision.",
                logfile_path=fixture.single_logfile,
            )
        )
        after = fixture.single_logfile.read_text(encoding="utf-8")

    assert result.report_facts["success"] is False
    assert result.report_facts["changed"] is False
    assert before == after


def test_project_session_private_execution_mutation_is_discarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Private executor mutations never reach the notebook logfile."""
    from wellplot.agent import direct_notebook

    def fail_execution(private_service: object, *_args: object, **_kwargs: object) -> object:
        document = private_service.document  # type: ignore[attr-defined]
        document.title = "private mutation"
        private_service.replace_document(document)  # type: ignore[attr-defined]
        return SimpleNamespace(success=False, errors=("executor failed",))

    monkeypatch.setattr(direct_notebook, "execute_authoring_plan", fail_execution)
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture = create_mcp_fixture_paths(Path(temporary_directory))
        output = fixture.fixture_dir / "draft.log.yaml"
        adapter = _direct_adapter(_FakeDirectSession(), REPO_ROOT)
        project = ProjectSession(
            authoring_session=adapter,  # type: ignore[arg-type]
            paths=ProjectPaths.under_root(REPO_ROOT, fixture.fixture_dir),
        )

        result = asyncio.run(
            project.run(
                goal="Build then fail execution.",
                source_logfile_path=fixture.single_logfile,
                output_logfile=output,
            )
        )
        persisted = output.read_text(encoding="utf-8")

    assert result.report_facts["success"] is False
    assert result.report_facts["rolled_back"] is True
    assert result.report_facts["changed"] is False
    assert "private mutation" not in persisted


def test_create_project_session_does_not_construct_legacy_or_mcp_runtime() -> None:
    """Project construction uses direct v2 composition, not the explicit MCP edge."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        root = Path(temporary_directory)
        with (
            mock.patch.object(
                AuthoringSession,
                "from_local_mcp",
                side_effect=AssertionError("legacy session must not be constructed"),
            ),
            mock.patch.object(
                notebook_module,
                "LocalStdioMcpRuntime",
                side_effect=AssertionError("MCP runtime must not be constructed"),
            ),
            mock.patch(
                "wellplot.agent.direct_notebook.load_async_openai_client",
                return_value=object(),
            ),
        ):
            session, _ = notebook_module.create_project_session(
                server_root=root,
                project_dir="workspace/demo-job",
                provider="openai",
                model="demo-model",
                api_key="test-key",
            )

    assert isinstance(session.authoring_session, DirectNotebookSession)
    backend = session.authoring_session.session.compiler.dependencies.planner.backend
    assert isinstance(backend, OpenAIBackendV2)


def test_create_project_session_uses_v2_compat_and_ollama_backends() -> None:
    """Compatibility aliases select async JSON-schema v2 transports."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        root = Path(temporary_directory)
        with mock.patch(
            "wellplot.agent.direct_notebook.load_async_openai_client",
            return_value=object(),
        ):
            compat, _ = notebook_module.create_project_session(
                server_root=root,
                project_dir="workspace/compat",
                provider="openai_compat",
                model="compat-model",
                api_key="test-key",
                base_url="https://example.invalid/v1",
            )
            ollama, _ = notebook_module.create_project_session(
                server_root=root,
                project_dir="workspace/ollama",
                provider="ollama",
            )

    compat_backend = compat.authoring_session.session.compiler.dependencies.planner.backend
    ollama_backend = ollama.authoring_session.session.compiler.dependencies.planner.backend
    assert isinstance(compat_backend, OpenAICompatibleBackendV2)
    assert compat_backend.structured_output == "json_schema"
    assert isinstance(ollama_backend, OpenAICompatibleBackendV2)
    assert ollama_backend.structured_output == "json_schema"


@pytest.mark.parametrize("invalid_timeout", [0, False, float("nan"), float("inf"), "30"])
def test_invalid_timeout_is_rejected_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch,
    invalid_timeout: object,
) -> None:
    """Reject invalid timeout settings before creating an async provider client."""
    from wellplot.agent import direct_notebook

    def fail_provider_construction(**_kwargs: object) -> object:
        pytest.fail("provider construction must not run for an invalid timeout")

    monkeypatch.setattr(direct_notebook, "_provider_backend", fail_provider_construction)
    with (
        TemporaryDirectory(dir=REPO_ROOT) as temporary_directory,
        pytest.raises((TypeError, ValueError)),
    ):
        direct_notebook._build_agent_session(
            provider="openai",
            model="demo-model",
            root=Path(temporary_directory),
            api_key="test-key",
            base_url=None,
            timeout=invalid_timeout,  # type: ignore[arg-type]
        )
