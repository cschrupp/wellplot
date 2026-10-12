"""Focused provider-free checks for the D5 single-engine composition."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic import ValidationError

from wellplot.agent.code_mode.canonical_workers import (
    SectionSemanticActionResponse,
    _failure,
)
from wellplot.agent.code_mode.facade import (
    CodeModeCompileResult,
    CompileWorkerEvidence,
    _provider_diagnostic,
)
from wellplot.agent.code_mode.semantic_actions import (
    AddFillAction,
    ExistingCurveSelector,
    LimitFill,
)
from wellplot.agent.code_mode.typed_section_worker import _canonical_failure
from wellplot.agent.code_mode.workflow import _provider_diagnostic_code
from wellplot.agent.composition import create_canonical_dependencies
from wellplot.agent.providers.base import ProviderFailureCategory, ProviderRequestError
from wellplot.agent.providers.response_diagnostics import (
    ProviderResponseFailureReason,
    StructuredResponseProviderError,
)
from wellplot.agent.semantic_runtime import SemanticMetrics
from wellplot.agent.session import AgentSession, AgentSessionConfig
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.model.intent import AuthoringDocumentIntent

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_canonical_entrypoints_do_not_load_retired_modules() -> None:
    """Canonical imports stay isolated from retired authoring engines."""
    result = subprocess.run(
        [sys.executable, "scripts/check_d5_single_engine_reachability.py", "--repo-root", "."],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


def test_legacy_authoring_session_is_not_a_public_package_export() -> None:
    """The retired engine is not reachable through the shipped agent package."""
    import wellplot.agent as agent_package

    with pytest.raises(AttributeError):
        _ = agent_package.AuthoringSession


def test_d5_production_manifest_is_current() -> None:
    """The successor production attestation matches the current sources."""
    result = subprocess.run(
        [sys.executable, "scripts/d5_single_engine_attestation.py", "--repo-root", ".", "--check"],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    result = json.loads(result.stdout)
    assert result["manifest_version"] == "wellplot.d5.single-engine-production.v2"
    components = set(result["production_components"])
    assert components
    assert "src/wellplot/agent/composition.py" in components
    assert "src/wellplot/agent/code_mode/canonical_workers.py" in components
    assert "src/wellplot/agent/code_mode/typed_section_worker.py" in components
    assert "src/wellplot/agent/code_mode/typed_delivery.py" not in components
    assert "src/wellplot/agent/core.py" not in components


def _document() -> AuthoringDocumentSpec:
    """Build the smallest valid document for session-control tests."""
    return AuthoringDocumentSpec(
        name="d5-test",
        title="D5 test",
        sections=[
            {
                "id": "main",
                "title": "Main Log",
                "tracks": [
                    {
                        "id": "gr",
                        "title": "Gamma Ray",
                        "kind": "normal",
                        "width_mm": 28,
                    }
                ],
            }
        ],
    )


def test_revision_action_schema_is_discriminated_and_branch_strict() -> None:
    """The decoder-visible schema carries operation structure, not nullable fields."""
    schema = SectionSemanticActionResponse.model_json_schema()
    assert schema["discriminator"]["propertyName"] == "action"
    assert set(schema["discriminator"]["mapping"]) == {
        "reconstruct",
        "update_curve_scale",
        "add_track",
        "add_fill",
    }
    add_fill = schema["$defs"]["AddFillAction"]
    assert add_fill["required"] == ["action", "target", "fill"]
    assert "track" not in add_fill["properties"]
    assert "scale" not in add_fill["properties"]

    action = SectionSemanticActionResponse.model_validate(
        {
            "action": "add_fill",
            "target": {"handle": "curve-1"},
            "fill": {
                "kind": "to_lower_limit",
                "semantic_id": "gr-fill",
                "target_binding": "GR",
            },
        }
    )
    assert isinstance(action.root, AddFillAction)
    assert action.root.target == ExistingCurveSelector(handle="curve-1")
    assert isinstance(action.root.fill, LimitFill)
    with pytest.raises(ValidationError):
        SectionSemanticActionResponse.model_validate(
            {
                "action": "add_fill",
                "target": {"handle": "curve-1"},
                "track": {},
                "fill": {
                    "kind": "to_lower_limit",
                    "semantic_id": "gr-fill",
                    "target_binding": "GR",
                },
            }
        )


def test_direct_and_mcp_adapters_reference_the_shared_composition_root() -> None:
    """Public adapters delegate worker construction to the same composition root."""
    dependencies = create_canonical_dependencies(backend=object(), server_root=REPO_ROOT)
    assert dependencies.planner.__class__.__name__ == "SemanticPlanner"
    assert dependencies.report_compiler.__class__.__name__ == "CanonicalReportWorker"
    assert dependencies.section_compiler.__class__.__name__ == "CanonicalSectionWorker"

    from wellplot.agent import direct_notebook
    from wellplot.mcp import agentic_server

    assert "create_canonical_compile_facade" in inspect.getsource(direct_notebook)
    assert "create_canonical_dependencies" in inspect.getsource(agentic_server)
    assert "TypedDeliverySectionCompiler" not in inspect.getsource(agentic_server)


def test_structured_output_failures_use_bounded_taxonomy() -> None:
    """Provider failures expose categories without raw responses or exception text."""
    transport = ProviderRequestError(
        ProviderFailureCategory.TRANSPORT,
        "transport detail must not escape",
    )
    assert _provider_diagnostic(transport).code == "provider_transport_failure"
    assert _provider_diagnostic_code(transport) == "provider_transport_failure"

    decode = StructuredResponseProviderError(
        "structured output invalid",
        response_reason=ProviderResponseFailureReason.INVALID_JSON,
    )
    assert _provider_diagnostic(decode).code == "structured_output_decode_failure"
    assert _provider_diagnostic_code(decode) == "structured_output_decode_failure"

    schema = StructuredResponseProviderError(
        "schema detail must not escape",
        response_reason=ProviderResponseFailureReason.SCHEMA_VALIDATION,
    )
    assert _provider_diagnostic(schema).code == "structured_schema_validation_failure"
    assert _provider_diagnostic_code(schema) == "structured_schema_validation_failure"

    assert (
        _canonical_failure("semantic_context_validation_failure", "safe").diagnostics[0].code
        == "semantic_context_validation_failure"
    )
    assert _failure("semantic_lowering_failure", "safe").diagnostics[0].code == (
        "semantic_lowering_failure"
    )


@dataclass
class _Compiler:
    """Capture the public session controls without invoking a provider."""

    calls: list[dict[str, object]] = field(default_factory=list)

    async def compile(self, **kwargs: object) -> CodeModeCompileResult:
        """Return one minimal successful result."""
        self.calls.append(kwargs)
        worker = CompileWorkerEvidence(
            kind="report",
            plan_order=0,
            success=True,
            metrics=SemanticMetrics(),
        )
        return CodeModeCompileResult(
            success=True,
            merged_intent=AuthoringDocumentIntent(title="D5 result"),
            workers=(worker,),
            metrics={
                "worker_count": 1,
                "successful_workers": 1,
                "failed_workers": 0,
                "total_program_chars": 0,
                "total_ast_nodes": 0,
                "total_statements": 0,
                "total_calls": 0,
                "total_repairs": 0,
                "total_loop_iterations": 0,
                "total_created_objects": 0,
                "max_nesting_depth": 0,
            },
        )


def test_session_controls_are_forwarded_from_one_configuration() -> None:
    """Planner and worker controls originate at the single session config boundary."""
    compiler = _Compiler()
    session = AgentSession(
        compiler=compiler,
        config=AgentSessionConfig(
            timeout_seconds=17,
            planner_temperature=0.0,
        ),
    )
    result = asyncio.run(session.revise(request="rename", document=_document()))
    assert result.success is True
    assert compiler.calls[0]["timeout_seconds"] == 17
    assert compiler.calls[0]["planner_temperature"] == 0.0
    assert compiler.calls[0]["temperature"] is None
    assert compiler.calls[0]["max_output_tokens"] is None
