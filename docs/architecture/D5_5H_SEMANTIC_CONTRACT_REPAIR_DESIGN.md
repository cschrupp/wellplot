# D5-5H Baseline-Compliance Closure Design

```yaml
authority: WELLPLOT-D5-5H-BASELINE-COMPLIANCE-CLOSURE-DESIGN-AUTH-001
parent_checkpoint: 9020db25ebe06db7f0f28654d63aabac4690fd7e
design_basis: docs/agent-code-mode-current-baseline.md
status: DESIGN ONLY / READY FOR INDEPENDENT REVIEW
implementation: NOT AUTHORIZED
provider_model_calls: 0
endpoint_calls: 0
experiment_execution: FORBIDDEN
src_wellplot_changes: 0
```

## 1. Scope and Applicability

D5-5H is a compliance-closure design for the accepted Agent/Code-Mode
Current Active Baseline. It is not a new A/B/C experiment and does not reopen
settled CM/TW questions. Its purpose is to bring the current canonical
semantic boundary into compliance with requirements already answered by the
baseline, then isolate only questions that remain genuinely unresolved.

The design applies to the existing path:

```text
shared composition root
  -> SemanticPlanner
  -> canonical report/section workers
  -> deterministic lowering and reconciliation
  -> AuthoringExecutor / AuthoringService
  -> verification, persistence, and rendering
```

The design forbids a second planner, DTO, compiler, validator, repair engine,
provider adapter, fallback engine, model-specific semantic path, or shadow
executor. `src/wellplot/**` implementation is not authorized by this design.

## 2. Mandatory Bootstrap and Non-Rediscovery Preflight

The implementation/review sequence must read, in order:

1. `AGENTS.md`;
2. `docs/agent-code-mode-current-baseline.md`;
3. the canonical source and contracts relevant to the selected gap.

For every proposed H work item, record:

- applicable baseline item(s);
- current implementation gap;
- whether the action is deterministic repair or genuine empirical
  uncertainty;
- why existing source, contracts, baseline, and accepted evidence do not
  already answer any remaining question; and
- expected implementation and regression consequence.

The baseline already answers the direction for G1-G6, G8, and G9. Those items
are deterministic compliance repairs, not experiments. G7 remains an open
preservation question only after its deterministic contract and regressions
are defined.

## 3. Gap Disposition

Each known gap receives exactly one disposition:

| Gap | Baseline basis | Disposition | Work type | Rationale |
| --- | --- | --- | --- | --- |
| G1 no-work-unit schema gap | R-02, R-04 | `IMPLEMENT` | deterministic repair | The canonical invariant is settled; the emitted provider contract must reject an empty work-unit plan before Python-only grading. |
| G2 optional revision hint | R-03, R-05 | `IMPLEMENT` | deterministic repair | The key must be structurally required but nullable; reconstruct permits null while revise validation requires a non-null target. |
| G3 hidden capability-parent closure | R-04 | `IMPLEMENT` | deterministic repair | A host-owned closure operation adds only uniquely determined parents and fails closed on semantic alternatives. |
| G4 incomplete revision inventory | R-01, R-05 | `IMPLEMENT` | deterministic repair | The host must expose bounded semantic addressability; canonical IDs and mutation handles remain host-owned. |
| G5 ambiguous source inventory state | R-01, R-05 | `IMPLEMENT` | deterministic repair | Inspected-empty, not-inspected, and unavailable are distinct host facts. |
| G6 title/header-slot ambiguity | K-02, R-01 | `IMPLEMENT` | deterministic repair | Report-level title and host-owned layout slots require separate typed semantics and examples. |
| G7 correction preservation | R-06 | `DEFER_OPEN` | deterministic guard first; bounded validation later | A machine-readable scope and before/after path-diff guard are required, but end-to-end retention is not yet established. |
| G8 non-causal negative grading | R-07 | `IMPLEMENT` | deterministic repair | Expected diagnostic owner/class, immutability, and no-persistence checks are already required. |
| G9 request/verifier mismatch | K-03, R-07 | `IMPLEMENT` | deterministic evaluation-contract repair | Historical artifacts remain immutable; a versioned successor contract or scientifically equivalent mutable verifier must carry the correction. |

No gap is classified as `REGRESSION_ONLY` because each listed gap either
describes a current contract defect or remains an explicit open question. No
gap is classified as `SUPERSEDED` without a deterministic source audit showing
that the current implementation no longer exhibits it.

## 4. Baseline Compliance Work Items

### H-01 Provider contract parity: G1 and G2

Implement only in the existing canonical contract:

- encode the report-or-section work-unit requirement in the provider-facing
  representation where the supported schema subset permits it;
- make `existing_section_hint` structurally required with no Pydantic default;
  reconstruct may emit explicit `null`, while revise-mode canonical semantic
  validation requires a non-null value;
- keep canonical `SemanticPlan` validation authoritative for semantic and
  scientific constraints after structural acceptance; and
- preserve one schema/model source rather than introducing a provider DTO.

The compliance proof must use the exact emitted schema and canonical
`SemanticPlan` validation. It must show:

- summary-only/no-work-unit input is rejected at the provider-facing boundary;
- minimal valid report and section work units pass both structural and
  canonical validation; and
- omission of the required `existing_section_hint` key is rejected
  structurally, while an explicit `null` is accepted only for reconstruct and
  rejected by revise-mode canonical validation.

**Why no experiment:** TW-07/TW-08 and current D5 evidence already answer the
requiredness direction. The remaining work is contract implementation and
regression proof, not an optional-vs-required live arm or a second planner
model.

### H-02 Host-owned deterministic capability closure: G3

Keep the canonical capability registry and hierarchy. Add one canonical,
host-owned deterministic parent-closure operation between provider selection
and final semantic validation:

```text
provider-selected capabilities
  -> deterministic host parent closure
  -> canonical semantic validation
```

The operation must preserve an already-selected legal parent, add a missing
parent only when exactly one legal semantic parent is possible, and recurse
only while every next parent remains uniquely determined. If multiple
semantically distinct parents are legal and none is selected, it must fail
closed with a bounded diagnostic listing the legal choices. It must preserve
provider order and unrelated task fields.

Closure is host completion, not another planner or validator, and no model
correction call is allowed solely to add a deterministic unique parent.

**Why no experiment:** the baseline already settles that hidden closure is an
ownership/contract defect. The implementation decision is bounded and
mechanically testable.

### H-03 Revision inventory: G4

Project the production revision context into one bounded semantic/addressable
inventory containing at least:

- section title/subtitle;
- track title, kind, semantic signature, and relevant existing values;
- binding channel, label, semantic signature, and relevant existing values; and
- applicable fills, scales, and other addressable objects.

The model does not own canonical IDs, filesystem paths, or mutation handles.
`existing_section_hint` remains a semantic clue that the host resolves
deterministically. Ambiguous, missing, or conflicting identity resolution
must fail closed without mutation or substitution. The TW-02I audit must show
that this semantic inventory is sufficient; if it is not, stop rather than
exposing implementation identities as a hidden protocol.

**Why no experiment:** TW-02I and current D5 evidence already establish the
input-sufficiency requirement. Compliance requires a source audit and
regression cases, not a new model comparison.

### H-04 Source inventory state: G5

Extend the existing host projection, without creating a second source model,
so every source declares whether its channels are:

```text
inspected
not_inspected
unavailable
```

When inspected, expose the bounded channel facts required by the worker. An
empty inspected channel set must not be indistinguishable from missing
inspection. Final source resolution remains host-owned.

**Why no experiment:** source ownership and provider-visible sufficiency are
already settled by TW-02I and R-01.

### H-05 Report title versus header slots: G6

Keep report-level title semantics distinct from host-owned header-slot
mutations. The canonical worker contract and examples must show:

- when a document/report title is requested;
- when a header-slot mutation is requested; and
- that empty slot groups do not make a valid document title invalid.

Do not solve this by recognizing benchmark wording or by rewriting a title into
another field.

**Why no experiment:** the current D5 inspectable evidence identifies the
contract ambiguity directly. The repair and its regression are deterministic.

### H-06 Causal negative grading: G8

Update the existing grader/evidence contract so every negative case asserts:

- exact expected diagnostic code/class;
- expected failure owner;
- zero intent or execution where required;
- unchanged canonical bytes/state;
- zero persistence; and
- no channel/source/target substitution.

Planner-terminal failures must not pass as host safe rejections merely because
an arbitrary diagnostic exists.

**Why no experiment:** the baseline already answers the acceptance rule. The
remaining work is deterministic grader correction and regression coverage.

### H-07 Request/verifier contract: G9

Treat historical frozen requests, gold, sealed campaign artifacts, and evidence
as immutable. If evaluation semantics are defective, document the defect and
create a versioned successor request/gold/verifier contract. If only current
mutable verifier code is wrong and can be corrected without changing the
historical scientific target, it may be corrected while the original artifact
remains unchanged.

If textual normalization is retained in a successor contract, it must be an
explicit semantic operation that cannot weaken the scientific requirement. Do
not add production phrase recognition or answer rewriting to make a frozen
case pass.

**Why no experiment:** this is a deterministic evaluation-contract mismatch
already exposed by current evidence, not model-capability uncertainty. The
historical contract remains evidence; a successor contract is the current
evaluation surface.

### H-08 Correction preservation: G7

Define and enforce the deterministic preservation contract before
implementation:

- correction receives a typed invalid fragment and machine-readable violation;
- the diagnostic identifies the affected task/path or equivalent bounded scope;
- valid unrelated subtrees remain addressable and are preserved;
- legal replacement scope is explicit;
- a before/after semantic path diff identifies every changed path;
- any change outside the authorized repair scope rejects the correction;
- final canonical validation and grading remain authoritative.

The existing canonical correction call remains the only correction call. There
is no silent whole-plan replacement and no second repair engine. The exact
end-to-end retention behavior remains `DEFER_OPEN`. Any later bounded
validation must be finite, use contrasting wording/names, and measure
preservation separately from semantic success.

**Why not claim closure now:** the baseline settles the required property and
the deterministic guard, but end-to-end retention after the guard is not yet
established. That is the only remaining implementation question in this
design that may justify later bounded validation.

## 5. Provider-Visible Sufficiency Audit

The TW-02I-derived audit is a compliance check, not a scientific hypothesis.
Before any dependent implementation is accepted, enumerate every scored
model-owned fact and identify its deterministic input source, state, and
provenance. The audit must fail if a required fact is supplied only by a hidden
fixture, an ungrounded hint, or a post-hoc expected artifact.

The audit must cover report title, section identity, track identity/kind,
binding/channel identity, scale, fill, source/channel availability, revision
target, and capability closure. Host-owned IDs, paths, rendering mechanics,
mutation, and persistence are not model-owned facts.

## 6. Regression and Provider-Free Acceptance Contract

The implementation slice, when separately authorized, must prove without
provider, endpoint, or model calls:

| Surface | Required proof |
| --- | --- |
| G1/G2 | exact emitted schema, empty-plan rejection, required revision target, canonical validation |
| G3 | host-owned unique parent closure, ambiguous-parent diagnostic, orphan rejection |
| G4 | semantic target inventory, reordered/ambiguous target rejection, no host-ID leakage |
| G5 | inspected-empty versus not-inspected/unavailable source state |
| G6 | title and header-slot semantic separation |
| G8 | exact diagnostic owner/class, immutability, no persistence |
| G9 | request/gold/verifier/example semantic consistency |
| G7 | machine-readable scope, deterministic before/after path diff, out-of-scope mutation rejection; no end-to-end success claim until separately validated |
| Architecture | one canonical engine, no new planner/DTO/compiler/validator, production attestation/reachability pass |
| Custody | existing accepted custody interfaces only; no synthetic replacement observer |
| Source boundary | `src/wellplot/**` unchanged in this design slice; any later implementation must be separately authorized |

Any failure in contract parity, source/target inventory, or causal grading
blocks qualification. It must not be addressed with prompt tuning, model
switching, fallback execution, or post-hoc rewriting.

## 7. Conditional Techniques and Explicit Non-Goals

Capability-local contract text is eligible only for a named residual semantic
mapping after H-01 through H-07 compliance. It is not a generic B0/B1 arm.

Prompt changes require a separate empirical claim, isolated variable, fresh
holdout, protected-regression gate, terminal-failure rule, and explicit
decision impact. Deterministic contract repairs do not require paired model
experiments.

Model comparison, live Qwen confirmation, and D5-5H live execution are out of
scope. No D5-5G rerun is authorized by this design. Historical CM/TW questions
must not be rebuilt as new experiments.

## 8. Stop and Revisit Conditions

Stop implementation/design progression for an explicit architecture review if:

- the supported provider schema subset cannot represent the settled work-unit
  and requiredness invariants;
- canonical production context cannot expose required semantic facts without
  hidden fixture authority;
- capability closure, target inventory, or source state requires a second
  semantic model or execution path;
- correction preservation cannot be bounded without changing the canonical
  engine; or
- request, gold, and verifier cannot be reconciled without changing the
  scientific target.

Those outcomes require `KEEP`, `ADAPT`, `REPLACE`, or `REOPEN` review. They do
not automatically authorize another experiment or live run.

## 9. Provenance

- Active authority: `docs/agent-code-mode-current-baseline.md` at
  `9020db25ebe06db7f0f28654d63aabac4690fd7e`.
- Methodology: `docs/project-decision-protocol.md` and `AGENTS.md` at the
  accepted Active Knowledge Lifecycle update.
- Historical reconciliation:
  `docs/architecture/D5_5F_HISTORICAL_SEMANTIC_CONTRACT_RECONCILIATION.md`.
- Historical consolidated memory:
  `docs/evaluations/agent-code-mode/EXP-TW-consolidated-development-memory.md`.
- Current forensic evidence:
  `docs/architecture/D5_5G_QWEN_LIVE_001_FORENSIC_ANALYSIS.md` and its JSON
  companion. The C0 record is `HARNESS` with no response validation, and
  historical request/gold/campaign artifacts remain immutable.

Historical mechanisms are evidence only. The unavailable `e24fd497...`
candidate is not design or implementation authority.

## 10. Governance Boundary

```yaml
active_baseline: ACCEPTED / ACTIVE PROJECT AUTHORITY
D5-5H_compliance_closure_design: READY FOR INDEPENDENT REVIEW
D5-5H_implementation: NOT AUTHORIZED
provider_model_calls: 0
endpoint_calls: 0
src_wellplot_changes: 0
experiments: FORBIDDEN
live_Qwen_confirmation: OUT OF SCOPE
model_comparison: OUT OF SCOPE
D5-5G_rerun: NOT AUTHORIZED
D5-5I: NOT AUTHORIZED
```

This document defines a baseline-compliance closure plan. It does not
implement or execute the proposed repairs.
