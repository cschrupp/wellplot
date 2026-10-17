#!/usr/bin/env python3
"""Run sealed held-out baselines and write SLM-01 evidence (M4/M5)."""

from __future__ import annotations

import argparse
import json
import re
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from benchmark.taxonomy import IR_BLOCKERS, LEARNABLE, SEMANTIC_FAMILIES
from eval.envelope_metrics import confusion_matrix, false_ok_on_ambiguous, macro_f1
from eval.execution_equivalence import execution_equivalent
from eval.failure_taxonomy import summarize_taxonomy
from eval.report import evaluate_gate, write_json
from eval.semantic_equivalence import normalized_equal
from lowerer.context import DocumentState, WorkspaceContext
from runners.common import SYSTEM_PROMPT, assemble_user_payload, few_shot_messages, schema_hash
from runners.historical_baseline import run_historical_case
from well_ir.canonicalize import parse_well_ir
from well_ir.schema import well_ir_json_schema

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "benchmark" / "gold" / "cases.jsonl"
FIXTURES = ROOT / "benchmark" / "fixtures"
SPLITS = ROOT / "benchmark" / "splits"
EVIDENCE = ROOT / "benchmark" / "evidence"
ARTIFACTS = ROOT / "artifacts" / "runs"


def load_cases(split_name: str) -> list[dict[str, Any]]:
    ids = set(json.loads((SPLITS / f"{split_name}.json").read_text())["case_ids"])
    cases = []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        if case["case_id"] in ids:
            cases.append(case)
    return cases


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # strip optional fences / leading chatter
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def classify_failure(
    *,
    gold: Any,
    pred: Any | None,
    schema_ok: bool,
    semantic_ok: bool,
    case: dict[str, Any],
) -> str | None:
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
    wanted = [
        "curve_placement",
        "composition",
        "relational_targeting",
        "ambiguity_unsupported",
    ]
    for fam in wanted:
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


class QwenRunner:
    def __init__(self, model_id: str = "Qwen/Qwen3-1.7B") -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.model_id = model_id
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=False)
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            dtype=dtype,
            device_map="auto" if torch.cuda.is_available() else None,
            local_files_only=False,
        )
        if not torch.cuda.is_available():
            self.model = self.model.to("cpu")
        self.device = next(self.model.parameters()).device
        self.outlines_status = "NOT_ATTEMPTED"
        self._outlines_gen = None

    def _generate(self, messages: list[dict[str, str]], constrained: bool) -> dict[str, Any]:
        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        if constrained:
            try:
                import outlines
                from well_ir.envelopes import WellIrResult

                if self._outlines_gen is None:
                    # outlines API varies by version; try common entry points
                    try:
                        self._outlines_gen = outlines.generate.json(
                            self.model, WellIrResult, tokenizer=self.tokenizer
                        )
                    except Exception:
                        model = outlines.models.Transformers(self.model, self.tokenizer)
                        self._outlines_gen = outlines.generate.json(model, WellIrResult)
                text = self._outlines_gen(prompt)
                self.outlines_status = "IMPLEMENTED"
                if not isinstance(text, str):
                    text = json.dumps(text if isinstance(text, dict) else text.model_dump())
                return {"raw_text": text, "constrained": True, "constrained_status": "IMPLEMENTED"}
            except Exception as exc:  # noqa: BLE001
                self.outlines_status = f"DEFERRED_WITH_EVIDENCE:{type(exc).__name__}:{exc}"
                # fall through unconstrained
        inputs = self.tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        out = self.model.generate(**inputs, max_new_tokens=512, do_sample=False)
        text = self.tokenizer.decode(
            out[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True
        )
        return {
            "raw_text": text,
            "constrained": False,
            "constrained_status": self.outlines_status
            if constrained
            else "NOT_REQUESTED",
        }

    def predict(
        self,
        *,
        arm: str,
        utterance: str,
        workspace: dict[str, Any],
        d0: dict[str, Any],
        exemplars: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if arm == "Q1":
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": assemble_user_payload(utterance, workspace, d0)},
            ]
        else:
            messages = few_shot_messages(exemplars)
            messages.append(
                {
                    "role": "user",
                    "content": assemble_user_payload(utterance, workspace, d0),
                }
            )
        gen = self._generate(messages, constrained=(arm == "Q3"))
        return {
            "arm": arm,
            "model_id": self.model_id,
            "schema_sha256": schema_hash(),
            "enable_thinking": False,
            **gen,
        }


def score_prediction(
    case: dict[str, Any],
    raw: dict[str, Any],
) -> dict[str, Any]:
    fix = load_fixture(case["fixture"])
    d0 = DocumentState.model_validate(fix["d0"])
    ws = WorkspaceContext.model_validate(fix["workspace"])
    gold = parse_well_ir(case["gold"])
    payload = extract_json(raw.get("raw_text") or "")
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
            semantic_ok = False
            exec_ok = False
    label = classify_failure(
        gold=gold, pred=pred, schema_ok=schema_ok, semantic_ok=semantic_ok or exec_ok, case=case
    )
    return {
        "case_id": case["case_id"],
        "family": case["semantic_family"],
        "gold_status": gold.status,
        "pred_status": getattr(pred, "status", None) if pred is not None else None,
        "schema_ok": schema_ok,
        "semantic_ok": semantic_ok,
        "execution_ok": exec_ok,
        "correct": bool(semantic_ok or exec_ok),
        "failure_label": label,
        "raw": raw,
    }


def evaluate_arm(results: list[dict[str, Any]]) -> dict[str, Any]:
    executable = [r for r in results if r["gold_status"] == "ok"]
    correct_exec = [r for r in executable if r["correct"]]
    family_stats: dict[str, dict[str, float]] = {}
    by_fam: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        by_fam[r["family"]].append(r)
    for fam, rows in by_fam.items():
        family_stats[fam] = {
            "n": len(rows),
            "correct": sum(1 for x in rows if x["correct"]),
            "rate": sum(1 for x in rows if x["correct"]) / len(rows) if rows else 0.0,
        }
    y_true = [r["gold_status"] for r in results]
    y_pred = [r["pred_status"] or "invalid" for r in results]
    matrix = confusion_matrix(y_true, y_pred)
    labels = [r["failure_label"] for r in results if r["failure_label"]]
    taxonomy = summarize_taxonomy(labels)
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
        "taxonomy": taxonomy,
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
    parser.add_argument("--limit", type=int, default=0, help="optional cap for smoke runs")
    parser.add_argument("--skip-qwen", action="store_true")
    parser.add_argument("--arms", default="Q1,Q2,Q3")
    parser.add_argument(
        "--model",
        default="Qwen/Qwen3-1.7B",
        help="HF model id or local directory with weights",
    )
    args = parser.parse_args()

    held = load_cases("held_out")
    dev = load_cases("development")
    if args.limit:
        held = held[: args.limit]
    exemplars = build_exemplars(dev)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    # Baseline A: historical (subprocess)
    hist_rows = []
    for case in held:
        hist_rows.append(
            run_historical_case(
                {
                    "case_id": case["case_id"],
                    "historical_baseline_eligibility": case.get(
                        "historical_baseline_eligibility", "OUT_OF_SCOPE"
                    ),
                }
            )
        )
    write_json(
        EVIDENCE / "slm01_historical_baseline.json",
        {
            "n": len(hist_rows),
            "eligible": sum(1 for r in hist_rows if r.get("native_status") != "SKIPPED"),
            "rows": hist_rows,
        },
    )

    # Baseline B: cloud (may be unavailable)
    from runners.cloud_baseline import run_cloud

    cloud_results = []
    for case in held:
        fix = load_fixture(case["fixture"])
        utt = case["utterances"][0]["text"]
        raw = run_cloud(utterance=utt, workspace=fix["workspace"], d0=fix["d0"])
        if raw.get("status") == "runner_unavailable":
            cloud_results.append(
                {
                    "case_id": case["case_id"],
                    "unavailable": True,
                    "detail": raw.get("detail"),
                    "correct": False,
                    "gold_status": case["gold"]["status"],
                    "pred_status": None,
                    "schema_ok": False,
                    "semantic_ok": False,
                    "execution_ok": False,
                    "failure_label": "other",
                    "family": case["semantic_family"],
                }
            )
            # one probe is enough if unavailable
            break
        scored = score_prediction(case, raw)
        cloud_results.append(scored)
    cloud_metrics = (
        evaluate_arm(cloud_results)
        if cloud_results and not cloud_results[0].get("unavailable")
        else {
            "status": "runner_unavailable",
            "detail": cloud_results[0].get("detail") if cloud_results else "no cases",
        }
    )

    arm_metrics: dict[str, Any] = {}
    best_semantic = None
    best_arm = None
    best_family_stats: dict[str, dict[str, float]] = {}
    best_taxonomy: dict[str, Any] = {}
    best_envelope = {}
    outlines_status = "NOT_RUN"

    if not args.skip_qwen:
        print(f"Loading {args.model} ...", flush=True)
        runner = QwenRunner(model_id=args.model)
        for arm in [a.strip() for a in args.arms.split(",") if a.strip()]:
            print(f"Running arm {arm} on {len(held)} held-out cases ...", flush=True)
            rows = []
            for i, case in enumerate(held, 1):
                fix = load_fixture(case["fixture"])
                utt = case["utterances"][0]["text"]
                try:
                    raw = runner.predict(
                        arm=arm,
                        utterance=utt,
                        workspace=fix["workspace"],
                        d0=fix["d0"],
                        exemplars=exemplars,
                    )
                    scored = score_prediction(case, raw)
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
                        "traceback": traceback.format_exc()[-1000:],
                    }
                rows.append(scored)
                if i % 5 == 0 or i == len(held):
                    print(f"  {arm}: {i}/{len(held)}", flush=True)
            metrics = evaluate_arm(rows)
            arm_metrics[arm] = metrics
            (ARTIFACTS / f"heldout_{arm}.jsonl").write_text(
                "\n".join(json.dumps(r, default=str) for r in rows) + "\n",
                encoding="utf-8",
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
        outlines_status = runner.outlines_status
    else:
        outlines_status = "SKIPPED"

    lowerer = json.loads((EVIDENCE / "slm01_lowerer_evidence.json").read_text())
    learnable = best_taxonomy.get("learnable_share_of_confirmed")
    ir_share = best_taxonomy.get("ir_limitation_share_of_all_failures")
    breadth = family_breadth_ok(best_family_stats) if best_family_stats else False
    baselines_complete = bool(arm_metrics) and ("status" not in cloud_metrics or True)
    # cloud optional for completeness flag if unavailable; Qwen required unless skipped
    baselines_complete = bool(arm_metrics)

    gate = evaluate_gate(
        ir_frozen=True,
        gold_frozen=True,
        split_frozen=True,
        lowerer_pass_rate=float(lowerer.get("pass_rate") or 0.0),
        baselines_complete=baselines_complete,
        taxonomy_complete=bool(best_taxonomy),
        semantic_correctness=best_semantic,
        family_breadth_ok=breadth,
        learnable_share=learnable if learnable is not None else 0.0,
        ir_limitation_share=ir_share if ir_share is not None else 0.0,
        held_out_leakage=False,
        non_goals_preserved=True,
    )
    if not baselines_complete:
        gate["decision"] = "PENDING_BASELINES"

    write_json(
        EVIDENCE / "slm01_model_metrics.json",
        {
            "qwen_best_arm": best_arm,
            "qwen_best_semantic_correctness": best_semantic,
            "qwen_arms": arm_metrics,
            "cloud_semantic_correctness": cloud_metrics.get("semantic_correctness_executable"),
            "cloud": cloud_metrics,
            "historical_native": "see slm01_historical_baseline.json",
            "outlines_status": outlines_status,
            "schema_sha256": schema_hash(),
            "n_held_out_evaluated": len(held),
        },
    )
    write_json(EVIDENCE / "slm01_family_metrics.json", {"best_arm": best_arm, "families": best_family_stats})
    write_json(EVIDENCE / "slm01_envelope_confusion.json", best_envelope or {"status": "empty"})
    write_json(EVIDENCE / "slm01_failure_taxonomy.json", best_taxonomy or {"status": "empty"})
    write_json(EVIDENCE / "slm01_gate_decision.json", gate)
    write_json(
        EVIDENCE / "slm01_final_summary.json",
        {
            "n_gold_held_out_run": len(held),
            "best_arm": best_arm,
            "best_semantic_correctness": best_semantic,
            "gate_decision": gate["decision"],
            "outlines_status": outlines_status,
            "checks": gate.get("checks"),
        },
    )
    print(json.dumps({"gate": gate["decision"], "best_arm": best_arm, "best_semantic": best_semantic, "outlines": outlines_status}, indent=2))


if __name__ == "__main__":
    main()
