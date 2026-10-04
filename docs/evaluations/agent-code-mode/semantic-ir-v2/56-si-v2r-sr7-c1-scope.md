# SI-V2R-SR7-C1 Schema Failure Localization

## Authorization

SR7-C1 is a bounded follow-up to C0. It uses the frozen NVIDIA configuration
and the same synthetic `probe_curve` request, with at most one full
`SemanticIRV2R` structured call plus one retry only for a transient transport
failure. It does not run A, B1, the CM-59A corpus, a 24-case comparison, or any
worker/program call.

The implementation baseline is C0 commit
`adfaa102da045626a2d5e8d153fbf973ffd55068`. No production, prompt, schema,
compiler, CM58, registry, gold, or qualification files are changed.

## Diagnostic Boundary

C1 separates transport status, JSON parsing, local JSON-Schema conformance,
canonical Pydantic validation, and synthetic semantic evaluation. The response
body is held only in memory. Persisted evidence contains bounded structural
projections, hashes and lengths, Pydantic error locations/types/categories,
JSON-Schema error paths/keywords, and response metadata. Raw assistant content
and credentials are never persisted.

The exact generated `SemanticIRV2R` JSON Schema is checked with the available
`jsonschema.Draft202012Validator`. The actual frozen Pydantic model is then
validated independently. The rule inventory records whether each relevant
constraint is explicit in JSON Schema or Python-only.

## Decision Boundary

C1 does not score the model or authorize SR7-P0. It classifies only the cause
of the B2 validation failure and whether configuration B may be frozen:

- `SI_V2R_SR7_C1_B_FREEZE_ALLOWED`;
- `SI_V2R_SR7_C1_B_FREEZE_FORBIDDEN`;
- `SI_V2R_SR7_C1_FAILURE_LOCALIZED_BUT_FREEZE_UNRESOLVED`;
- `SI_V2R_SR7_C1_FAILURE_CAUSE_UNRESOLVED`;
- `SI_V2R_SR7_C1_EVIDENCE_INSUFFICIENT`;
- `SI_V2R_SR7_C1_REWORK_REQUIRED`.

Even `B_FREEZE_ALLOWED` leaves SR7-P0 separately gated by independent review.
