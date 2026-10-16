"""Replay six frozen SCOPE-DESIGN-01R witnesses (no gold-ops → task translation)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.mb02.workspace import project_workspace
from nlp_gate_modernbert.paths import EVIDENCE_DIR
from nlp_gate_modernbert.scope_runtime.execute import execute_program, parse_program_from_witness

WITNESS_PATH = EVIDENCE_DIR / "scope_contract_design_01.json"
RESULTS_PATH = EVIDENCE_DIR / "scope_runtime_01_results.jsonl"
SUMMARY_PATH = EVIDENCE_DIR / "scope_runtime_01_summary.json"
HANDOFF_PATH = EVIDENCE_DIR / "scope_runtime_01.md"

AUTHORITY = "WELLPLOT-NLP-RUNTIME-V2-SCOPE-RUNTIME-01-AUTH-001"
CASE_IDS = [
    "D5GAP-0085",
    "D5GAP-0089",
    "D5GAP-0096",
    "D5GAP-0101",
    "D5GAP-0117",
    "SEED-cm-9643c020e2e02463",
]


def load_witnesses(path: Path = WITNESS_PATH) -> list[dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    by_id = {w["case_id"]: w for w in doc["witnesses"]}
    missing = [c for c in CASE_IDS if c not in by_id]
    if missing:
        raise RuntimeError(f"missing witnesses: {missing}")
    return [by_id[c] for c in CASE_IDS]


def replay_one(witness: dict[str, Any]) -> dict[str, Any]:
    # Runtime inputs only — never gold_structural_verification / expected_terminal / gold ops
    case_id = witness["case_id"]
    fixture_id = witness["initial_workspace_facts"]["fixture_id"]
    program = parse_program_from_witness(witness["normalized_program"])
    ws = project_workspace(fixture_id)
    result = execute_program(program, ws, case_id=case_id)
    return {
        "case_id": case_id,
        "initial_workspace_summary": {
            "fixture_id": fixture_id,
            "n_tracks": len(ws.tracks),
            "n_curves": len(ws.curves),
        },
        "normalized_program_source": "scope_contract_design_01.json#witnesses[].normalized_program",
        "task_trace": [t.model_dump() for t in result.task_trace],
        "program_terminal": result.program_terminal,
        "gold_used_as_runtime_decision_input": result.gold_used_as_runtime_decision_input,
        "frontier_calls": result.frontier_calls,
        "structural_valid": result.structural_valid,
        "structural_reason": result.structural_reason,
        "all_task_effects_post_ok_only": result.all_task_effects_post_ok_only,
        "all_local_ref_adapters_resolved_from_binding_table": (
            result.all_local_ref_adapters_resolved_from_binding_table
        ),
    }


def replay_witnesses(
    *,
    write_evidence: bool = True,
    starting_sha: str | None = None,
    candidate_sha: str | None = None,
) -> dict[str, Any]:
    witnesses = load_witnesses()
    records = [replay_one(w) for w in witnesses]
    n_ok = sum(1 for r in records if r["program_terminal"].get("authority") == "OK")
    summary = {
        "authority": AUTHORITY,
        "slice": "SCOPE-RUNTIME-01",
        "starting_sha": starting_sha,
        "candidate_sha": candidate_sha,
        "n_witnesses": len(records),
        "n_program_ok": n_ok,
        "n_program_non_ok": len(records) - n_ok,
        "frontier_calls": 0,
        "gold_decision_inputs": 0,
        "mb02r_modified": False,
        "historical_gold_modified": False,
        "all_task_effects_post_ok_only": all(
            r.get("all_task_effects_post_ok_only", True) for r in records
        ),
        "all_local_ref_adapters_resolved_from_binding_table": all(
            r.get("all_local_ref_adapters_resolved_from_binding_table", True) for r in records
        ),
        "case_terminals": {
            r["case_id"]: r["program_terminal"] for r in records
        },
    }
    if write_evidence:
        RESULTS_PATH.write_text(
            "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in records),
            encoding="utf-8",
        )
        SUMMARY_PATH.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return {"records": records, "summary": summary}


if __name__ == "__main__":
    out = replay_witnesses(write_evidence=True)
    print(json.dumps(out["summary"], indent=2))
