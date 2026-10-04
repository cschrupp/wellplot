# SI-V2R SR7-P0 — Pre-Live Paired Comparison Harness Freeze

## Status

Provider-free harness implementation requires semantic-equivalence rework before
acceptance. The authorized baseline is
`9c0dfd2fa0a060195199f21655ccdffd2cc68c9c`. This slice defines the future A/B
comparison; it does not execute either configuration.

The comparison is explicitly a model-plus-serving-configuration study on the
repeatedly inspected CM59A diagnostic set. It is not a generalization claim,
model-only causal claim, or production qualification. A favorable result would
require a separately authorized fresh qualification corpus.

## Frozen Inputs

- 24 request cases and 2 repeated attempts per configuration.
- V2R gold SHA-256: `eb4803c1b0265f72e2b7f3f97176afe585698473f108d60768e792e4ecfca0a5`.
- Request corpus SHA-256: `b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b`.
- SemanticIRV2R schema SHA-256: `d84cdef165ba6d060addd3ed73b018a1f10a3e70ef4a674b5d1a06352c0d58d8`.
- System prompt SHA-256: `5ebdd3da9bc3cdf78442a97ba0a2ef9fc1c0d5e8b1ca641f18a30fe1b0cb50e3`.
- Structural retry prompt SHA-256: `27c6a43c7f611a79401914b6732dbcec946493bba51058c1eb1d1245f47990f0`.

## Hard Boundaries

P0 makes no provider, endpoint, worker, CM59A, or metadata calls. It does not
change prompts, schemas, gold, CM58, V2R, production routing, or ADR-CM57.
The future live runner is a separate P1 authorization.

## Terminal State

`SI_V2R_SR7_P0_HARNESS_FROZEN` is not currently claimed. The repaired
dimension-level semantic-equivalence predicates, adversarial invariance tests,
and regenerated artifact hashes must independently pass before that terminal
state can be considered. Until then the result is
`SI_V2R_SR7_P0_REWORK_REQUIRED` and P1 remains unauthorized.
