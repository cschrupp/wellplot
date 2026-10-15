#!/usr/bin/env python3
"""Inventory CM/TW seeds from a frozen historical commit via git show."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HISTORICAL_SHA = "d77649765dee81ebd0b8f460ac28515b244f70da"
OUT = Path(__file__).resolve().parents[1] / "benchmark" / "inventory"

SOURCE_PATHS = [
    "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json",
    "tests/fixtures/typed_worker/cm56_shadow_cases.json",
    "tests/fixtures/typed_worker/cm57c_shadow_cases.json",
    "tests/fixtures/typed_worker/cm57p10_final_promotion_cases.json",
    "tests/fixtures/typed_worker/cm57p5_fresh_holdout.json",
    "tests/fixtures/typed_worker/cm57p7_fresh_promotion.json",
    "docs/evaluations/agent-code-mode/EXP-TW-consolidated-development-memory.md",
    "docs/evaluations/agent-code-mode/CM-59A-development-memory.md",
    "docs/evaluations/agent-code-mode/CM-43-development-memory.md",
]


def git_show(path: str) -> str | None:
    proc = subprocess.run(
        ["git", "show", f"{HISTORICAL_SHA}:{path}"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        # fall back to historical worktree if present
        alt = Path("/home/user/projects/wellplot-historical") / path
        if alt.exists():
            return alt.read_text(encoding="utf-8")
        return None
    return proc.stdout


def classify_request(request: str, family: str | None = None) -> tuple[str, str]:
    text = (request or "").lower()
    fam = (family or "").upper()
    if fam in {"REPORT_ONLY"} or "handover" in text or "approval" in text:
        return "OUT_OF_SCOPE_V1", "report_semantics"
    if "vdl" in text or "waveform" in text or "raster" in text or "array" in text:
        return "OUT_OF_SCOPE_V1", "array_vdl_semantics"
    if "annotation" in text or "marker" in text or "glyph" in text:
        return "OUT_OF_SCOPE_V1", "annotation_semantics"
    if "section" in text and ("main pass" in text or "repeat" in text):
        return "PARTIALLY_REUSABLE", "multi_section_but_may_contain_curve_ops"
    if any(
        k in text
        for k in (
            "track",
            "bind",
            "scale",
            "reverse",
            "density",
            "neutron",
            "gamma",
            "curve",
            "fill",
            "overlay",
        )
    ):
        return "IN_SCOPE_V1", "plot_editing_semantics"
    if not request.strip():
        return "INSUFFICIENT_CONTEXT", "empty_request"
    return "PARTIALLY_REUSABLE", "needs_human_mapping"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sources = []
    candidates = []
    for path in SOURCE_PATHS:
        sources.append(
            {
                "source_id": path.replace("/", "_"),
                "repository": "cschrupp/wellplot",
                "source_ref": HISTORICAL_SHA,
                "path": path,
                "source_kind": "historical_fixture"
                if path.endswith(".json")
                else "development_memory",
            }
        )
        raw = git_show(path)
        if raw is None:
            continue
        if path.endswith(".json"):
            data = json.loads(raw)
            cases = data.get("cases", []) if isinstance(data, dict) else []
            for case in cases:
                request = case.get("request", "")
                decision, reason = classify_request(request, case.get("family"))
                candidates.append(
                    {
                        "source_kind": "historical_fixture",
                        "source_id": path.split("/")[-1],
                        "repository": "cschrupp/wellplot",
                        "source_commit": HISTORICAL_SHA,
                        "source_path": path,
                        "source_case_id": case.get("case_id"),
                        "request": request,
                        "family": case.get("family") or case.get("group") or case.get("category"),
                        "inventory_decision": decision,
                        "decision_reason": reason,
                        "adaptation": "abstracted",
                        "historical_baseline_eligibility": (
                            "ELIGIBLE"
                            if decision == "IN_SCOPE_V1"
                            else "OUT_OF_SCOPE"
                        ),
                    }
                )
        else:
            candidates.append(
                {
                    "source_kind": "development_memory",
                    "source_id": path.split("/")[-1],
                    "repository": "cschrupp/wellplot",
                    "source_commit": HISTORICAL_SHA,
                    "source_path": path,
                    "source_case_id": None,
                    "request": None,
                    "inventory_decision": "PARTIALLY_REUSABLE",
                    "decision_reason": "memory_for_manual_mining",
                    "adaptation": "abstracted",
                    "historical_baseline_eligibility": "INPUT_NOT_REPRESENTABLE",
                }
            )

    (OUT / "seed_sources.json").write_text(
        json.dumps({"historical_sha": HISTORICAL_SHA, "sources": sources}, indent=2) + "\n",
        encoding="utf-8",
    )
    with (OUT / "seed_candidates.jsonl").open("w", encoding="utf-8") as fh:
        for row in candidates:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    summary = {
        "n_candidates": len(candidates),
        "by_decision": {},
    }
    for row in candidates:
        summary["by_decision"][row["inventory_decision"]] = (
            summary["by_decision"].get(row["inventory_decision"], 0) + 1
        )
    (OUT / "seed_inventory_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
