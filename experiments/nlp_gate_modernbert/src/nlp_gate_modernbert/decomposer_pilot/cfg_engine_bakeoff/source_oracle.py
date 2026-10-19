"""Invoke the test-only independent WELL-EBNF-1 recognizer as source-language oracle."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.fixtures import (
    NEGATIVE,
    POSITIVE,
)


def _load_recognizer(repo_root: Path):
    path = (
        repo_root
        / "experiments"
        / "nlp_gate_modernbert"
        / "tests"
        / "support"
        / "well_ebnf1_recognizer.py"
    )
    if not path.is_file():
        raise FileNotFoundError(f"independent recognizer missing: {path}")
    name = "well_ebnf1_recognizer_oracle"
    # Dataclass processing requires the module to be in sys.modules before exec.
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load recognizer from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def source_oracle_parity(repo_root: Path, well_bytes: bytes) -> dict[str, Any]:
    """Prove fixture labels against the independent WELL-EBNF-1 recognizer."""
    mod = _load_recognizer(repo_root)
    grammar = mod.parse_well_ebnf1(well_bytes)
    pos_rows = []
    neg_rows = []
    for label, text in POSITIVE:
        got = bool(mod.recognize(grammar, text))
        pos_rows.append(
            {
                "label": label,
                "oracle_accepted": got,
                "expected": True,
                "pass": got is True,
            }
        )
    for label, text in NEGATIVE:
        got = bool(mod.recognize(grammar, text))
        neg_rows.append(
            {
                "label": label,
                "oracle_accepted": got,
                "expected": False,
                "pass": got is False,
            }
        )
    pos_pass = all(r["pass"] for r in pos_rows)
    neg_pass = all(r["pass"] for r in neg_rows)
    return {
        "recognizer_path": str(
            repo_root
            / "experiments/nlp_gate_modernbert/tests/support/well_ebnf1_recognizer.py"
        ),
        "positive": pos_rows,
        "negative": neg_rows,
        "positive_pass": pos_pass,
        "negative_pass": neg_pass,
        "pass": pos_pass and neg_pass,
    }
