"""Gate evaluation and evidence report writers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    except TypeError:
        # Mixed key types (e.g. int GPU id vs "cpu") cannot sort_keys
        text = json.dumps(payload, indent=2, sort_keys=False, default=str)
    path.write_text(text + "\n", encoding="utf-8")


def evaluate_gate(
    *,
    ir_frozen: bool,
    gold_frozen: bool,
    split_frozen: bool,
    lowerer_pass_rate: float,
    baselines_complete: bool,
    taxonomy_complete: bool,
    semantic_correctness: float | None,
    family_breadth_ok: bool,
    learnable_share: float | None,
    ir_limitation_share: float | None,
    held_out_leakage: bool,
    non_goals_preserved: bool,
) -> dict[str, Any]:
    checks = {
        "ir_frozen": ir_frozen,
        "gold_frozen": gold_frozen,
        "split_frozen": split_frozen,
        "lowerer_100": lowerer_pass_rate >= 1.0 - 1e-12,
        "baselines_complete": baselines_complete,
        "taxonomy_complete": taxonomy_complete,
        "semantic_floor_50": semantic_correctness is not None and semantic_correctness >= 0.50,
        "family_breadth": family_breadth_ok,
        "learnable_ge_70": learnable_share is not None and learnable_share >= 0.70,
        "ir_limit_lt_15": ir_limitation_share is not None and ir_limitation_share < 0.15,
        "no_leakage": not held_out_leakage,
        "non_goals": non_goals_preserved,
    }
    if ir_limitation_share is not None and ir_limitation_share >= 0.15:
        decision = "IR-REWORK"
    elif semantic_correctness is not None and semantic_correctness < 0.50 and all(
        checks[k]
        for k in (
            "ir_frozen",
            "gold_frozen",
            "split_frozen",
            "lowerer_100",
            "baselines_complete",
            "taxonomy_complete",
            "no_leakage",
            "non_goals",
        )
    ):
        decision = "MODEL-SIZE-FAIL"
    elif all(checks.values()):
        decision = "PASS"
    elif not checks["ir_limit_lt_15"] or not checks["lowerer_100"] or not checks["ir_frozen"]:
        decision = "IR-REWORK"
    elif checks["semantic_floor_50"] is False and checks["lowerer_100"]:
        decision = "MODEL-SIZE-FAIL"
    else:
        decision = "IR-REWORK"

    return {"decision": decision, "checks": checks}
