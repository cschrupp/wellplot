# SR4 Representation Consistency

## Selected model

SR4 selects **Option B: explicit pre/post semantic wrappers** as the contract
model. This preserves model evidence for diagnosis while making the post-safety
representation authoritative only when all consumed components are synchronized.

Option A, a single transformed wrapper, is compatible with the contract but is
less explicit about what the model emitted. Option C, making the sidecar
diagnostic-only, is acceptable only for the current dormant V2R path and cannot
be used to claim final system correctness where the sidecar is consumed. Option
D, tolerating a stale sidecar behind an authoritative legacy plan, is rejected.

## Lifecycle matrix

The full machine-readable matrix is in
`tests/fixtures/semantic_ir_v2r_sr4/representation_matrix.json`.

| Representation | Lifecycle | Authority | Current status |
| --- | --- | --- | --- |
| `SemanticIRV2R` | pre-safety | model input | provider-facing semantic source |
| `reference_intents` | pre-safety | diagnostic model semantics | preserved by V2R compiler; not active production input |
| `SemanticPlan.section_tasks[*].capability_ids` | pre-safety legacy projection | diagnostic until safety | consumed by current CM58 code |
| post-CM58 safe plan | post-safety | system authority | future synchronized boundary |
| worker-visible semantic metadata | post-safety | downstream contract | current production consumption unresolved |

At the future authoritative boundary, the safe plan and reference sidecar must
agree section by section. A removed capability with a retained reference intent,
or the inverse, is a representation conflict, not a successful repair.

The active production graph currently consumes the legacy planner plan and CM58
results; V2R is not routed into it. This document therefore records future
authority without claiming that the dormant sidecar is currently consumed by
production workers.

## Required future transition

Any implementation that gives deterministic reference admissibility system
credit must produce or validate a synchronized post-safety wrapper before
scoring final semantics or exposing the result to a downstream consumer. The
implementation must preserve model-side diagnostics separately.
