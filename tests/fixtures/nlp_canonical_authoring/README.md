# A01 Golden Fixture Set

This provider-free fixture set freezes synthetic authoring behavior before
planner or worker contract changes. It contains no LAS/DLIS payload bytes and
does not use C01, C02, D4/D5 gold, or private scientific assets.

`a01_golden_contract.json` separates:

- `model_contract_gold`: request-local semantic operations or an expected
  bounded reject/unresolved outcome;
- `host_crud_gold`: expected host-resolved target and CRUD effect;
- `expected_model_state`: selected final-state projections and preservation
  requirements, where applicable;
- `visual_evidence`: explicitly not generated and never grading authority.

The synthetic FORGE documents are validated with the existing
`AuthoringDocumentSpec`. Source inventories describe channel facts and explicit
inspection states only; source paths are synthetic labels, not filesystem
locations.

This fixture set was prepared under accepted A00 architecture checkpoint
`c6ec436619418b3831a1c9decd7d3c15efebb74c`, on implementation baseline
`a17ee8672bde988e823da6ad199d97aa44270b18`. A01 changed no production source,
made no provider/model/endpoint calls, and did not access scientific D5/C02
fixtures or evidence.

## Frozen File Identity

```text
file: a01_golden_contract.json
sha256: 6f8486ed825d252ffbc3882dc96220824376405b0780c8b98f8e919258bdfa7a
```

Recompute with:

```bash
sha256sum tests/fixtures/nlp_canonical_authoring/a01_golden_contract.json
```

The hash covers the fixture file only, not this README or its tests.
