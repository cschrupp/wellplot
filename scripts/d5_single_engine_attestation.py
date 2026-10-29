"""Fail-closed production attestation for the canonical D5 runtime."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "architecture" / "D5_SINGLE_ENGINE_PRODUCTION_MANIFEST.json"
MANIFEST_VERSION = "wellplot.d5.single-engine-production.v2"

# These are the supported NLP/runtime roots. The manifest closure is derived
# from their internal imports, rather than copied from the historical D4 list.
D5_CANONICAL_ENTRYPOINTS = (
    "src/wellplot/__init__.py",
    "src/wellplot/agent/__init__.py",
    "src/wellplot/agent/direct_notebook.py",
    "src/wellplot/agent/notebook.py",
    "src/wellplot/mcp/agentic.py",
    "src/wellplot/mcp/agentic_server.py",
)

D5_RETIRED_SOURCE_PATHS = (
    "src/wellplot/agent/core.py",
    "src/wellplot/agent/stable_fallback.py",
    "src/wellplot/agent/branch_compiler.py",
    "src/wellplot/agent/compilation.py",
    "src/wellplot/agent/operation_executor.py",
    "src/wellplot/agent/reconciliation_bridge.py",
    "src/wellplot/agent/code_mode/program_worker.py",
    "src/wellplot/agent/code_mode/report_worker.py",
    "src/wellplot/agent/code_mode/repair.py",
    "src/wellplot/agent/code_mode/typed_delivery.py",
    "src/wellplot/agent/code_mode/semantic_ir_v2.py",
    "src/wellplot/agent/code_mode/semantic_ir_v2_compiler.py",
    "src/wellplot/agent/code_mode/semantic_ir_v2_registry.py",
    "src/wellplot/agent/code_mode/semantic_ir_v2r.py",
    "src/wellplot/agent/code_mode/semantic_ir_v2r_compiler.py",
    "src/wellplot/agent/code_mode/visual_correction.py",
    "src/wellplot/agent/graph/__init__.py",
    "src/wellplot/agent/providers/openai.py",
    "src/wellplot/agent/providers/openai_compat.py",
    "src/wellplot/agent/providers/openai_program_v2.py",
    "src/wellplot/agent/providers/_openai_chat.py",
    "src/wellplot/agent/providers/_openai_responses.py",
    "src/wellplot/agent/providers/_program_output.py",
    "src/wellplot/authoring_program/grammar.py",
    "src/wellplot/authoring_program/interpreter.py",
    "src/wellplot/authoring_program/program_runtime.py",
    "src/wellplot/authoring_program/validator.py",
)

RETIRED_SECTION_COMPILER_SYMBOLS = frozenset(
    {"TypedSectionCompiler", "TypedSectionGenerationResult"}
)
EXECUTABLE_AUDIT_ROOTS = ("src", "scripts", "tests")


def _module_path(repo_root: Path, module: str) -> Path | None:
    """Resolve one internal module name to a source path."""
    source_root = repo_root / "src"
    candidate = source_root / Path(*module.split("."))
    module_file = candidate.with_suffix(".py")
    if module_file.is_file():
        return module_file
    package_file = candidate / "__init__.py"
    return package_file if package_file.is_file() else None


def _relative_import_module(
    module: str,
    node: ast.ImportFrom,
    *,
    is_package: bool,
) -> str:
    """Resolve an AST relative import using Python package semantics."""
    package_parts = module.split(".") if is_package else module.split(".")[:-1]
    levels_up = node.level - 1
    if levels_up:
        if levels_up >= len(package_parts):
            return ""
        package_parts = package_parts[:-levels_up]
    return ".".join(package_parts + ([node.module] if node.module else []))


def _import_candidates(module: str, node: ast.AST, *, is_package: bool) -> tuple[str, ...]:
    """Return possible internal module names referenced by one AST import."""
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if not isinstance(node, ast.ImportFrom):
        return ()
    base = (
        _relative_import_module(module, node, is_package=is_package)
        if node.level
        else (node.module or "")
    )
    if not base:
        return ()
    return (base, *(f"{base}.{alias.name}" for alias in node.names if alias.name != "*"))


def canonical_component_paths(repo_root: Path = REPO_ROOT) -> tuple[str, ...]:
    """Derive the canonical production source closure from supported roots."""
    module_by_path = {
        path: path.relative_to(repo_root).as_posix()
        for path in (repo_root / "src" / "wellplot").rglob("*.py")
    }
    pending = [
        path for relative in D5_CANONICAL_ENTRYPOINTS if (path := repo_root / relative).is_file()
    ]
    discovered: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in discovered:
            continue
        discovered.add(path)
        relative_path = path.relative_to(repo_root / "src")
        if path.name == "__init__.py":
            module = ".".join(relative_path.parent.parts)
            is_package = True
        else:
            module = ".".join(relative_path.with_suffix("").parts)
            is_package = False
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for candidate in _import_candidates(module, node, is_package=is_package):
                if candidate != "wellplot" and candidate.startswith("wellplot."):
                    imported = _module_path(repo_root, candidate)
                    if imported is not None and imported not in discovered:
                        pending.append(imported)

    paths = tuple(sorted(module_by_path[path] for path in discovered if path in module_by_path))
    if not paths:
        raise RuntimeError("Canonical production closure is empty.")
    return paths


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one repository file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_components(repo_root: Path = REPO_ROOT) -> dict[str, str]:
    """Compute and hash the canonical production closure."""
    retired = [relative for relative in D5_RETIRED_SOURCE_PATHS if (repo_root / relative).exists()]
    if retired:
        raise RuntimeError(f"Retired production sources remain: {retired!r}")
    components = canonical_component_paths(repo_root)
    return {relative: sha256_file(repo_root / relative) for relative in components}


def retired_section_compiler_violations(repo_root: Path = REPO_ROOT) -> list[str]:
    """Find executable references or alternate section-compiler definitions."""
    violations: list[str] = []
    for root_name in EXECUTABLE_AUDIT_ROOTS:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(repo_root).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in RETIRED_SECTION_COMPILER_SYMBOLS:
                    violations.append(f"{relative}:{node.lineno}: retired symbol {node.id}")
                elif (
                    isinstance(node, ast.Attribute)
                    and node.attr in RETIRED_SECTION_COMPILER_SYMBOLS
                ):
                    violations.append(f"{relative}:{node.lineno}: retired symbol {node.attr}")
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        if alias.name.rsplit(".", 1)[-1] in RETIRED_SECTION_COMPILER_SYMBOLS:
                            violations.append(
                                f"{relative}:{node.lineno}: retired import {alias.name}"
                            )
                elif isinstance(node, ast.ClassDef):
                    normalized_name = node.name.casefold()
                    if (
                        "section" in normalized_name
                        and "compiler" in normalized_name
                        and not node.name.startswith("_")
                    ):
                        violations.append(
                            f"{relative}:{node.lineno}: alternate section compiler {node.name}"
                        )
    return violations


def build_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Build the deterministic successor manifest."""
    return {
        "manifest_version": MANIFEST_VERSION,
        "authority": "WELLPLOT-D5-2R2-SINGLE-ENGINE-CLOSEOUT",
        "historical_d4_attestation": "scripts/nlp_d4_live_acceptance.py",
        "canonical_entrypoints": list(D5_CANONICAL_ENTRYPOINTS),
        "production_components": current_components(repo_root),
    }


def verify_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Verify the manifest set and every component hash fail-closed."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = build_manifest(repo_root)
    if manifest != expected:
        raise RuntimeError("D5 production component attestation drifted.")
    violations = retired_section_compiler_violations(repo_root)
    if violations:
        raise RuntimeError("Retired executable section compiler found: " + "; ".join(violations))
    return expected


def main() -> int:
    """Generate or verify the successor manifest."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    if args.write:
        MANIFEST_PATH.write_text(
            json.dumps(build_manifest(repo_root), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    result = verify_manifest(repo_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
