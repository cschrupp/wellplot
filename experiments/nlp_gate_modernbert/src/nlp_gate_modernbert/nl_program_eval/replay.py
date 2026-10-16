"""Replay harness fixtures → evidence results/summary (handoff md is closeout-authored)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.nl_program_eval.evaluate import evaluate_raw_candidate, load_candidate_file
from nlp_gate_modernbert.paths import EVIDENCE_DIR

AUTHORITY = "WELLPLOT-NLP-RUNTIME-V2-NL-PROGRAM-EVAL-HARNESS-01-AUTH-001"
SLICE = "NL-PROGRAM-EVAL-HARNESS-01"

HARNESS_DIR = EVIDENCE_DIR / "nl_program_eval_harness_01"
MANIFEST_PATH = HARNESS_DIR / "manifest.json"
CANDIDATES_DIR = HARNESS_DIR / "candidates"
RESULTS_PATH = EVIDENCE_DIR / "nl_program_eval_harness_01_results.jsonl"
SUMMARY_PATH = EVIDENCE_DIR / "nl_program_eval_harness_01_summary.json"
HANDOFF_PATH = EVIDENCE_DIR / "nl_program_eval_harness_01.md"


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_ok(entry: dict[str, Any], result: dict[str, Any]) -> bool:
    exp = entry.get("expected_evaluation") or {}
    if "semantically_equivalent" in exp:
        if result.get("semantically_equivalent") != exp["semantically_equivalent"]:
            return False
    required = exp.get("required_labels") or []
    labels = set(result.get("failure_labels") or [])
    diags = set(result.get("diagnostics") or [])
    for lab in required:
        if lab == "BENIGN_REDUNDANT_TASK":
            if lab not in diags and lab not in labels:
                return False
        elif lab == "EQUIVALENT":
            if result.get("semantically_equivalent") is not True:
                return False
        elif lab not in labels:
            # DECOMPOSITION_SCHEMA_INVALID / etc.
            if lab not in labels:
                return False
    return True


def replay_one(entry: dict[str, Any], *, candidates_dir: Path = CANDIDATES_DIR) -> dict[str, Any]:
    """Evaluate one manifest entry. expected_evaluation used only for assertion metadata."""
    case_id = entry["case_id"]
    filename = entry["filename"]
    raw = load_candidate_file(candidates_dir / filename)
    # Candidate file must be pure program — no expected-result metadata
    forbidden = {"expected_evaluation", "candidate_fixture_role", "scenario", "case_id"}
    if forbidden.intersection(raw.keys()):
        raise RuntimeError(f"candidate_file_contains_harness_metadata:{filename}")

    ev = evaluate_raw_candidate(case_id, raw)
    record = ev.to_json()
    record["filename"] = filename
    record["scenario"] = entry.get("scenario")
    record["candidate_fixture_role"] = entry.get("candidate_fixture_role", "HARNESS_TEST_VECTOR")
    record["expected_evaluation"] = entry.get("expected_evaluation")
    record["expected_outcome_match"] = _expected_ok(entry, record)
    return record


def replay_all(
    *,
    write_evidence: bool = True,
    starting_sha: str | None = None,
    candidate_sha: str | None = None,
) -> dict[str, Any]:
    manifest = load_manifest()
    records = [replay_one(e) for e in manifest["fixtures"]]

    label_counts: Counter[str] = Counter()
    for r in records:
        for lab in r.get("failure_labels") or []:
            label_counts[lab] += 1

    n_schema_valid = sum(1 for r in records if r.get("schema_valid"))
    n_schema_invalid = len(records) - n_schema_valid
    n_eq = sum(1 for r in records if r.get("semantically_equivalent") is True)
    n_neq = sum(1 for r in records if r.get("semantically_equivalent") is False)
    n_terminal_ok = sum(
        1
        for r in records
        if (r.get("runtime_gate") or {}).get("candidate_terminal", {}).get("authority") == "OK"
    )
    n_terminal_mismatch = sum(
        1 for r in records if "RUNTIME_TERMINAL_MISMATCH" in (r.get("failure_labels") or [])
    )
    n_benign = sum(
        1 for r in records if "BENIGN_REDUNDANT_TASK" in (r.get("diagnostics") or [])
    )
    oracle_before = sum(1 for r in records if r.get("oracle_access_before_freeze"))
    digests = [r.get("candidate_digest") for r in records if r.get("candidate_digest")]
    collisions = len(digests) - len(set(digests))
    all_match = all(r.get("expected_outcome_match") for r in records)

    summary = {
        "authority": AUTHORITY,
        "slice": SLICE,
        "provenance": {
            "results_jsonl": "replay.py",
            "summary_replay_counters": "replay.py",
            "handoff_md": "closeout-authored (not written by replay.py)",
            "negative_tests": "CLOSEOUT_ATTESTATION (pytest; not replay output)",
            "tests_passed": "CLOSEOUT_ATTESTATION (pytest; not replay output)",
        },
        "starting_sha": starting_sha,
        "candidate_sha": candidate_sha,
        "n_fixtures": len(records),
        "n_schema_valid": n_schema_valid,
        "n_schema_invalid": n_schema_invalid,
        "n_equivalent": n_eq,
        "n_non_equivalent": n_neq,
        "failure_label_counts": dict(sorted(label_counts.items())),
        "n_terminal_ok": n_terminal_ok,
        "n_terminal_mismatch": n_terminal_mismatch,
        "n_benign_redundant": n_benign,
        "oracle_access_before_freeze": oracle_before,
        "candidate_digest_collisions": collisions,
        "all_expected_fixture_outcomes_match": all_match,
        "real_decomposer_calls": 0,
        "oracle_candidate_generation_at_runtime": 0,
        "epistemic_claim": (
            "Harness proves frozen/hand-authored ScopeNormalizedPrograms evaluate "
            "reproducibly under Q3; does not demonstrate English→Program generation performance."
        ),
    }

    if write_evidence:
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_PATH.write_text(
            "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in records),
            encoding="utf-8",
        )
        SUMMARY_PATH.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return {"records": records, "summary": summary}


def main() -> None:
    out = replay_all()
    print(json.dumps(out["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
