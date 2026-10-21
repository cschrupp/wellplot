# Agent / Code-Mode Current Active Baseline

```yaml
baseline: agent-code-mode-current-baseline
effective_from: 13fd5384059da9649df0958527592ec24f1ae2e9
scope: agent and Code-Mode semantic planning and authoring
status: active project authority
provider_model_calls: 0
```

This document is the concise current baseline for the agent/Code-Mode semantic
boundary. It promotes accepted CM/TW/D5 knowledge into current project
authority. Historical records remain immutable evidence and are cited for
provenance; they are not themselves current implementation instructions.

Evidence strength and project knowledge status are independent. Evidence uses
`ESTABLISHED`, `ADAPTED`, `EMPIRICALLY_SUPPORTED`, or `NOVEL`. Project status
uses the statuses defined by the project decision protocol.

## 1. Scope and Applicability

This baseline applies to:

- `SemanticPlanner` and canonical report/section workers;
- provider-facing semantic schemas and prompts;
- deterministic semantic lowering, reconciliation, execution, persistence,
  rendering, and verification;
- provider-free and live experiments that measure this boundary.

It does not authorize a new experiment, production redesign, provider call,
model substitution, or D5-5H implementation. A later accepted architecture
decision may supersede an item explicitly; a historical experiment alone may
not.

## 2. Current Canonical Architecture

The only production semantic path is:

```text
shared composition root
  -> SemanticPlanner
  -> canonical report/section workers
  -> deterministic semantic lowering
  -> reconcile_authoring
  -> AuthoringExecutor / AuthoringService
  -> verification, persistence, and rendering
```

The model supplies explicit semantic facts needed by the task. The host owns
stable identifiers, source resolution, paths, mutation, presentation defaults,
execution, persistence, rendering, and final verification. A fallback engine,
shadow semantic engine, model-specific compiler, or provider-specific
execution path is outside the active architecture.

## 3. Settled Architectural Invariants

### K-01 - One canonical semantic engine

- **Status:** `SETTLED_ARCHITECTURAL_INVARIANT`
- **Evidence:** `ADAPTED`
- **Provenance:** accepted D5 architecture and historically demonstrated
  single-engine convergence
- **Boundary:** all agent and Code-Mode authoring flows
- **Finding:** all flows use the shared composition root and canonical
  planner/worker/lowering/reconciliation path.
- **Consequence:** do not add fallback engines, shadow executors, or
  model-specific semantic paths to mask contract failures.
- **Regression:** D5 reachability/attestation and entry-point tests must prove
  one production path.
- **Reopen:** only with contradictory production evidence and architecture
  review choosing `KEEP`, `ADAPT`, `REPLACE`, or `REOPEN`.

### K-02 - Typed semantic ownership boundary

- **Status:** `SETTLED_ARCHITECTURAL_INVARIANT`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** historically demonstrated by TW-02/02I and TW-03S
- **Boundary:** model output versus host execution
- **Finding:** model output contains explicit task semantics; host code owns
  identity, resolution, mutation, rendering, and execution mechanics.
- **Consequence:** do not ask the model to infer facts absent from its input or
  to own host identifiers and paths.
- **Regression:** provider-input sufficiency and ownership audits remain
  required.
- **Reopen:** contradictory evidence must identify the affected ownership
  boundary and its applicability.

### K-03 - Structural validity is not semantic correctness

- **Status:** `SETTLED_ARCHITECTURAL_INVARIANT`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** historically demonstrated by TW-03/03S
- **Boundary:** provider response, semantic validation, and host execution
- **Finding:** valid JSON and schema-valid objects can still encode wrong
  scientific semantics.
- **Consequence:** preserve separate provider/structured, semantic, host
  safety, and deterministic grading outcomes.
- **Regression:** valid-but-wrong semantic cases and deterministic failure
  classes must remain distinct.
- **Reopen:** only if a bounded study disproves the separation for a defined
  contract, not because a score aggregates the classes.

### K-04 - Deterministic safety contains damage but does not repair meaning

- **Status:** `SETTLED_ARCHITECTURAL_INVARIANT`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** historically demonstrated by CM-59A
- **Boundary:** safety, reconciliation, and verification layers
- **Finding:** fail-closed safety and mutation containment do not make an
  incorrect semantic plan correct.
- **Consequence:** stable wrong-plan escapes remain failures; safety evidence
  cannot substitute for semantic evidence.
- **Regression:** protected-regression, wrong-plan, and terminal-failure gates
  are required.
- **Reopen:** only through explicit contradiction review.

### K-05 - Historical artifacts are immutable evidence

- **Status:** `SETTLED_ARCHITECTURAL_INVARIANT`
- **Evidence:** `ADAPTED`
- **Provenance:** evidence-custody practice and accepted D5 campaign rules
  campaign rules
- **Boundary:** all CM/TW/D5 artifacts and sealed campaigns
- **Finding:** historical results are preserved, not rewritten or silently
  promoted into current implementation authority.
- **Consequence:** `e24fd497...` is unavailable, unpublished, and
  non-authoritative; it is not reconstructed or treated as implemented.
- **Regression:** custody digests and historical immutability checks remain
  mandatory where applicable.
- **Reopen:** only if the original artifact is recovered or a new accepted
  decision explicitly supersedes the custody record.

## 4. Implementation Requirements

### R-01 - Provider-visible input sufficiency

- **Status:** `IMPLEMENTATION_REQUIREMENT`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** historically demonstrated by TW-02I; current gap is
  supported by current D5 evidence
- **Boundary:** every model-scored semantic fact
- **Requirement:** expose a deterministic, path-free input source and
  provenance for each scored fact. The host owns final resolution.
- **Implementation consequence:** do not rely on hidden artifacts or absent
  channel/target facts.
- **Regression consequence:** audit every scored field and distinguish
  inspected, not-inspected, and unavailable inventory states.
- **Reopen:** only when a concrete input-sufficiency counterexample is
  documented and applicability is assessed.

### R-02 - Provider/schema/Python contract parity

- **Status:** `IMPLEMENTATION_REQUIREMENT`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** current D5 evidence
- **Boundary:** native provider schema through Python validation
- **Requirement:** every immediate post-provider rejection must be represented
  in the provider contract where feasible, or exposed through an explicit
  machine-readable correction contract.
- **Implementation consequence:** schema, prompt, Python models, compiler, and
  grader must agree on required fields, omission semantics, and cross-field
  invariants.
- **Regression consequence:** hash and inspect the exact emitted schema; test
  wire-valid/Python-invalid counterexamples.
- **Reopen:** after a changed contract is isolated and independently reviewed.

### R-03 - Required semantic discriminators

- **Status:** `IMPLEMENTATION_REQUIREMENT`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** historically demonstrated by TW-07/08 for local
  llama.cpp/Qwen; current violation is supported by current D5 evidence
- **Boundary:** provider-facing fields that choose a branch, target, or work
  unit
- **Requirement:** mandatory semantic fields must be required in the native
  provider schema. Defaults are not a substitute for explicit model output.
- **Implementation consequence:** `existing_section_hint` and equivalent
  branch/identity fields cannot be optional when revise-mode validation needs
  them.
- **Regression consequence:** requiredness and omission tests must be wired to
  the exact schema hash.
- **Reopen:** only for a new provider/build with one-variable evidence.

### R-04 - Explicit capability-parent closure

- **Status:** `IMPLEMENTATION_REQUIREMENT`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** current D5 evidence, grounded by TW-03S
- **Boundary:** capability hierarchy and work-unit validation
- **Requirement:** parent closure must be encoded in a validatable semantic
  shape or supplied through an explicit host closure operation.
- **Implementation consequence:** the provider must not guess hidden section or
  parent capabilities.
- **Regression consequence:** orphan-child plans and valid closure plans must
  be tested separately.
- **Reopen:** only with a documented alternative contract and ownership proof.

### R-05 - Revision and source inventory semantics

- **Status:** `IMPLEMENTATION_REQUIREMENT`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** current D5 evidence, grounded by TW-02I
- **Boundary:** revision workers and source selection
- **Requirement:** revision context must include bounded addressable object
  inventory: section title/reference, track identity/signature, binding
  identity/channel, and relevant existing values. Source inventory must state
  whether channels were inspected, not inspected, or unavailable.
- **Implementation consequence:** natural-language hints are clues, not IDs;
  ambiguity fails closed and source resolution remains host-owned.
- **Regression consequence:** reordered, ambiguous, missing, and inspected-empty
  inventories require separate tests.
- **Reopen:** when a concrete inventory omission or false-positive is found.

### R-06 - Bounded correction and preservation

- **Status:** `IMPLEMENTATION_REQUIREMENT`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** current D5 evidence; proposed preservation treatment is an
  adapted design hypothesis
- **Boundary:** correction after semantic or host validation failure
- **Requirement:** correction must preserve valid semantic subtrees or prove a
  complete replacement against the original request and context. It must
  report exact violations and legal choices.
- **Implementation consequence:** whole-plan regeneration cannot silently drop
  valid target, source, or closure facts.
- **Regression consequence:** compare before/after projections and require
  unchanged unrelated state.
- **Reopen:** after a bounded preservation counterexample.

### R-07 - Causal outcome grading

- **Status:** `REGRESSION_REQUIREMENT`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** current D5 evidence
- **Boundary:** negative cases and terminal evidence
- **Requirement:** a negative result must match the expected diagnostic class,
  failure owner, unchanged canonical bytes/state, no persistence, and no
  substitution. Any diagnostic is insufficient.
- **Implementation consequence:** planner-terminal failure remains distinct
  from host safe rejection.
- **Regression consequence:** assert exact diagnostic and owner, not only the
  presence of a diagnostic field.
- **Reopen:** if a bounded counterexample demonstrates causal misgrading.

### R-08 - Controlled empirical changes

- **Status:** `REGRESSION_REQUIREMENT`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** historically demonstrated by TW-05/06 and CM-57P10
- **Boundary:** any provider-facing schema, prompt, example, inventory, or
  validator change
- **Requirement:** for a deterministic contract or invariant correction, use
  deterministic and regression proof. When making an empirical claim about
  model/provider behavior or promoting a changed contract on that basis,
  isolate one variable, hash the exact inputs, and evaluate paired arms on a
  fresh holdout.
- **Implementation consequence:** deterministic repairs do not require an
  unnecessary model experiment; broad prompt tuning and bundled empirical
  changes still require causal localization.
- **Regression consequence:** require stability, protected-regression, and
  terminal-failure gates; aggregate score alone cannot promote a change.
- **Reopen:** when a controlled study identifies a new causal boundary.

## 5. Regression Requirements

The following checks are mandatory when their code surface is changed:

- provider schema and Python validation reject/accept the same structural
  language;
- required branch and revision discriminators are emitted and validated;
- capability parent closure is explicit;
- source inventory state and revision target inventory are inspectable;
- corrections preserve unrelated valid semantics;
- negative cases match the intended diagnostic owner and class;
- request, gold, verifier, and examples share one semantic contract;
- no fixture-specific phrase recognition or answer rewriting enters production;
- no fallback engine, model switch, or alternate semantic compiler masks a
  contract failure;
- production reachability/attestation covers the actual canonical closure.

Each regression must identify the invariant, evidence class, applicable
boundary, and failure that would reopen the relevant baseline item.

## 6. Conditional Techniques

### T-01 - Capability-local contracts

- **Status:** `CONDITIONAL_TECHNIQUE`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** historically demonstrated by CM-56R8
- **Boundary:** a named capability with a known mapping ambiguity
- **Use:** concise contract text and synthetic examples may be added only for
  the affected capability, with field-level metrics and no benchmark answers.
- **Not established:** this is not a universal prompt repair.
- **Reopen:** if a fresh paired study shows regressions or no decision value.

### T-02 - Prompt revision

- **Status:** `CONDITIONAL_TECHNIQUE`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** historically demonstrated effect in CM-57P10; current
  composition remains an adapted design hypothesis
- **Boundary:** only after schema/input/grading defects are controlled
- **Use:** versioned paired evaluation on a fresh holdout with protected
  regressions and terminal rules.
- **Reopen:** any protected regression or failure to meet the predeclared gate.

### T-03 - Bounded repair

- **Status:** `CONDITIONAL_TECHNIQUE`
- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** adapted design hypothesis supported by current D5 evidence
- **Boundary:** one explicit correction path after a typed violation
- **Use:** preserve valid subtrees and never add a second engine or unbounded
  retry loop.
- **Reopen:** if correction changes unrelated semantics or obscures causality.

### T-04 - Model comparison

- **Status:** `CONDITIONAL_TECHNIQUE`
- **Evidence:** `ADAPTED`
- **Provenance:** adapted design hypothesis pending a bounded comparison
- **Boundary:** only after the canonical contract, input, and grading baseline
  is fresh and accepted
- **Use:** compare models only on an interpretable, finite, unchanged contract.
- **Reopen:** any unresolved contract defect blocks model conclusions.

## 7. Superseded / Do-Not-Repeat

Each item below is a `SUPERSEDED_DO_NOT_REPEAT` project status:

- Generic optional-versus-required discriminator experiments on the already
  tested local Qwen path.
- Generic "do capability-local examples help?" experiments without a named
  field-level ambiguity.
- Broad prompt tuning before structural contract and input sufficiency are
  corrected.
- Another model comparison while canonical contract defects remain unresolved.
- Treating schema-valid output as semantic success.
- Treating any diagnostic or unchanged artifact as a negative-case pass.
- Rebuilding historical CM/TW questions as new D5 experiments.
- Fixture-specific phrase recognition or answer rewriting in production.
- Global compatibility suppression, fallback engines, model switching, or
  alternate semantic compilers used to mask contract failures.
- Reconstructing `e24fd497...` solely to recover its SHA.

These are not claims that the historical experiments were valueless. They are
current decisions not to repeat or promote their superseded forms.

## 8. Genuinely Open Questions

These remain `GENUINELY_OPEN_QUESTION`; each is a decision-bearing question,
not an authorization to run a study:

### O-01 - Current contract parity after repair

- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** present defect is supported by current D5 evidence; repaired
  result is not established
- **Question:** after a bounded contract correction, do emitted schema,
  prompt, Python validation, deterministic lowering, and grading agree for all
  scored work-unit shapes?
- **Impact:** determines whether semantic performance can be interpreted.
- **Reopen/closure:** close only with provider-free contract tests and an
  independently reviewed finite study.

### O-02 - Production input sufficiency after inventory repair

- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** current D5 evidence; applicability of a repaired inventory
  is unresolved
- **Question:** does every scored current-D5 fact have a deterministic,
  provider-visible source with explicit inventory state?
- **Impact:** determines whether model failures are attributable to the model.
- **Reopen/closure:** close with an ownership/provenance audit and unseen
  wording/name cases.

### O-03 - Whole-plan correction preservation

- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** current D5 evidence; preservation approach is an adapted
  design hypothesis
- **Question:** can the existing correction path retain all unrelated valid
  semantic facts while correcting one bounded violation?
- **Impact:** determines whether correction results are scientifically
  interpretable.
- **Reopen/closure:** close with before/after semantic projections and exact
  preservation grading.

### O-04 - Remaining semantic mappings after inherited fixes

- **Evidence:** `EMPIRICALLY_SUPPORTED`
- **Provenance:** known failures are supported by current D5 evidence; exact
  residual set is unresolved
- **Question:** which report, target, source, scale, binding, and capability
  mappings still fail after the inherited baseline requirements are applied?
- **Impact:** determines whether a remaining issue is contract, input,
  provider, model, or host behavior.
- **Reopen/closure:** close only with a finite, contrasting, non-rediscovery
  evaluation.

### O-05 - End-to-end repaired baseline

- **Evidence:** `ADAPTED`
- **Provenance:** adapted design hypothesis; no repaired end-to-end result is
  accepted in this baseline
- **Question:** does the consolidated repaired contract improve semantic
  outcomes without protected regressions or stable wrong-plan escapes?
- **Impact:** determines whether the repaired contract can become active
  implementation authority.
- **Reopen/closure:** close with fresh holdout, stability, terminal taxonomy,
  and promotion gates.

## 9. Current Known Gaps Between Baseline and Implementation

The baseline is authoritative even where the current implementation does not
yet comply. These are gaps, not permission to silently repair them:

1. The provider schema can accept a summary-only plan that Python rejects
   because a report or section work unit is required.
2. `existing_section_hint` can be nullable/defaulted on the provider path while
   revise-mode validation requires it.
3. Capability-parent closure is rejected later in Python rather than expressed
   in the provider-facing contract or an explicit closure operation.
4. Revision context does not consistently expose a bounded target inventory.
5. Source summaries can encode `channels: []` without saying whether the
   source was inspected or unavailable.
6. Report title semantics and host header-slot semantics are not sufficiently
   distinguished in the current worker contract/examples.
7. Correction regenerates a complete plan and can lose valid unrelated facts.
8. Negative grading can accept an unrelated diagnostic instead of the expected
   failure owner/class.
9. At least one frozen request/verifier pair disagrees about semantic remark
   text; production rewriting is not an acceptable fix.

These gaps must be addressed by a separately authorized, finite study or
implementation decision. They do not reopen settled architecture or authorize
model comparison.

## 10. Provenance Map

- Methodology and authority lifecycle: `docs/project-decision-protocol.md`,
  `AGENTS.md`, and `docs/decision-log.md`, adopted at `13fd5384...`.
- Historical consolidated evidence: `docs/evaluations/agent-code-mode/EXP-TW-consolidated-development-memory.md`.
- Historical reconciliation and minimum constraints:
  `docs/architecture/D5_5F_HISTORICAL_SEMANTIC_CONTRACT_RECONCILIATION.md`.
- Current D5 causal evidence and custody:
  `docs/architecture/D5_5G_QWEN_LIVE_001_FORENSIC_ANALYSIS.md` and its JSON
  companion, plus the sealed campaign artifacts they digest.
- Current architecture and implementation contracts: `src/wellplot/agent`,
  `src/wellplot/agent/code_mode`, relevant tests, and the accepted D5 design
  records.
- CM-56R8, CM-57P10, and CM-59A are historical evidence referenced by the
  reconciliation and consolidated memory.

The unavailable pre-baseline local candidate `e24fd497...` is recorded only as
historical conversation evidence. It was never published and is not a source
of current authority.

## 11. Reopening Rules

1. Do not reopen a settled item because a new experiment is interesting.
2. Record concrete contradictory evidence and its applicability first.
3. Separate WellPlot facts, external facts, engineering inference, and novel
   design choices.
4. Choose `KEEP`, `ADAPT`, `REPLACE`, or `REOPEN` in an explicit architecture
   review.
5. Update this baseline and its Knowledge Delta before dependent work begins.
6. Promote mechanically testable settled findings to regression/invariant
   checks; record why when mechanical testing is not reasonable.

## 12. Current Knowledge Delta

### Promoted

- The CM/TW/D5 findings listed in sections 3-5 are now active project
  constraints rather than archive-only observations.
- Schema/input/grading defects must be repaired or bounded before model
  capability conclusions are drawn.
- Non-rediscovery preflight and baseline freshness are required for dependent
  work.

### Changed

- Evidence strength is now explicitly separate from project knowledge status.
- Accepted results require a Knowledge Delta and active-baseline update before
  dependent slices proceed.

### Superseded

- Archive-first progression from accepted result directly to another dependent
  experiment.
- The pre-baseline assumption that an unpublished implementation candidate can
  be treated as current authority.

### New open questions

- O-01 through O-05 above remain open pending a separately authorized study.

### No-change findings

- The single canonical engine remains authoritative.
- Historical artifacts remain immutable.
- No provider/model calls, source changes, or D5-5H implementation are part
  of this baseline construction.

### Required baseline/regression updates

- Future contract work must add exact schema parity, inventory, preservation,
  causal-negative, and request/verifier consistency checks before qualification.
- Any dependent design must cite this baseline and complete the methodology
  non-rediscovery preflight.
