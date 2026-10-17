# WELLPLOT-NLP-SLM-01 Authorization

## Purpose

Prove that a compact WELL-IR semantic compiler boundary is the right abstraction for WellPlot NLP, and whether untuned `Qwen/Qwen3-1.7B` is a rational QLoRA candidate (SLM-02).

## Location

- Branch: `exp/wellplot-nlp-slm-01`
- Code: `experiments/nlp_slm_01/`
- Historical seed SHA: `d77649765dee81ebd0b8f460ac28515b244f70da`

## Non-goals

No production model replacement, no mandatory adapter, no full fine-tune, no prod GPU requirement, no deterministic engine changes for the model, no LangGraph orchestration, no large synthetic corpus before freeze, no held-out tuning, no promotion into `src/wellplot/` during SLM-01.

## Architecture

`NL + workspace → WELL-IR v1 → deterministic lowerer → DocumentState / LogDocument`

WELL-IR is a domain-semantic intent/ops delta, not a LogDocument mirror.

## Gate outcomes

`PASS` | `IR-REWORK` | `MODEL-SIZE-FAIL` | `PENDING_BASELINES`

See `experiments/nlp_slm_01/benchmark/evidence/slm01_gate_decision.json`.

## Isolation invariant

Deleting `experiments/nlp_slm_01/` must leave the WellPlot package behavior unchanged. Product code must never import experiment modules.
