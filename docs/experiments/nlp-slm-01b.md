# WELLPLOT-NLP-SLM-01B Authorization

## Purpose

Follow-on to SLM-01 after `MODEL-SIZE-FAIL` on untuned `Qwen/Qwen3-1.7B`.
Test whether ~3B bases clear the same evidence gate on frozen WELL-IR / gold / splits.

## Location

- Branch: `exp/wellplot-nlp-slm-01` (same lineage)
- Code: `experiments/nlp_slm_01/` (reuse IR, gold, evaluator, prompts)
- Evidence prefix: `slm01b_*`
- Parent: [nlp-slm-01.md](nlp-slm-01.md)

## Non-goals

Same as SLM-01. No IR rewrite. No SLM-02 QLoRA until a 01B arm passes.

## Arms (4)

| ID | Weights | Runtime |
|----|---------|---------|
| C | `unsloth/SmolLM3-3B-GGUF` `SmolLM3-3B-UD-Q4_K_XL.gguf` | llama.cpp CUDA |
| D | `unsloth/Phi-4-mini-instruct-GGUF` `Phi-4-mini-instruct-Q4_K_M.gguf` | llama.cpp CUDA |
| A | `unsloth/SmolLM3-3B` BF16 safetensors | HF Transformers CUDA + CPU offload |
| B | `unsloth/Phi-4-mini-instruct` BF16 safetensors | HF Transformers CUDA + CPU offload |

Order: smoke all four, then full sealed held-out **C → D → A → B**.

## Protocol

- Reuse SLM-01 system prompt, few-shot, Q1/Q2 decoding (temp 0, max 512).
- Q3 / Outlines deferred.
- Gate thresholds unchanged; **best arm** is the decision signal (do not average stacks).
- Provenance must record backend, dtype/quant, offload, and weight snapshot paths.

## Runtime notes (WSL RTX 3060 6 GB)

- GGUF arms use `~/.unsloth/llama.cpp/build/bin/llama-server` with `-ngl 99 -c 8192 --jinja`.
- HF BF16 arms need CUDA torch; experiment `.venv` wheel installs have been flaky — use Unsloth Studio Python (`~/.unsloth/studio/unsloth_studio/bin/python`, torch+cu130) when needed.
- Phi-4 HF: `trust_remote_code=False` (bundled `modeling_phi3.py` breaks on Transformers 5.x).
- Smoke (n=8, Q2): C/D/A ≈ 50% semantic; B BF16 offload ≈ 0% and ~40 min/8 cases.

## Result (sealed held-out n=70)

| Arm | Best prompt | Semantic (executable) | Notes |
|-----|-------------|----------------------|-------|
| A SmolLM3 BF16 | Q2 | **28.1%** | Best 01B arm |
| C SmolLM3 GGUF Q4 | Q2 | 21.1% | |
| D Phi-4 GGUF Q4 | Q2 | 21.1% | |
| B Phi-4 BF16 | Q1 | 15.8% | Q2 aborted (RAM offload too slow) |
| *ref* Qwen3-1.7B (SLM-01) | Q2 | **42.1%** | Still stronger than all ~3B arms |

**Gate:** `MODEL-SIZE-FAIL` (best arm A; below 50% floor; family breadth fail).

**Implication:** Untuned ~3B does not beat Qwen3-1.7B on this task; local 3B fine-tune on RTX 3060 6 GB is impractical. Any SLM-02 QLoRA should target **Qwen3-1.7B** on a host with real VRAM (e.g. Unsloth), not 3B on this laptop.

## Gate outcomes

`PASS` | `IR-REWORK` | `MODEL-SIZE-FAIL` | `PENDING_BASELINES`

See `experiments/nlp_slm_01/benchmark/evidence/slm01b_gate_decision.json` and `slm01b_final_summary.json`.
