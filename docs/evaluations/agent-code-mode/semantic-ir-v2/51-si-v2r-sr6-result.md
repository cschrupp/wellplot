# SI-V2R-SR6 Result

## Decision

`SI_V2R_SR6_NO_ADDITIONAL_SYSTEM_RECOVERY`

The SR5-eligible dimensions were regraded deterministically and reproduced
the accepted SR2 row statuses exactly. No additional historical system pass
was created. The result is therefore a complete bounded check with no
additional recovery, not a new model score.

## Provenance

- SR6 checkpoint: `d46b280bbe1326fa1664778c66377067beb2a557`
- SR5 checkpoint consumed: `d46b280bbe1326fa1664778c66377067beb2a557`
- Raw evidence SHA-256: `9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08`
- Regrade completeness: `PARTIALLY_REGRADABLE`
- Provider inference calls: `0`
- Endpoint calls: `0`
- Worker/program calls: `0`
- Production behavior: unchanged
- ADR-CM57: unchanged

## Preserved decisions

The original historical provider decision remains
`SI_V2R_PROVIDER_BOUNDARY_REJECTED`. LQ0 remains 28/48 and 14/24; SR2
remains 34/48 and 17/24; SR5 remains
`SI_V2R_SR5_APPLICABILITY_MAP_COMPLETE` with
`RE_GRADE_PARTIALLY_READY`.

SR6 grants no credit for unspecified-reference overreach, representation
conflict, unresolved constraint scope, annotation ownership, unresolved
requirements, reference kind/target, or structural failures.

## Next boundary

No provider rerun, prompt experiment, ownership-policy change, CM58 change,
or production integration follows from SR6. Any future work must be separately
authorized and must not treat the contract-bounded status as a model
qualification.
