# WELLPLOT-NLP-SLM-02 Authorization

## Purpose

QLoRA fine-tune of `Qwen/Qwen3-1.7B` on frozen SLM-01 development SFT export, then sealed held-out retest with the same WELL-IR gate as SLM-01.

## Inputs (frozen from SLM-01)

- Gold + splits + WELL-IR (unchanged held-out)
- Train: `experiments/nlp_slm_01/artifacts/exports/dev_sft.jsonl` (284 rows)
- Val select: `artifacts/exports/val_sft.jsonl` (95 rows)
- Base weights: local Qwen3-1.7B snapshot under experiment ModelScope cache

## Method

- Framework: Unsloth QLoRA 4-bit
- Prompt: same `SYSTEM_PROMPT` + single-turn user payload as SLM-01 Q1 (no few-shot in training rows)
- `enable_thinking: false`
- No held-out training; no IR rewrite

## Outputs

- Adapter under `experiments/nlp_slm_01/artifacts/adapters/slm02_qwenv17_qlora/` (gitignored pattern)
- Evidence: `benchmark/evidence/slm02_*`

## Gate

Same thresholds as SLM-01 on sealed held-out. Compare to untuned Qwen Q2 baseline (~42.1%).

## Result (first run)

| Arm | Semantic (executable) | Notes |
|-----|----------------------|-------|
| **Q1 (tuned)** | **82.5%** | 47/70 overall correct; Δ +40.4 pts vs untuned Q2 |
| Q2 (tuned) | 0% | Broken: few-shot prompts exceed 4096 ctx (truncation) |
| Untuned Qwen Q2 (ref) | 42.1% | SLM-01 |

Family rates (Q1): placement/fills/intervals/relational strong (≥0.92); composition 0.38; **ambiguity_unsupported 0/13** (false `ok` on ambiguous) → `family_breadth` fail.

**Gate decision file:** `IR-REWORK` (breadth), not `MODEL-SIZE-FAIL`. Semantic floor **passed**.

Adapter: `artifacts/adapters/slm02_qwenv17_qlora/` (Unsloth QLoRA 4-bit, 284 train / 95 val, 3 epochs).
