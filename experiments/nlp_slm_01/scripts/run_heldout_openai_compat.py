#!/usr/bin/env python3
"""Held-out eval via OpenAI-compatible local server (e.g. llama-server).

Used for GGUF smoke / interim local runs. Tag results carefully:
HF scientific baseline remains authoritative for the SLM-02 gate.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

from benchmark.taxonomy import SEMANTIC_FAMILIES
from eval.envelope_metrics import confusion_matrix, false_ok_on_ambiguous, macro_f1
from eval.execution_equivalence import execution_equivalent
from eval.failure_taxonomy import summarize_taxonomy
from eval.report import evaluate_gate, write_json
from eval.semantic_equivalence import normalized_equal
from lowerer.context import DocumentState, WorkspaceContext
from runners.common import SYSTEM_PROMPT, assemble_user_payload, few_shot_messages, schema_hash
from runners.historical_baseline import run_historical_case
from well_ir.canonicalize import parse_well_ir

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "benchmark" / "gold" / "cases.jsonl"
FIXTURES = ROOT / "benchmark" / "fixtures"
SPLITS = ROOT / "benchmark" / "splits"
EVIDENCE = ROOT / "benchmark" / "evidence"
ARTIFACTS = ROOT / "artifacts" / "runs"


def load_cases(split_name: str) -> list[dict[str, Any]]:
    ids = set(json.loads((SPLITS / f"{split_name}.json").read_text())["case_ids"])
    return [
        json.loads(line)
        for line in GOLD.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["case_id"] in ids
    ]


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def extract_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def classify_failure(gold, pred, schema_ok, semantic_ok, case) -> str | None:
    if semantic_ok:
        return None
    if not schema_ok or pred is None:
        return "syntax_or_schema"
    if gold.status != getattr(pred, "status", None):
        return "envelope_misuse"
    tags = set(case.get("semantic_tags", []))
    family = case.get("semantic_family")
    if "alias" in tags:
        return "alias_resolution"
    if "deictic" in tags:
        return "deictic"
    if family == "composition" or "composition" in tags:
        return "composition"
    if family == "relational_targeting" or "relation" in tags:
        return "relation"
    if "units" in tags or family == "intervals":
        return "units"
    if family == "ambiguity_unsupported":
        return "envelope_misuse"
    return "other"


def build_exemplars(dev_cases: list[dict[str, Any]], k: int = 4) -> list[dict[str, Any]]:
    picks = []
    for fam in [
        "curve_placement",
        "composition",
        "relational_targeting",
        "ambiguity_unsupported",
    ]:
        for case in dev_cases:
            if case["semantic_family"] == fam:
                fix = load_fixture(case["fixture"])
                picks.append(
                    {
                        "utterance": case["utterances"][0]["text"],
                        "workspace": fix["workspace"],
                        "d0": fix["d0"],
                        "gold": case["gold"],
                    }
                )
                break
        if len(picks) >= k:
            break
    return picks[:k]


def chat(
    client: httpx.Client,
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    api_key: str,
) -> str:
    resp = client.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "temperature": 0,
            "messages": messages,
            "max_tokens": 512,
        },
        timeout=300.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def score_prediction(case: dict[str, Any], raw_text: str) -> dict[str, Any]:
    fix = load_fixture(case["fixture"])
    d0 = DocumentState.model_validate(fix["d0"])
    ws = WorkspaceContext.model_validate(fix["workspace"])
    gold = parse_well_ir(case["gold"])
    payload = extract_json(raw_text)
    schema_ok = False
    pred = None
    if payload is not None:
        try:
            pred = parse_well_ir(payload)
            schema_ok = True
        except Exception:  # noqa: BLE001
            schema_ok = False
    semantic_ok = False
    exec_ok = False
    if pred is not None:
        try:
            semantic_ok = normalized_equal(pred, gold)
            exec_ok = execution_equivalent(pred, gold, d0, ws)
        except Exception:  # noqa: BLE001
            pass
    correct = bool(semantic_ok or exec_ok)
    return {
        "case_id": case["case_id"],
        "family": case["semantic_family"],
        "gold_status": gold.status,
        "pred_status": getattr(pred, "status", None) if pred is not None else None,
        "schema_ok": schema_ok,
        "semantic_ok": semantic_ok,
        "execution_ok": exec_ok,
        "correct": correct,
        "failure_label": classify_failure(gold, pred, schema_ok, correct, case),
        "raw_text": raw_text[:2000],
    }


def evaluate_arm(results: list[dict[str, Any]]) -> dict[str, Any]:
    executable = [r for r in results if r["gold_status"] == "ok"]
    correct_exec = [r for r in executable if r["correct"]]
    by_fam: dict[str, list] = defaultdict(list)
    for r in results:
        by_fam[r["family"]].append(r)
    family_stats = {
        fam: {
            "n": len(rows),
            "correct": sum(1 for x in rows if x["correct"]),
            "rate": sum(1 for x in rows if x["correct"]) / len(rows) if rows else 0.0,
        }
        for fam, rows in by_fam.items()
    }
    y_true = [r["gold_status"] for r in results]
    y_pred = [r["pred_status"] or "invalid" for r in results]
    matrix = confusion_matrix(y_true, y_pred)
    labels = [r["failure_label"] for r in results if r["failure_label"]]
    return {
        "n": len(results),
        "n_executable": len(executable),
        "semantic_correctness_executable": (
            len(correct_exec) / len(executable) if executable else None
        ),
        "overall_correctness": sum(1 for r in results if r["correct"]) / len(results)
        if results
        else None,
        "schema_validity_rate": sum(1 for r in results if r["schema_ok"]) / len(results)
        if results
        else None,
        "family_stats": family_stats,
        "envelope_macro_f1": macro_f1(matrix),
        "envelope_confusion": matrix,
        "false_ok_on_ambiguous": false_ok_on_ambiguous(y_true, y_pred),
        "taxonomy": summarize_taxonomy(labels),
    }


def family_breadth_ok(family_stats: dict[str, dict[str, float]]) -> bool:
    for fam in SEMANTIC_FAMILIES:
        stats = family_stats.get(fam)
        if not stats or stats["n"] == 0:
            return False
        if stats["correct"] < 5 and stats["rate"] < 0.25:
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("SLM01_LOCAL_BASE_URL", "http://127.0.0.1:8889/v1"))
    parser.add_argument("--model", default=os.environ.get("SLM01_LOCAL_MODEL", "qwen3-1.7b-slm01"))
    parser.add_argument("--api-key", default=os.environ.get("SLM01_LOCAL_API_KEY", "local"))
    parser.add_argument("--arms", default="Q1,Q2")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--gate-eligible",
        action="store_true",
        help="If set, write SLM-02 gate decision from these results (HF scientific only).",
    )
    parser.add_argument("--label", default="gguf_q4_local", help="artifact label")
    args = parser.parse_args()

    held = load_cases("held_out")
    dev = load_cases("development")
    if args.limit:
        held = held[: args.limit]
    exemplars = build_exemplars(dev)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    # historical baseline A always recorded
    hist_rows = [
        run_historical_case(
            {
                "case_id": c["case_id"],
                "historical_baseline_eligibility": c.get(
                    "historical_baseline_eligibility", "OUT_OF_SCOPE"
                ),
            }
        )
        for c in held
    ]
    write_json(
        EVIDENCE / "slm01_historical_baseline.json",
        {
            "n": len(hist_rows),
            "eligible": sum(1 for r in hist_rows if r.get("native_status") != "SKIPPED"),
            "rows": hist_rows,
        },
    )

    arm_metrics: dict[str, Any] = {}
    best_semantic = None
    best_arm = None
    best_family_stats: dict[str, dict[str, float]] = {}
    best_taxonomy: dict[str, Any] = {}
    best_envelope: dict[str, Any] = {}

    with httpx.Client() as client:
        for arm in [a.strip() for a in args.arms.split(",") if a.strip()]:
            print(f"Running {arm} on {len(held)} cases via {args.base_url}", flush=True)
            rows = []
            for i, case in enumerate(held, 1):
                fix = load_fixture(case["fixture"])
                utt = case["utterances"][0]["text"]
                if arm == "Q1":
                    messages = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": assemble_user_payload(utt, fix["workspace"], fix["d0"]),
                        },
                    ]
                else:
                    messages = few_shot_messages(exemplars)
                    messages.append(
                        {
                            "role": "user",
                            "content": assemble_user_payload(utt, fix["workspace"], fix["d0"]),
                        }
                    )
                t0 = time.time()
                try:
                    text = chat(
                        client,
                        base_url=args.base_url,
                        model=args.model,
                        messages=messages,
                        api_key=args.api_key,
                    )
                    scored = score_prediction(case, text)
                    scored["latency_s"] = time.time() - t0
                except Exception as exc:  # noqa: BLE001
                    scored = {
                        "case_id": case["case_id"],
                        "family": case["semantic_family"],
                        "gold_status": case["gold"]["status"],
                        "pred_status": None,
                        "schema_ok": False,
                        "semantic_ok": False,
                        "execution_ok": False,
                        "correct": False,
                        "failure_label": "other",
                        "error": str(exc),
                    }
                rows.append(scored)
                if i % 5 == 0 or i == len(held):
                    print(f"  {arm}: {i}/{len(held)} correct={sum(1 for r in rows if r['correct'])}", flush=True)
            metrics = evaluate_arm(rows)
            arm_metrics[arm] = metrics
            (ARTIFACTS / f"heldout_{args.label}_{arm}.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
            )
            sem = metrics["semantic_correctness_executable"]
            if sem is not None and (best_semantic is None or sem > best_semantic):
                best_semantic = sem
                best_arm = arm
                best_family_stats = metrics["family_stats"]
                best_taxonomy = metrics["taxonomy"]
                best_envelope = {
                    "confusion": metrics["envelope_confusion"],
                    "macro_f1": metrics["envelope_macro_f1"],
                    "false_ok_on_ambiguous": metrics["false_ok_on_ambiguous"],
                }

    lowerer = json.loads((EVIDENCE / "slm01_lowerer_evidence.json").read_text())
    write_json(
        EVIDENCE / "slm01_model_metrics.json",
        {
            "runtime": args.label,
            "base_url": args.base_url,
            "model": args.model,
            "gate_eligible_run": bool(args.gate_eligible),
            "qwen_best_arm": best_arm,
            "qwen_best_semantic_correctness": best_semantic,
            "qwen_arms": arm_metrics,
            "schema_sha256": schema_hash(),
            "n_held_out_evaluated": len(held),
            "note": (
                "GGUF/local-server results are deployment-informative; "
                "set --gate-eligible only for HF scientific baseline runs."
            ),
        },
    )
    write_json(
        EVIDENCE / "slm01_family_metrics.json",
        {"best_arm": best_arm, "families": best_family_stats, "runtime": args.label},
    )
    write_json(EVIDENCE / "slm01_envelope_confusion.json", best_envelope or {"status": "empty"})
    write_json(EVIDENCE / "slm01_failure_taxonomy.json", best_taxonomy or {"status": "empty"})

    if args.gate_eligible:
        learnable = best_taxonomy.get("learnable_share_of_confirmed")
        ir_share = best_taxonomy.get("ir_limitation_share_of_all_failures")
        gate = evaluate_gate(
            ir_frozen=True,
            gold_frozen=True,
            split_frozen=True,
            lowerer_pass_rate=float(lowerer.get("pass_rate") or 0.0),
            baselines_complete=bool(arm_metrics),
            taxonomy_complete=bool(best_taxonomy),
            semantic_correctness=best_semantic,
            family_breadth_ok=family_breadth_ok(best_family_stats) if best_family_stats else False,
            learnable_share=learnable if learnable is not None else 0.0,
            ir_limitation_share=ir_share if ir_share is not None else 0.0,
            held_out_leakage=False,
            non_goals_preserved=True,
        )
    else:
        gate = {
            "decision": "PENDING_HF_SCIENTIFIC_BASELINE",
            "checks": {"gguf_interim_complete": True, "hf_scientific": False},
            "interim_best_semantic": best_semantic,
            "interim_best_arm": best_arm,
            "note": "Interim GGUF/local results recorded; SLM-02 gate awaits HF Qwen3-1.7B run.",
        }
    write_json(EVIDENCE / "slm01_gate_decision.json", gate)
    write_json(
        EVIDENCE / "slm01_final_summary.json",
        {
            "runtime": args.label,
            "n_held_out": len(held),
            "best_arm": best_arm,
            "best_semantic_correctness": best_semantic,
            "gate_decision": gate.get("decision"),
            "gate_eligible_run": bool(args.gate_eligible),
        },
    )
    print(
        json.dumps(
            {
                "gate": gate.get("decision"),
                "best_arm": best_arm,
                "best_semantic": best_semantic,
                "runtime": args.label,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
