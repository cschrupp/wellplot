"""Tests for the direct Code Mode v2 Python session boundary."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import NoReturn

import pytest

import wellplot
from wellplot.agent import (
    AgentDiagnostic,
    AgentSession,
    AgentSessionConfig,
    AgentSourceConfig,
)
from wellplot.agent.code_mode.facade import (
    CodeModeCompileResult,
    CompileDiagnostic,
    CompileMetrics,
    CompileWorkerEvidence,
)
from wellplot.agent.mcp import LocalStdioMcpRuntime
from wellplot.authoring_program.models import ProgramMetrics
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.model.intent import AuthoringDocumentIntent


def _document() -> AuthoringDocumentSpec:
    """Build a minimal canonical document for direct session calls."""
    return AuthoringDocumentSpec(
        name="session-test",
        title="Current report",
        sections=[
            {
                "id": "existing",
                "title": "Existing section",
                "tracks": [
                    {
                        "id": "track",
                        "title": "Track",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                ],
            }
        ],
    )


def _metrics(*, workers: int = 1, failed: int = 0) -> CompileMetrics:
    """Build deterministic aggregate compile metrics."""
    return CompileMetrics(
        worker_count=workers,
        successful_workers=workers - failed,
        failed_workers=failed,
        total_program_chars=20,
        total_ast_nodes=3,
        total_statements=1,
        total_calls=1,
        total_repairs=0,
        total_loop_iterations=0,
        total_created_objects=1,
        max_nesting_depth=1,
    )


def _success_result() -> CodeModeCompileResult:
    """Build a successful internal facade result."""
    worker = CompileWorkerEvidence(
        kind="report",
        plan_order=0,
        success=True,
        metrics=ProgramMetrics(),
    )
    return CodeModeCompileResult(
        success=True,
        merged_intent=AuthoringDocumentIntent(title="Generated report"),
        workers=(worker,),
        metrics=_metrics(),
    )


def _failure_result() -> CodeModeCompileResult:
    """Build a bounded internal facade failure without an intent."""
    diagnostic = CompileDiagnostic(
        stage="planner",
        code="provider.timeout",
        message="Provider request timed out.",
        retryable=True,
    )
    worker = CompileWorkerEvidence(
        kind="report",
        plan_order=0,
        success=False,
        diagnostics=(diagnostic,),
        metrics=ProgramMetrics(),
    )
    return CodeModeCompileResult(
        success=False,
        diagnostics=(diagnostic,),
        workers=(worker,),
        metrics=_metrics(failed=1),
    )


@dataclass
class _Compiler:
    """Structural fake for the host-injected compiler contract."""

    result: CodeModeCompileResult
    calls: list[dict[str, object]] = field(default_factory=list)

    async def compile(self, **kwargs: object) -> CodeModeCompileResult:
        """Record the direct session call and return bounded evidence."""
        self.calls.append(kwargs)
        return self.result


def _run(awaitable: object) -> object:
    """Run one public async call in a fresh event loop."""
    return asyncio.run(awaitable)  # type: ignore[arg-type]


def test_public_imports_are_additive_and_do_not_touch_top_level_wellplot() -> None:
    """CM-50 exposes only the new session types from the agent package."""
    from wellplot.agent import AgentSessionResult

    assert AgentSessionResult is not None
    assert not hasattr(wellplot, "AgentSession")


def test_build_uses_reconstruct_mode_and_preserves_host_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Build delegates directly without applying or retaining canonical state."""
    compiler = _Compiler(_success_result())
    session = AgentSession(
        compiler=compiler,
        config=AgentSessionConfig(
            timeout_seconds=15,
            temperature=0.2,
            max_output_tokens=800,
        ),
    )
    document = _document()
    before = document.model_dump(mode="python")
    sources = (
        AgentSourceConfig(
            candidate_id="source-1",
            root_id="project",
            path="data/example.las",
            labels=("primary",),
            trusted_format="las",
        ),
    )

    def fail_if_mcp_is_used(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("direct AgentSession must not open an MCP session")

    monkeypatch.setattr(LocalStdioMcpRuntime, "open_session", fail_if_mcp_is_used)
    result = _run(
        session.build(
            request="  Build this report. ",
            document=document,
            sources=sources,
        )
    )

    assert result.success is True
    assert result.intent == AuthoringDocumentIntent(title="Generated report")
    assert document.model_dump(mode="python") == before
    assert len(compiler.calls) == 1
    call = compiler.calls[0]
    assert call["request"] == "Build this report."
    assert call["mode"] == "reconstruct"
    assert call["document"] is document
    assert call["timeout_seconds"] == 15
    assert call["temperature"] == 0.2
    assert call["max_output_tokens"] == 800
    source = call["source_candidates"][0]
    assert source.path == "data/example.las"
    assert source.trusted_format == "las"


def test_revise_uses_revise_mode_and_projects_bounded_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revision maps only to revise mode and exposes no raw execution material."""
    compiler = _Compiler(_success_result())
    session = AgentSession(compiler=compiler)

    def fail_if_mcp_is_used(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("direct AgentSession must not open an MCP session")

    monkeypatch.setattr(LocalStdioMcpRuntime, "open_session", fail_if_mcp_is_used)
    result = _run(session.revise(request="Change the title.", document=_document()))

    assert result.mode == "revise"
    assert compiler.calls[0]["mode"] == "revise"
    inspection = result.inspection()
    assert inspection["intent_present"] is True
    serialized = repr(inspection)
    assert "provider" not in serialized
    assert "wp.report" not in serialized
    assert "generated authoring source" not in serialized
    assert "LangGraph" not in serialized
    assert "data/example" not in serialized


def test_failed_compilation_projects_without_intent() -> None:
    """Facade failures remain bounded public failures and never expose intent."""
    compiler = _Compiler(_failure_result())
    result = _run(AgentSession(compiler=compiler).build(request="Build.", document=_document()))

    assert result.success is False
    assert result.intent is None
    assert result.diagnostics[0].code == "provider.timeout"
    assert result.workers[0].success is False
    assert result.metrics.failed_workers == 1


def test_session_configuration_rejects_invalid_limits() -> None:
    """Public execution limits follow the provider request validation rules."""
    with pytest.raises(ValueError):
        AgentSessionConfig(timeout_seconds=0)
    with pytest.raises(ValueError):
        AgentSessionConfig(temperature=-0.1)
    with pytest.raises(ValueError):
        AgentSessionConfig(max_output_tokens=0)
    with pytest.raises((TypeError, ValueError)):
        AgentSessionConfig(timeout_seconds=True)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_seconds": math.inf},
        {"timeout_seconds": -math.inf},
        {"timeout_seconds": math.nan},
        {"temperature": math.inf},
        {"temperature": -math.inf},
        {"temperature": math.nan},
        {"timeout_seconds": "15"},
        {"temperature": "0.2"},
        {"max_output_tokens": "800"},
        {"max_output_tokens": 800.0},
    ],
)
def test_session_configuration_rejects_nonfinite_and_coercible_values(
    kwargs: dict[str, object],
) -> None:
    """Session settings must match the provider contract without coercion."""
    with pytest.raises((TypeError, ValueError)):
        AgentSessionConfig(**kwargs)


def test_empty_request_is_rejected_before_compiler_call() -> None:
    """The public boundary does not dispatch blank requests."""
    compiler = _Compiler(_success_result())
    with pytest.raises(ValueError, match="non-empty"):
        _run(AgentSession(compiler=compiler).build(request=" \n ", document=_document()))
    assert compiler.calls == []


def test_public_diagnostic_model_accepts_only_safe_fields() -> None:
    """The additive public models remain strict and immutable."""
    diagnostic = AgentDiagnostic(stage="provider", code="provider.timeout", message="timeout")
    with pytest.raises(ValueError):
        AgentDiagnostic.model_validate(
            {
                **diagnostic.model_dump(),
                "provider_object": object(),
            }
        )
