# WELLPLOT-NLP-SLM-03 Authorization

## Purpose

QLoRA fine-tune of `Qwen/Qwen3-1.7B` on the D5-grounded SLM-03 freeze (trainable support levels only), then Q1 sealed held-out retest with dual scoring.

## Inputs (frozen)

- Gold / splits / schema: see `docs/experiments/nlp-slm-03-freeze.md` and `benchmark/FREEZE.md`
- Train: `artifacts/exports/dev_sft.jsonl` (trainable filter applied)
- Val: `artifacts/exports/val_sft.jsonl`
- Base: local Qwen3-1.7B ModelScope snapshot

## Method

- Unsloth QLoRA 4-bit; r=16, α=32, dropout 0.05
- 3 epochs, lr 2e-4, max-seq 2048, seed 20251013
- Prompt: 1.2-candidate SYSTEM_PROMPT + single-turn payload; `enable_thinking: false`
- No few-shot (Q1 only); no held-out training

## Eval

- Q1 on sealed held-out
- (a) D5-executable floor: `d5_current` + `d5_context_lowerable` + `envelope_only`
- (b) Full held-out breadth (informational for authoring/resolver rows)
- Evidence: `benchmark/evidence/slm03_*`

## Outputs

- Adapter: `artifacts/adapters/slm03_qwenv17_qlora/`
- Train script: `scripts/train_slm03_unsloth.py`
- Eval: `scripts/run_slm03_heldout.py`
- Evidence: `benchmark/evidence/slm03_*`

## Result (first run)

| Scope | Metric | Value |
|---|---|---|
| D5-executable floor (n=26) | Semantic (executable) | **60%** |
| Full held-out (n=50) | Overall correct | 30% |
| Future-ops probe (n=24) | Overall correct | 25% |

Floor families: composition 3/3; display 2/4; fills 3/7; track_creation 1/2; **ambiguity_unsupported 0/10**.

Gate: **IR-REWORK** (`family_breadth` fail; `semantic_floor_50` pass). Same failure mode as SLM-02 (false `ok` / miss on ambiguity).
