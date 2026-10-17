# WELLPLOT-NLP-SLM-03 Freeze (no train yet)

## Purpose

Replace the SLM-01 WELL-IR 1.0 gold with the D5-grounded 300-case corpus and freeze
splits/schema/fixtures for a future Qwen3-1.7B QLoRA retrain (authorized separately).

## Inputs

- ZIP: `experiments/nlp_slm_01/artifacts/exports/wellplot_slm01_d5_grounded_300_r1.zip`
- D5 baseline: `d5/single-engine-convergence` @ `560ec48d2b2809ed2feb55467da15195f527ec44`
- Installer: `experiments/nlp_slm_01/scripts/freeze_slm03_d5_corpus.py`

## Freeze decisions

| Decision | Choice |
|---|---|
| Gold | Replace `cases.jsonl` with 300 D5-grounded rows |
| IR | Sole `1.2-candidate` schema |
| SFT include | `d5_current` + `d5_context_lowerable` + `envelope_only` |
| SFT exclude | `authoring_supported` + `resolver_extension` |
| Splits | Stratified ~70/15/15 by family + support_level; held-out keeps all levels |
| Fixtures | Keep `d0_*`; install 16 `d5_*` manifests as authored |
| Train | Freeze-only; no Unsloth until explicit SLM-03 authorize |
| Old 1.0 | Archived under `benchmark/archive/slm01_well_ir_1_0/` |
| CM candidates | Parked; not merged |

## Status mix (300)

- ok 233 · ambiguous 10 · unsupported 43 · invalid 14
- Support: d5_current 77 · d5_context_lowerable 20 · authoring_supported 106 · resolver_extension 30 · envelope_only 67
- Trainable pool: 164 cases

## Outputs

- `benchmark/gold/cases.jsonl` + `corpus_meta.json`
- `benchmark/schema/well_ir_1_2_candidate.schema.json`
- `benchmark/fixtures/d5_*.json` (16)
- `benchmark/splits/*.json`
- `artifacts/exports/dev_sft.jsonl` / `val_sft.jsonl` (trainable filter applied)
- `artifacts/exports/slm03_freeze_summary.json`
- `benchmark/FREEZE.md`

## Next (not done)

Authorize SLM-03 Unsloth QLoRA on the new `dev_sft` / `val_sft`, then sealed held-out retest with dual reporting: D5-executable floor vs full-support-level breadth.
