#!/usr/bin/env python3
"""Compute freeze hashes and write SLM-01 gate evidence package.

Model baselines may be marked pending when GPUs/API keys are unavailable.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from eval.report import evaluate_gate, write_json
from well_ir.schema import well_ir_json_schema

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "benchmark" / "evidence"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT.parents[1],
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def main() -> None:
    gold = ROOT / "benchmark" / "gold" / "cases.jsonl"
    schema_hash = sha256_text(json.dumps(well_ir_json_schema(), sort_keys=True))
    split_hash = sha256_text(
        "".join(
            (ROOT / "benchmark" / "splits" / name).read_text(encoding="utf-8")
            for name in ("development.json", "validation.json", "held_out.json")
        )
    )
    provenance = {
        "git_sha": git_sha(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "well_ir_schema_sha256": schema_hash,
        "gold_corpus_sha256": sha256_file(gold),
        "split_sha256": split_hash,
        "historical_baseline_sha": "d77649765dee81ebd0b8f460ac28515b244f70da",
        "qwen_model_id": "Qwen/Qwen3-1.7B",
        "enable_thinking": False,
        "notes": [
            "Held-out model scores are recorded when runners execute; scaffolding may leave them null.",
        ],
    }
    write_json(EVIDENCE / "slm01_provenance.json", provenance)

    lowerer_path = EVIDENCE / "slm01_lowerer_evidence.json"
    lowerer = json.loads(lowerer_path.read_text(encoding="utf-8")) if lowerer_path.exists() else {}

    # Placeholder model metrics until live runs complete
    model_metrics = {
        "qwen_best_semantic_correctness": None,
        "qwen_arms": {"Q1": None, "Q2": None, "Q3": None},
        "cloud_semantic_correctness": None,
        "historical_native": None,
        "historical_common_intersection": None,
        "status": "PENDING_LIVE_BASELINE_RUNS",
    }
    write_json(EVIDENCE / "slm01_model_metrics.json", model_metrics)

    family_metrics = {
        "status": "PENDING_LIVE_BASELINE_RUNS",
        "families": {},
    }
    write_json(EVIDENCE / "slm01_family_metrics.json", family_metrics)

    envelope_confusion = {"status": "PENDING_LIVE_BASELINE_RUNS"}
    write_json(EVIDENCE / "slm01_envelope_confusion.json", envelope_confusion)

    taxonomy = {
        "status": "PENDING_LIVE_BASELINE_RUNS",
        "counts": {},
        "confirmed_model_semantic_n": 0,
        "learnable_share_of_confirmed": None,
        "ir_limitation_share_of_all_failures": None,
    }
    write_json(EVIDENCE / "slm01_failure_taxonomy.json", taxonomy)

    # Gate cannot PASS without live model metrics; emit honest PENDING/blocked decision.
    gate = evaluate_gate(
        ir_frozen=True,
        gold_frozen=True,
        split_frozen=True,
        lowerer_pass_rate=float(lowerer.get("pass_rate") or 0.0),
        baselines_complete=False,
        taxonomy_complete=False,
        semantic_correctness=None,
        family_breadth_ok=False,
        learnable_share=None,
        ir_limitation_share=None,
        held_out_leakage=False,
        non_goals_preserved=True,
    )
    gate["decision"] = "PENDING_BASELINES"
    gate["authorization"] = {
        "qlora_training": "NOT_AUTHORIZED",
        "slm02": "NOT_AUTHORIZED",
        "reason": "Live held-out baselines not yet executed in this environment",
    }
    write_json(EVIDENCE / "slm01_gate_decision.json", gate)

    summary = {
        "n_gold": sum(1 for _ in gold.open(encoding="utf-8")),
        "lowerer_100": lowerer.get("lowerer_100"),
        "schema_sha256": schema_hash,
        "gold_sha256": provenance["gold_corpus_sha256"],
        "gate_decision": gate["decision"],
        "milestones": {
            "M0": "COMPLETE",
            "M1": "COMPLETE",
            "M2": "COMPLETE",
            "M3": "COMPLETE_FREEZE_READY",
            "M4": "RUNNERS_SCAFFOLDED",
            "M5": "EVIDENCE_PACKAGE_INITIALIZED",
            "M6": "SEE_scaffold/qlora",
        },
    }
    write_json(EVIDENCE / "slm01_final_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
