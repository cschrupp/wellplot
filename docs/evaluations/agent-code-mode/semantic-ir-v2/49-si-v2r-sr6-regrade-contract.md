# SI-V2R-SR6 Regrade Contract

## Input authority

The authenticated raw population is joined by `(case_id, attempt)` with the
frozen SR2 adjusted rows and SR5 applicability rows. The SR5 rows are copied
into every SR6 row, including their applicability dimensions, blockers, and
boolean eligibility map. No SR6 classifier recomputes whether a contract
dimension ought to be eligible.

## Credit rule

For a structurally evaluable row, a residual can be removed only when its
dimension maps to a `true` SR5 eligibility flag. In this population, the
report-presence eligibility has already been applied by the accepted SR2
interpretation. The eligible explicit-reference rows do not contain an
additional admissibility residual. Consequently SR6 must not manufacture a
new recovery.

The following states never receive deterministic credit:

- `MODEL_OWNED`
- `BLOCKED_BY_REPRESENTATION_CONFLICT`
- `BLOCKED_BY_UNRESOLVED_CONTRACT`
- `FAIL_CLOSED`
- `NOT_EVALUABLE`

Report content, reference kind, reference target, annotation semantics,
unresolved requirements, and unresolved constraint scope remain outside the
eligible credit boundary.

## Row status

Each row retains its frozen model status and SR2 status and receives one of:

- `PASS` when no residual remains after exact SR5-flagged credit;
- `FAIL` when a model-owned or blocked residual remains;
- `NOT_EVALUABLE` for the six structural failures.

The derivation rejects an unexpected `SEMANTIC_PASS -> FAIL` transition rather
than silently introducing a regression. A model failure may become a system
pass only when every residual was covered by an already-true SR5 flag.

## Residual interpretation

Verde and Iris retain both `REFERENCE_REPRESENTATION_CONFLICT` and
`REFERENCE_UNSPECIFIED_POLICY_BLOCK`; historical CM58.1 removal is not enough
to grant reference credit. Garnet retains `CONSTRAINT_SCOPE_UNRESOLVED`.
Amber retains `ANNOTATION_ERROR`, and Iris retains annotation, unresolved
requirement, and reference residuals. These are not model-score corrections.

## Terminal decision

The result is `SI_V2R_SR6_NO_ADDITIONAL_SYSTEM_RECOVERY` when the exact
SR5-bounded regrade produces no row-status changes relative to SR2. Otherwise,
an otherwise valid bounded regrade is
`SI_V2R_SR6_PARTIAL_REGRADE_COMPLETE`. Missing or unauthenticated evidence is
`SI_V2R_SR6_EVIDENCE_INSUFFICIENT`; derivation or transition violations are
`SI_V2R_SR6_REWORK_REQUIRED`.
