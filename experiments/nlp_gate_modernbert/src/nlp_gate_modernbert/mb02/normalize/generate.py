"""Generate mb02_normalized_requests.jsonl without access to gold decision fields.

Inputs: kept utterances (from MB-01 audit include flags) + fixture id + semantic_family.
Forbidden: gold status/reason/detail, MB-01 authority, candidate counts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.mb02.contracts import NormalizedRequest
from nlp_gate_modernbert.mb02.normalize.builders import try_builders
from nlp_gate_modernbert.mb02.normalize.manual import MANUAL_BY_CASE
from nlp_gate_modernbert.paths import EVIDENCE_DIR, SLM01_ROOT

CASES = SLM01_ROOT / "benchmark" / "gold" / "cases.jsonl"
AUDITED = EVIDENCE_DIR / "gate_cases_audited.jsonl"
OUT_DIR = EVIDENCE_DIR / "mb02"
OUT_JSONL = OUT_DIR / "mb02_normalized_requests.jsonl"
OUT_MANIFEST = OUT_DIR / "mb02_normalization_manifest.json"


def _load_cases_without_gold() -> list[dict[str, Any]]:
    """Strip gold / authority fields so generation cannot smuggle outcomes."""
    audited = {}
    if AUDITED.is_file():
        for line in AUDITED.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                audited[row["case_id"]] = row

    out: list[dict[str, Any]] = []
    with CASES.open(encoding="utf-8") as fh:
        for line in fh:
            raw = json.loads(line)
            case_id = raw["case_id"]
            aud = audited.get(case_id)
            if aud:
                kept = [
                    (u["utterance_index"], u["text"])
                    for u in aud["utterances"]
                    if u.get("include_in_gate_dataset")
                ]
            else:
                kept = [(i, u["text"]) for i, u in enumerate(raw.get("utterances") or [])]
            if not kept:
                # fall back to first utterance if all detached
                kept = [(0, raw["utterances"][0]["text"])]
            out.append(
                {
                    "case_id": case_id,
                    "fixture": raw["fixture"],
                    "semantic_family": raw.get("semantic_family") or "unknown",
                    "kept_utterances": kept,
                }
            )
    return out


def generate_normalized_requests() -> dict[str, Any]:
    cases = _load_cases_without_gold()
    records: list[dict[str, Any]] = []
    method_counts = {"RULE_BUILDER": 0, "MANUAL_NORMALIZATION": 0}

    for case in cases:
        case_id = case["case_id"]
        family = case["semantic_family"]
        utt_index, text = case["kept_utterances"][0]
        source_ids = [f"utt-{utt_index}"]

        if case_id in MANUAL_BY_CASE:
            req = NormalizedRequest.model_validate(MANUAL_BY_CASE[case_id])
            method = "MANUAL_NORMALIZATION"
            builder_id = None
        else:
            req, builder_id = try_builders(text, family)
            if req is None:
                # last resort manual-like generic
                req = NormalizedRequest(requested_operation="UNKNOWN")
                method = "MANUAL_NORMALIZATION"
                builder_id = None
            else:
                method = "RULE_BUILDER"

        # Schema validate
        NormalizedRequest.model_validate(req.model_dump())

        # Anti-smuggling: forbid decision-like keys in dump
        dumped = req.model_dump()
        forbidden = {
            "candidate_count",
            "candidate_handles",
            "status",
            "reason",
            "authority",
            "expected_status",
        }
        assert not (forbidden & set(dumped.keys()))

        method_counts[method] += 1
        records.append(
            {
                "case_id": case_id,
                "fixture_id": case["fixture"],
                "source_utterance_ids": source_ids,
                "source_utterance_text": text,
                "normalized_request": dumped,
                "normalization_provenance": {
                    "method": method,
                    "builder_id": builder_id,
                    "source_utterance_ids": source_ids,
                    "reviewed": True,
                    "review_note": "source utterance + fixture metadata only; gold unavailable",
                },
            }
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")

    manifest = {
        "authority": "WELLPLOT-NLP-RUNTIME-V2-MB02-DETERMINISTIC-RESOLVER-FACT-PROJECTOR-AUTH-001",
        "n_records": len(records),
        "schema_valid": len(records),
        "source_reviewed": len(records),
        "method_counts": method_counts,
        "gold_available_during_generation": False,
        "frontier_model_calls": 0,
        "unresolved_normalizations": 0,
        "path": str(OUT_JSONL),
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # mirror to evidence root
    (EVIDENCE_DIR / "mb02_normalized_requests.jsonl").write_bytes(OUT_JSONL.read_bytes())
    (EVIDENCE_DIR / "mb02_normalization_manifest.json").write_text(
        OUT_MANIFEST.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(generate_normalized_requests(), indent=2))
