#!/usr/bin/env python3
"""Build a deterministic static reachability inventory for the agent migration.

The inventory deliberately parses source with :mod:`ast` instead of importing
Wellplot. It records current evidence and migration intent separately: a module
can be reachable today while still being classified for replacement or deletion
after a future cutover.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_BASELINE_SHA = "f03f76bda097bf93e4c640e0fc1a6b82b372bd0c"
CLASSIFICATION_LABELS = (
    "keep",
    "refactor",
    "replace",
    "delete-after-cutover",
    "test-only",
    "historical-doc-only",
)
REQUIRED_CLASSIFICATIONS = {
    "wellplot.agent.core": "delete-after-cutover",
    "wellplot.agent.branch_compiler": "delete-after-cutover",
    "wellplot.agent.compilation": "delete-after-cutover",
    "wellplot.agent.operation_executor": "delete-after-cutover",
    "wellplot.agent.reconciliation_bridge": "delete-after-cutover",
    "wellplot.agent.stable_fallback": "delete-after-cutover",
    "wellplot.agent.tool_contract": "delete-after-cutover",
    "wellplot.agent.graph.worker_contracts": "replace",
    "wellplot.agent.graph.section_worker": "replace",
    "wellplot.agent.graph.report_worker": "replace",
    "wellplot.agent.graph.report_requirements": "replace",
    "wellplot.agent.graph.report_tasks": "replace",
    "wellplot.agent.graph.provider_adapter": "replace",
}
PRODUCTION_SEED_CATEGORIES = frozenset({"public_package", "mcp_entry", "notebook_entry"})


class InventoryError(ValueError):
    """Raised when a static inventory cannot be trusted."""


@dataclass(frozen=True)
class SourceModule:
    """One local Python module available to the static resolver."""

    module: str
    path: Path
    is_package: bool


@dataclass(frozen=True)
class Seed:
    """One public or project-script entry point for reachability analysis."""

    seed_id: str
    module: str
    category: str
    path: Path


@dataclass(frozen=True)
class RawImport:
    """One runtime-relevant import declaration found by the AST visitor."""

    module: str | None
    names: tuple[str, ...]
    level: int
    line: int
    is_from_import: bool

    @property
    def display_name(self) -> str:
        """Return a stable human-readable representation of this declaration."""
        prefix = "." * self.level
        if self.is_from_import:
            module = self.module or ""
            names = ", ".join(self.names)
            return f"from {prefix}{module} import {names}"
        return f"import {self.module or ''}"


@dataclass(frozen=True)
class UnresolvedImport:
    """One local-looking import that static resolution could not map."""

    source: str
    line: int
    import_name: str
    reason: str

    def as_dict(self) -> dict[str, object]:
        """Serialize this unresolved reference without machine-local paths."""
        return {
            "source": self.source,
            "line": self.line,
            "import": self.import_name,
            "reason": self.reason,
            "resolution": None,
        }


@dataclass(frozen=True)
class Classification:
    """One migration-intent classification independent of current reachability."""

    label: str
    rationale: str

    def as_dict(self) -> dict[str, str]:
        """Return the machine-readable migration classification."""
        return {"classification": self.label, "rationale": self.rationale}


class _RuntimeImportVisitor(ast.NodeVisitor):
    """Collect imports except those nested in direct TYPE_CHECKING blocks."""

    def __init__(self) -> None:
        self.imports: list[RawImport] = []

    def visit_Import(self, node: ast.Import) -> None:
        """Record each absolute import declaration."""
        for alias in node.names:
            self.imports.append(
                RawImport(
                    module=alias.name,
                    names=(),
                    level=0,
                    line=node.lineno,
                    is_from_import=False,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Record each absolute or relative from-import declaration."""
        self.imports.append(
            RawImport(
                module=node.module,
                names=tuple(alias.name for alias in node.names),
                level=node.level,
                line=node.lineno,
                is_from_import=True,
            )
        )

    def visit_If(self, node: ast.If) -> None:
        """Skip only direct TYPE_CHECKING bodies while retaining runtime else branches."""
        if _is_type_checking_guard(node.test):
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)


def _is_type_checking_guard(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "typing"
        and node.attr == "TYPE_CHECKING"
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--output", help="Write the JSON inventory to this path.")
    parser.add_argument(
        "--migration-baseline-sha",
        default=MIGRATION_BASELINE_SHA,
        help="Frozen CM-00 migration baseline SHA.",
    )
    parser.add_argument(
        "--reachability-analysis-sha",
        required=True,
        help="Commit SHA whose topology is the comparison point for this analysis.",
    )
    return parser.parse_args(argv)


def _module_name(path: Path, *, root: Path, package: str) -> tuple[str, bool]:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join((package, *parts)) if parts else package, is_package


def _discover_modules(repo_root: Path) -> dict[str, SourceModule]:
    roots = (
        (repo_root / "src" / "wellplot", "wellplot"),
        (repo_root / "scripts", "scripts"),
    )
    modules: dict[str, SourceModule] = {}
    for root, package in roots:
        if not root.is_dir():
            raise InventoryError(f"Expected source root does not exist: {root}")
        for path in sorted(root.rglob("*.py")):
            module, is_package = _module_name(path, root=root, package=package)
            if module in modules:
                raise InventoryError(f"Duplicate module resolution for {module!r}.")
            modules[module] = SourceModule(module=module, path=path, is_package=is_package)
    return modules


def _discover_seeds(
    modules: dict[str, SourceModule],
    *,
    repo_root: Path,
) -> tuple[Seed, ...]:
    required = (
        ("wellplot.agent", "public_package"),
        ("wellplot.mcp.agentic", "mcp_entry"),
        ("wellplot.mcp.agentic_server", "mcp_entry"),
        ("wellplot.agent.notebook", "notebook_entry"),
    )
    seeds: list[Seed] = []
    for module, category in required:
        source = modules.get(module)
        if source is None:
            raise InventoryError(f"Required production seed is missing: {module}")
        seeds.append(Seed(seed_id=module, module=module, category=category, path=source.path))
    for source in modules.values():
        if source.module.startswith("scripts.") and not source.is_package:
            seeds.append(
                Seed(
                    seed_id=source.path.relative_to(repo_root).as_posix(),
                    module=source.module,
                    category="script_entry",
                    path=source.path,
                )
            )
    return tuple(sorted(seeds, key=lambda item: item.seed_id))


def _package_name(source: SourceModule) -> str:
    if source.is_package:
        return source.module
    return source.module.rpartition(".")[0]


def _relative_base(package: str, level: int) -> str | None:
    parts = package.split(".") if package else []
    parent_length = len(parts) - (level - 1)
    if parent_length <= 0:
        return None
    return ".".join(parts[:parent_length])


def _join_module(*parts: str) -> str:
    return ".".join(part for part in parts if part)


def _is_local_namespace(module: str) -> bool:
    return (
        module == "wellplot"
        or module.startswith("wellplot.")
        or module == "scripts"
        or module.startswith("scripts.")
    )


def _script_fallback_module(
    module: str, source: SourceModule, modules: dict[str, SourceModule]
) -> str | None:
    if not source.module.startswith("scripts.") or "." in module:
        return None
    candidate = f"scripts.{module}"
    return candidate if candidate in modules else None


def _resolve_import(
    raw_import: RawImport,
    *,
    source: SourceModule,
    modules: dict[str, SourceModule],
) -> tuple[set[str], tuple[UnresolvedImport, ...]]:
    targets: set[str] = set()
    unresolved: list[UnresolvedImport] = []
    package = _package_name(source)
    base = raw_import.module or ""

    if raw_import.level:
        parent = _relative_base(package, raw_import.level)
        if parent is None:
            unresolved.append(
                UnresolvedImport(
                    source=source.module,
                    line=raw_import.line,
                    import_name=raw_import.display_name,
                    reason="relative import escapes the local package root",
                )
            )
            return targets, tuple(unresolved)
        base = _join_module(parent, base)
    elif not raw_import.is_from_import or (base and not _is_local_namespace(base)):
        fallback = _script_fallback_module(base, source, modules)
        if fallback is not None:
            base = fallback

    if base in modules:
        targets.add(base)
    elif raw_import.level or _is_local_namespace(base):
        unresolved.append(
            UnresolvedImport(
                source=source.module,
                line=raw_import.line,
                import_name=raw_import.display_name,
                reason="local module target was not found",
            )
        )
        return targets, tuple(unresolved)
    else:
        return targets, tuple(unresolved)

    if raw_import.is_from_import:
        for name in raw_import.names:
            candidate = _join_module(base, name)
            if candidate in modules:
                targets.add(candidate)
    return targets, tuple(unresolved)


def _collect_edges(
    modules: dict[str, SourceModule],
) -> tuple[dict[tuple[str, str], set[tuple[int, str]]], tuple[UnresolvedImport, ...]]:
    edges: dict[tuple[str, str], set[tuple[int, str]]] = {}
    unresolved: set[UnresolvedImport] = set()
    for source in modules.values():
        try:
            tree = ast.parse(source.path.read_text(encoding="utf-8"), filename=str(source.path))
        except (OSError, SyntaxError) as exc:
            raise InventoryError(f"Could not parse {source.path}: {exc}") from exc
        visitor = _RuntimeImportVisitor()
        visitor.visit(tree)
        for raw_import in visitor.imports:
            targets, missing = _resolve_import(raw_import, source=source, modules=modules)
            unresolved.update(missing)
            for target in targets:
                if target == source.module:
                    continue
                edges.setdefault((source.module, target), set()).add(
                    (raw_import.line, raw_import.display_name)
                )
    return edges, tuple(
        sorted(unresolved, key=lambda item: (item.source, item.line, item.import_name))
    )


def _shortest_paths(
    seeds: tuple[Seed, ...],
    edges: dict[tuple[str, str], set[tuple[int, str]]],
) -> dict[str, dict[str, list[str]]]:
    adjacency: dict[str, list[str]] = {}
    for source, target in edges:
        adjacency.setdefault(source, []).append(target)
    for targets in adjacency.values():
        targets.sort()

    paths: dict[str, dict[str, list[str]]] = {}
    for seed in seeds:
        queue: deque[tuple[str, list[str]]] = deque([(seed.module, [seed.module])])
        visited = {seed.module}
        while queue:
            module, path = queue.popleft()
            paths.setdefault(module, {})[seed.seed_id] = path
            for target in adjacency.get(module, []):
                if target in visited:
                    continue
                visited.add(target)
                queue.append((target, [*path, target]))
    return paths


def _classification_for(module: str) -> Classification:
    if module in REQUIRED_CLASSIFICATIONS:
        if module.startswith("wellplot.agent.graph."):
            return Classification(
                "replace",
                (
                    "Current structured-output graph worker is replaced by Code Mode "
                    "program generation while preserving its semantic responsibility."
                ),
            )
        return Classification(
            "delete-after-cutover",
            (
                "Legacy provider, tool-loop, branch, or operation architecture may be "
                "deleted only after v2 reachability and acceptance gates pass."
            ),
        )
    if module == "wellplot.agent.execution_trace":
        return Classification(
            "keep",
            "Provider-neutral execution tracing remains useful across both migration engines.",
        )
    if module in {
        "wellplot.agent",
        "wellplot.agent.notebook",
        "wellplot.agent.mcp",
        "wellplot.mcp.agentic",
        "wellplot.mcp.agentic_server",
    } or module.startswith("wellplot.agent.providers."):
        return Classification(
            "refactor",
            (
                "Public, notebook, MCP, or provider hosting edge must be migrated to "
                "the v2 session path without changing its external responsibility."
            ),
        )
    if module.startswith("wellplot.agent.graph."):
        return Classification(
            "refactor",
            (
                "Current graph support module needs a later v2 disposition; CM-02 does "
                "not authorize deletion."
            ),
        )
    if module.startswith("scripts."):
        return Classification(
            "test-only",
            (
                "Project development, evaluation, or migration helper; it is not a "
                "production package entry point."
            ),
        )
    return Classification(
        "keep",
        (
            "Canonical authoring, rendering, validation, capability, or stable MCP "
            "responsibility retained through the migration."
        ),
    )


def _validate_classifications(
    modules: dict[str, SourceModule],
    classifications: dict[str, Classification],
    *,
    require_migration_modules: bool,
) -> None:
    if set(classifications) != set(modules):
        missing = sorted(set(modules) - set(classifications))
        extra = sorted(set(classifications) - set(modules))
        raise InventoryError(f"Classification coverage mismatch: missing={missing}, extra={extra}.")
    for module, classification in classifications.items():
        if classification.label not in CLASSIFICATION_LABELS:
            raise InventoryError(
                f"Module {module!r} uses unknown classification {classification.label!r}."
            )
        if not classification.rationale.strip():
            raise InventoryError(f"Module {module!r} has an empty classification rationale.")
    if not require_migration_modules:
        return
    for module, expected in REQUIRED_CLASSIFICATIONS.items():
        actual = classifications.get(module)
        if actual is None:
            raise InventoryError(f"Required migration module {module!r} was not discovered.")
        if actual.label != expected:
            raise InventoryError(
                f"Required module {module!r} must be classified {expected!r}, got {actual.label!r}."
            )


def _validate_production_unresolved(
    unresolved: tuple[UnresolvedImport, ...],
    paths: dict[str, dict[str, list[str]]],
    seeds: tuple[Seed, ...],
) -> None:
    categories = {seed.seed_id: seed.category for seed in seeds}
    failures = [
        item
        for item in unresolved
        if "wellplot" in item.import_name
        and any(
            categories[seed_id] in PRODUCTION_SEED_CATEGORIES
            for seed_id in paths.get(item.source, {})
        )
    ]
    if failures:
        details = ", ".join(f"{item.source}:{item.line} ({item.import_name})" for item in failures)
        raise InventoryError(
            f"Required production seeds have unresolved Wellplot imports: {details}."
        )


def _legacy_reachability_summary(
    paths: dict[str, dict[str, list[str]]],
    seeds: tuple[Seed, ...],
) -> dict[str, list[str]]:
    categories = {seed.seed_id: seed.category for seed in seeds}
    summary = {
        "reachable_from_public_runtime": [],
        "reachable_only_from_notebook": [],
        "reachable_only_from_scripts": [],
        "currently_unreachable": [],
    }
    for module in sorted(REQUIRED_CLASSIFICATIONS):
        seed_categories = {categories[seed_id] for seed_id in paths.get(module, {})}
        if seed_categories & {"public_package", "mcp_entry"}:
            summary["reachable_from_public_runtime"].append(module)
        elif "notebook_entry" in seed_categories:
            summary["reachable_only_from_notebook"].append(module)
        elif "script_entry" in seed_categories:
            summary["reachable_only_from_scripts"].append(module)
        else:
            summary["currently_unreachable"].append(module)
    return summary


def build_inventory(
    repo_root: str | Path,
    *,
    migration_baseline_sha: str,
    reachability_analysis_sha: str,
    require_migration_modules: bool = True,
) -> dict[str, object]:
    """Build one deterministic static reachability inventory without imports."""
    normalized_root = Path(repo_root).resolve()
    if not migration_baseline_sha.strip() or not reachability_analysis_sha.strip():
        raise InventoryError("Both migration and reachability analysis SHAs are required.")
    modules = _discover_modules(normalized_root)
    seeds = _discover_seeds(modules, repo_root=normalized_root)
    edge_details, unresolved = _collect_edges(modules)
    paths = _shortest_paths(seeds, edge_details)
    _validate_production_unresolved(unresolved, paths, seeds)
    classifications = {module: _classification_for(module) for module in modules}
    _validate_classifications(
        modules,
        classifications,
        require_migration_modules=require_migration_modules,
    )

    classification_totals = {
        label: sum(
            1 for classification in classifications.values() if classification.label == label
        )
        for label in CLASSIFICATION_LABELS
    }
    serialized_edges = [
        {
            "source": source,
            "target": target,
            "lines": sorted(line for line, _ in details),
            "imports": sorted(import_name for _, import_name in details),
        }
        for (source, target), details in sorted(edge_details.items())
    ]
    serialized_modules = [
        {
            "module": module,
            "path": source.path.relative_to(normalized_root).as_posix(),
            "reachable": module in paths,
            "reachable_from": {
                seed_id: paths[module][seed_id] for seed_id in sorted(paths.get(module, {}))
            },
        }
        for module, source in sorted(modules.items())
    ]
    return {
        "schema_version": 1,
        "migration_baseline_sha": migration_baseline_sha,
        "reachability_analysis_sha": reachability_analysis_sha,
        "seeds": [
            {
                "seed_id": seed.seed_id,
                "module": seed.module,
                "category": seed.category,
                "path": seed.path.relative_to(normalized_root).as_posix(),
            }
            for seed in seeds
        ],
        "modules": serialized_modules,
        "edges": serialized_edges,
        "unresolved": [item.as_dict() for item in unresolved],
        "classifications": {
            module: classifications[module].as_dict() for module in sorted(classifications)
        },
        "summary": {
            "classification_totals": classification_totals,
            "legacy_reachability": _legacy_reachability_summary(paths, seeds),
            "unresolved_count": len(unresolved),
        },
        "limitations": [
            (
                "Static AST analysis does not resolve dynamic imports, plugin entry "
                "points, or string-based module loading."
            ),
            (
                "TYPE_CHECKING and typing.TYPE_CHECKING bodies are excluded; compound "
                "conditions are intentionally not evaluated."
            ),
            (
                "Classifications express migration intent and do not authorize deletion "
                "or imply current reachability."
            ),
        ],
    }


def _serialize_inventory(inventory: dict[str, object]) -> str:
    return json.dumps(inventory, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Build and optionally write one reachability manifest."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        inventory = build_inventory(
            args.repo_root,
            migration_baseline_sha=args.migration_baseline_sha,
            reachability_analysis_sha=args.reachability_analysis_sha,
        )
    except InventoryError as exc:
        print(f"check_agent_reachability: {exc}", file=sys.stderr)
        return 1
    serialized = _serialize_inventory(inventory)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
        print(f"Wrote reachability inventory: {output}")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
