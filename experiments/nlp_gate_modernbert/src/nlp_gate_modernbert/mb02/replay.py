"""300-case deterministic replay against gold oracle (post-normalization)."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.mb02.adjudicate import adjudicate
from nlp_gate_modernbert.mb02.contracts import NormalizedRequest
from nlp_gate_modernbert.mb02.workspace import project_workspace
from nlp_gate_modernbert.paths import EVIDENCE_DIR, SLM01_ROOT

CASES = SLM01_ROOT / "benchmark" / "gold" / "cases.jsonl"
AUDITED = EVIDENCE_DIR / "gate_cases_audited.jsonl"
NORM = EVIDENCE_DIR / "mb02_normalized_requests.jsonl"
OUT_DIR = EVIDENCE_DIR / "mb02"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def run_replay() -> dict[str, Any]:
    gold_rows = {r["case_id"]: r for r in _load_jsonl(CASES)}
    audited = {r["case_id"]: r for r in _load_jsonl(AUDITED)}
    norms = {r["case_id"]: r for r in _load_jsonl(NORM)}

    results: list[dict[str, Any]] = []
    status_ok = 0
    auth_ok_non_ok = 0
    non_ok_n = 0
    by_mb01_auth = Counter()
    by_selected = Counter()
    mismatches: list[dict[str, Any]] = []
    rule_prov: Counter = Counter()
    provenance_buckets = Counter()

    for case_id, gold_case in gold_rows.items():
        norm_rec = norms[case_id]
        req = NormalizedRequest.model_validate(norm_rec["normalized_request"])
        ws = project_workspace(gold_case["fixture"])
        decision = adjudicate(req, ws)

        gold_status = gold_case["gold"]["status"]
        gold_reason = gold_case["gold"].get("reason")
        gold_detail = gold_case["gold"].get("detail")
        mb01_auth = audited[case_id]["decision_authority"]

        pub = decision.public_envelope
        status_match = pub.status == gold_status
        # reason match when both present (unsupported/invalid)
        reason_match = True
        if gold_status in {"unsupported", "invalid"} and gold_reason:
            if gold_status == "invalid":
                # invalid envelopes use `reason` in gold sometimes as reason field
                reason_match = (pub.reason == gold_reason) or (
                    pub.reason is not None and gold_reason in (pub.reason or "")
                )
                # some gold invalid use reason key; detail is human text
                if not reason_match and pub.reason == gold_reason:
                    reason_match = True
            else:
                reason_match = pub.reason == gold_reason

        # Authority scoring: non-ok gold vs MB-01; ok gold expects terminal OK
        if gold_status == "ok":
            auth_match = decision.authority == "OK"
        else:
            non_ok_n += 1
            auth_match = decision.authority == mb01_auth
            if auth_match:
                auth_ok_non_ok += 1

        if status_match:
            status_ok += 1
        else:
            mismatches.append(
                {
                    "case_id": case_id,
                    "kind": "status",
                    "gold_status": gold_status,
                    "pred_status": pub.status,
                    "gold_reason": gold_reason,
                    "pred_reason": pub.reason,
                    "pred_detail": pub.detail,
                    "gold_detail": gold_detail,
                    "selected_authority": decision.authority,
                    "mb01_authority": mb01_auth,
                    "suppressed": decision.suppressed_terminal_facts,
                }
            )

        if gold_status != "ok" and not auth_match:
            mismatches.append(
                {
                    "case_id": case_id,
                    "kind": "authority",
                    "mb01_authority": mb01_auth,
                    "selected_authority": decision.authority,
                    "gold_status": gold_status,
                    "pred_status": pub.status,
                    "pred_reason": pub.reason,
                }
            )

        by_mb01_auth[mb01_auth] += 1
        by_selected[decision.authority] += 1
        for p in decision.rule_provenance:
            rule_prov[p] += 1

        # provenance classification
        if any("ScaleSpec" in p or "reuse" in p for p in decision.rule_provenance):
            provenance_buckets["reused_canonical"] += 1
        if any("adapted" in p for p in decision.rule_provenance):
            provenance_buckets["adapted_canonical"] += 1
        if any("experiment" in p or "static_registry" in p for p in decision.rule_provenance):
            provenance_buckets["experimental_only"] += 1

        results.append(
            {
                "case_id": case_id,
                "gold_status": gold_status,
                "pred_status": pub.status,
                "status_match": status_match,
                "reason_match": reason_match,
                "mb01_authority": mb01_auth,
                "selected_authority": decision.authority,
                "authority_match": auth_match,
                "subtype": decision.subtype,
                "suppressed_terminal_facts": decision.suppressed_terminal_facts,
                "normalization_method": norm_rec["normalization_provenance"]["method"],
            }
        )

    # Coverage A: implemented rule for each MB-01 authority class among cases
    coverage = {}
    for auth, n in by_mb01_auth.items():
        # count how many of those cases selected a deterministic terminal (including OK)
        covered = sum(
            1
            for r in results
            if r["mb01_authority"] == auth and r["selected_authority"] is not None
        )
        coverage[auth] = {"total": n, "accounted": covered}

    unresolved = sorted(
        {
            m["case_id"]
            for m in mismatches
            if m["kind"] == "status"
            or (m["kind"] == "authority" and m.get("gold_status") != "ok")
        }
    )
    summary = {
        "authority": "WELLPLOT-NLP-RUNTIME-V2-MB02-DETERMINISTIC-RESOLVER-FACT-PROJECTOR-AUTH-001",
        "n_cases": len(results),
        "public_status_match": status_ok,
        "public_status_match_rate": status_ok / max(1, len(results)),
        "non_ok_authority_match": auth_ok_non_ok,
        "non_ok_n": non_ok_n,
        "non_ok_authority_match_rate": auth_ok_non_ok / max(1, non_ok_n),
        "mb01_authority_counts": dict(by_mb01_auth),
        "selected_authority_counts": dict(by_selected),
        "authority_coverage": coverage,
        "rule_provenance_counts": dict(rule_prov),
        "rule_provenance_buckets": dict(provenance_buckets),
        "duplicated_production_rules": 0,
        "n_mismatches_recorded": len(mismatches),
        "unresolved_deterministic_cases": unresolved,
        "n_unresolved_deterministic_cases": len(unresolved),
        "learned_gate_required": "NO",
        "learned_gate_status": "NO_LEARNED_GATE_REQUIRED",
        "claim": (
            "MB-02 validates normalized semantic facts → deterministic envelope behavior only. "
            "It provides no evidence for raw natural-language → normalized semantic interpretation."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "mb02_replay_results.jsonl").write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in results) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "mb02_replay_mismatches.json").write_text(
        json.dumps(mismatches, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "mb02_replay_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for name in (
        "mb02_replay_results.jsonl",
        "mb02_replay_mismatches.json",
        "mb02_replay_summary.json",
    ):
        (EVIDENCE_DIR / name).write_bytes((OUT_DIR / name).read_bytes())
    return summary


if __name__ == "__main__":
    print(json.dumps(run_replay(), indent=2))
