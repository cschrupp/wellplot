#!/usr/bin/env python3
"""Qwen3-1.7B Stage-1 runners (Q1/Q2/Q3).

Requires optional extra: pip install -e ".[eval]"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from runners.common import SYSTEM_PROMPT, assemble_user_payload, few_shot_messages, schema_hash

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "Qwen/Qwen3-1.7B"


def run_qwen(
    *,
    arm: str,
    utterance: str,
    workspace: dict[str, Any],
    d0: dict[str, Any],
    exemplars: list[dict[str, Any]] | None = None,
    constrained: bool = False,
) -> dict[str, Any]:
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:  # pragma: no cover
        return {
            "status": "runner_unavailable",
            "detail": f"transformers/torch not installed: {exc}",
            "arm": arm,
            "model_id": MODEL_ID,
        }

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto" if torch.cuda.is_available() else None,
    )

    if arm == "Q1":
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": assemble_user_payload(utterance, workspace, d0)},
        ]
    else:
        messages = few_shot_messages(exemplars or [])
        messages.append(
            {
                "role": "user",
                "content": assemble_user_payload(utterance, workspace, d0),
            }
        )

    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )

    if constrained and arm == "Q3":
        try:
            import outlines
            from well_ir.envelopes import WellIrResult

            runnable = outlines.generate.json(model, WellIrResult, tokenizer=tokenizer)
            result = runnable(prompt)
            text = result if isinstance(result, str) else json.dumps(result)
            return {
                "arm": arm,
                "model_id": MODEL_ID,
                "constrained": True,
                "schema_sha256": schema_hash(),
                "raw_text": text,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "arm": arm,
                "model_id": MODEL_ID,
                "constrained": False,
                "constrained_status": "DEFERRED_WITH_EVIDENCE",
                "detail": str(exc),
                "schema_sha256": schema_hash(),
            }

    inputs = tokenizer(prompt, return_tensors="pt")
    if torch.cuda.is_available():
        inputs = {k: v.cuda() for k, v in inputs.items()}
    out = model.generate(**inputs, max_new_tokens=512, do_sample=False)
    text = tokenizer.decode(out[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True)
    return {
        "arm": arm,
        "model_id": MODEL_ID,
        "constrained": False,
        "schema_sha256": schema_hash(),
        "raw_text": text,
        "enable_thinking": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=["Q1", "Q2", "Q3"], required=True)
    parser.add_argument("--case-json", type=Path, required=True)
    args = parser.parse_args()
    case = json.loads(args.case_json.read_text(encoding="utf-8"))
    result = run_qwen(
        arm=args.arm,
        utterance=case["utterance"],
        workspace=case["workspace"],
        d0=case["d0"],
        exemplars=case.get("exemplars"),
        constrained=args.arm == "Q3",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
