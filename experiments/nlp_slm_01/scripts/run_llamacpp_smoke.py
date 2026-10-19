#!/usr/bin/env python3
"""CPU llama.cpp / GGUF deployment smoke (secondary; not SLM-02 gate)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from runners.common import SYSTEM_PROMPT, assemble_user_payload
from well_ir.canonicalize import parse_well_ir

ROOT = Path(__file__).resolve().parents[1]
GGUF = ROOT / "artifacts" / "models" / "Qwen3-1.7B-GGUF" / "Qwen3-1.7B-Q4_K_M.gguf"
GOLD = ROOT / "benchmark" / "gold" / "cases.jsonl"
FIXTURES = ROOT / "benchmark" / "fixtures"
OUT = ROOT / "benchmark" / "evidence" / "slm01_llamacpp_smoke.json"


def main() -> None:
    if not GGUF.exists() or GGUF.stat().st_size < 500_000_000:
        raise SystemExit(f"GGUF missing or incomplete: {GGUF}")

    from llama_cpp import Llama

    llm = Llama(
        model_path=str(GGUF),
        n_ctx=4096,
        n_threads=8,
        verbose=False,
    )

    cases = []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        if case["semantic_family"] in {
            "curve_placement",
            "composition",
            "relational_targeting",
            "fills",
            "ambiguity_unsupported",
        }:
            cases.append(case)
        if len(cases) >= 15:
            break

    rows = []
    t0 = time.time()
    for case in cases:
        fix = json.loads((FIXTURES / f"{case['fixture']}.json").read_text(encoding="utf-8"))
        utt = case["utterances"][0]["text"]
        user = assemble_user_payload(utt, fix["workspace"], fix["d0"])
        prompt = (
            f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        started = time.time()
        out = llm(
            prompt,
            max_tokens=512,
            temperature=0.0,
            stop=["<|im_end|>", "<|endoftext|>"],
        )
        text = out["choices"][0]["text"]
        elapsed = time.time() - started
        schema_ok = False
        try:
            start = text.find("{")
            end = text.rfind("}")
            payload = json.loads(text[start : end + 1]) if start >= 0 and end > start else None
            if payload is not None:
                parse_well_ir(payload)
                schema_ok = True
        except Exception:  # noqa: BLE001
            schema_ok = False
        rows.append(
            {
                "case_id": case["case_id"],
                "family": case["semantic_family"],
                "schema_ok": schema_ok,
                "latency_s": elapsed,
                "raw_preview": text[:400],
            }
        )
        print(f"{case['case_id']} schema_ok={schema_ok} {elapsed:.1f}s", flush=True)

    report = {
        "role": "deployment_smoke_only",
        "affects_slm02_gate": False,
        "gguf": str(GGUF),
        "gguf_bytes": GGUF.stat().st_size,
        "n_cases": len(rows),
        "schema_ok_rate": sum(1 for r in rows if r["schema_ok"]) / len(rows) if rows else 0.0,
        "mean_latency_s": sum(r["latency_s"] for r in rows) / len(rows) if rows else None,
        "wall_s": time.time() - t0,
        "rows": rows,
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
