# SI-V2R-SR4 Semantic Ownership and Representation Contract

## Authority

- Baseline: `e14c8814fd3b8f7cb8faae745cba907e537be3b3`
- Upstream result: SI-V2R-SR3, `e14c8814fd3b8f7cb8faae745cba907e537be3b3`
- Provider inference calls: `0`
- Endpoint calls: `0`
- Worker/program calls: `0`
- Production changes: `0`
- Scoring changes: `0`

SR4 is a provider-free contract-design slice. It does not regrade the frozen
LQ0 or SR2 evidence, change prompts or schemas, modify CM58, or implement a
new safety layer.

## Problem

SR3 separated four residual mechanisms but left three ownership questions open:

1. whether deterministic policy may reject unrequested reference presence;
2. whether feature-local and section-level constraint placement are equivalent;
3. whether annotation and unresolved semantics remain model-owned.

The V2R compiler also preserves `reference_intents` beside the legacy
`SemanticPlan`. A safety transformation that changes only the legacy plan can
leave contradictory representations. SR4 therefore treats representation
consistency as a decision-bearing invariant.

## External evidence

- MLIR canonicalization requires semantic preservation and says correctness
  must not depend on canonicalization. This is adapted as a rule that safety
  reconciliation must be explicit and observable.
- Vega-Lite represents axes and annotation-like rules explicitly rather than
  treating their meaning as prose. This supports explicit annotation and
  reference semantics, but is only an analogy because WellPlot reference tracks
  can carry data.
- Semantic evaluation work for text-to-SQL distinguishes structural form from
  observable meaning. This supports checking scope and downstream behavior,
  not accepting any textual relocation automatically.

## Evidence classification

- Report-presence ownership: `EMPIRICALLY_SUPPORTED` and already accepted by
  SR1/SR2.
- Reference admissibility boundary: `ADAPTED` from the existing CM58.1 policy.
- Reference kind and target remaining model-owned: `EMPIRICALLY_SUPPORTED` by
  V2R's explicit intent model and SR3 evidence.
- Synchronized pre/post semantic wrappers: `ADAPTED`; the lifecycle is not yet
  implemented in production.
- Constraint scope and inheritance rules: `NOVEL` WellPlot contract, with
  explicit fail-closed behavior.
- Annotation and unresolved-requirement ownership: `EMPIRICALLY_SUPPORTED`.

## Decision

SR4 freezes the machine-readable ownership, ambiguity, and representation
policies in the accompanying fixtures. The terminal decision is recorded in
`43-si-v2r-sr4-result.md` and `tests/fixtures/semantic_ir_v2r_sr4/result.json`.

No historical score is recalculated. The SR3 result remains unchanged.

## Hard stop

The next activity, if separately authorized, is a provider-free review or
historical regrade against this contract. SR4 does not authorize that regrade,
model inference, a prompt change, or production implementation.
