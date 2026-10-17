#!/usr/bin/env python3
"""HF Transformers CUDA runner with GPU→CPU offload (SLM-01B arms A/B)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runners.common import SYSTEM_PROMPT, assemble_user_payload, few_shot_messages, schema_hash

ROOT = Path(__file__).resolve().parents[1]


class HfOffloadRunner:
    def __init__(
        self,
        model_path: str | Path,
        *,
        model_id: str,
        gpu_memory_gib: float = 4.0,
        cpu_memory_gib: float = 28.0,
        trust_remote_code: bool = True,
    ) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.model_id = model_id
        self.model_path = str(model_path)
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA required for SLM-01B HF arms (got CPU-only torch)")

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path,
            trust_remote_code=trust_remote_code,
            local_files_only=True,
        )
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        self.dtype_name = str(dtype).replace("torch.", "")
        max_memory = {0: f"{gpu_memory_gib}GiB", "cpu": f"{cpu_memory_gib}GiB"}
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            dtype=dtype,
            device_map="auto",
            max_memory=max_memory,
            trust_remote_code=trust_remote_code,
            local_files_only=True,
            low_cpu_mem_usage=True,
        )
        self.model.eval()
        # JSON-safe keys (int GPU index is fine for HF, not for sort_keys dumps)
        self.offload = {
            "device_map": "auto",
            "max_memory": {str(k): v for k, v in max_memory.items()},
            "dtype": self.dtype_name,
        }

    def _apply_chat(self, messages: list[dict[str, str]]) -> str:
        kwargs: dict[str, Any] = {
            "tokenize": False,
            "add_generation_prompt": True,
        }
        # SmolLM3 / Qwen-style templates may accept enable_thinking
        try:
            return self.tokenizer.apply_chat_template(
                messages, enable_thinking=False, **kwargs
            )
        except TypeError:
            return self.tokenizer.apply_chat_template(messages, **kwargs)

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
        prompt = self._apply_chat(messages)
        inputs = self.tokenizer(prompt, return_tensors="pt")
        # device_map models: move inputs to first parameter device when possible
        try:
            first = next(self.model.parameters()).device
            inputs = {k: v.to(first) for k, v in inputs.items()}
        except StopIteration:
            pass
        with self.torch.inference_mode():
            out = self.model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        text = self.tokenizer.decode(
            out[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True
        )
        return {
            "arm": arm,
            "model_id": self.model_id,
            "model_path": self.model_path,
            "backend": "hf_cuda_offload",
            "offload": self.offload,
            "schema_sha256": schema_hash(),
            "enable_thinking": False,
            "constrained": False,
            "raw_text": text,
        }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--arm", choices=["Q1", "Q2"], default="Q2")
    parser.add_argument("--case-json", type=Path, required=True)
    args = parser.parse_args()
    case = json.loads(args.case_json.read_text(encoding="utf-8"))
    runner = HfOffloadRunner(args.model_path, model_id=args.model_id)
    result = runner.predict(
        arm=args.arm,
        utterance=case["utterance"],
        workspace=case["workspace"],
        d0=case["d0"],
        exemplars=case.get("exemplars") or [],
    )
    print(json.dumps(result, indent=2)[:2000])


if __name__ == "__main__":
    main()
