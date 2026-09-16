"""Tests for the direct Code Mode v2 notebook authoring adapter."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

import pytest

pytest.importorskip("lasio")

try:
    from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
except ModuleNotFoundError:  # pragma: no cover - unittest discovery mode
    from _mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
from wellplot.agent import AuthoringResult, AuthoringSession, ProjectPaths, ProjectSession
from wellplot.agent import notebook as notebook_module
from wellplot.agent.direct_notebook import DirectNotebookSession
from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2
from wellplot.agent.providers.openai_v2 import OpenAIBackendV2
from wellplot.agent.session import (
    AgentMetrics,
    AgentSessionResult,
    AgentWorkerEvidence,
    AgentWorkerMetrics,
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

    async def build(self, *, request: str, document: object, sources: object) -> AgentSessionResult:
        """Return one bounded build result without provider or MCP calls."""
        del document, sources
        self.calls.append((request, 1))
        return _result(
            success=self.success,
            intent=AuthoringDocumentIntent(title="Direct notebook build") if self.success else None,
        )

    async def revise(
        self, *, request: str, document: object, sources: object
    ) -> AgentSessionResult:
        """Return one bounded revision result without provider or MCP calls."""
        del document, sources
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


def _direct_adapter(fake_session: _FakeDirectSession, root: Path) -> DirectNotebookSession:
    """Wrap a fake v2 session with notebook metadata."""
    return DirectNotebookSession(
        session=fake_session,  # type: ignore[arg-type]
        provider="openai",
        model="fake-model",
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
