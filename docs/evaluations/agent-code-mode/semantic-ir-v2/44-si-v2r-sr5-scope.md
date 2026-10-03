# SI-V2R-SR5 Historical Contract Applicability Review

## Authority

- Baseline: `eb9736ddda9feb9e5e601760822da7e0e3933286`
- Raw evidence: `/tmp/si-v2r-live.jsonl`
- Raw evidence SHA-256: `9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08`
- Population: 48 attempts, 24 cases, two attempts per case
- Provider inference calls: `0`
- Endpoint calls: `0`
- Worker/program calls: `0`
- Production changes: `0`
- Historical score calculations: `0`

SR5 is a provider-free applicability review. It applies the accepted SR4
ownership and representation contract to authenticated historical LQ0 rows
without changing the LQ0, SR2, or SR3 results.

## Question

For each historical semantic dimension, SR5 records whether the frozen SR4
contract applies, leaves the decision to the model, blocks system credit on a
representation conflict, blocks it on an unresolved contract, fails closed, or
cannot evaluate the row because structural output was unavailable.

Coverage, correctness, and score remain separate:

```text
coverage       -> was the SR4 rule classifiable here?
correctness    -> what the frozen historical evidence says happened
score          -> unchanged historical LQ0/SR2 facts
```

`CONTRACT_APPLICABLE` never means “pass.” `MODEL_OWNED` never creates a new
failure or pass. Blocked and unavailable states are retained as evidence, not
repaired.

## Frozen upstream facts

The checked-in SR5 artifacts retain the upstream records unchanged:

- LQ0 decision: `SI_V2R_PROVIDER_BOUNDARY_REJECTED`;
- SR2 decision: `SI_V2R_SR2_REPORT_PRESENCE_RESOLVED`;
- SR3 decision: `SI_V2R_SR3_ROOT_MECHANISMS_RESOLVED`;
- SR4 decision: `SI_V2R_SR4_OWNERSHIP_CONTRACT_PARTIAL`.

Historical scores are not copied into the applicability rows as new score
fields and are not recalculated by this slice.

## Hard stop

SR5 does not run a provider, alter prompts or schemas, modify CM58/V2R, create
counterfactual semantic objects, or start a historical regrade. A later
regrade would require separate authorization and must preserve every blocked,
model-owned, and not-evaluable state identified here.

The terminal decision is `SI_V2R_SR5_APPLICABILITY_MAP_COMPLETE` when every
row and relevant dimension receives a defined SR4 applicability state. That
decision is compatible with `RE_GRADE_PARTIALLY_READY`; readiness is a process
decision, not a score.
