# Typed Worker Experimental Program — Consolidated Development Memory

## 1. Status

This document consolidates the experimental sequence from EXP-TW-00 through EXP-TW-08.

Final frozen baseline:

```text
68232ee
```

Branch:

```text
eval/mcp-stabilization
```

The experimental program is complete through remediation validation.

No production adoption has occurred.

Across the entire TW sequence, the experiments remained outside `src/wellplot` unless explicitly interacting with existing production types as read-only dependencies. Historical experiments were preserved rather than rewritten when later evidence corrected or refined an earlier hypothesis.

The final experimental result is:

> The strengthened typed-worker schema can preserve all TW-03S structural guarantees and recover reliable local llama.cpp/Qwen structured generation when the discriminated track `kind` fields are required rather than Pydantic-defaulted.

This conclusion was reached incrementally. It was not assumed at the beginning of the investigation.

---

# 2. Original problem

The typed natural-language authoring path in WellPlot had become difficult to stabilize.

Repeated inference changes tended to fix one case while breaking another. The CBL/VDL example was particularly useful because it exercised several hard requirements simultaneously:

* multiple ordered tracks;
* scalar and array channels;
* repeated views of the same CBL channel;
* different scales for the repeated CBL views;
* reversed scales;
* source selection;
* an array VDL track with its own scientific sample-axis semantics;
* strict preservation of track and binding order.

At the architectural level, the broader goal was also becoming clearer.

WellPlot should eventually support:

```text
natural-language request
        ↓
planner / task decomposition
        ↓
independent typed section tasks
        ↓
specialized semantic workers
        ↓
structural validation
        ↓
task/context semantic validation
        ↓
deterministic compiler
        ↓
renderer
```

The system should also be able to grow when WellPlot adds new concepts such as:

* image tracks;
* additional scientific track types;
* well diagrams;
* new plot sections;
* other domain-specific visualization components.

The wrong response to the instability would have been to immediately add more agents, repair loops, LangGraph orchestration, prompt complexity, fallback models, or ad hoc parsing.

Before adding orchestration, we needed to answer a more fundamental question:

> Can a single typed semantic worker boundary be made reliable, scientifically meaningful, deterministic downstream, and extensible?

The experimental program was created to answer that question one variable at a time.

---

# 3. Experimental strategy

The investigation followed several rules.

## 3.1 Freeze the scientific problem first

The benchmark had to be frozen before observing model behavior.

Otherwise the target could drift whenever the model failed.

The CBL benchmark therefore became a fixed empirical corpus containing:

* `main_pass`;
* `repeat_pass`;
* source candidates `source-1` and `source-2`;
* exact available channels and scalar/array types;
* repeated CBL views;
* the intended VDL semantics;
* canonical scientific scales and axes;
* a deterministic semantic success criterion.

---

## 3.2 Separate failure classes

The investigation deliberately distinguished:

```text
provider failure
```

from:

```text
structured-output failure
```

from:

```text
schema-valid but task-semantically-wrong output
```

from:

```text
compiler / host-completion failure
```

These categories must not be collapsed into a generic "LLM failed" outcome.

---

## 3.3 Keep semantic intent separate from implementation

The worker schema should express scientific meaning, not rendering mechanics.

Worker-visible semantic concepts could include:

* section title;
* track role and kind;
* channel selection;
* curve scale;
* reverse direction;
* repeated-view identity;
* VDL profile;
* VDL sample axis.

Worker-visible output should not include:

* filesystem paths;
* canonical source paths;
* renderer classes;
* matplotlib concepts;
* layout coordinates;
* provider internals;
* procedural handles;
* compiler-generated IDs;
* host identities.

Those belong to deterministic host-side completion.

---

## 3.4 Prefer type invariants over prompt instructions

If a state is scientifically or structurally impossible, the schema should ideally make it impossible to express.

For example:

```text
array track + curve binding
```

should not merely be "discouraged" through a prompt if it is structurally invalid.

Conversely, benchmark-specific wrong answers should remain semantic validation failures rather than being hard-coded into the schema.

This produced the distinction:

```text
schema-invalid
    = impossible under the semantic type system

Gate-A-invalid
    = structurally representable but incorrect for this particular task
```

---

## 3.5 Change one thing at a time

Once working and failing examples existed, the strategy became:

```text
known-good case
        ↓
change one structural feature
        ↓
measure
        ↓
locate first collapse
        ↓
bisect again
```

This proved critical later in the investigation.

---

# 4. Frozen benchmark and Gate A

The benchmark contains two sections:

```text
Main Pass
Repeat Pass
```

with opaque source selections:

```text
source-1
source-2
```

The important semantic structure includes:

* Combo track;
* Depth reference track;
* CBL track;
* VDL array track.

Two views of the same `CBL` channel are semantically distinct:

```text
cbl_0_100
cbl_0_10
```

The VDL track is not simply another scalar curve. It carries array semantics including:

* VDL profile;
* track x-scale;
* sample-axis unit;
* sample-axis bounds;
* sample count/tick semantics;
* source origin;
* source step.

Gate A ultimately checks, among other things:

* selected source is allowed;
* selected channels belong to that source;
* scalar/array compatibility;
* section and track identity;
* track order;
* binding order;
* repeated CBL multiplicity and identity;
* exact curve scales/reversal;
* exact VDL scientific semantics.

Gate A remains task-specific.

The schema should not hard-code the CBL benchmark itself.

---

# 5. EXP-TW-00 — Freeze the empirical corpus

Final baseline:

```text
a31ff70
```

## Question

Can the full CBL semantic context and success criteria be frozen before any typed-worker generation is observed?

## Work

TW-00 captured:

* report task;
* two section tasks;
* resolved section contexts;
* opaque source candidates;
* per-source channel inventories;
* channel scalar/array kinds;
* host-only provenance;
* deterministic corpus hashes.

Gate A was also defined before provider generation.

## Result

The benchmark became replayable independently of:

* planner behavior;
* provider behavior;
* source discovery;
* filesystem search;
* public routing;
* future orchestration.

## Importance

This prevented later experiments from moving the target to accommodate provider behavior.

Production delta:

```text
0
```

---

# 6. EXP-TW-01 — Define the initial semantic output schema

Final baseline:

```text
6f9a2d6
```

## Question

What is the smallest typed worker output capable of representing the frozen CBL task without exposing renderer or runtime mechanics?

## Initial schema

The first semantic contract contained:

```text
SectionDraft
TrackDraft
CurveBindingDraft
RasterBindingDraft
```

The schema preserved:

* section identity;
* source candidate;
* ordered tracks;
* track kinds;
* ordered bindings;
* scalar versus raster identity.

Unknown fields were rejected.

## Result

Manually authored golden drafts for both sections:

* validated structurally;
* passed Gate A;
* survived serialization round trips;
* preserved track order;
* preserved repeated `CBL, CBL` multiplicity.

Negative tests rejected:

* unknown source;
* unavailable channel;
* scalar/array mismatch;
* collapsed repeated binding;
* reordered tracks.

## Importance

TW-01 established that a clean semantic worker boundary was feasible without renderer leakage.

Production delta:

```text
0
```

---

# 7. EXP-TW-02 — Deterministic compiler

Final baseline:

```text
c844a9f
```

## Question

Can a valid semantic draft be compiled deterministically into WellPlot's canonical authoring intent without asking the model to produce implementation details?

## Boundary

```text
SectionDraft
        ↓
structural validation
        ↓
Gate A
        ↓
deterministic compiler
        ↓
AuthoringDocumentIntent
```

The compiler:

* preserved semantic ordering;
* preserved source selection;
* preserved repeated bindings;
* created host-owned identities;
* did not repair;
* did not infer missing semantics;
* did not reorder;
* did not deduplicate.

## Result

Both golden drafts compiled deterministically.

This demonstrated that the model did not need to generate executable/rendering representations directly.

## Importance

The eventual architecture could therefore remain:

```text
LLM → semantic intent → deterministic host compiler
```

rather than:

```text
LLM → renderer/program internals
```

Production delta:

```text
0
```

---

# 8. EXP-TW-02R — Correct the semantic contract

Primary corrective commit:

```text
1f2302c
```

Evidence-corrected baseline:

```text
afc9f71
```

## Problem discovered

The original TW-01/TW-02 semantic contract was too weak to encode all scientific information actually necessary for the frozen CBL artifact.

This was an experimental-contract problem, not a provider problem.

Instead of rewriting the historical experiments, TW-02R introduced a corrected contract.

## Corrected worker-owned semantics

The worker now owns:

* section title;
* source candidate;
* ordered track role/kind/title;
* curve scales;
* reversal;
* repeated CBL view identity;
* VDL profile;
* VDL sample axis;
* VDL x-scale.

The two CBL views became explicitly distinct:

```text
cbl_0_100
cbl_0_10
```

## Host-owned/defaulted values

The host retained deterministic ownership of:

* track widths;
* binding labels;
* colors;
* line styles;
* line widths;
* VDL colormap;
* colorbar;
* grid policy;
* canonical paths;
* source format;
* renderer details.

## Result

The corrected golden drafts:

* passed corrected Gate A;
* deterministically completed host presentation policy;
* reconciled successfully;
* executed through the private authoring-service path.

## Importance

This established the real semantic ownership boundary.

The worker would decide scientific meaning.

The host would decide deterministic presentation/mechanics.

Production delta:

```text
0
```

---

# 9. EXP-TW-02I — Prove provider-input sufficiency

Final baseline:

```text
ad7a0ad
```

## Question

Before blaming a provider for wrong output, does the provider actually receive every semantic fact required to produce the corrected output?

## Input contract

TW-02I introduced:

```text
TypedWorkerTaskInput
        +
WorkerSectionInput
        ↓
TypedWorkerInputBundle
```

The typed input contains all worker-scored semantics:

* section title;
* source candidate;
* track role/kind/title;
* channel requirements;
* curve scales/reversal;
* repeated CBL identities;
* VDL x-scale;
* VDL profile;
* VDL sample axis.

It excludes host and renderer details.

## Provenance audit

Every required output field was mapped to:

```text
provider input path
        +
frozen benchmark evidence path
```

The audit failed if a required provider-visible fact was removed.

It did not use the expected output as a hidden fallback.

## Result

The input contract was proven sufficient.

## Importance

From this point onward, a semantically wrong provider response could be meaningfully interpreted as a model/output-contract failure rather than missing input information.

Production delta:

```text
0
```

---

# 10. EXP-TW-03 — First live provider-generation experiment

Initial implementation:

```text
333dbcb
```

Corrected/final baseline:

```text
151efd0
```

## Question

Given the complete typed worker input and corrected semantic response model, how reliably can providers produce a valid result on the first attempt?

## Protocol

Each attempt performed:

```text
TypedWorkerInputBundle
        ↓
one generate_structured(...)
        ↓
SectionDraft
        ↓
corrected Gate A
```

Exactly one provider call.

No:

* retries;
* repair;
* fallback;
* reflection;
* critic;
* orchestration;
* normalization;
* output patching.

## Local llama.cpp / Qwen result

Model:

```text
qwen3.6-35b-a3b
```

Results:

```text
main_pass:   1/10 Gate-A success
repeat_pass: 3/10 Gate-A success

total:       4/20
```

Critically:

```text
20/20 structurally valid
```

The model could satisfy the original output schema consistently.

The dominant semantic failure involved the VDL boundary:

* VDL represented as a curve rather than raster;
* missing VDL `x_scale`;
* sometimes both.

Most source selection, scalar values, repeated CBL identity, and TT reversal were substantially more reliable.

## OpenRouter / Nemotron result

Model:

```text
nvidia/nemotron-3-ultra-550b-a55b:free
```

Results:

```text
19/20 structurally valid
10/20 Gate-A success
```

The remaining semantic failures were more heterogeneous:

* VDL raster mistakes;
* missing VDL x-scale;
* title errors;
* TENS bound reversal;
* one omitted depth track.

## Interpretation

Three important conclusions emerged.

### 1. Typed input was sufficient

The providers had the information they needed.

### 2. Model capability mattered

Nemotron materially outperformed local Qwen semantically.

### 3. Some failures looked like type-system failures

For example:

```text
array VDL track expressed with a curve binding
```

was not merely the wrong benchmark answer.

It was an invalid structural relationship that the schema allowed.

That observation motivated TW-03S.

---

# 11. EXP-TW-03S — Strengthen the type system

Initial commit:

```text
9eb8458
```

Final baseline:

```text
21bd657
```

## Question

Can genuine structural invariants be moved into the type system without hard-coding CBL-specific answers?

## Strengthened schema

`SectionDraftS` introduced:

```text
NormalTrackDraftS
ReferenceTrackDraftS
ArrayTrackDraftS
```

with the following invariants:

```text
normal
    → curve bindings only

reference
    → curve bindings only

array
    → raster bindings only

array
    → x_scale required
```

The track-role domain remained:

```text
combo
depth
cbl
vdl
```

No role→kind coupling was added.

The schema did not encode:

* Main Pass;
* Repeat Pass;
* source-1/source-2;
* CBL values;
* TT/TENS values;
* VDL numbers;
* benchmark track order.

## Replay result

Historical TW-03 outputs were replayed through the stronger schema.

For local Qwen:

```text
main:
historical structural 10
historical Gate A      1
03S structural         1

repeat:
historical structural 10
historical Gate A      3
03S structural         3
```

Every observed Qwen Gate-A failure was rejected structurally.

For Nemotron:

```text
main:
historical structural 10
historical Gate A      6
03S structural         7

repeat:
historical structural 9
historical Gate A      4
03S structural         6
```

Some failures moved into structural rejection.

Three failures remained structurally valid semantic errors, which was correct.

Most importantly:

```text
Gate-A success never increased artificially
```

## Interpretation

TW-03S demonstrated that the stronger schema encoded genuine semantic invariants rather than benchmark answers.

This was the desired type system.

At this stage the natural next question was whether semantic repair could improve the remaining valid-but-wrong drafts.

---

# 12. EXP-TW-04 — One bounded semantic repair

Harness:

```text
602af4d
```

Evidence:

```text
f9cde8b
```

Final corrected baseline:

```text
91c4151
```

## Question

If the first output is structurally valid under `SectionDraftS` but semantically wrong for the typed task, can exactly one targeted repair call recover it?

## Protocol

```text
first SectionDraftS call
        ↓
structural validation
        ↓
Gate A
        ↓
if semantic failure only
        ↓
deterministic diff against TypedWorkerTaskInput
        ↓
one repair call
        ↓
final Gate A
```

Maximum:

```text
2 provider calls
```

No recursive repair.

No transport retry.

No fallback.

No critic.

No LangGraph.

## Local Qwen result

Unexpectedly:

```text
main:   0/10 structurally valid
repeat: 0/10 structurally valid
```

All 20 first calls ended as:

```text
structured_output_failure / invalid_response
```

Therefore:

```text
0 repair-eligible cases
```

This was a major clue.

The same local model had produced:

```text
20/20 structured SectionDraft
```

in TW-03.

Now it produced:

```text
0/20 structured SectionDraftS
```

The strengthened schema had exposed a new structured-output compatibility problem.

## OpenRouter/Nemotron result

First calls:

```text
12/20 structurally valid
6/20 Gate-A success
6 repair eligible
```

Repair:

```text
6 repair calls
2 recovered
4 structured-output failures
```

Final:

```text
8/20 success
```

Repair conversion:

```text
2/6 = 33.3%
```

## Interpretation

The bounded repair mechanism was executable and sometimes useful.

However, repair was no longer the highest-priority problem.

The critical new finding was:

> Local Qwen could satisfy the historical response schema but could not reliably satisfy the strengthened response schema at all.

Therefore the next task was not "improve repair."

It was:

> Find exactly which schema change caused the compatibility collapse.

---

# 13. EXP-TW-05 — Compatibility bisect from `SectionDraft` to `SectionDraftS`

Implementation:

```text
a4a9d31
```

Evidence:

```text
804139f
```

Final corrected baseline:

```text
2e317e1
```

## Question

At which exact schema transition does local llama.cpp/Qwen structured generation stop working?

## Ladder

```text
S0 historical SectionDraft

S1 + track discriminated union

S2 + normal/reference curve-only

S3 + array raster-only

S4 + array x_scale required

S5 exact SectionDraftS
```

Only the response schema changed.

Provider, model, input, prompt, adapter, and request settings remained controlled.

## Result

S0:

```text
20/20 structured
8/20 Gate A
```

S1:

```text
0/20 structured
20/20 invalid_response
```

Therefore:

```text
first compatibility collapse = S0 → S1
```

An aborted S2 run contained six additional `invalid_response` rows, but because the S2 section was incomplete those observations were retained only for auditability and excluded from inference.

## Interpretation

The structural restrictions themselves had not yet been introduced.

The collapse occurred when the single `TrackDraft` representation became a discriminated branch union.

However, S1 changed several JSON-Schema characteristics simultaneously:

* one object became three branch definitions;
* `kind` representation changed;
* branch `$ref`s appeared;
* `oneOf` appeared;
* discriminator mapping appeared.

Therefore it was still incorrect to conclude:

```text
"discriminators are broken"
```

A smaller bisect was needed.

---

# 14. EXP-TW-06 — Union-form micro-bisect

Implementation:

```text
5c4b3a3
```

Final baseline:

```text
1f5da6e
```

## Question

Which standard Pydantic union representation actually causes the S0→S1 collapse?

## Variants

```text
U0
historical SectionDraft

U1
single track model
field-level Literal union

U2
ordinary union of three track branch models

U3
same exact U2 branches
+ Pydantic discriminator

U4
exact TW-05 S1
```

## Results

```text
U0: 20/20 structured
U1: 20/20 structured
U2: 20/20 structured
U3: 20/20 structured
U4:  0/20 structured
```

Gate-A counts varied, but compatibility did not degrade until U4.

## What TW-06 ruled out

The compatibility problem was not caused by:

```text
Literal / const
```

because U1 worked.

It was not caused by:

```text
multiple object branches
```

because U2 worked.

It was not caused by:

```text
ordinary unions
```

because U2 worked.

It was not caused by:

```text
Pydantic discriminated unions in general
```

because U3 worked.

It was not caused simply by:

```text
JSON-Schema discriminator metadata
```

because U3 included it and remained 20/20 compatible.

## Remaining difference

The important residual difference was visible in the branch `kind` fields.

U3:

```python
kind: Literal["normal"]
```

U4:

```python
kind: Literal["normal"] = "normal"
```

In emitted JSON Schema this meant:

U3:

```text
kind has const
kind has no default
kind is required
```

U4:

```text
kind has const
kind has default
kind is not required
```

This became the TW-07 hypothesis.

---

# 15. EXP-TW-07 — Required versus defaulted discriminator isolation

Implementation:

```text
d4c73d3
```

Final baseline:

```text
79f3173
```

## Question

Does changing only the discriminated branch tag from required to Pydantic-defaulted reproduce the compatibility collapse?

## Experimental design

D0 and D1 were generated through the same native Pydantic model factory.

They used identical emitted model names:

```text
SectionDraftTag
NormalTrackTag
ReferenceTrackTag
ArrayTrackTag
```

Same:

* branch count;
* `oneOf`;
* `$ref` targets;
* discriminator property;
* discriminator mapping;
* non-`kind` fields;
* input;
* prompt;
* provider configuration.

Only this changed:

D0:

```python
kind: Literal["normal"]
```

D1:

```python
kind: Literal["normal"] = "normal"
```

Equivalent changes were made for `reference` and `array`.

## Native schema difference

D1 added:

```text
properties.kind.default
```

for the three branches.

D1 also removed:

```text
kind
```

from each branch's `required` list.

No other substantive schema difference was present.

## Results

D0:

```text
20/20 structurally valid
4/20 Gate A
```

D1:

```text
0/20 structurally valid
20/20 invalid_response
```

Provider failures:

```text
0
```

## Interpretation

This was the strongest causal result in the investigation up to that point.

> Changing the discriminated branch tag from required to Pydantic-defaulted reproduced the full local llama.cpp/Qwen structured-output collapse.

The causal claim is at the native Pydantic representation level.

TW-07 did not separately distinguish whether the lower-level trigger is:

```text
"default"
```

itself,

or:

```text
removing kind from required
```

or their interaction.

Native Pydantic couples those consequences.

That distinction was not necessary for the immediate WellPlot design decision.

---

# 16. EXP-TW-08 — Validate the remediation on the full strengthened schema

Implementation:

```text
4fd71c3
```

Initial evidence:

```text
7088b0d
```

Final evidence-corrected baseline:

```text
68232ee
```

## Question

Can the full TW-03S strengthened schema keep every desired structural guarantee while changing only the track discriminator tags from defaulted to required?

This is the key remediation-validation experiment.

## R0

Exact frozen:

```text
SectionDraftS
```

with defaulted track discriminator tags.

## R1

Semantically identical strengthened schema, except:

```python
kind: Literal["normal"]
kind: Literal["reference"]
kind: Literal["array"]
```

are required.

## Preconditions proven before live calls

R1 preserved every TW-03S invariant:

```text
normal → curve only
reference → curve only
array → raster only
array requires x_scale
```

It also preserved:

* role domain;
* no role→kind coupling;
* golden semantics;
* exact track order;
* exact binding order;
* exact scale values;
* reverse values;
* VDL semantics;
* corrected Gate A;
* deterministic compiler projection.

R0 and R1 had identical:

* branch names;
* branch count;
* `oneOf` ordering;
* `$ref` targets;
* discriminator property;
* discriminator mapping;
* non-tag fields;
* leaf models.

Only the three track-tag default/required representations changed.

Leaf defaults such as:

```text
ScaleDraft.kind = linear
CurveBindingDraft.kind = curve
RasterBindingDraft.kind = raster
RasterBindingDraft.profile = vdl
```

were intentionally untouched.

## Provider controls

Both R0 and R1 used:

```text
llama_cpp
qwen3.6-35b-a3b
temperature = 1.0
max_tokens = 16384
timeout = 900
thinking = false
```

Both used the same TW-02I input.

Both used the exact TW-04 strengthened prompt:

```text
Return exactly one SectionDraftS matching the typed input bundle.
Use no fields outside the SectionDraftS schema.
```

The final evidence correction at `68232ee` fixed the documentation to reflect this actual prompt.

## R0 result

Defaulted strengthened tags:

```text
1/20 structurally valid
19/20 invalid_response
0/20 Gate-A success
0 provider failures
```

The old incompatibility therefore reproduced strongly, although not as an absolute 0/20 collapse in this particular sample.

## R1 result

Required strengthened tags:

```text
20/20 structurally valid
20/20 Gate-A success
0 structured-output failures
0 provider failures
```

Both sections individually achieved:

```text
main_pass:   10/10 structural, 10/10 Gate A
repeat_pass: 10/10 structural, 10/10 Gate A
```

## Interpretation

TW-08 answered the engineering question that motivated the entire compatibility investigation:

> The stronger type system does not need to be weakened to recover local model compatibility.

Required discriminated track tags simultaneously preserved:

```text
TW-03S structural correctness
```

and recovered:

```text
20/20 structured-output compatibility
```

and in this run achieved:

```text
20/20 task-semantic Gate-A validity
```

No retries.

No repair.

No fallback.

No prompt tuning.

No provider switching.

No grammar workaround.

No custom parser.

---

# 17. Complete causal chain

The experimental sequence can be summarized as:

```text
Original problem:
inference was brittle and fixes caused regressions
        ↓
freeze benchmark and semantic success criterion
        ↓
prove minimal typed semantic boundary
        ↓
prove deterministic host compiler
        ↓
correct semantic ownership
        ↓
prove provider has sufficient typed input
        ↓
run first provider experiment
        ↓
Qwen: 20/20 schema-valid but only 4/20 semantic success
        ↓
observe impossible VDL curve/array shapes
        ↓
strengthen type system
        ↓
historical bad Qwen shapes become schema-invalid
        ↓
try one bounded semantic repair
        ↓
unexpected discovery:
Qwen cannot produce strengthened schema at all
        ↓
historical schema 20/20
strengthened schema 0/20
        ↓
bisect schema
        ↓
collapse first appears when S1 representation introduced
        ↓
micro-bisect unions
        ↓
Literal works
ordinary union works
discriminated union works
exact S1 fails
        ↓
difference narrowed to defaulted discriminator tag
        ↓
controlled D0/D1 experiment
        ↓
required tag 20/20
defaulted tag 0/20
        ↓
apply required tag to full strengthened schema
        ↓
R0 defaulted strengthened schema 1/20
R1 required strengthened schema 20/20
        ↓
all TW-03S invariants preserved
        ↓
20/20 Gate A
```

---

# 18. What the program has demonstrated

## 18.1 The typed-worker architecture is viable

The fundamental architecture remains sound:

```text
typed semantic input
        ↓
LLM semantic worker
        ↓
typed semantic output
        ↓
structural validation
        ↓
task-specific semantic validation
        ↓
deterministic host completion/compiler
```

There is no evidence from this experiment series that WellPlot needs to abandon typed semantic workers.

---

## 18.2 Stronger types improved correctness

Moving genuine invariants into the schema correctly rejected impossible states.

This did not increase benchmark success artificially.

TW-03S showed that schema strengthening can cleanly separate:

```text
impossible shape
```

from:

```text
valid shape, wrong answer
```

---

## 18.3 The strengthened type system was not the root problem

At first, TW-04 made it look as if `SectionDraftS` itself might simply be too complex for local Qwen.

TW-05 through TW-07 disproved that interpretation.

Local Qwen successfully handled:

* literal unions;
* ordinary object unions;
* discriminated unions;
* the same branch topology;
* the same semantic complexity.

The critical compatibility difference was the defaulted discriminated track tag representation.

---

## 18.4 The failure was at the structured-output boundary

The problem occurred before Gate A.

This is important.

The sequence was not:

```text
model generates a valid SectionDraftS
        ↓
semantic values happen to be wrong
```

It was usually:

```text
provider request completes
        ↓
response cannot validate as requested structured schema
        ↓
invalid_response
```

That distinction prevented the team from wasting effort on:

* prompt tuning;
* semantic repair;
* better semantic diagnostics;
* LangGraph;
* model critics.

Those mechanisms cannot repair an output that never crosses the structured boundary.

---

## 18.5 Repair is possible but not the first lever

TW-04 showed:

```text
2/6
```

repair-eligible Nemotron semantic failures could be recovered with one bounded repair call.

Therefore targeted semantic repair remains a valid future mechanism.

But it should operate only after the structured output contract is reliable.

The investigation correctly prioritized contract reliability first.

---

# 19. What is specifically ruled out

Within the tested local llama.cpp/Qwen path, the evidence argues against the following explanations for the TW-04 collapse.

Not simply:

```text
Qwen cannot produce structured JSON
```

Historical schema:

```text
20/20
```

Not simply:

```text
the schema is too strict
```

Required strengthened schema:

```text
20/20
```

Not:

```text
Literal / const is unsupported
```

TW-06 U1:

```text
20/20
```

Not:

```text
multiple object models are unsupported
```

TW-06 U2:

```text
20/20
```

Not:

```text
unions are unsupported
```

TW-06 U2:

```text
20/20
```

Not:

```text
discriminated unions are unsupported
```

TW-06 U3:

```text
20/20
```

Not:

```text
the TW-03S normal/reference/array restrictions are inherently incompatible
```

TW-08 R1:

```text
20/20
```

The strongest supported trigger is:

```text
defaulted/optional discriminated track tags
```

in this provider/model/schema path.

---

# 20. What remains unproven

The experimental program intentionally stops short of claims not supported by evidence.

It has not established whether the lower-level implementation behavior belongs specifically to:

* llama.cpp JSON-Schema grammar conversion;
* Qwen generation behavior;
* Pydantic schema interpretation;
* the OpenAI-compatible structured-output interaction;
* another component in the schema-consumer chain.

It also has not independently isolated:

```text
"default" keyword
```

versus:

```text
removal from required
```

because native Pydantic changes both when a field receives a default.

That distinction is not currently necessary for WellPlot's design decision.

The experiments also do not prove that every provider will exhibit the same behavior.

The strongest remediation evidence is specifically for:

```text
local llama.cpp
qwen3.6-35b-a3b
```

---

# 21. Architectural conclusion

The evidence supports the following worker-contract design:

```text
NormalTrackDraftS
    kind: Literal["normal"]          # required
    bindings: curve only

ReferenceTrackDraftS
    kind: Literal["reference"]       # required
    bindings: curve only

ArrayTrackDraftS
    kind: Literal["array"]           # required
    bindings: raster only
    x_scale: required
```

with:

```text
discriminated union on kind
```

and without:

```text
kind = "normal"
kind = "reference"
kind = "array"
```

defaults at the track discriminator boundary.

This gives the desired combination:

```text
strong semantic type guarantees
+
reliable local structured generation
```

The experiment therefore does not support weakening `SectionDraftS` back toward the historical permissive `SectionDraft`.

---

# 22. Implications for future agentic architecture

This investigation originally happened in the context of deciding whether WellPlot should move toward a more agentic/modular generation architecture.

The result strengthens that direction, but also clarifies the sequencing.

The future system can reasonably evolve toward:

```text
planner / decomposer
        ↓
parallel section or component tasks
        ↓
specialized typed semantic workers
        ↓
structural type validation
        ↓
context/task semantic validation
        ↓
deterministic compiler
        ↓
renderer
```

However, orchestration should not compensate for bad contracts.

The TW series demonstrates that a great deal of apparent "LLM unreliability" can actually come from:

* insufficient contracts;
* invalid type relationships;
* structured-output schema representation;
* provider/schema incompatibility.

Those should be isolated before adding more agents.

---

# 23. Experimental methodology worth retaining

Several practices proved particularly valuable and should remain part of WellPlot development.

## Freeze evidence before generation

Do not let expected behavior drift after seeing model failures.

## Preserve failed experiments

Do not rewrite historical slices.

Add corrective experiments.

## Separate semantic and structural errors

They have different remedies.

## Compare working and failing examples

When both exist:

```text
bisect the difference
```

before designing anything new.

## Avoid speculative architecture

TW-05 through TW-08 succeeded because they stayed on established:

* Pydantic;
* JSON Schema;
* existing provider adapter;
* existing typed worker boundary.

No custom grammar was required.

## Require exact controls

Input, prompt, model, request settings, and provider adapter must remain constant when testing schema differences.

## Keep production untouched until evidence is sufficient

The entire diagnostic and remediation-validation sequence remained experimental.

This allowed the causal investigation to finish before changing runtime behavior.

---

# 24. Commit and baseline lineage

| Slice             | Purpose                                    | Final / important commit |
| ----------------- | ------------------------------------------ | ------------------------ |
| TW-00             | Freeze corpus and Gate A                   | `a31ff70`                |
| TW-01             | Initial typed semantic schema              | `6f9a2d6`                |
| TW-02             | Deterministic compiler                     | `c844a9f`                |
| TW-02R            | Correct semantic ownership/contract        | `1f2302c`                |
| TW-02R correction | Evidence correction                        | `afc9f71`                |
| TW-02I            | Typed provider-input sufficiency           | `ad7a0ad`                |
| TW-03             | First provider harness                     | `333dbcb`                |
| TW-03 final       | Corrected provider evidence                | `151efd0`                |
| TW-03S            | Strengthened structural schema             | `21bd657`                |
| TW-04             | Single semantic repair harness             | `602af4d`                |
| TW-04 evidence    | Live evidence                              | `f9cde8b`                |
| TW-04 final       | Evidence correction                        | `91c4151`                |
| TW-05             | Schema compatibility bisect                | `a4a9d31`                |
| TW-05 evidence    | Live evidence                              | `804139f`                |
| TW-05 final       | Partial-S2 evidence correction             | `2e317e1`                |
| TW-06             | Union-form micro-bisect                    | `5c4b3a3`                |
| TW-06 final       | Live evidence                              | `1f5da6e`                |
| TW-07             | Required/defaulted discriminator isolation | `d4c73d3`                |
| TW-07 final       | Live evidence                              | `79f3173`                |
| TW-08             | Required strengthened-schema remediation   | `4fd71c3`                |
| TW-08 evidence    | Live evidence                              | `7088b0d`                |
| TW-08 final       | Prompt evidence correction                 | `68232ee`                |

Final branch state:

```text
eval/mcp-stabilization == 68232ee
```

---

# 25. Final experimental result

The complete program began with a broad reliability problem:

> WellPlot's natural-language semantic generation was brittle, and changes intended to improve one inference case repeatedly caused regressions elsewhere.

The investigation progressively separated:

```text
input sufficiency
schema design
semantic validity
model capability
structured-output compatibility
repair behavior
```

The decisive sequence was:

```text
historical permissive schema:
20/20 local structured generation
        ↓
strengthened schema:
near-total structured collapse
        ↓
union/discriminator bisect
        ↓
discriminated union itself proven compatible
        ↓
defaulted discriminator isolated
        ↓
required/defaulted controlled test:
20/20 vs 0/20
        ↓
full strengthened remediation:
1/20 vs 20/20
        ↓
R1 also 20/20 Gate A
```

The resulting engineering conclusion is:

> **The strengthened typed-worker contract is viable. Its structural guarantees should be retained. For the tested local llama.cpp/Qwen structured-output path, the track discriminator fields must be explicit required fields rather than Pydantic-defaulted tags.**

This conclusion is supported independently by:

1. historical first-attempt evidence;
2. strengthened-schema replay;
3. schema compatibility bisect;
4. union-form bisect;
5. controlled required/defaulted discriminator experiment;
6. full strengthened-schema remediation validation.

No production change has yet been authorized.

---

# 26. Current decision boundary

EXP-TW-08 is complete.

Frozen experimental baseline:

```text
68232ee
```

The diagnostic question has been answered sufficiently for the current architecture.

Another schema compatibility experiment is not presently required.

The next separately authorized step should be a **production-adoption review/slice**, whose purpose would be to determine how the validated required-discriminator representation should replace or supersede the current runtime contract while:

* preserving all TW-03S invariants;
* preserving existing compiler behavior;
* preserving typed input;
* preserving Gate A;
* avoiding unrelated provider or orchestration changes;
* adding regression coverage for the discovered defaulted-discriminator failure mode.

That work is outside this experimental memory and has not yet begun.
