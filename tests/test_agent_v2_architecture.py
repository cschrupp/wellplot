"""Static dependency constraints for the future Code Mode v2 boundary."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "src"
WELLPLOT_ROOT = SOURCE_ROOT / "wellplot"
AUTHORING_PROGRAM_ROOT = WELLPLOT_ROOT / "authoring_program"
CAPABILITIES_ROOT = WELLPLOT_ROOT / "capabilities"
CODE_MODE_ROOT = WELLPLOT_ROOT / "agent" / "code_mode"
PROVIDER_BASE = WELLPLOT_ROOT / "agent" / "providers" / "base.py"

AUTHORING_DOMAIN_ROOTS = (
    WELLPLOT_ROOT / "model",
    CAPABILITIES_ROOT,
    AUTHORING_PROGRAM_ROOT,
)
AUTHORING_DOMAIN_FILES = tuple(sorted(WELLPLOT_ROOT.glob("authoring*.py")))

MCP_DEPENDENCIES = ("mcp", "wellplot.mcp")
PROGRAM_AND_CAPABILITY_DEPENDENCIES = (
    "wellplot.agent",
    "langgraph",
    *MCP_DEPENDENCIES,
)
LEGACY_CODE_MODE_DEPENDENCIES = (
    "wellplot.agent.core",
    "wellplot.agent.branch_compiler",
    "wellplot.agent.compilation",
    "wellplot.agent.operation_executor",
    "wellplot.agent.reconciliation_bridge",
    "wellplot.agent.stable_fallback",
    "wellplot.agent.tool_contract",
    "wellplot.agent.mcp",
    *MCP_DEPENDENCIES,
)


@dataclass(frozen=True)
class ImportReference:
    """One statically resolved import found in a production source file."""

    path: Path
    line: int
    module: str


def _iter_python_files(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        return ()
    return tuple(sorted(root.rglob("*.py")))


def _module_package(path: Path, *, source_root: Path) -> str:
    relative_parts = list(path.relative_to(source_root).with_suffix("").parts)
    if relative_parts[-1] == "__init__":
        relative_parts.pop()
    else:
        relative_parts.pop()
    return ".".join(relative_parts)


def _relative_import_base(package: str, level: int) -> str:
    package_parts = package.split(".") if package else []
    parent_count = len(package_parts) - (level - 1)
    if parent_count <= 0:
        return ""
    return ".".join(package_parts[:parent_count])


def _join_module(*parts: str) -> str:
    return ".".join(part for part in parts if part)


def _imported_modules(node: ast.Import | ast.ImportFrom, *, package: str) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)

    base = node.module or ""
    if node.level:
        base = _join_module(_relative_import_base(package, node.level), base)
    if node.module:
        return (base, *(_join_module(base, alias.name) for alias in node.names))
    return tuple(_join_module(base, alias.name) for alias in node.names)


def _collect_import_references(
    paths: tuple[Path, ...],
    *,
    source_root: Path,
) -> tuple[ImportReference, ...]:
    references: list[ImportReference] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        package = _module_package(path, source_root=source_root)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                references.extend(
                    ImportReference(path=path, line=node.lineno, module=module)
                    for module in _imported_modules(node, package=package)
                )
    return tuple(references)


def _matches_dependency(module: str, dependency: str) -> bool:
    return module == dependency or module.startswith(f"{dependency}.")


def _assert_no_dependencies(
    roots: tuple[Path, ...],
    *,
    forbidden: tuple[str, ...],
) -> None:
    paths = {path for root in roots for path in _iter_python_files(root)}
    if roots == AUTHORING_DOMAIN_ROOTS:
        paths.update(AUTHORING_DOMAIN_FILES)
    violations = [
        reference
        for reference in _collect_import_references(
            tuple(sorted(paths)),
            source_root=SOURCE_ROOT,
        )
        if any(_matches_dependency(reference.module, dependency) for dependency in forbidden)
    ]
    assert not violations, "\n".join(
        f"{reference.path.relative_to(REPO_ROOT)}:{reference.line}: "
        f"forbidden dependency {reference.module!r}"
        for reference in violations
    )


def _assert_marker_package(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    body = tree.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    assert not body, f"{path.relative_to(REPO_ROOT)} must remain a docstring-only marker."


def test_code_mode_boundary_packages_are_docstring_only_markers() -> None:
    """CM-01 establishes intentional v2 boundaries without executable runtime code."""
    _assert_marker_package(AUTHORING_PROGRAM_ROOT / "__init__.py")
    _assert_marker_package(CODE_MODE_ROOT / "__init__.py")


def test_program_and_capabilities_do_not_depend_on_agent_graph_or_mcp() -> None:
    """Program and capability layers remain independent of agent and MCP edges."""
    _assert_no_dependencies(
        (AUTHORING_PROGRAM_ROOT, CAPABILITIES_ROOT),
        forbidden=PROGRAM_AND_CAPABILITY_DEPENDENCIES,
    )


def test_code_mode_does_not_depend_on_legacy_agent_or_mcp_modules() -> None:
    """The future v2 graph boundary cannot grow on the legacy orchestration stack."""
    _assert_no_dependencies(
        (CODE_MODE_ROOT,),
        forbidden=LEGACY_CODE_MODE_DEPENDENCIES,
    )


def test_provider_v2_contract_stays_provider_neutral() -> None:
    """The new provider contract cannot depend on legacy or concrete adapters."""
    forbidden = (
        "wellplot.agent.core",
        "wellplot.agent.graph",
        "wellplot.mcp",
        "langgraph",
        "openai",
        "anthropic",
        "nvidia",
        "wellplot.authoring_program.interpreter",
    )
    violations = [
        reference
        for reference in _collect_import_references(
            (PROVIDER_BASE,),
            source_root=SOURCE_ROOT,
        )
        if any(_matches_dependency(reference.module, dependency) for dependency in forbidden)
    ]
    assert not violations, "\n".join(
        f"{reference.path.relative_to(REPO_ROOT)}:{reference.line}: "
        f"forbidden dependency {reference.module!r}"
        for reference in violations
    )


def test_domain_authoring_modules_do_not_depend_on_the_agent_package() -> None:
    """Canonical authoring and domain layers remain below the agent boundary."""
    _assert_no_dependencies(AUTHORING_DOMAIN_ROOTS, forbidden=("wellplot.agent",))


def test_import_scanner_resolves_absolute_and_relative_imports(tmp_path: Path) -> None:
    """The guard resolves both import syntaxes before checking dependencies."""
    source_root = tmp_path / "src"
    authoring_program = source_root / "wellplot" / "authoring_program"
    code_mode = source_root / "wellplot" / "agent" / "code_mode"
    authoring_program.mkdir(parents=True)
    code_mode.mkdir(parents=True)
    program_file = authoring_program / "worker.py"
    code_mode_file = code_mode / "worker.py"
    program_file.write_text(
        "import langgraph.graph\nfrom ..agent import core\nfrom .something import value\n",
        encoding="utf-8",
    )
    code_mode_file.write_text(
        "import mcp.client\nfrom ...mcp import service\nfrom .. import core\n",
        encoding="utf-8",
    )

    modules = {
        reference.module
        for reference in _collect_import_references(
            (program_file, code_mode_file),
            source_root=source_root,
        )
    }

    assert {
        "langgraph.graph",
        "mcp.client",
        "wellplot.agent.core",
        "wellplot.authoring_program.something",
        "wellplot.agent",
        "wellplot.mcp",
    }.issubset(modules)
