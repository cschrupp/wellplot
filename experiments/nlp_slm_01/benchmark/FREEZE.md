# SLM-03 freeze boundary (D5-grounded 300)

After this freeze, model results must not change WELL-IR semantics or held-out labels
without an explicit new freeze revision.

## Active freeze (`d5-grounded-300-r1`)

- Branch baseline: `d5/single-engine-convergence` @ `560ec48d2b2809ed2feb55467da15195f527ec44`
- WELL-IR: `1.2-candidate`
- Schema: `benchmark/schema/well_ir_1_2_candidate.schema.json`
- Gold: `benchmark/gold/cases.jsonl` (300 unique `(fixture, gold)` targets)
- Splits: `benchmark/splits/{development,validation,held_out}.json` (stratified ~70/15/15 by family + support_level; seed `20251013`)
- D5 fixtures: 16 manifests under `benchmark/fixtures/d5_*.json` (`fixture_format: d5_semantic_manifest_r1`)
- Legacy `d0_*` fixtures retained for the audited original 152

### Trainable support levels (SFT export filter)

Included: `d5_current`, `d5_context_lowerable`, `envelope_only`  
Excluded from SFT (eval-only): `authoring_supported`, `resolver_extension`

Export: `scaffold/qlora/export_training_data.py` → `artifacts/exports/dev_sft.jsonl`, `val_sft.jsonl`

### Parked / archived

- SLM-01 WELL-IR 1.0 gold/splits/schema: `benchmark/archive/slm01_well_ir_1_0/`
- CM/TW/D4 mapped candidates: `artifacts/exports/cm_tw_d4_mapped_candidates.jsonl` (parked; not merged)

Held-out membership is sealed. No Unsloth train until SLM-03 training is explicitly authorized.

See also: `docs/experiments/nlp-slm-03-freeze.md` and `artifacts/exports/slm03_freeze_summary.json`.
