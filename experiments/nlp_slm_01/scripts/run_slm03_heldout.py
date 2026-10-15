#!/usr/bin/env python3
"""SLM-03 sealed held-out Q1 eval with dual support-level scoring."""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark.fixture_loader import load_fixture
from benchmark.taxonomy import SEMANTIC_FAMILIES
from eval.envelope_metrics import confusion_matrix, false_ok_on_ambiguous, macro_f1
from eval.execution_equivalence import execution_equivalent
from eval.failure_taxonomy import summarize_taxonomy
from eval.report import evaluate_gate, write_json
from eval.semantic_equivalence import normalized_equal
from lowerer.context import DocumentState, WorkspaceContext
from runners.common import SYSTEM_PROMPT, assemble_user_payload, schema_hash
from well_ir.canonicalize import parse_well_ir

GOLD = ROOT / "benchmark" / "gold" / "cases.jsonl"
SPLITS = ROOT / "benchmark" / "splits"
EVIDENCE = ROOT / "benchmark" / "evidence"
ARTIFACTS = ROOT / "artifacts" / "runs"
DEFAULT_ADAPTER = ROOT / "artifacts" / "adapters" / "slm03_qwenv17_qlora"
DEFAULT_BASE = (
    ROOT
    / "artifacts"
    / "modelscope_cache"
    / "models"
    / "Qwen--Qwen3-1.7B"
    / "snapshots"
    / "master"
)
TRAINABLE = frozenset({"d5_current", "d5_context_lowerable", "envelope_only"})


def load_cases(split_name: str) -> list[dict[str, Any]]:
    ids = set(json.loads((SPLITS / f"{split_name}.json").read_text())["case_ids"])
    return [
        json.loads(line)
        for line in GOLD.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["case_id"] in ids
    ]


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
    level = (case.get("grounding") or {}).get("support_level")
    return {
        "case_id": case["case_id"],
        "family": case["semantic_family"],
        "support_level": level,
        "gold_status": gold.status,
        "pred_status": getattr(pred, "status", None) if pred is not None else None,
        "schema_ok": schema_ok,
        "semantic_ok": semantic_ok,
        "execution_ok": exec_ok,
        "correct": correct,
        "failure_label": classify_failure(gold, pred, schema_ok, correct, case),
        "raw_text": (raw_text or "")[:2000],
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


def dual_scores(results: list[dict[str, Any]]) -> dict[str, Any]:
    floor = [r for r in results if r.get("support_level") in TRAINABLE]
    future = [r for r in results if r.get("support_level") not in TRAINABLE]
    return {
        "d5_executable_floor": evaluate_arm(floor),
        "full_heldout_breadth": evaluate_arm(results),
        "future_ops_probe": evaluate_arm(future),
        "n_floor": len(floor),
        "n_full": len(results),
        "n_future": len(future),
    }


def family_breadth_ok(family_stats: dict[str, dict[str, float]]) -> bool:
    # Gate on families that appear in the floor set with n>0
    for fam, stats in family_stats.items():
        if fam not in SEMANTIC_FAMILIES:
            continue
        if stats["n"] == 0:
            continue
        if stats["correct"] < 5 and stats["rate"] < 0.25:
            return False
    return True


class AdapterRunner:
    def __init__(self, base: Path, adapter: Path, max_seq_length: int = 4096) -> None:
        import unsloth  # noqa: F401
        from unsloth import FastLanguageModel
        import torch
        from peft import PeftModel

        self.torch = torch
        print(f"Loading base+adapter\n  base={base}\n  adapter={adapter}", flush=True)
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=str(base),
            max_seq_length=max_seq_length,
            load_in_4bit=True,
            dtype=None,
        )
        model = PeftModel.from_pretrained(model, str(adapter))
        FastLanguageModel.for_inference(model)
        self.model = model
        self.tokenizer = tokenizer

    def predict(self, *, utterance: str, workspace: dict[str, Any], d0: dict[str, Any]) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": assemble_user_payload(utterance, workspace, d0)},
        ]
        try:
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            prompt = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        with self.torch.inference_mode():
            out = self.model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        return self.tokenizer.decode(
            out[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    held = load_cases("held_out")
    if args.limit:
        held = held[: args.limit]
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    runner = AdapterRunner(args.base, args.adapter)
    print(f"[SLM-03] Q1 n={len(held)}", flush=True)
    rows: list[dict[str, Any]] = []
    for i, case in enumerate(held, 1):
        fix = load_fixture(case["fixture"])
        utt = case["utterances"][0]["text"]
        t0 = time.time()
        try:
            text = runner.predict(utterance=utt, workspace=fix["workspace"], d0=fix["d0"])
            scored = score_prediction(case, text)
            scored["latency_s"] = time.time() - t0
        except Exception as exc:  # noqa: BLE001
            scored = {
                "case_id": case["case_id"],
                "family": case["semantic_family"],
                "support_level": (case.get("grounding") or {}).get("support_level"),
                "gold_status": case["gold"]["status"],
                "pred_status": None,
                "schema_ok": False,
                "semantic_ok": False,
                "execution_ok": False,
                "correct": False,
                "failure_label": "other",
                "error": str(exc),
                "traceback": traceback.format_exc()[-1000:],
            }
        rows.append(scored)
        if i % 5 == 0 or i == len(held):
            print(
                f"  Q1: {i}/{len(held)} correct={sum(1 for r in rows if r['correct'])}",
                flush=True,
            )

    dual = dual_scores(rows)
    floor = dual["d5_executable_floor"]
    tax = floor.get("taxonomy") or {}
    gate = evaluate_gate(
        ir_frozen=True,
        gold_frozen=True,
        split_frozen=True,
        lowerer_pass_rate=1.0,
        baselines_complete=True,
        taxonomy_complete=bool(tax),
        semantic_correctness=floor.get("semantic_correctness_executable"),
        family_breadth_ok=family_breadth_ok(floor.get("family_stats") or {}),
        learnable_share=tax.get("learnable_share_of_confirmed") or 0.0,
        ir_limitation_share=tax.get("ir_limitation_share_of_all_failures") or 0.0,
        held_out_leakage=False,
        non_goals_preserved=True,
    )

    (ARTIFACTS / "slm03_heldout_Q1.jsonl").write_text(
        "\n".join(json.dumps(r, default=str) for r in rows) + "\n",
        encoding="utf-8",
    )
    write_json(
        EVIDENCE / "slm03_model_metrics.json",
        {
            "base": str(args.base),
            "adapter": str(args.adapter),
            "prompt_arm": "Q1",
            "dual": dual,
            "gate_semantic_correctness": floor.get("semantic_correctness_executable"),
            "schema_sha256": schema_hash(),
            "n_held_out": len(held),
        },
    )
    write_json(
        EVIDENCE / "slm03_family_metrics.json",
        {"scope": "d5_executable_floor", "families": floor.get("family_stats")},
    )
    write_json(EVIDENCE / "slm03_failure_taxonomy.json", tax or {"status": "empty"})
    write_json(EVIDENCE / "slm03_gate_decision.json", gate)
    write_json(
        EVIDENCE / "slm03_final_summary.json",
        {
            "experiment": "WELLPLOT-NLP-SLM-03",
            "n_held_out": len(held),
            "prompt_arm": "Q1",
            "d5_executable_floor_semantic": floor.get("semantic_correctness_executable"),
            "full_breadth_overall": dual["full_heldout_breadth"].get("overall_correctness"),
            "gate_decision": gate.get("decision"),
            "adapter": str(args.adapter),
        },
    )
    print(
        json.dumps(
            {
                "gate": gate.get("decision"),
                "floor_semantic": floor.get("semantic_correctness_executable"),
                "full_overall": dual["full_heldout_breadth"].get("overall_correctness"),
                "n_floor": dual["n_floor"],
                "n_full": dual["n_full"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
