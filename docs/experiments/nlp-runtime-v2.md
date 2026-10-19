# WellPlot NLP Runtime V2

**Status:** Active experiment track — **Amendment R1** (3-arm encoder bake-off)  
**Compiler frozen reference:** SLM-03 / Qwen3-1.7B (immutable comparison artifacts)  
**IR target:** WELL-IR 1.2-candidate  
**D5 baseline:** `d5/single-engine-convergence` @ `560ec48d2b2809ed2feb55467da15195f527ec44`

## Amendment R1

MB-03 is a **three-arm bake-off**: RoBERTa-base / ModernBERT-base / UltraBERT-150M.  
MB-03 remains **hard-blocked** until MB-01 and MB-02 are independently accepted.  
MB-04 selects exactly one encoder; MB-05 integrates that encoder with unchanged SLM-03.  
T5 remains downstream. UltraBERT requires pinned revision + custom-code review before load.

Where Appendix A still says “ModernBERT only,” **R1 Codex plan wins**.

## Documents

| Doc | Role |
|---|---|
| [nlp-runtime-v2-codex-execution-plan.md](nlp-runtime-v2-codex-execution-plan.md) | **Authoritative Codex slice order (R1)** |
| [nlp-runtime-v2-architecture.md](nlp-runtime-v2-architecture.md) | Long-range architecture (Appendix A) |
| [nlp-slm-02-vs-03-analysis-report.md](nlp-slm-02-vs-03-analysis-report.md) | Frozen SLM-02/03 analysis |
| [nlp-slm-03-freeze.md](nlp-slm-03-freeze.md) | SLM-03 corpus freeze |

## Experiment roots

| Path | Role |
|---|---|
| `experiments/nlp_slm_01/` | Frozen SLM-01…03 evidence + SLM-03 adapter |
| `experiments/nlp_gate_modernbert/` | Encoder-gate experiment (MB-00+; all three arms) |

## Current authorized slice

**MB-00 complete — awaiting independent acceptance.**  
Do **not** start MB-01 / MB-03 train / T5 / LangGraph / SLM-04 without a new authority.
