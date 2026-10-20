# D5-5F Historical Semantic-Contract Reconciliation

```yaml
authority: WELLPLOT-D5-5F-HISTORICAL-SEMANTIC-CONTRACT-RECONCILIATION-AUTH-001
scope: read-only evidence reconciliation
current_d5_branch: implementation/d5-5-comparative-model-qualification
current_d5_checkpoint: a81b69df5d9880a54a34be597ca56798f6744ba9
historical_authority: d77649765dee81ebd0b8f460ac28515b244f70da
provider_model_calls_during_reconciliation: 0
production_changes: 0
contract_implementation: not performed
```

## Purpose and Evidence Boundary

This document reconciles the historical typed-worker and Code-Mode evidence
with the current D5-5 inspectable Qwen campaign before any semantic-contract
change is made. It is not a summary of the archive and it does not authorize
or design D5-5G.

The historical source is the `eval/mcp-stabilization` lineage at
`d77649765dee81ebd0b8f460ac28515b244f70da`. Its relevant records are the
`EXP-TW-00` through `EXP-TW-08` development memories and summaries, and
`CM-56R8`, `CM-57P10`, and `CM-59A`. The archive uses CM and EXP-TW names;
those are the historical Code-Mode/typed-worker records referred to by this
reconciliation.

The current D5 evidence is the sealed, inspectable campaign
`d5-5-qwen-inspectable-002` in
`workspace/evaluations/d5-5/qwen-inspectable-002/`, plus its HTML inspection
report and current D5 source/validator contracts. It is distinct from the
earlier sealed `d5-5-qwen-001` campaign discussed in the D5-5D artifact.

The inspectable campaign custody was independently consistent: state, journal,
evidence, model-I/O, and terminal digests matched. It completed all nine turns
with 22 logical/provider/model calls and no infrastructure failure. Six turns
failed deterministic grading and three passed. No raw credentials or hidden
reasoning are used here.

Evidence strength in this document means:

* **HISTORICALLY_DEMONSTRATED**: a controlled historical comparison directly
  measured the claimed effect.
* **SUPPORTED_BY_CURRENT_D5_EVIDENCE**: the current captured prompts, outputs,
  validators, or sealed artifacts directly support the finding.
* **ADAPTED_DESIGN_HYPOTHESIS**: a bounded proposal for the next study derived
  from the preceding evidence, not an established result.

## Historical Reconciliation Matrix

### TW-02 and TW-02I: Ownership and Input Sufficiency

**Experiment:** `EXP-TW-02` tested the boundary between a typed semantic draft
and deterministic host compilation. `EXP-TW-02I` then audited whether every
worker-scored output fact had a provider-visible source.

**Controlled variable:** the experimental typed semantic representation and its
input bundle, not the provider or production runtime. TW-02 excluded paths,
canonical IDs, renderer mechanics, and provider concepts. TW-02I added a
deterministic `TypedWorkerTaskInput` beside the bounded worker context.

**Measured result:** the corrected worker-owned values included section title,
source candidate, ordered track role/kind/title, channel requirements, scales,
reversal, repeated CBL view identity, VDL profile, VDL sample axis, and VDL
x-scale. Host-owned values included widths, labels, colors, line styles,
colormap, colorbar, grid policy, paths, source format, and renderer details.
The provenance audit failed if a required provider value was removed and did
not use the expected artifact as a hidden fallback.

**Causal strength:** **HISTORICALLY_DEMONSTRATED** for the ownership boundary
and provider-input sufficiency of that frozen CBL representation. It does not
prove that every future WellPlot representation will be sufficient.

**D5 implication:** expose every model-scored semantic fact in a deterministic,
path-free input projection; keep IDs, source resolution, mechanics, mutation,
and rendering host-owned. Do not ask a worker to infer facts absent from its
input.

**Current D5:** aligned in architecture: planner/worker separation and host
resolution exist. Partially violated in practice: revision prompts sometimes
omit the target inventory and source summaries can represent an uninspected
channel set as `channels: []`, so the model-facing context does not always
prove what is known versus unknown.

### TW-03: Structural Validity Is Not Semantic Correctness

**Experiment:** `EXP-TW-03` measured first-attempt generation from the
corrected typed input using one structured call per attempt.

**Controlled variable:** first-attempt provider generation under a fixed input,
prompt, response model, provider, and Gate-A scorer. There was no repair,
retry, fallback, normalization, or orchestration.

**Measured result:** local Qwen produced 20/20 structurally valid outputs, but
only 4/20 passed Gate A in the local section split. The model could emit a
legal draft while still misrepresenting scientific semantics.

**Causal strength:** **HISTORICALLY_DEMONSTRATED** for the distinction between
wire/schema validity and task-semantic correctness in this workload.

**D5 implication:** report at least four separate outcomes: provider failure,
structured-output failure, schema-valid semantic failure, and deterministic
host/compiler failure. A valid JSON object is not evidence of a valid WellPlot
operation.

**Current D5:** aligned in the broad custody taxonomy, but the current grader
and inspectable report can obscure the first semantic boundary. Failed worker
outputs are commonly represented only by downstream verifier errors, and the
negative grader can accept a wrong upstream failure mechanism.

### TW-03S: Type Genuine Structural Invariants

**Experiment:** `EXP-TW-03S` replayed historical drafts through a strengthened
schema containing structural relationships.

**Controlled variable:** only the experimental response type and its structural
validation; benchmark values, role names, source identities, prompt, and Gate-A
semantic scorer remained separate.

**Measured result:** normal/reference tracks were restricted to curve bindings;
array tracks were restricted to raster bindings and required an x-scale. Qwen
historical VDL failures moved to structural rejection, while representable
semantic failures remained Gate-A failures. Gate-A success did not increase.

**Causal strength:** **HISTORICALLY_DEMONSTRATED** for moving genuinely
impossible shapes into the type system without encoding CBL answers.

**D5 implication:** schema-invalid should mean structurally impossible; a
benchmark-specific wrong title, scale, or channel should remain a semantic
failure. Structural invariants must be expressed in the canonical response
model, not merely discouraged in prose.

**Current D5:** the canonical section model has useful structural types, but
some task-level invariants remain Python-only. The planner schema accepts a
summary with no report or section task, and its JSON schema allows
`existing_section_hint: null` while the Python validator requires it in revise
mode.

### TW-05 and TW-06: Schema Compatibility Requires a Controlled Bisect

**Experiment:** `EXP-TW-05` changed one response-schema feature at a time from
the historical control. `EXP-TW-06` decomposed the first collapse using native
Pydantic representations while holding provider, input, prompt, settings,
adapter, and evaluator constant.

**Controlled variable:** response model/schema representation only. TW-05 found
the first completed collapse at the historical control to S1 transition:
20/20 structured for S0 versus 0/20 for S1. TW-06 found U0, U1, U2, and U3 all
at 20/20 structured, while exact U4 reproduced 0/20.

**Measured result:** the discriminator keyword alone was not proven causal.
The exact S1 schema differed from the working U3 representation in additional
native details. The experiment localized a compatibility boundary without
assigning blame to llama.cpp, Qwen, Pydantic, or one JSON-Schema keyword.

**Causal strength:** **HISTORICALLY_DEMONSTRATED** for the need to bisect
schema representation under fixed controls; **ADAPTED_DESIGN_HYPOTHESIS** for
applying the same discipline to the current D5 models.

**D5 implication:** freeze and hash the exact native schema, audit its emitted
JSON rather than only Python declarations, and change one representational
feature per bounded study. Do not infer provider compatibility from a type
annotation or from a logically equivalent schema on paper.

**Current D5:** violated by the planner contract. The wire schema and Python
model do not express the same cross-field language, so the provider can pass
the transport schema and still be rejected immediately afterward.

### TW-07 and TW-08: Required Tags Versus Defaulted Tags

**Experiment:** `EXP-TW-07` changed only the Pydantic discriminator tag from
required to defaulted. `EXP-TW-08` repeated the comparison using the full
strengthened typed-worker schema.

**Controlled variable:** the tag requiredness/default representation. Branch
names, mappings, non-tag fields, provider input, prompt, compiler, and Gate-A
behavior were held constant.

**Measured result:** TW-07 recorded required D0 at 20/20 structured and 4/20
Gate A, versus defaulted D1 at 0/20 structured and 0/20 Gate A. TW-08 recorded
defaulted R0 at 1/20 structured and 0/20 Gate A, versus required R1 at 20/20
structured and 20/20 Gate A. The R1 semantic projection and compiler behavior
were equivalent to R0 where represented.

**Causal strength:** **HISTORICALLY_DEMONSTRATED** at the coupled native-schema
level for this local llama.cpp/Qwen path. The experiments do not isolate the
`default` keyword from the `required` list or prove generality to every
provider.

**D5 implication:** if a semantic discriminator or field is necessary to
select a legal branch or preserve an explicit request, it must be required in
the provider-facing schema. Do not encode “required in prose, nullable/default
in schema, mandatory in Python” as a normal contract.

**Current D5:** directly violated by `existing_section_hint` and by the
summary-only planner shape. The current inspectable run reproduces exactly the
failure pattern these experiments warned about.

### CM-56R8: Capability-Local Semantic Contracts

**Experiment:** `CM-56R8` compared the current authoritative-request worker
boundary (A) against the exact same payload plus concise capability-local
semantic contracts (B), across five cases and three paired attempts.

**Controlled variable:** the selected capability-local contract text only.
Input, selected capabilities, source/channel context, response schema,
compiler, evaluator, provider, and model were shared.

**Measured result:** both arms had 15/15 structured/context/compiler-valid
rows and 0/15 complete scientific passes. B recovered raster-profile checks
9/9 with zero regressions, but recovered 0/9 track x-scale, 0/6 binding
scale, and 0/3 sample-axis checks.

**Causal strength:** **HISTORICALLY_DEMONSTRATED** for selective recovery of a
capability-local field; not evidence that prose contracts solve semantic
mapping generally.

**D5 implication:** contract text must name the semantic destination and
distinguish nearby fields, but each contract must be measured field by field.
Examples must teach mapping rules rather than supply benchmark answers.

**Current D5:** source/channel and scale semantics are described, but the
planner and workers still rely on broad natural-language requirements and do
not consistently expose enough target inventory for revision linking.

### CM-57P10: Prompt Structure Can Move Results, but Does Not Authorize Promotion

**Experiment:** `CM-57P10` compared production prompt P with the frozen RC
prompt on a fresh 24-case holdout, two attempts per case, using the same
production planner, schema, source summary, provider, and model.

**Controlled variable:** prompt arm P versus RC; all other listed controls were
frozen.

**Measured result:** P had 4/24 stable passes and RC had 16/24 stable passes.
RC had no unstable cases and satisfied many family gains, but it had one
protected regression and two terminal failures. The final promotion contract
required at least 18 stable RC passes, no protected regressions, and other
closure conditions, so RC was correctly rejected.

**Causal strength:** **HISTORICALLY_DEMONSTRATED** for a large prompt-structure
effect under the tested Qwen workload; **ADAPTED_DESIGN_HYPOTHESIS** for any
particular current-D5 prompt composition.

**D5 implication:** prompts are part of the semantic interface and require
versioned, paired, fresh-holdout evaluation. A higher aggregate score cannot
override regressions or terminal failures.

**Current D5:** aligned with the need for bounded correction and preservation,
but current D5 has not isolated a prompt-only repair after eliminating schema
and grading defects. It must not use the 16/24 result as a promotion target.

### CM-59A: Deterministic Safety Helps but Does Not Replace the Boundary

**Experiment:** `CM-59A` reevaluated the production planner plus deterministic
capability, report-boundary, and section-leaf safety layers on 24 fresh cases,
two sequential attempts each.

**Controlled variable:** the accepted production planner/safety system and its
fixed corpus; the experiment used explicit terminal and safety decision rules.

**Measured result:** 24/24 cases were stable. The final replacement population
had 21 stable passes, two stable planner failures, and one stable wrong-plan
escape, below the 22/24 acceptance threshold. Safety regressions, reference
violations, parent-closure violations, duplicate capabilities, instability, and
provider infrastructure failures were zero.

**Causal strength:** **HISTORICALLY_DEMONSTRATED** for deterministic safety
ownership and for the fact that safety layers cannot compensate for all
planner-boundary errors.

**D5 implication:** keep host safety fail-closed and classify planner-terminal
failures separately from safe deterministic rejection. Do not call a system
accepted because unsafe mutations are prevented if semantic planning remains
wrong.

**Current D5:** aligned on mutation containment, but the negative grader is too
weak: it accepts any diagnostic code. Current evidence shows that an upstream
planner failure can receive the same PASS as the intended ambiguity,
source-missing, or channel-missing path.

## Current D5 Contract Reconciliation

### Provider Schema Versus Python-Only Invariants

The current inspectable campaign proves a concrete mismatch. The transmitted
planner JSON Schema accepts a `SemanticPlan` containing only `summary` and
`unresolved_requirements`. Python then rejects it because
`SemanticPlan.validate_work_units()` requires a report or section task. The
captured outputs for `D4-L01:T2` calls 9 and 10 were wire-schema-valid but
Python-invalid.

The same mismatch appears for revision targets. `existing_section_hint` is
nullable/defaulted in the provider schema, but `validate_semantic_plan()`
requires it for every revise-mode section task. Calls 11-12 and 14-22 show
semantically invalid plans of this kind.

**Classification:** `SUPPORTED_BY_CURRENT_D5_EVIDENCE`.

**Constraint:** every rejection that can occur immediately after provider
validation must be represented in the provider-facing contract where feasible,
or returned as an explicit, machine-readable correction contract. A natural-
language rule cannot be the only representation of a required field.

### Optional/Defaulted Fields That Are Semantically Mandatory

The historical required/defaulted tag bisects establish a strong local
precedent against defaulting a provider field that determines branch identity.
Current D5 repeats that design error with `existing_section_hint` and an empty
plan shape.

**Classification:** `HISTORICALLY_DEMONSTRATED` for the representation rule;
`SUPPORTED_BY_CURRENT_D5_EVIDENCE` for the current violation.

**Constraint:** required semantic fields must be required in the native
provider schema. Omission should mean “not requested” only when the host
contract explicitly defines that meaning.

### Report Title Versus Header-Slot Semantics

The title turn is a useful diagnostic. The planner correctly produced a report
task containing `title: Formation Integrity Review`. The report worker then
invented `report_title`, received an error because `header_slots` and all slot
groups were empty, and returned `title` in `general_fields` rather than using
the top-level title field. The response schema did contain a top-level title,
but the prompt did not give a worked distinction between document title and
host header slots.

**Classification:** `SUPPORTED_BY_CURRENT_D5_EVIDENCE`.

**Constraint:** report-level semantic fields and host-owned slot mutations
must be separate types with examples showing which one applies. Empty slot
groups must not be presented as if they are the only way to express a
document-level title.

### Capability-Parent Closure

The planner’s JSON schema accepts `track.normal` plus `binding.curve` without
`section.log_plot`; Python rejects that plan because the capability hierarchy
requires a section parent. The T3, fill, and negative-case correction attempts
show this failure directly.

**Classification:** `SUPPORTED_BY_CURRENT_D5_EVIDENCE`, with the general
principle `HISTORICALLY_DEMONSTRATED` by TW-03S-style structural validation.

**Constraint:** capability closure must be encoded as a validatable semantic
shape or represented by a host-generated closure operation whose input/output
contract is explicit. The provider should not be asked to guess a hidden
parent rule.

### Revision Target Inventory

The current planner receives section titles and source summaries, but the
section worker owns the detailed existing-curve context. Several correction
responses omit `existing_section_hint`, and the model does not consistently
receive a compact inventory of existing tracks, bindings, and fills when a
revision targets one of them.

**Classification:** `SUPPORTED_BY_CURRENT_D5_EVIDENCE`.

**Constraint:** revision workers need a bounded, host-grounded inventory of
addressable semantic objects: section title, stable host reference, track
identity/signature, binding identity/channel, and relevant existing values.
Natural-language hints remain clues, not IDs; ambiguity must fail closed.

### Source Inventory State

Historical TW-02I demonstrates that source candidate and channel facts must be
provider-visible. Current D5 source summaries may contain a candidate with
`channels: []` without declaring whether channels were not inspected or were
inspected and found empty. That ambiguity makes “use only available channels”
hard to reason about and weakens safe rejection.

**Classification:** `HISTORICALLY_DEMONSTRATED` for input sufficiency and
`SUPPORTED_BY_CURRENT_D5_EVIDENCE` for the current representation gap.

**Constraint:** source inventory must carry an explicit state such as
`inspected`, `not_inspected`, or `unavailable`, plus channel kind/mnemonic
facts when inspected. The model may select only from host-provided candidates;
the host owns final source resolution.

### Whole-Plan Regeneration During Correction

The current bounded correction regenerates the complete planner response. In
the inspectable run, a correction that fixed or preserved some original facts
could still omit the revision target or the required capability closure. This
creates unnecessary loss of valid semantic information.

**Classification:** `SUPPORTED_BY_CURRENT_D5_EVIDENCE`.

**Constraint:** correction must operate on a typed invalid fragment with a
machine-readable violation and preserve already-valid subtrees, or explicitly
revalidate a complete replacement against the original request and context.
The next study should measure preservation of valid fields, not only final
pass/fail.

### Ambiguity Handling

The accepted architecture correctly requires ambiguous target resolution to
fail closed. However, the current safety grader treats any unchanged artifact
with any diagnostic as a valid negative result. The three negative PASS rows
therefore prove containment, not the intended ambiguity/source/channel route.

**Classification:** `SUPPORTED_BY_CURRENT_D5_EVIDENCE`.

**Constraint:** each negative case must require its exact bounded diagnostic
class, zero intent, unchanged canonical bytes/state, zero persistence, and no
substitution. Planner-terminal failure must remain distinct from host safe
rejection.

### Negative-Case Grading

The current grader checks `diagnostic_code` for presence rather than matching
the expected code/class. An offline counterexample using
`planner.missing_existing_section_hint` passes all three safety contracts.

**Classification:** `SUPPORTED_BY_CURRENT_D5_EVIDENCE`.

**Constraint:** outcome grading must be causal: expected diagnostic, expected
failure owner, no mutation, and no persistence. A generic failure flag is not
an acceptance proof.

### CBL Request/Verifier Mismatch

The generated CBL artifact preserved the requested remark text, but the
verifier required the different literal phrase `Reconstruct only the supported
subset`. This caused CBL-02 to fail while the other relevant CBL requirements
passed. The mismatch is in the frozen request/verifier contract, not evidence
that the model failed to understand the request.

**Classification:** `SUPPORTED_BY_CURRENT_D5_EVIDENCE`.

**Constraint:** request, gold, verifier, and examples must share a semantic
contract. Textual normalization may be used only when it is explicitly
defined and does not weaken scientific requirements. Do not add production
rewrites that turn one benchmark phrase into another.

## Reuse and Non-Reuse Register

### REUSE_CANDIDATE

* The TW-02/02I ownership boundary: typed semantic facts in, deterministic
  host completion out, with a provider-input sufficiency audit.
* TW-03’s separate structural, semantic, provider, and host failure classes.
* TW-03S’s genuine type invariants, preserving task-specific values for the
  semantic grader.
* TW-05/06’s one-variable native-schema bisect and schema hashing.
* TW-07/08’s required-field discipline for branch/identity discriminators,
  subject to fresh D5 schema compatibility tests.
* CM-56R8’s capability-local contract pattern, synthetic examples, and
  field-level recovery metrics.
* CM-57P10’s fresh holdout, paired arms, stability, protected-regression gate,
  and hard-stop decision rule.
* CM-59A’s explicit terminal taxonomy, separate safety-layer evidence, and
  rejection of stable wrong-plan escapes.

### SUPERSEDED

* The historical defaulted-discriminator representation used by TW-07 D1 and
  TW-08 R0 is superseded by the required-tag representation for the tested
  local path.
* The current D5 convention that leaves cross-field invariants only in Python
  is superseded as a contract pattern; it is retained only as failure evidence.
* The earlier D5-5D comparison conclusion that treats inspectable negative
  passes as fully proven is superseded by the causal-grading finding here.

### INCONCLUSIVE

* TW-05 did not prove that the discriminator keyword alone caused collapse.
* TW-07/08 did not isolate `default` from `required` at the lower-level
  consumer, and they tested only local llama.cpp/Qwen.
* CM-57P10 did not prove that RC is universally better; it was rejected due to
  protected regression and terminal failures.
* The current D5 result does not prove that a stronger model would pass; it
  proves contract, target, and grading defects exist.
* The historical Luna structured-output stop is provider-boundary evidence, not
  a semantic model comparison.

### BENCHMARK_SPECIFIC

* Exact CBL field names, section names, source candidates, CBL repeated-view
  identities, and fixed numeric values are evidence inputs, not reusable prompt
  instructions.
* The CM-57P10 24-case corpus and 18-pass promotion threshold are experiment
  controls, not D5 production requirements.

### REJECTED

* Fixture-specific phrase recognition or answer rewriting in production.
* Global compatibility-mirror suppression or any other normalization that
  hides unrelated changes from preservation grading.
* Broad prompt tuning without a fresh, paired holdout and protected-regression
  gate.
* Adding retries, fallback engines, or a second semantic architecture to mask
  an inconsistent contract.

## Minimum Constraints for D5-5G

The following are the minimum constraints for a subsequent D5-5G study. They
are not a D5-5G design or implementation.

1. **Contract parity:** the provider-facing schema, serialized prompt contract,
   Python validation, deterministic compiler, and grader must agree on required
   fields, omission semantics, and cross-field invariants.
   *(HISTORICALLY_DEMONSTRATED; SUPPORTED_BY_CURRENT_D5_EVIDENCE.)*
2. **Typed semantic boundary:** model output contains only explicit semantic
   facts needed for the task; host code owns IDs, paths, source resolution,
   mutation, presentation defaults, execution, persistence, and rendering.
   *(HISTORICALLY_DEMONSTRATED.)*
3. **Provider-visible sufficiency:** every scored model-owned field has a
   deterministic input source, with explicit inventory state and provenance.
   *(HISTORICALLY_DEMONSTRATED.)*
4. **Requiredness discipline:** fields that choose a branch, identify a
   revision target, or are mandatory for a work unit cannot be optional/defaulted
   in the native provider schema.
   *(HISTORICALLY_DEMONSTRATED; SUPPORTED_BY_CURRENT_D5_EVIDENCE.)*
5. **No hidden closure rules:** capability-parent closure and target ownership
   must be either structurally represented or host-resolved through an explicit
   contract; they cannot exist only as prose plus a later Python rejection.
   *(SUPPORTED_BY_CURRENT_D5_EVIDENCE.)*
6. **Bounded correction:** correction must preserve valid semantic subtrees or
   prove complete replacement against the original request; each correction
   reports exact violations and legal choices.
   *(SUPPORTED_BY_CURRENT_D5_EVIDENCE; ADAPTED_DESIGN_HYPOTHESIS.)*
7. **Causal grading:** negative cases require their expected diagnostic owner
   and class, plus unchanged bytes/state and no persistence. Generic diagnostics
   do not pass.
   *(SUPPORTED_BY_CURRENT_D5_EVIDENCE.)*
8. **Fresh evaluation:** measure first-pass validity, semantic field accuracy,
   correction retention, safe-failure classification, and stability separately
   on contrasting unseen wording and names. No case-specific production logic.
   *(HISTORICALLY_DEMONSTRATED; ADAPTED_DESIGN_HYPOTHESIS.)*
9. **One-variable discipline:** any prompt, schema, example, inventory, or
   validator change must be isolated, hashed, and tested provider-free before a
   bounded provider study.
   *(HISTORICALLY_DEMONSTRATED.)*
10. **Promotion gate:** improvement must be judged with a fresh holdout,
    protected regressions, terminal-failure rules, and a predefined stop
    condition. Aggregate score alone is insufficient.
    *(HISTORICALLY_DEMONSTRATED.)*

The smallest study consistent with these constraints would compare a baseline
contract against one corrected contract on a finite development set, then
evaluate the selected candidate on an unseen holdout. It should report where
errors occur: provider/structured, planner shape, target/source linking,
semantic field mapping, host safety, and deterministic grading. This sentence
is a study boundary, not an authorization to run it.

## External Evidence Check

The historical evidence is primary for WellPlot-specific decisions. The
following external sources support the general engineering interpretation:

* [llama.cpp GBNF and JSON-Schema guide](https://raw.githubusercontent.com/ggml-org/llama.cpp/b11669/grammars/README.md): JSON Schema constrains output but is not injected into the prompt. This directly supports separating wire constraint from semantic explanation.
* [PICARD, EMNLP 2021](https://aclanthology.org/2021.emnlp-main.779/): incremental constrained decoding improves formal-output validity but addresses admissibility, not task semantics.
* [RAT-SQL, ACL 2020](https://aclanthology.org/2020.acl-main.677/): schema encoding and schema linking are distinct sources of text-to-structure error.
* [DIN-SQL](https://arxiv.org/abs/2304.11015): bounded decomposition and self-correction can improve semantic parsing, but this is evidence for controlled decomposition, not permission for unbounded repair.
* [Anthropic’s tool-design guidance](https://www.anthropic.com/engineering/writing-tools-for-agents): explicit names, input/output relationships, meaningful bounded context, and informative errors improve agent/tool reliability.
* [LIDA, ACL 2023](https://aclanthology.org/2023.acl-demo.11/): visualization generation benefits from staged summarization, generation, execution, evaluation, and repair; WellPlot should adapt the staged evaluation boundary, not adopt LIDA’s code-execution architecture.
* [Semantic Evaluation for Text-to-SQL, EMNLP 2020](https://aclanthology.org/2020.emnlp-main.29/): execution-oriented semantic evaluation is more reliable than surface-form comparison, supporting WellPlot’s requirement that verification distinguish wording from scientific meaning.

These external techniques are **ESTABLISHED** in their original settings and
the WellPlot application is **ADAPTED**. None establishes that a particular
prompt, schema, or model will satisfy the D5 workload without the bounded
WellPlot study described above.

## Reconciliation Outcome

The historical record does not support replacing Qwen, adding a second engine,
or immediately launching another full qualification. It supports a narrower
conclusion:

```text
current D5 semantic boundary
    has provider-schema / Python-contract divergence
    has insufficiently explicit revision/source context
    has whole-plan correction loss
    has causal-grading gaps
    has at least one request/verifier mismatch
```

Those defects can make frontier and local models appear similarly weak because
the shared interface is underspecified or inconsistently scored. That is an
engineering hypothesis supported by the current evidence, not proof that
model capability is irrelevant. The next legitimate activity is a separately
designed D5-5G semantic-contract repair study built from these constraints.

No repaired contract, prompt, schema, provider call, or campaign was created by
this reconciliation.
