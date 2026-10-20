# D5-5G Inspectable Historical-Claim Revalidation

```yaml
authority: WELLPLOT-D5-5G-INSPECTABLE-HISTORICAL-CLAIM-REVALIDATION-DESIGN-AUTH-001
slice: D5-5G
parent_d5_5f: cb4d141432721af132ae1c175885d570d7f05b46
branch: design/d5-5g-inspectable-historical-claim-revalidation
status: DESIGN_ONLY / READY_FOR_INDEPENDENT_REVIEW
provider_model_calls: 0
implementation_authorized: NO
execution_authorized: NO
```

## Purpose

D5-5F reconciled the historical TW/CM program with current inspectable Qwen
evidence. It did not promote historical observations into current contract
authority. This document defines the smallest fresh study needed to revalidate
the historical mechanisms that could affect a later semantic-contract decision.

This is a mechanism revalidation, not a reproduction of the historical
campaigns and not a semantic-contract repair. Historical aggregate scores are
context only; they are not current acceptance targets.

The study must use the current D5 model-I/O visibility and custody standard.
Every attempted case must expose the first boundary at which the observed
result diverges from the expected semantic contract.

## Hard Boundaries

```yaml
provider_model_calls: 0 until a separately approved live revalidation gate
src_wellplot_changes: 0
production_changes: 0
current_semantic_contract_changes: 0
prompt_changes: 0 in this design slice
schema_changes: 0 in this design slice
historical_artifact_mutation: FORBIDDEN
experiment_execution: NOT AUTHORIZED
new_provider: FORBIDDEN
new_adapter: FORBIDDEN
new_worker: FORBIDDEN
```

### Single-canonical-engine invariant

D5-5G MUST NOT create, prototype, introduce, shadow, fork, emulate, or
temporarily stand up any new semantic engine of any kind.

Forbidden includes:

* a second planner engine;
* a second worker engine;
* an alternate semantic pipeline;
* an experimental parallel compiler;
* a shadow lowering or execution path;
* a model-specific semantic engine;
* a compatibility engine;
* a repair engine that duplicates canonical semantics;
* an adapter layer that becomes another semantic runtime;
* an evaluation-only semantic executor;
* a temporary experimental engine intended for later removal.

The only permitted execution architecture is:

```text
existing case/input
  -> existing canonical composition root
  -> existing planner/workers
  -> existing provider boundary
  -> existing deterministic lowering/reconciliation/execution
  -> existing verifier/evaluation surfaces
```

Read-only instrumentation, custody, synthetic fixtures, offline validators,
comparison logic, and inspection renderers are allowed only when they observe
the canonical path and do not reproduce or replace semantic execution. If an
experimental requirement appears to require a new semantic engine, alternate
planner/worker pipeline, duplicate compiler, or shadow execution path, stop
and escalate rather than implement it.

## Evidence Status Classification

Each historical claim entering D5-5G must be assigned one status before any
revalidation is run:

```yaml
OFFLINE_REPRODUCIBLE:
  deterministic behavior can be reproduced from committed inputs and code
LIVE_REVALIDATION_REQUIRED:
  model/provider behavior may change and needs current inspectable evidence
HYPOTHESIS_ONLY:
  historical evidence suggests a mechanism but does not isolate causality
NOT_DECISION_BEARING:
  result is benchmark-specific, aggregate-only, or outside the next contract
```

| Historical claim | Status | Reason |
| --- | --- | --- |
| TW-02/TW-02I host ownership and input sufficiency | `OFFLINE_REPRODUCIBLE` | Typed boundary and provenance checks are deterministic. |
| TW-03/TW-03S structural versus semantic boundary | `OFFLINE_REPRODUCIBLE` plus `LIVE_REVALIDATION_REQUIRED` for model behavior | Structural rejection can be replayed; model first-pass behavior cannot be carried forward. |
| TW-07/TW-08 required versus defaulted discriminator effect | `LIVE_REVALIDATION_REQUIRED` | Historical result was local-Qwen-only and did not isolate all lower-level consumers. |
| CM-56R8 capability-local contract effect | `LIVE_REVALIDATION_REQUIRED` | Recovery was selective and family-specific. |
| CM-57P10 prompt-arm aggregate improvement | `HYPOTHESIS_ONLY` | The promoted arm was rejected by protected-regression rules. |
| CM-59A aggregate 21/24 result | `NOT_DECISION_BEARING` | It is a historical system score, not a current contract target. |
| correction preserving valid semantic subtrees | `LIVE_REVALIDATION_REQUIRED` | Current D5 evidence shows whole-plan loss; the mechanism must be measured directly. |

## Frozen Scope

D5-5G has exactly three bounded revalidation axes. They are not three new
engines and do not authorize production changes.

```yaml
axis_a: schema_requiredness / TW-07-TW-08 mechanism
axis_b: capability_local_semantic_contract / CM-56R8 mechanism
axis_c: correction_preservation / current D5 and bounded-repair evidence
```

The exact historical nine-turn D4/D5 population is not the D5-5G study
population. D5-5G must use small, synthetic, mechanism-isolating cases with
fresh wording and names, while retaining the canonical D5 engine and
evaluation boundaries. No historical case, score, prompt, gold, or artifact
may be silently rewritten.

## Common Inspectable Custody

Every attempted revalidation case must produce an immutable, redacted
inspection record with the following ordered sections:

```text
CASE / EXPECTED SEMANTICS

1. MODEL INPUT STATE
   section inventory
   track inventory
   binding inventory
   source candidates
   channel inventory and inspection state

2. EXACT MODEL-FACING REQUEST
   system prompt
   user payload
   response schema
   request controls
   content and configuration hashes

3. EXACT RAW MODEL RESPONSE
   raw provider envelope
   assistant content
   response hash

4. STRUCTURED-OUTPUT BOUNDARY
   JSON decoding
   provider-schema validation

5. CANONICAL WELLPlot BOUNDARY
   response-model validation
   cross-field invariants
   target resolution
   source resolution
   capability-closure result

6. RESULTING SEMANTICS
   semantic object or projection
   deterministic host transformations

7. EVALUATION
   expected semantics
   observed semantics
   field-level diff
   diagnostic owner and class
   persistence/render result when applicable

8. FIRST DIVERGENCE
   exactly one boundary classification
```

Provider reasoning text is not scientific evidence. It must not rescue or
condemn a result. The result is determined by structured output and canonical
deterministic boundaries.

Each record must also include:

```yaml
axis:
case_id:
attempt_index:
model:
provider_boundary:
implementation_checkpoint:
input_hashes:
schema_hash:
prompt_hashes:
response_hash:
terminal_status:
provider_calls:
model_calls:
```

## First-Divergence Taxonomy

```yaml
PROVIDER_OR_STRUCTURED:
  response unavailable, malformed, or rejected at the provider/schema boundary
PLANNER_SHAPE:
  output parses but cannot form the required canonical work-unit shape
TARGET_OR_SOURCE_LINKING:
  semantic target or source inventory cannot be resolved unambiguously
SEMANTIC_FIELD:
  canonical object exists but a requested field/value is wrong or absent
CAPABILITY_CLOSURE:
  requested capability is not a valid closed canonical capability path
HOST_SAFETY:
  deterministic safety or ownership rules reject the proposed mutation
DETERMINISTIC_GRADING:
  evaluator/verifier disagrees with a valid semantic result or has a contract defect
HARNESS:
  custody, transport instrumentation, or lifecycle defect prevents interpretation
```

Only the earliest failed boundary is causal for a case. Later failures are
secondary observations and must not be promoted to model conclusions.

## Axis A — Schema Requiredness

### Claim under test

TW-07/TW-08 suggest that a semantic discriminator represented as
required/explicit performs materially better than the semantically equivalent
defaulted/optional representation. Historical evidence does not isolate the
native consumer mechanism and does not establish a current universal rule.

### Controlled variable

Compare exactly two provider-facing representations of one discriminator:

```yaml
A0:
  discriminator: optional/defaulted representation
A1:
  discriminator: explicitly required representation
```

Everything else must be byte-identical: model/provider, system prompt, user
request, semantic task, available inventory, schema descriptions, request
controls, canonical validator, deterministic grader, and attempt order. The
semantic task must have two visibly distinct branches so omission is observable
rather than silently defaultable.

### Frozen study design

```yaml
provider_lane: existing approved WellPlot provider boundary only
model: one frozen model selected by a future live authority
arms: A0, A1
development_attempts: 4 per arm maximum
holdout_attempts: 0 until development confirms an interpretable mechanism
concurrency: 1
```

The four-attempt development matrix is a diagnostic minimum, not a statistical
acceptance claim. A later authority may authorize a finite confirmation matrix
only after inspecting this result.

### Observables and decision rules

For every attempt record provider/schema validity, discriminator presence and
value, canonical validation, branch selection, semantic field accuracy, and
first divergence. Also record whether omission was rejected, defaulted, or
silently interpreted.

```yaml
confirm_historical_mechanism:
  A0 shows repeated omission/default or branch ambiguity and A1 preserves the
  discriminator with no protected regression under identical controls.
falsify_historical_mechanism:
  A0 and A1 have equivalent discriminator observability and semantic outcomes,
  or another first divergence dominates both arms.
inconclusive:
  provider/schema failure, unstable transport, sparse behavior, or any
  uncontrolled difference between arms.
stop:
  prompt/schema drift, cross-arm state leakage, or non-canonical execution path.
```

No result may be summarized as “required is better” without showing the
discriminator boundary and ruling out provider or canonical-shape failures.

## Axis B — Capability-Local Semantic Contract

### Claim under test

CM-56R8 suggests that concise capability-local contracts with synthetic
examples can recover specific semantic families, but recovery was selective
and did not prove a universal prompt remedy.

### Controlled variable

Compare the current minimal contract with the same exact request/context/schema
plus one capability-local mapping contract:

```yaml
B0: current minimal contract
B1: current contract + explicit capability-local mapping and examples
```

The B1 contract may be evaluated as an experiment input only after a future
design review. It must not be added to production by this document. The
mapping must identify the semantic field, allowed value domain, source
inventory, and one positive and one non-matching example without embedding
benchmark-specific names or answers.

### Frozen study design

Use one semantic family at a time. Begin with two families selected from
current D5 failures, not the entire historical CM-56R8 matrix. Use four
attempts per arm per family at most during development, with fresh names and
wording. Measure field-level outcomes instead of only whole-case pass/fail.

```yaml
families_initially:
  - one revision-target or report-slot mapping family
  - one source/channel or capability-closure family
arms: B0, B1
development_attempts: 4 per arm per family maximum
```

### Observables and decision rules

Capture whether the requested field appears, its canonical value, provenance
to the inspected input, target/source resolution, capability closure, unrelated
field preservation, and first divergence. A whole-case pass is secondary.

```yaml
confirm_historical_mechanism:
  B1 improves the predeclared target field across fresh wording and names,
  with no protected regression or hidden host repair.
falsify_historical_mechanism:
  B0 and B1 are equivalent, or B1 helps one family while failing the declared
  field/provenance contract for the other.
inconclusive:
  improvement occurs only after an uncontrolled prompt, schema, inventory, or
  grader difference, or provider/structured failures dominate.
stop:
  B1 requires fixture-shaped literals, benchmark answers, a second semantic
  path, or host code that rewrites an incorrect answer.
```

The study must not use reasoning text to explain an absent field. The emitted
structured answer and canonical boundary determine the result.

## Axis C — Correction Preservation

### Claim under test

Current D5 evidence shows that whole-plan regeneration during correction can
lose valid fields such as `existing_section_hint`, source clues, scale, or
target identity. Historical bounded-repair evidence suggests preservation
should be measured directly, but does not authorize a repair architecture.

### Controlled variable

Compare only correction behavior:

```yaml
C0: existing whole-plan regeneration behavior
C1: a study-only preservation condition whose output is compared against the
    original valid semantic subtree before any production adoption
```

C1 must be specified in a later implementation/design review. This document
does not define or implement a second correction engine. If C1 requires a
shadow semantic executor, it is disallowed; the study must instead observe the
canonical correction boundary and stop.

### Frozen study design

Use a small set of synthetic plans with one deliberately missing field and at
least three valid unrelated subtrees: target identity, source clue, and scale
or presentation value. Use fresh wording and names. Four attempts per
condition maximum during development.

### Observables and decision rules

Before correction, record a hash and field projection of every valid subtree.
After correction, compare each subtree, the requested repair, diagnostics,
mutation bytes, persistence, and render. Record whether correction retained,
changed, dropped, or ambiguously re-resolved each valid subtree.

```yaml
confirm_current_d5_failure:
  C0 drops or changes a valid unrelated subtree while addressing the missing
  field, and first divergence is correction preservation.
falsify_current_d5_failure:
  C0 preserves every predeclared valid subtree under the controlled case.
inconclusive:
  the initial plan is not valid before correction, the correction target is
  ambiguous, or harness/grader defects prevent comparison.
stop:
  any attempt to add a parallel repair engine, replay a semantic plan through a
  duplicate executor, or silently rewrite the expected result.
```

The study must separately report preservation and final success. A final PASS
does not prove preservation if an unrelated subtree changed.

## Shared Experimental Controls

All future authorized executions must freeze and hash:

```yaml
implementation_checkpoint: exact canonical D5 checkpoint
provider/model: exact selected lane and model
system_prompt: exact bytes
user_payload: exact bytes
response_schema: exact bytes
request_controls: exact serialized controls
semantic_inputs: inventories, sources, and capability state
grader: exact evaluator version and gold
```

Arms execute sequentially with no shared mutable state. Each arm and axis
receives a fresh artifact root and campaign namespace. No historical campaign
may be resumed, replayed, or overwritten.

The first provider/model call, if later authorized, is part of revalidation.
It is not a D5-5F result or a qualification campaign. A provider/schema
rejection is terminal for that attempt, not permission to replay it under
another prompt.

## Promotion and Stop Rules

D5-5G may produce evidence for a later D5-5H semantic-contract repair study.
It cannot authorize production adoption, change the canonical schema, change
prompts, add examples, alter graders, or select a new model.

Stop before any implementation decision if:

* a protected architectural boundary is crossed;
* the canonical engine is not the sole semantic execution path;
* an arm has uncontrolled prompt/schema/input differences;
* custody or inspection is incomplete;
* a failure cannot be assigned to the first-divergence taxonomy;
* an aggregate score is being used as a causal conclusion;
* a proposed improvement depends on benchmark-specific wording.

No historical mechanism is promoted solely because it raises a score. A
candidate mechanism must show the declared boundary effect, field-level
benefit, stability across fresh wording, and no protected regression before a
separate D5-5H design may consider it.

## Required D5-5G Handoff

The implementation/design handoff must state:

```yaml
Single canonical engine preserved: YES
New semantic engine introduced: NO
Shadow/parallel semantic execution path introduced: NO
Provider/model calls: 0 for this design slice
src/wellplot changes: 0
production changes: 0
historical artifacts mutated: NO
D5-5G implementation: NOT AUTHORIZED
D5-5G execution: NOT AUTHORIZED
D5-5H: NOT AUTHORIZED
status: STOP FOR INDEPENDENT DESIGN REVIEW
```

## Evidence Basis

The WellPlot-specific evidence basis is:

```yaml
historical:
  - TW-02
  - TW-02I
  - TW-03
  - TW-03S
  - TW-05
  - TW-06
  - TW-07
  - TW-08
  - CM-56R8
  - CM-57P10
  - CM-59A
current:
  campaign: d5-5-qwen-inspectable-002
  checkpoint: a81b69df5d9880a54a34be597ca56798f6744ba9
  model: qwen3.6-35b-a3b
  completed_turns: 9
  logical_calls: 22
  terminal_decision: FAIL / SEMANTIC_CONTRACT
```

External evidence informs interpretation but does not become WellPlot
authority:

* [llama.cpp grammar and JSON-Schema guide](https://raw.githubusercontent.com/ggml-org/llama.cpp/b11669/grammars/README.md)
* [PICARD, EMNLP 2021](https://aclanthology.org/2021.emnlp-main.779/)
* [RAT-SQL, ACL 2020](https://aclanthology.org/2020.acl-main.677/)
* [DIN-SQL](https://arxiv.org/abs/2304.11015)
* [Anthropic tool-design guidance](https://www.anthropic.com/engineering/writing-tools-for-agents)

These sources support constrained output, schema linking, bounded
decomposition, and explicit tool contracts in their original settings. They
do not establish that any D5 prompt/schema/model combination will pass.

## Final Disposition

```yaml
D5-5F: ACCEPTED AS HISTORICAL RECONCILIATION
D5-5G: DESIGN ONLY / READY FOR INDEPENDENT REVIEW
D5-5G implementation: NOT AUTHORIZED
D5-5G provider/model execution: NOT AUTHORIZED
D5-5H: NOT AUTHORIZED
production_promotion: NOT AUTHORIZED
```
