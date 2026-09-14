"""CM-25 proof that external capabilities use the generic contract only."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from fixtures.test_capability_plugin import external_capability
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry
from wellplot.model.intent import AuthoringDocumentIntent

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTECTED_RUNTIME_FILES = (
    REPO_ROOT / "src/wellplot/agent/graph/workflow.py",
    REPO_ROOT / "src/wellplot/agent/graph/planner.py",
    REPO_ROOT / "src/wellplot/agent/graph/section_worker.py",
    REPO_ROOT / "src/wellplot/authoring_program/interpreter.py",
)


def _imported_modules(path: Path) -> set[str]:
    """Collect statically declared absolute and relative import names."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _expected_intent(note: str) -> AuthoringDocumentIntent:
    """Return the exact canonical intent expected from the fixture handler."""
    return AuthoringDocumentIntent.model_validate(
        {
            "remarks": [
                {
                    "remark_id": "external-note",
                    "title": "External Note",
                    "text": note,
                }
            ]
        }
    )


def test_external_capability_registers_and_is_not_builtin() -> None:
    """A fresh registry can register the fixture without production changes."""
    builtins = create_builtin_registry()
    assert builtins.contains("extension.synthetic") is False

    registry = CapabilityRegistry()
    spec = external_capability()
    registry.register(spec)

    assert registry.get("extension.synthetic") is spec
    assert registry.get("synthetic note") is spec
    assert registry.planning_catalog() == (spec.planning_descriptor(),)


def test_external_capability_exposes_all_descriptor_surfaces() -> None:
    """The external declaration supports v1 and v2 descriptors deterministically."""
    spec = external_capability()

    planning = spec.planning_descriptor()
    worker = spec.worker_descriptor()
    code_mode = spec.code_mode_worker_descriptor()

    assert planning["id"] == "extension.synthetic"
    assert worker["artifact_schema"]["title"] == "ExternalNoteArtifact"
    assert code_mode["arguments_schema"]["title"] == "ExternalNoteArguments"
    assert code_mode["worker_hints"] == ["Accept one concise note."]
    assert code_mode["examples"] == ["extension.synthetic(note='Check cement bond')"]
    assert all(
        key not in code_mode for key in ("handler", "compiler", "module", "module_path", "callable")
    )

    first = json.dumps(code_mode, sort_keys=True)
    second = json.dumps(spec.code_mode_worker_descriptor(), sort_keys=True)
    assert first == second


def test_external_capability_uses_registry_held_contract_for_execution() -> None:
    """Registry lookup, validation, handler dispatch, and canonical output are generic."""
    registry = CapabilityRegistry([external_capability()])
    spec = registry.get("synthetic note")
    assert spec.arguments_model is not None
    assert spec.handler is not None

    arguments = spec.arguments_model.model_validate({"note": "Check cement bond"})
    result = spec.handler(arguments)

    assert result == _expected_intent("Check cement bond")


def test_external_capability_preserves_the_dual_mode_v1_contract() -> None:
    """The fixture's required v1 artifact and compiler remain usable."""
    spec = external_capability()
    artifact = spec.artifact_model.model_validate({"note": "Legacy worker input"})

    assert spec.compiler(artifact) == _expected_intent("Legacy worker input")


def test_protected_runtime_modules_do_not_depend_on_the_fixture() -> None:
    """Adding the fixture requires no orchestration or interpreter dependency."""
    forbidden = "tests.fixtures.test_capability_plugin"
    for path in PROTECTED_RUNTIME_FILES:
        assert forbidden not in _imported_modules(path), path


def test_fixture_does_not_import_graph_mcp_or_provider_layers() -> None:
    """The external-looking fixture depends only on public domain contracts."""
    fixture = REPO_ROOT / "tests/fixtures/test_capability_plugin.py"
    modules = _imported_modules(fixture)
    forbidden_prefixes = (
        "langgraph",
        "mcp",
        "wellplot.agent",
        "wellplot.mcp",
        "wellplot.authoring_program.interpreter",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in modules
        for prefix in forbidden_prefixes
    )
