"""Focused provider-free checks for the D5 single-engine composition."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import inspect
import json
import os
import subprocess
import sys
import types
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


def _attestation_module() -> types.ModuleType:
    """Load the provider-free attestation implementation under test."""
    path = REPO_ROOT / "scripts" / "d5_single_engine_attestation.py"
    spec = importlib.util.spec_from_file_location("d5_single_engine_attestation", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_package_relative_imports_use_package_aware_closure() -> None:
    """Package exports and relative imports reach their actual child modules."""
    attestation = _attestation_module()
    paths = {
        "src/wellplot/__init__.py": (
            "from . import renderers\nfrom .capabilities import create_builtin_registry\n"
        ),
        "src/wellplot/renderers/__init__.py": (
            "from .matplotlib import MatplotlibRenderer\nfrom .plotly import PlotlyRenderer\n"
        ),
        "src/wellplot/renderers/matplotlib.py": "class MatplotlibRenderer: pass\n",
        "src/wellplot/renderers/plotly.py": "class PlotlyRenderer: pass\n",
        "src/wellplot/capabilities/__init__.py": (
            "from .builtins import create_builtin_registry\n"
            "from .registry import CapabilityRegistry\n"
        ),
        "src/wellplot/capabilities/builtins.py": "def create_builtin_registry(): pass\n",
        "src/wellplot/capabilities/registry.py": "class CapabilityRegistry: pass\n",
    }
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as directory:
        root = Path(directory)
        for relative, content in paths.items():
            file_path = root / relative
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
        discovered = set(attestation.canonical_component_paths(root))
    assert {
        "src/wellplot/renderers/matplotlib.py",
        "src/wellplot/renderers/plotly.py",
        "src/wellplot/capabilities/builtins.py",
        "src/wellplot/capabilities/registry.py",
    } <= discovered


def test_attestation_rejects_executable_retired_compiler_and_alternate_class(
    tmp_path: Path,
) -> None:
    """AST retirement checks reject code while ignoring prose references."""
    attestation = _attestation_module()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "history.md").write_text(
        "Historical note: TypedSectionCompiler was retired.\n", encoding="utf-8"
    )
    script = tmp_path / "scripts" / "candidate.py"
    script.write_text(
        "from archive import TypedSectionCompiler\nclass AlternateSectionCompiler:\n    pass\n",
        encoding="utf-8",
    )

    violations = attestation.retired_section_compiler_violations(tmp_path)

    assert any("TypedSectionCompiler" in violation for violation in violations)
    assert any("AlternateSectionCompiler" in violation for violation in violations)
    script.write_text("# TypedSectionCompiler was used in historical evidence.\n", encoding="utf-8")
    assert attestation.retired_section_compiler_violations(tmp_path) == []


def test_relative_import_resolution_covers_package_and_module_cases() -> None:
    """Relative imports resolve correctly for packages and ordinary modules."""
    attestation = _attestation_module()
    parse = ast.parse

    package_child = parse("from .x import y\n").body[0]
    package_parent = parse("from ..x import y\n").body[0]
    package_import = parse("from . import module\n").body[0]
    assert (
        attestation._relative_import_module("wellplot.pkg", package_child, is_package=True)
        == "wellplot.pkg.x"
    )
    assert (
        attestation._relative_import_module("wellplot.pkg", package_parent, is_package=True)
        == "wellplot.x"
    )
    assert (
        attestation._relative_import_module("wellplot.pkg.module", package_child, is_package=False)
        == "wellplot.pkg.x"
    )
    assert (
        attestation._relative_import_module("wellplot.pkg.module", package_parent, is_package=False)
        == "wellplot.x"
    )
    assert attestation._import_candidates("wellplot.pkg", package_import, is_package=True) == (
        "wellplot.pkg",
        "wellplot.pkg.module",
    )


def test_transitive_manifest_drift_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed transitive production module invalidates the committed manifest."""
    attestation = _attestation_module()
    root = tmp_path
    files = {
        "src/wellplot/__init__.py": "from . import renderers\n",
        "src/wellplot/renderers/__init__.py": "from .matplotlib import Renderer\n",
        "src/wellplot/renderers/matplotlib.py": "class Renderer: pass\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(attestation.build_manifest(root), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(attestation, "MANIFEST_PATH", manifest_path)
    attestation.verify_manifest(root)

    (root / "src/wellplot/renderers/matplotlib.py").write_text(
        "class Renderer:\n    changed = True\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="attestation drifted"):
        attestation.verify_manifest(root)


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
