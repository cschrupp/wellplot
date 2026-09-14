"""Tests for the static CM-02 agent reachability inventory."""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_SHA = "d92826130c433dd1ca95202949898c472cce398a"
MANIFEST_PATH = REPO_ROOT / "docs" / "evaluations" / "agent-code-mode" / "CM-02-reachability.json"
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_agent_reachability.py"
SPEC = importlib.util.spec_from_file_location("check_agent_reachability", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - repository layout guard
    raise RuntimeError(f"Cannot load reachability analyzer from {SCRIPT_PATH}")
reachability = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reachability
SPEC.loader.exec_module(reachability)

MIGRATION_BASELINE_SHA = reachability.MIGRATION_BASELINE_SHA
Classification = reachability.Classification
InventoryError = reachability.InventoryError
_serialize_inventory = reachability._serialize_inventory
_validate_classifications = reachability._validate_classifications
build_inventory = reachability.build_inventory
main = reachability.main


def _write_module(root: Path, relative_path: str, source: str = "") -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _create_fixture_repository(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repository"
    _write_module(repo_root, "src/wellplot/__init__.py")
    _write_module(repo_root, "src/wellplot/agent/__init__.py", "from . import core\n")
    _write_module(repo_root, "src/wellplot/agent/core.py")
    _write_module(repo_root, "src/wellplot/agent/notebook.py", "from . import core\n")
    _write_module(repo_root, "src/wellplot/mcp/__init__.py")
    _write_module(
        repo_root,
        "src/wellplot/mcp/agentic.py",
        "from wellplot.agent import core\n"
        "if TYPE_CHECKING:\n"
        "    from wellplot.agent import missing\n"
        "if typing.TYPE_CHECKING:\n"
        "    from wellplot.agent import missing_from_typing\n",
    )
    _write_module(
        repo_root,
        "src/wellplot/mcp/agentic_server.py",
        "from ..agent import core\n",
    )
    _write_module(repo_root, "scripts/__init__.py")
    _write_module(repo_root, "scripts/helper.py")
    _write_module(repo_root, "scripts/entry.py", "from helper import value\n")
    return repo_root


def test_inventory_resolves_imports_and_retains_seed_provenance(tmp_path: Path) -> None:
    """Absolute, relative, and script imports produce per-seed shortest paths."""
    inventory = build_inventory(
        _create_fixture_repository(tmp_path),
        migration_baseline_sha=MIGRATION_BASELINE_SHA,
        reachability_analysis_sha=ANALYSIS_SHA,
        require_migration_modules=False,
    )
    edges = {(edge["source"], edge["target"]) for edge in inventory["edges"]}
    modules = {module["module"]: module for module in inventory["modules"]}

    assert ("wellplot.mcp.agentic", "wellplot.agent") in edges
    assert ("wellplot.mcp.agentic", "wellplot.agent.core") in edges
    assert ("wellplot.mcp.agentic_server", "wellplot.agent.core") in edges
    assert ("scripts.entry", "scripts.helper") in edges
    assert "wellplot.agent.missing" not in {target for _, target in edges}
    assert "wellplot.agent.missing_from_typing" not in {target for _, target in edges}
    assert modules["wellplot.agent.core"]["reachable_from"]["wellplot.agent"] == [
        "wellplot.agent",
        "wellplot.agent.core",
    ]
    assert modules["wellplot.agent.core"]["reachable_from"]["wellplot.mcp.agentic"] == [
        "wellplot.mcp.agentic",
        "wellplot.agent.core",
    ]
    assert inventory["unresolved"] == []


def test_analyzer_does_not_import_wellplot_runtime_modules() -> None:
    """CM-02 derives architecture evidence without importing Wellplot itself."""
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"), filename=str(SCRIPT_PATH))
    imported_modules = {
        module
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for module in (
            (alias.name for alias in node.names)
            if isinstance(node, ast.Import)
            else ((node.module,) if node.module else ())
        )
    }

    wellplot_imports = [
        module
        for module in imported_modules
        if module == "wellplot" or module.startswith("wellplot.")
    ]

    assert not wellplot_imports


def test_inventory_output_is_deterministic_and_rewrites_identically(tmp_path: Path) -> None:
    """The same source tree and analysis inputs produce byte-identical JSON."""
    repo_root = _create_fixture_repository(tmp_path)
    first = build_inventory(
        repo_root,
        migration_baseline_sha=MIGRATION_BASELINE_SHA,
        reachability_analysis_sha=ANALYSIS_SHA,
        require_migration_modules=False,
    )
    second = build_inventory(
        repo_root,
        migration_baseline_sha=MIGRATION_BASELINE_SHA,
        reachability_analysis_sha=ANALYSIS_SHA,
        require_migration_modules=False,
    )
    output = tmp_path / "inventory.json"

    assert _serialize_inventory(first) == _serialize_inventory(second)
    assert (
        main(
            [
                "--repo-root",
                str(REPO_ROOT),
                "--reachability-analysis-sha",
                ANALYSIS_SHA,
                "--output",
                str(output),
            ]
        )
        == 0
    )
    first_write = output.read_bytes()
    assert (
        main(
            [
                "--repo-root",
                str(REPO_ROOT),
                "--reachability-analysis-sha",
                ANALYSIS_SHA,
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert output.read_bytes() == first_write


def test_inventory_rejects_unknown_classification() -> None:
    """Classification labels are checked independently from reachability results."""
    with pytest.raises(InventoryError, match="unknown classification"):
        _validate_classifications(
            {"wellplot.agent.core": object()},
            {"wellplot.agent.core": Classification("unknown", "test rationale")},
            require_migration_modules=False,
        )


def test_inventory_rejects_unresolved_wellplot_import_from_production_seed(
    tmp_path: Path,
) -> None:
    """A missing Wellplot target reachable from a required seed invalidates the inventory."""
    repo_root = _create_fixture_repository(tmp_path)
    _write_module(
        repo_root,
        "src/wellplot/agent/notebook.py",
        "import wellplot.missing_module\n",
    )

    with pytest.raises(InventoryError, match="unresolved Wellplot imports"):
        build_inventory(
            repo_root,
            migration_baseline_sha=MIGRATION_BASELINE_SHA,
            reachability_analysis_sha=ANALYSIS_SHA,
            require_migration_modules=False,
        )


def test_required_migration_modules_are_classified_in_current_inventory() -> None:
    """The committed project inventory covers every CM-02 required legacy module."""
    inventory = build_inventory(
        REPO_ROOT,
        migration_baseline_sha=MIGRATION_BASELINE_SHA,
        reachability_analysis_sha=ANALYSIS_SHA,
    )

    classifications = inventory["classifications"]
    assert classifications["wellplot.agent.core"]["classification"] == "delete-after-cutover"
    assert classifications["wellplot.agent.graph.worker_contracts"]["classification"] == "replace"


def test_committed_manifest_remains_a_valid_frozen_cm02_record() -> None:
    """Later slices do not rewrite CM-02's static snapshot of its own worktree."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["migration_baseline_sha"] == MIGRATION_BASELINE_SHA
    assert manifest["reachability_analysis_sha"] == ANALYSIS_SHA
    assert manifest["summary"]["unresolved_count"] == 0
    assert manifest["unresolved"] == []
    assert manifest["classifications"]["wellplot.agent.core"] == {
        "classification": "delete-after-cutover",
        "rationale": (
            "Legacy provider, tool-loop, branch, or operation architecture may be deleted "
            "only after v2 reachability and acceptance gates pass."
        ),
    }
    assert manifest["classifications"]["wellplot.agent.graph.worker_contracts"] == {
        "classification": "replace",
        "rationale": (
            "Current structured-output graph worker is replaced by Code Mode program generation "
            "while preserving its semantic responsibility."
        ),
    }
