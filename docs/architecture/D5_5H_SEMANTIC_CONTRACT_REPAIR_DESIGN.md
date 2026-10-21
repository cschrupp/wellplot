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
| G2 optional revision hint | R-03, R-05 | `IMPLEMENT` | deterministic repair | Revision target identity is already a settled requirement; omission must not be represented as an acceptable default. |
| G3 hidden capability-parent closure | R-04 | `IMPLEMENT` | deterministic repair | The parent relationship must be represented structurally or by an explicit host-owned closure contract. |
| G4 incomplete revision inventory | R-01, R-05 | `IMPLEMENT` | deterministic repair | The host must expose a bounded addressable target inventory; natural-language hints are not identifiers. |
| G5 ambiguous source inventory state | R-01, R-05 | `IMPLEMENT` | deterministic repair | Inspected-empty, not-inspected, and unavailable are distinct host facts. |
| G6 title/header-slot ambiguity | K-02, R-01 | `IMPLEMENT` | deterministic repair | Report-level title and host-owned layout slots require separate typed semantics and examples. |
| G7 correction preservation | R-06 | `DEFER_OPEN` | deterministic contract first; bounded validation later | The requirement is settled, but the least-risk implementation and end-to-end preservation result are not yet established. |
| G8 non-causal negative grading | R-07 | `IMPLEMENT` | deterministic repair | Expected diagnostic owner/class, immutability, and no-persistence checks are already required. |
| G9 request/verifier mismatch | K-03, R-07 | `IMPLEMENT` | deterministic evaluation-contract repair | Request, gold, verifier, and examples must share semantics; production phrase rewriting is forbidden. |

No gap is classified as `REGRESSION_ONLY` because each listed gap either
describes a current contract defect or remains an explicit open question. No
gap is classified as `SUPERSEDED` without a deterministic source audit showing
that the current implementation no longer exhibits it.

## 4. Baseline Compliance Work Items

### H-01 Provider contract parity: G1 and G2

Implement only in the existing canonical contract:

- encode the report-or-section work-unit requirement in the provider-facing
  representation where the supported schema subset permits it;
- make revision target identity explicit and required when revise semantics
  require it;
- keep canonical `SemanticPlan` validation authoritative for semantic and
  scientific constraints after structural acceptance; and
- preserve one schema/model source rather than introducing a provider DTO.

The compliance proof must use the exact emitted schema and canonical
`SemanticPlan` validation. It must show:

- summary-only/no-work-unit input is rejected at the provider-facing boundary;
- minimal valid report and section work units pass both structural and
  canonical validation; and
- omission of a required revision target is rejected with a bounded diagnostic.

**Why no experiment:** TW-07/TW-08 and current D5 evidence already answer the
requiredness direction. The remaining work is contract implementation and
regression proof, not an optional-vs-required live arm.

### H-02 Explicit capability closure: G3

Keep the canonical capability registry and hierarchy. Choose one deterministic
contract implementation, to be justified during implementation review:

- represent the required parent closure in the canonical structural contract;
  or
- expose a host-owned closure operation with explicit input/output semantics
  before canonical validation.

The provider must not infer hidden parents, and host closure must not become a
second semantic planner.

**Why no experiment:** the baseline already settles that hidden closure is an
ownership/contract defect. The implementation decision is bounded and
mechanically testable.

### H-03 Revision inventory: G4

Project the production revision context into one bounded, host-grounded
inventory containing at least:

- section title and stable host reference;
- track identity/signature and relevant existing values;
- binding identity/channel and relevant existing values; and
- applicable fills, scales, and other addressable objects.

Natural-language labels remain clues. Ambiguous, missing, or conflicting
identity resolution must fail closed without mutation or substitution.

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

Reconcile the frozen request, gold, verifier, and examples around semantic
meaning. If textual normalization is retained, it must be an explicitly
documented contract operation that cannot weaken the scientific requirement.
Do not add production phrase recognition or answer rewriting to make a frozen
case pass. If the request and verifier cannot be reconciled without changing
the scientific target, record the contradiction for architecture review rather
than silently changing either side.

**Why no experiment:** this is a deterministic evaluation-contract mismatch
already exposed by current evidence, not model-capability uncertainty.

### H-08 Correction preservation: G7

Define the deterministic preservation contract before implementation:

- correction receives a typed invalid fragment and machine-readable violation;
- valid unrelated subtrees remain addressable and are preserved;
- legal replacement scope is explicit;
- before/after projections identify every changed path; and
- final canonical validation and grading remain authoritative.

The exact end-to-end retention behavior remains `DEFER_OPEN`. Any later
bounded validation must be finite, use contrasting wording/names, and measure
preservation separately from semantic success. It must not introduce a second
repair engine or unbounded retry loop.

**Why not implement a full answer now:** the baseline settles the required
property but not which bounded implementation achieves it without unintended
semantic loss. That is the only remaining implementation question in this
design that may justify later empirical validation.

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
| G3 | explicit parent closure or explicit host closure operation; orphan rejection |
| G4 | complete target inventory, reordered/ambiguous target rejection, no mutation |
| G5 | inspected-empty versus not-inspected/unavailable source state |
| G6 | title and header-slot semantic separation |
| G8 | exact diagnostic owner/class, immutability, no persistence |
| G9 | request/gold/verifier/example semantic consistency |
| G7 | deterministic preservation projection contract; no claim of end-to-end success until separately validated |
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
  companion. The C0 record is `HARNESS` with no response validation.

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
