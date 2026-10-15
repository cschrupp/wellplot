#!/usr/bin/env python3
"""Offline sanity: score gold against itself (100% oracle) on development split."""

from __future__ import annotations

import json
from pathlib import Path

from eval.execution_equivalence import execution_equivalent
from eval.semantic_equivalence import normalized_equal
from lowerer.context import DocumentState, WorkspaceContext
from well_ir.canonicalize import parse_well_ir

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    split = set(
        json.loads((ROOT / "benchmark/splits/development.json").read_text())["case_ids"]
    )
    n = 0
    ok = 0
    for line in (ROOT / "benchmark/gold/cases.jsonl").open(encoding="utf-8"):
        case = json.loads(line)
        if case["case_id"] not in split:
            continue
        n += 1
        fix = json.loads(
            (ROOT / "benchmark/fixtures" / f"{case['fixture']}.json").read_text(encoding="utf-8")
        )
        d0 = DocumentState.model_validate(fix["d0"])
        ws = WorkspaceContext.model_validate(fix["workspace"])
        gold = parse_well_ir(case["gold"])
        if normalized_equal(gold, gold) and execution_equivalent(gold, gold, d0, ws):
            ok += 1
    print(json.dumps({"split": "development", "n": n, "oracle_pass": ok, "rate": ok / n if n else 0}))


if __name__ == "__main__":
    main()
