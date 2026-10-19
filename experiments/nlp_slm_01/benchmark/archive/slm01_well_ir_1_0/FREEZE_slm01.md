# SLM-01 freeze boundary (M3)

After this freeze, model results must not change WELL-IR semantics or held-out labels.

Frozen artifacts (see `evidence/slm01_provenance.json` for hashes):

- WELL-IR v1 Pydantic models under `well_ir/`
- JSON Schema at `benchmark/schema/well_ir_v1.json`
- Gold corpus `benchmark/gold/cases.jsonl`
- Splits under `benchmark/splits/`
- CommonSemanticFacts schema
- Failure taxonomy labels in `benchmark/taxonomy.py`
- Lowering contracts under `lowerer/contracts/`

Held-out membership is sealed. Prompt/exemplar engineering uses development only; validation for config choice; held-out for the single final protocol run.
