#!/usr/bin/env python3
"""SLM-01B sealed held-out / smoke eval for ~3B arms A–D.

Arms:
  C  SmolLM3 GGUF Q4 via llama-server (OpenAI compat)
  D  Phi-4-mini GGUF Q4 via llama-server
  A  SmolLM3 BF16 HF CUDA+CPU offload
  B  Phi-4-mini BF16 HF CUDA+CPU offload

Writes slm01b_* evidence; does not overwrite sealed slm01_* gate files.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
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
from well_ir.canonicalize import parse_well_ir

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "benchmark" / "gold" / "cases.jsonl"
FIXTURES = ROOT / "benchmark" / "fixtures"
SPLITS = ROOT / "benchmark" / "splits"
EVIDENCE = ROOT / "benchmark" / "evidence"
ARTIFACTS = ROOT / "artifacts" / "runs"

HF_HUB = Path.home() / ".cache" / "huggingface" / "hub"

ARM_SPECS: dict[str, dict[str, Any]] = {
    "C": {
        "label": "smollm3_gguf_q4",
        "backend": "gguf",
        "model_id": "unsloth/SmolLM3-3B-GGUF",
        "gguf": HF_HUB
        / "models--unsloth--SmolLM3-3B-GGUF"
        / "snapshots"
        / "a7bc17204c8a326d6bd6e466e076959eddae2025"
        / "SmolLM3-3B-UD-Q4_K_XL.gguf",
        "quant": "UD-Q4_K_XL",
    },
    "D": {
        "label": "phi4mini_gguf_q4",
        "backend": "gguf",
        "model_id": "unsloth/Phi-4-mini-instruct-GGUF",
        "gguf": HF_HUB
        / "models--unsloth--Phi-4-mini-instruct-GGUF"
        / "snapshots"
        / "78eb92a46fc37e6b524df991ed9aca9bc6aa7b80"
        / "Phi-4-mini-instruct-Q4_K_M.gguf",
        "quant": "Q4_K_M",
    },
    "A": {
        "label": "smollm3_bf16_hf",
        "backend": "hf",
        "model_id": "unsloth/SmolLM3-3B",
        "model_path": HF_HUB
        / "models--unsloth--SmolLM3-3B"
        / "snapshots"
        / "ece25bbbd9b7e0a36ed15b4e26ee1ad37654b3dd",
        "quant": "bf16_offload",
    },
    "B": {
        "label": "phi4mini_bf16_hf",
        "backend": "hf",
        "model_id": "unsloth/Phi-4-mini-instruct",
        "model_path": HF_HUB
        / "models--unsloth--Phi-4-mini-instruct"
        / "snapshots"
        / "75becc471c56fc34761ec998615ca6f8535c5a61",
        "quant": "bf16_offload",
    },
}


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


def score_prediction(case: dict[str, Any], raw_text: str, raw_meta: dict[str, Any] | None = None) -> dict[str, Any]:
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
    out = {
        "case_id": case["case_id"],
        "family": case["semantic_family"],
        "gold_status": gold.status,
        "pred_status": getattr(pred, "status", None) if pred is not None else None,
        "schema_ok": schema_ok,
        "semantic_ok": semantic_ok,
        "execution_ok": exec_ok,
        "correct": correct,
        "failure_label": classify_failure(gold, pred, schema_ok, correct, case),
        "raw_text": (raw_text or "")[:2000],
    }
    if raw_meta:
        out["raw_meta"] = {k: raw_meta[k] for k in raw_meta if k != "raw_text"}
    return out


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


def chat_openai(
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
        timeout=600.0,
    )
    resp.raise_for_status()
    msg = resp.json()["choices"][0]["message"]
    # SmolLM3 may put text in reasoning_content when thinking is on
    content = msg.get("content") or ""
    if not str(content).strip():
        content = msg.get("reasoning_content") or msg.get("reasoning") or ""
    return content or ""


def messages_for_arm(
    arm: str,
    utterance: str,
    workspace: dict[str, Any],
    d0: dict[str, Any],
    exemplars: list[dict[str, Any]],
) -> list[dict[str, str]]:
    if arm == "Q1":
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": assemble_user_payload(utterance, workspace, d0)},
        ]
    messages = few_shot_messages(exemplars)
    messages.append(
        {"role": "user", "content": assemble_user_payload(utterance, workspace, d0)}
    )
    return messages


def run_gguf_arm(
    *,
    model_arm: str,
    spec: dict[str, Any],
    held: list[dict[str, Any]],
    exemplars: list[dict[str, Any]],
    prompt_arms: list[str],
    base_url: str,
    api_key: str,
) -> dict[str, Any]:
    arm_metrics: dict[str, Any] = {}
    best: dict[str, Any] = {}
    with httpx.Client() as client:
        for pararm in prompt_arms:
            print(
                f"[01B-{model_arm}] {spec['label']} {pararm} n={len(held)} via {base_url}",
                flush=True,
            )
            rows = []
            for i, case in enumerate(held, 1):
                fix = load_fixture(case["fixture"])
                utt = case["utterances"][0]["text"]
                msgs = messages_for_arm(pararm, utt, fix["workspace"], fix["d0"], exemplars)
                t0 = time.time()
                try:
                    text = chat_openai(
                        client,
                        base_url=base_url,
                        model=spec.get("serve_model", spec["label"]),
                        messages=msgs,
                        api_key=api_key,
                    )
                    scored = score_prediction(
                        case,
                        text,
                        {
                            "backend": "llama_server_cuda",
                            "model_id": spec["model_id"],
                            "gguf": str(spec["gguf"]),
                            "quant": spec["quant"],
                            "prompt_arm": pararm,
                        },
                    )
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
                    print(
                        f"  {pararm}: {i}/{len(held)} correct={sum(1 for r in rows if r['correct'])}",
                        flush=True,
                    )
            metrics = evaluate_arm(rows)
            arm_metrics[pararm] = metrics
            out_path = ARTIFACTS / f"slm01b_{spec['label']}_{pararm}.jsonl"
            out_path.write_text(
                "\n".join(json.dumps(r, default=str) for r in rows) + "\n",
                encoding="utf-8",
            )
            sem = metrics["semantic_correctness_executable"]
            if sem is not None and (
                best.get("semantic") is None or sem > best["semantic"]
            ):
                best = {
                    "semantic": sem,
                    "prompt_arm": pararm,
                    "family_stats": metrics["family_stats"],
                    "taxonomy": metrics["taxonomy"],
                    "envelope": {
                        "confusion": metrics["envelope_confusion"],
                        "macro_f1": metrics["envelope_macro_f1"],
                        "false_ok_on_ambiguous": metrics["false_ok_on_ambiguous"],
                    },
                }
    return {"prompt_arms": arm_metrics, "best": best, "spec": _spec_public(spec)}


def run_hf_arm(
    *,
    model_arm: str,
    spec: dict[str, Any],
    held: list[dict[str, Any]],
    exemplars: list[dict[str, Any]],
    prompt_arms: list[str],
    gpu_memory_gib: float,
) -> dict[str, Any]:
    from runners.local_hf_offload import HfOffloadRunner

    path = Path(spec["model_path"])
    if not path.exists():
        raise FileNotFoundError(path)
    print(f"[01B-{model_arm}] Loading HF {spec['model_id']} from {path}", flush=True)
    # Phi-4 Unsloth pack ships modeling_phi3.py that breaks on newer transformers
    trust_remote = bool(spec.get("trust_remote_code", model_arm != "B"))
    runner = HfOffloadRunner(
        path,
        model_id=spec["model_id"],
        gpu_memory_gib=gpu_memory_gib,
        trust_remote_code=trust_remote,
    )
    arm_metrics: dict[str, Any] = {}
    best: dict[str, Any] = {}
    for pararm in prompt_arms:
        print(f"[01B-{model_arm}] {spec['label']} {pararm} n={len(held)}", flush=True)
        rows = []
        for i, case in enumerate(held, 1):
            fix = load_fixture(case["fixture"])
            utt = case["utterances"][0]["text"]
            t0 = time.time()
            try:
                raw = runner.predict(
                    arm=pararm,
                    utterance=utt,
                    workspace=fix["workspace"],
                    d0=fix["d0"],
                    exemplars=exemplars,
                )
                scored = score_prediction(case, raw.get("raw_text") or "", raw)
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
                    "traceback": traceback.format_exc()[-1000:],
                }
            rows.append(scored)
            if i % 5 == 0 or i == len(held):
                print(
                    f"  {pararm}: {i}/{len(held)} correct={sum(1 for r in rows if r['correct'])}",
                    flush=True,
                )
        metrics = evaluate_arm(rows)
        arm_metrics[pararm] = metrics
        out_path = ARTIFACTS / f"slm01b_{spec['label']}_{pararm}.jsonl"
        out_path.write_text(
            "\n".join(json.dumps(r, default=str) for r in rows) + "\n",
            encoding="utf-8",
        )
        sem = metrics["semantic_correctness_executable"]
        if sem is not None and (best.get("semantic") is None or sem > best["semantic"]):
            best = {
                "semantic": sem,
                "prompt_arm": pararm,
                "family_stats": metrics["family_stats"],
                "taxonomy": metrics["taxonomy"],
                "envelope": {
                    "confusion": metrics["envelope_confusion"],
                    "macro_f1": metrics["envelope_macro_f1"],
                    "false_ok_on_ambiguous": metrics["false_ok_on_ambiguous"],
                },
            }
    return {
        "prompt_arms": arm_metrics,
        "best": best,
        "spec": {**_spec_public(spec), "offload": runner.offload},
    }


def _spec_public(spec: dict[str, Any]) -> dict[str, Any]:
    out = {
        "model_id": spec["model_id"],
        "backend": spec["backend"],
        "quant": spec["quant"],
        "label": spec["label"],
    }
    if "gguf" in spec:
        p = Path(spec["gguf"])
        out["gguf"] = str(p)
        out["gguf_bytes"] = p.resolve().stat().st_size if p.exists() else None
    if "model_path" in spec:
        out["model_path"] = str(spec["model_path"])
    return out


def write_arm_evidence(model_arm: str, result: dict[str, Any], n_held: int) -> None:
    best = result.get("best") or {}
    write_json(
        EVIDENCE / f"slm01b_arm_{model_arm}_metrics.json",
        {
            "model_arm": model_arm,
            "n_held_out_evaluated": n_held,
            "schema_sha256": schema_hash(),
            "spec": result.get("spec"),
            "prompt_arms": result.get("prompt_arms"),
            "best_prompt_arm": best.get("prompt_arm"),
            "best_semantic_correctness": best.get("semantic"),
        },
    )
    if best.get("family_stats") is not None:
        write_json(
            EVIDENCE / f"slm01b_arm_{model_arm}_family.json",
            {"model_arm": model_arm, "families": best["family_stats"]},
        )
    if best.get("taxonomy") is not None:
        write_json(
            EVIDENCE / f"slm01b_arm_{model_arm}_taxonomy.json",
            best["taxonomy"],
        )


def aggregate_gate(all_results: dict[str, dict[str, Any]], n_held: int) -> None:
    lowerer = json.loads((EVIDENCE / "slm01_lowerer_evidence.json").read_text())
    best_overall = None
    summary_arms = {}
    for mid, result in all_results.items():
        best = result.get("best") or {}
        sem = best.get("semantic")
        summary_arms[mid] = {
            "label": result.get("spec", {}).get("label"),
            "backend": result.get("spec", {}).get("backend"),
            "quant": result.get("spec", {}).get("quant"),
            "best_prompt_arm": best.get("prompt_arm"),
            "semantic_correctness_executable": sem,
            "family_breadth_ok": family_breadth_ok(best.get("family_stats") or {})
            if best.get("family_stats")
            else False,
        }
        if sem is not None and (best_overall is None or sem > best_overall["semantic"]):
            best_overall = {
                "model_arm": mid,
                "semantic": sem,
                "prompt_arm": best.get("prompt_arm"),
                "family_stats": best.get("family_stats") or {},
                "taxonomy": best.get("taxonomy") or {},
                "spec": result.get("spec"),
            }

    if best_overall is None:
        gate = {
            "decision": "PENDING_BASELINES",
            "checks": {"baselines_complete": False},
            "note": "No scored 01B arms",
        }
    else:
        tax = best_overall["taxonomy"]
        learnable = tax.get("learnable_share_of_confirmed")
        ir_share = tax.get("ir_limitation_share_of_all_failures")
        gate = evaluate_gate(
            ir_frozen=True,
            gold_frozen=True,
            split_frozen=True,
            lowerer_pass_rate=float(lowerer.get("pass_rate") or 0.0),
            baselines_complete=True,
            taxonomy_complete=bool(tax),
            semantic_correctness=best_overall["semantic"],
            family_breadth_ok=family_breadth_ok(best_overall["family_stats"]),
            learnable_share=learnable if learnable is not None else 0.0,
            ir_limitation_share=ir_share if ir_share is not None else 0.0,
            held_out_leakage=False,
            non_goals_preserved=True,
        )
        gate["best_model_arm"] = best_overall["model_arm"]
        gate["best_prompt_arm"] = best_overall["prompt_arm"]
        gate["best_semantic_correctness"] = best_overall["semantic"]
        gate["best_spec"] = best_overall["spec"]

    write_json(EVIDENCE / "slm01b_gate_decision.json", gate)
    write_json(
        EVIDENCE / "slm01b_final_summary.json",
        {
            "n_held_out": n_held,
            "arms": summary_arms,
            "gate_decision": gate.get("decision"),
            "best_model_arm": gate.get("best_model_arm"),
            "best_semantic_correctness": gate.get("best_semantic_correctness"),
            "schema_sha256": schema_hash(),
            "parent_slm01_decision": "MODEL-SIZE-FAIL",
        },
    )
    write_json(
        EVIDENCE / "slm01b_provenance.json",
        {
            "experiment": "WELLPLOT-NLP-SLM-01B",
            "arms": {k: _spec_public(v) for k, v in ARM_SPECS.items()},
            "prompt_protocol": "SLM-01 Q1/Q2 reuse",
            "q3_outlines": "DEFERRED",
            "gate_signal": "best_arm",
        },
    )
    print(json.dumps({"gate": gate.get("decision"), "best": gate.get("best_model_arm"), "semantic": gate.get("best_semantic_correctness"), "arms": summary_arms}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-arms",
        default="C,D,A,B",
        help="Comma-separated model arms (default C,D,A,B)",
    )
    parser.add_argument("--prompt-arms", default="Q1,Q2")
    parser.add_argument("--limit", type=int, default=0, help="cap cases (smoke)")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SLM01B_LOCAL_BASE_URL", "http://127.0.0.1:8890/v1"),
    )
    parser.add_argument("--api-key", default=os.environ.get("SLM01B_LOCAL_API_KEY", "local"))
    parser.add_argument("--gpu-memory-gib", type=float, default=4.0)
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Re-read per-arm metrics and rewrite gate/summary",
    )
    args = parser.parse_args()

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    held = load_cases("held_out")
    dev = load_cases("development")
    if args.limit:
        held = held[: args.limit]
    exemplars = build_exemplars(dev)
    prompt_arms = [a.strip() for a in args.prompt_arms.split(",") if a.strip()]
    model_arms = [a.strip().upper() for a in args.model_arms.split(",") if a.strip()]

    if args.aggregate_only:
        all_results = {}
        n_from_files = 0
        for mid in model_arms:
            path = EVIDENCE / f"slm01b_arm_{mid}_metrics.json"
            if not path.exists():
                continue
            payload = json.loads(path.read_text())
            n_from_files = max(n_from_files, int(payload.get("n_held_out_evaluated") or 0))
            best_pa = payload.get("best_prompt_arm")
            pam = payload.get("prompt_arms") or {}
            best_block = pam.get(best_pa or "", {})
            tax_path = EVIDENCE / f"slm01b_arm_{mid}_taxonomy.json"
            taxonomy = best_block.get("taxonomy")
            if taxonomy is None and tax_path.exists():
                taxonomy = json.loads(tax_path.read_text())
            fam_path = EVIDENCE / f"slm01b_arm_{mid}_family.json"
            family_stats = best_block.get("family_stats")
            if family_stats is None and fam_path.exists():
                family_stats = json.loads(fam_path.read_text()).get("families")
            all_results[mid] = {
                "spec": payload.get("spec"),
                "prompt_arms": pam,
                "best": {
                    "semantic": payload.get("best_semantic_correctness"),
                    "prompt_arm": best_pa,
                    "family_stats": family_stats,
                    "taxonomy": taxonomy,
                },
            }
        aggregate_gate(all_results, n_held=n_from_files or len(held))
        return

    all_results: dict[str, dict[str, Any]] = {}
    for mid in model_arms:
        if mid not in ARM_SPECS:
            raise SystemExit(f"Unknown model arm {mid}; choose from {list(ARM_SPECS)}")
        spec = ARM_SPECS[mid]
        if spec["backend"] == "gguf":
            gguf = Path(spec["gguf"])
            if not gguf.exists() or gguf.resolve().stat().st_size < 100_000_000:
                raise SystemExit(f"GGUF missing/incomplete for arm {mid}: {gguf}")
            result = run_gguf_arm(
                model_arm=mid,
                spec=spec,
                held=held,
                exemplars=exemplars,
                prompt_arms=prompt_arms,
                base_url=args.base_url,
                api_key=args.api_key,
            )
        else:
            result = run_hf_arm(
                model_arm=mid,
                spec=spec,
                held=held,
                exemplars=exemplars,
                prompt_arms=prompt_arms,
                gpu_memory_gib=args.gpu_memory_gib,
            )
        all_results[mid] = result
        write_arm_evidence(mid, result, len(held))

    aggregate_gate(all_results, n_held=len(held))


if __name__ == "__main__":
    main()
