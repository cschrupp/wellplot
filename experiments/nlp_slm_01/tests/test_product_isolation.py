from __future__ import annotations

import ast
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[3] / "src" / "wellplot"
EXPERIMENT = Path(__file__).resolve().parents[1]


def test_product_does_not_import_experiment() -> None:
    offenders = []
    for path in PRODUCT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("well_ir") or "nlp_slm_01" in alias.name:
                        offenders.append(str(path))
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("well_ir") or "nlp_slm_01" in node.module:
                    offenders.append(str(path))
    assert offenders == []


def test_experiment_tree_exists() -> None:
    assert (EXPERIMENT / "well_ir").is_dir()
    assert (EXPERIMENT / "lowerer").is_dir()
