#!/usr/bin/env python3
"""Prove deterministic lowerer passes all gold ok contracts."""

from __future__ import annotations

import json
from pathlib import Path

from lowerer.apply import apply_well_ir, check_invariants
from lowerer.context import DocumentState, WorkspaceContext
from well_ir.canonicalize import parse_well_ir

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "benchmark" / "gold" / "cases.jsonl"
FIXTURES = ROOT / "benchmark" / "fixtures"
EVIDENCE = ROOT / "benchmark" / "evidence"


def main() -> None:
    total = 0
    ok_cases = 0
    failures = []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        total += 1
        gold = parse_well_ir(case["gold"])
        if gold.status != "ok":
            continue
        ok_cases += 1
        fix = json.loads((FIXTURES / f"{case['fixture']}.json").read_text(encoding="utf-8"))
        d0 = DocumentState.model_validate(fix["d0"])
        ws = WorkspaceContext.model_validate(fix["workspace"])
        try:
            lowered = apply_well_ir(d0, gold, ws).document
            bad = check_invariants(lowered, case["lowerer_invariants"])
            if bad:
                failures.append({"case_id": case["case_id"], "errors": bad})
        except Exception as exc:  # noqa: BLE001
            failures.append({"case_id": case["case_id"], "errors": [str(exc)]})

    report = {
        "total_cases": total,
        "ok_programs": ok_cases,
        "failures": failures,
        "pass_rate": 1.0 if not failures and ok_cases else (0.0 if failures else 1.0),
        "lowerer_100": len(failures) == 0 and ok_cases > 0,
    }
    if ok_cases and not failures:
        report["pass_rate"] = 1.0
    elif ok_cases:
        report["pass_rate"] = (ok_cases - len(failures)) / ok_cases
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "slm01_lowerer_evidence.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
