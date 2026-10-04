# SR7-P0 Comparison Contract

The atomic unit is `case × semantic_dimension × configuration × attempt`.
There are 24 cases and two repeated measurements per configuration, not 48
independent tasks.

## Scoring Layers

Primary model accuracy uses only `PRIMARY_MODEL_OBLIGATION`. Raw report and
unspecified-reference behavior are also reported as
`RAW_MODEL_DIAGNOSTIC`, never folded into the primary model score. Structural
reliability, compiler outcomes, deterministic safety, and contract-credited
system outcomes remain separate layers.

Per-dimension paired comparison matches attempt indices only when both sides are
semantically evaluable. Missing structural or infrastructure observations are
not imputed. Case relations use dominance: mixed A/B dimension wins are
`UNCHANGED` with reason `MIXED_TRADEOFF`, and equal wins are `UNCHANGED` with
reason `EQUAL`.

Semantic grading uses dimension-level equivalence rather than raw object
equality. Semantic IDs are local correlation handles and are ignored as spelling;
relationship targets are compared by feature position; owned report, section,
feature, annotation, constraint, and unresolved text is normalized using the
accepted LQ0 preservation rules. Section order uses only ordered ID-invariant
hard semantic signatures, and annotation uses ordered annotation feature
positions. Context moved to a different semantic owner still fails
`REQUIRED_CONTEXT`.

## Retry and Ordering Rules

Each logical attempt permits at most one structural retry and one transient
infrastructure retry. Structural retries are for canonical correction only and
never reinterpret user semantics. Infrastructure exhaustion makes the study
`INCONCLUSIVE_INFRASTRUCTURE`.

The 96-row schedule is deterministic and balanced: each case runs
`A1,B1,B2,A2` for even indexes and `B1,A1,A2,B2` for odd indexes. Concurrency
is one.

## Directional Results

Future labels are `CONFIGURATION_B_DIRECTIONALLY_BETTER`,
`CONFIGURATION_A_DIRECTIONALLY_BETTER`, `NO_CLEAR_DIRECTIONAL_DIFFERENCE`,
`INCONCLUSIVE_INFRASTRUCTURE`, `INCONCLUSIVE_CONFIGURATION_DRIFT`, and
`INCONCLUSIVE_EVIDENCE`. No arbitrary material-improvement threshold or p-value
is a promotion gate.
