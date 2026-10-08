# WellPlot NLP D4 — Bounded Integrated Live Acceptance Design

## Status

`DESIGN_REWORK_PENDING_REVIEW / HARNESS_NOT_AUTHORIZED / LIVE_INFERENCE_NOT_AUTHORIZED`

Design authorization:

```text
WELLPLOT-NLP-D4-DESIGN-001
```

Design rework authorization:

```text
WELLPLOT-NLP-D4-DESIGN-REWORK-001
```

Current design rework authorization:

```text
WELLPLOT-NLP-D4-DESIGN-REWORK-002
```

Previous design-rework parent:

```text
0a966e1bdb4a4acadf2ea583009e5b9ba7bb1e7b
```

Current design-rework parent:

```text
f07600bf88856d91012192f231be857ccb067744
```

Input baseline:

```text
2c8e851fcd8b315e5d1861652a97984202db7488
WELLPLOT_NLP_D3_ACCEPTED
```

Design branch:

```text
delivery/nlp-d4-live-acceptance-design
```

D1 through D3 are accepted. D4 is the bounded integrated live-acceptance gate from the current NLP completion plan.

This document authorizes **no provider call, endpoint probe, model inference, harness implementation, production change, routing change, prompt change, or release promotion**.

---

# 1. Purpose

D4 answers one release-relevant question:

> Can the current accepted WellPlot Code Mode v2 stack, using the current public default live provider/model configuration, produce safe and scientifically correct scientist-visible outcomes across the two accepted workflows under a small frozen population containing unseen wording, value, source, and failure variations?

D4 is not:

- a planner benchmark;
- a model tournament;
- prompt research;
- a comparison against historical V2R candidates;
- a new Semantic IR experiment;
- a provider-selection exercise;
- a production cutover.

The acceptance object remains the final persisted/rendered artifact or the verified zero-mutation failure outcome.

---

# 2. D4 Phase Separation

D4 must remain split into independently reviewed gates.

## D4A — provider-free harness

Future work may implement the frozen cases, graders, call counter, evidence journal, and preflight checks.

D4A makes:

```text
provider calls = 0
endpoint calls = 0
model calls = 0
program-provider calls = 0
```

D4A must be independently reviewed before live execution.

## D4B — live execution

Only a separate explicit live authorization may run the frozen harness.

No code, case, grader, threshold, model, provider, or source change is permitted between D4B authorization and execution.

## D4C — provider-free finalization

After the live population completes, derive the bounded summary and decision without making more provider calls.

No production promotion follows automatically.

---

# 3. Frozen Live Configuration

D4 evaluates one release-candidate configuration only.

```text
engine: v2
provider_requested: openai
model_requested: gpt-5.4
timeout_seconds: 120
concurrency: 1

planner:
  temperature = 0.0
  max_output_tokens = None / omitted

report worker:
  temperature = None / omitted
  max_output_tokens = None / omitted

section worker:
  temperature = None / omitted
  max_output_tokens = None / omitted

program repair:
  temperature = None / omitted
  max_output_tokens = None / omitted
```

This reflects the frozen production graph rather than a generic provider default:

- `DEFAULT_AUTHORING_ENGINE` is `v2`;
- `create_project_session(... provider="openai")` is the public default;
- the current frozen code resolves the OpenAI default model label to `gpt-5.4`;
- `workflow.py` calls the semantic planner with `temperature=0.0`;
- report/section workers inherit the session temperature, which is `None` in the default route;
- repair generation inherits the worker temperature.

The future live harness must pass the model explicitly as `gpt-5.4`; it must not rely on an environment override.

Decision-bearing model provenance is limited to what the current WellPlot boundary can prove:

```text
requested provider = openai
requested model = gpt-5.4
requested-model drift = 0
WellPlot-side provider fallback = 0
WellPlot-side model fallback = 0
```

D4 does **not** claim that the provider's internal deployed snapshot/model identity was independently observed unless D4A later proves that through a bounded, reviewed observation.

No provider substitution.

No OpenAI-compatible local fallback.

If this exact requested configuration cannot be instantiated at live-execution time:

```text
D4_LIVE_ACCEPTANCE_INCONCLUSIVE
STOP
```

A different provider/model requires a separately reviewed design amendment.

---

# 4. Production Path Under Test

D4 must execute the accepted Code Mode v2 stack:

```text
SemanticPlanner
→ SemanticEnricher
→ ReportProgramCompiler / ProgramSectionCompiler
→ merge
→ deterministic reconciliation
→ AuthoringService execution
→ validation
→ persistence
→ renderer
```

Scientist-facing operations enter through:

```text
DirectNotebookSession.run()
DirectNotebookSession.revise()
DirectNotebookSession.render_logfile_to_file()
```

D4A may compose the session explicitly rather than call the convenience factory only so that a transparent evidence backend can count provider calls and returned usage metrics.

The actual delegated backend must still be the unchanged backend created by the current production OpenAI provider path.

No production module may be changed merely for observability.

---

# 5. Transparent Provider Evidence Wrapper

D4A may define a harness-local `CountingBackend` implementing the existing `ModelBackendProtocol`.

It may wrap the real production backend and delegate:

```text
generate_structured(...)
generate_program(...)
```

without changing arguments or outputs.

This wrapper observes **logical WellPlot generation calls**, not raw HTTP attempts.

It may record only:

- monotonically increasing logical-generation-call index;
- operation kind: `structured` or `program`;
- requested provider label;
- requested model label;
- request temperature;
- request max-output-token setting;
- success/failure;
- stable provider failure category;
- reported input tokens;
- reported output tokens;
- reported total tokens;
- reported provider-call latency;
- local wall-clock latency.

It must not record:

- credentials;
- authorization headers;
- environment dumps;
- raw provider response objects;
- hidden reasoning;
- raw generated program text;
- raw structured provider payloads.

The wrapper has **no retry behavior**.

It enforces the D4 logical-generation-call cap before delegation.

All semantic retries/corrections remain the existing production behavior.

SDK transport retries occur below this wrapper and are accounted for separately; the wrapper must never label its call count as an observed physical HTTP-request count.

---

# 6. Existing Internal Retry Envelope

The production planner already permits at most:

```text
2 logical structured-generation calls per scientist turn
```

(one initial call plus one schema/semantic correction).

Each report/section worker permits:

```text
1 initial logical program-generation call
+ at most 2 bounded repair-generation calls
= 3 logical program-generation calls maximum per worker
```

These are application-level semantic retry/repair limits.

The OpenAI Python SDK has a separate transport-retry policy below `ModelBackendProtocol`.

The frozen repository dependency environment currently resolves:

```text
openai == 2.34.0
```

D4A must provider-free inspect and freeze the actual runtime SDK retry setting. The expected current release-candidate value is:

```text
max_retries = 2
```

If provider-free inspection shows a different value, D4A must STOP for design review rather than silently changing the campaign accounting.

D4 adds no retry outside the production semantic envelope or SDK's frozen transport policy.

No harness-level retry.

No smoke inference.

No selective case rerun.

No automatic resume after interruption.

---

# 7. Real Source Set

D4 uses local external data and does not commit source files.

## CBL construction data

Use exactly the D3 frozen real DLIS pair:

```text
workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis
size = 111573216
sha256 = 3ceb9100fd654d710155672a50a9e0f24ce9705db6ef8e424140f29bd02131f7

workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis
size = 3294924
sha256 = a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640
```

Required channel contract remains the accepted D3 contract.

## LAS revision data

Use:

```text
workspace/data/CBL_Main_REV1.las
```

This source is already referenced by:

```text
examples/cbl_main.log.yaml
```

D4A must perform a provider-free preflight and freeze before any future live authorization:

- file exists;
- file size;
- SHA-256;
- real LAS parsing;
- exact observed channel inventory;
- at minimum scalar `GR`, `CALI`, and `RT`;
- `NPHI` must be absent for the frozen missing-channel case.

If the real LAS is absent, cannot be parsed, lacks a required channel, or contains `NPHI`:

```text
D4A BLOCKED — SOURCE PREFLIGHT
```

Do not substitute synthetic LAS data.

Do not change the case population automatically.

All three real source files remain gitignored and uncommitted.

---

# 8. Provider-Free Starting Artifacts

D4A must construct disposable case-local artifacts before any future inference.

## CBL seed

Reuse the D3 minimum-valid construction scaffold:

```text
main_pass
  source = CBL_Main.dlis
  combo anchor = normal / 50 mm / zero bindings

repeat_pass
  source = CBL_Repeat.dlis
  combo anchor = normal / 50 mm / zero bindings
```

No requested scientific content may be preseeded.

## LAS base seed

Start from the structure of:

```text
examples/cbl_main.log.yaml
```

but stage the frozen real LAS into the disposable case directory as:

```text
CBL_Main_REV1.las
```

Normalize the live-test starting document provider-free to:

```text
title = Original Well Log Report
section id = main
section title = Main Log
tracks = depth, cbl, vdl, gr, cali, rt
GR scale = linear 0..100
GR fills = []
no Resistivity QC track
source basename = CBL_Main_REV1.las
```

All other state becomes preservation baseline.

D4 gold must be derived from this frozen provider-free seed before provider construction.

---

# 9. Population

The D4 population contains:

```text
5 cases
9 scientist turns
1 live attempt per turn
```

There is no repeated stochastic trial and no second arm.

The population intentionally contains:

- unseen wording;
- unseen requested values;
- alternate real channel usage;
- DLIS and LAS source types;
- direct success;
- successive stateful revision;
- ambiguity requiring clarification;
- missing source;
- missing channel.

---

# 10. Case D4-C01 — CBL Construction, Unseen Wording

Workflow:

```text
CBL-CONSTRUCT
```

Sources:

```text
CBL_Main.dlis
CBL_Repeat.dlis
```

One scientist turn.

Frozen request:

```text
Using CBL_Main.dlis as the main-pass data and CBL_Repeat.dlis as the repeat-pass
data, finish the supported cased-hole CBL/VDL report in the existing scaffold.
Keep the existing section identities main_pass and repeat_pass and limit the
report to the heading, remarks, those two strip sections, and the tail.

Use these service titles, in order: "Cement Bond Log", "Variable Density Log",
and "Gamma Ray - CCL".

Set the report metadata to:
Company University of Utah; well FORGE 16B (78)-32; field Utah Forge; county
Beaver; state Utah; section NWSW 32; township 26; range 9; footage
972' FSL & 523' FWL; latitude 38.501242; longitude -112.882661; logging date
08-May-2023; KB 5445.50 ft; GL 5415.00 ft; DF 5445.00 ft; drilling and log
datum Kelly Bushing; top interval 25.00 ft; bottom interval 4845.00 ft; fluid
Fresh Water; run ONE; driller depth 4980.00 ft; logged depth TD Not Tag;
density 8.4 lbm/gal; maximum temperature 177.2 degF; logged by
D. May / D. Jones; witnessed by Leroy Swearingen.

Include three remarks:
1. Supported Reconstruction Scope — reconstruct only the supported heading,
remarks, main pass, repeat pass, and tail; do not invent unsupported well
diagrams, calibration reports, or vendor parameter tables.
2. Data Sources — use the staged DLIS files for the main and repeat passes.
3. Public Data and IP Notice — keep the WellPlot reproduction boundary explicit
and do not recreate vendor disclaimer artwork.

For each pass, use four tracks from left to right:
combo = normal 50 mm; depth = reference 10 mm; cbl = normal 44 mm;
vdl = array 48 mm.

On combo:
ECGR_STGC → "Gamma Ray (ECGR_STGC) QTGC-B", linear 0..150,
#16a34a, width 0.8.
TT → "Transit Time for CBL (TT) QSLT-B", linear 200..400 reversed,
#2142ff, width 0.75.
TENS → "Cable Tension (TENS)", linear 5000..0, #111111 dashed,
width 0.65.
MTEM → "Mud Temperature (MTEM) LEH-MT", linear 100..500,
#111111, width 0.9.

On depth:
STIT → "Stuck Tool Indicator, Total (STIT)", linear 0..50,
#111111, width 0.65.
TDSP → "Cable Drag", linear 0..50, #92400e dotted, width 0.65.
VSEC → "Tool_Tot. Drag", linear 0..50, #1d4ed8 dashed, width 0.65.

On cbl, plot CBL twice with two different binding identities. Both labels are
"CBL Amplitude (CBL) QSLT-B". The first is linear 0..100, #111111, width 0.75.
The second is linear 0..10, #2563eb dashed, width 0.65.

On vdl, plot VDL as a raster labelled
"VDL VariableDensity (VDL) QSLT-B". Use a linear track scale 200..1200,
profile vdl, gray_r, colorbar enabled with label Amplitude in the header, and
sample axis enabled in us from 200 to 1200 with 7 ticks, source origin 40 and
step 10. Hide both vertical main and secondary grid lines.

Use only channels actually present in the staged sources, preserve the full
labels above, and keep the result restrained and readable.
```

This request must not equal the D3 frozen request after normalization.

Acceptance:

```text
DIRECT_CORRECT
CBL-01..CBL-09 PASS
real non-empty render
persisted bytes unchanged by grader/render
```

No user correction is permitted.

---

# 11. Case D4-L01 — Successive LAS Revisions With New Values

Workflow:

```text
LAS-REVISE
```

Source:

```text
CBL_Main_REV1.las
```

Four sequential turns against the same evolving persisted artifact.

## L01-T1

```text
Rename this report "Formation Integrity Review". Do not alter the plotted sections.
```

Expected:

```text
title = Formation Integrity Review
all unrelated state preserved
```

## L01-T2

```text
In Main Log, set the Gamma Ray curve to a linear 5–125 scale. Leave its label and styling unchanged.
```

Expected:

```text
GR scale = linear 5..125
unrelated state preserved
```

## L01-T3

```text
Append a 30 mm normal track named "Resistivity QC" to Main Log. Plot RT on it as "Resistivity QC" with a linear 0–5 scale.
```

Expected:

```text
one new final track
title = Resistivity QC
kind = normal
width = 30 mm
one RT curve
label = Resistivity QC
scale = linear 0..5
prior state preserved
```

## L01-T4

```text
On Main Log's GR track, fill from the Gamma Ray curve to its lower scale boundary with #f2e8a0 at 20% opacity; preserve everything else.
```

Expected:

```text
GR lower-limit fill
color = #f2e8a0
alpha = 0.20
target = grounded GR binding
all previous accepted changes preserved
```

Each turn must:

- persist;
- reload;
- pass a case-specific LAS before/after contract;
- preserve prohibited paths;
- render successfully.

Final state must contain all four cumulative requested changes.

Outcome:

```text
DIRECT_CORRECT
```

for every turn.

---

# 12. Case D4-L02 — Ambiguity Then Explicit Clarification

Provider-free seed:

- two sections;
- titles:
  - `Main Log – Upper`
  - `Main Log – Lower`;
- both are valid real-LAS-backed sections;
- both contain a grounded GR curve starting at linear `0..100`.

## L02-T1 ambiguous request

```text
In Main Log, change the Gamma Ray curve to a linear 20–110 scale.
```

Required outcome:

```text
SAFE_ACTIONABLE_FAILURE
changed = false
persisted bytes exactly unchanged
no submitted intent applied
```

Preferred deterministic category:

```text
enrichment.section_hint_ambiguous
```

A persisted mutation after this request is an immediate release-blocking failure.

## L02-T2 clarification

Only after T1 is proven unchanged:

```text
Apply that 20–110 linear Gamma Ray scale change only to Main Log – Upper.
```

Expected:

```text
Main Log – Upper GR = linear 20..110
Main Log – Lower GR unchanged at linear 0..100
all other state preserved
real render succeeds
```

Case outcome:

```text
CORRECT_AFTER_CLARIFICATION
```

---

# 13. Case D4-L03 — Missing Explicit Source

Seed:

single `Main Log` real-LAS-backed document.

Request:

```text
In Main Log, add a 24 mm normal track titled "Neutron QC" and plot NPHI from missing_neutron.las on it with a linear 0–45 scale.
```

Expected:

```text
SAFE_ACTIONABLE_FAILURE
changed = false
bytes unchanged
no Neutron QC track
no NPHI binding
```

Preferred deterministic category:

```text
enrichment.source_missing
```

Silent fallback to `CBL_Main_REV1.las` is an immediate release-blocking failure.

---

# 14. Case D4-L04 — Channel Unavailable In Valid Source

Precondition:

```text
CBL_Main_REV1.las exists and does not contain NPHI
```

Request:

```text
In Main Log, add a 24 mm normal track titled "Neutron QC" and plot NPHI from CBL_Main_REV1.las on it with a linear 0–45 scale.
```

Expected:

```text
SAFE_ACTIONABLE_FAILURE
changed = false
bytes unchanged
no Neutron QC track
no substituted channel
```

A valid safe terminal failure may occur at planner, enrichment, worker dry-run, or reconciliation boundaries, but it must:

- be non-provider/non-infrastructure;
- expose a non-empty actionable diagnostic/user-report reason;
- leave the artifact exactly unchanged.

Substitution of `GR`, `CALI`, `RT`, or any other available channel is an immediate release-blocking failure.

---

# 15. Unseen-Population Guard

D4A must compute normalized SHA-256 hashes for all nine scientist turns.

It must assert that none is byte-equivalent to the exact accepted D1-D3 scientist requests.

The harness may reuse accepted deterministic starting structures and graders.

It may not reuse the exact accepted request strings as live cases.

No D4 request may be changed after D4A independent acceptance.

---

# 16. Logical Generation and Transport Retry Budgets

No harness retries are authorized.

## Logical generation-call budget

At the WellPlot `ModelBackendProtocol` boundary:

| Case | Turns | Maximum logical generation calls |
| --- | ---: | ---: |
| D4-C01 | 1 | 11 |
| D4-L01 | 4 | 20 |
| D4-L02 | 2 | 7 |
| D4-L03 | 1 | 2 |
| D4-L04 | 1 | 5 |
| **Total** | **9** | **45** |

Derivation:

```text
planner <= 2 logical calls / turn
worker <= 3 logical calls / dispatched worker

CBL:
2 + (3 workers × 3) = 11

one-worker accepted LAS turn:
2 + 3 = 5

pre-worker deterministic rejection:
2
```

The `CountingBackend` must hard-stop **before logical generation call 46 is delegated**.

Logical-call-cap exhaustion is:

```text
D4_LIVE_ACCEPTANCE_INCONCLUSIVE
```

not a semantic failure.

## SDK transport retry budget

The WellPlot logical-call counter does not directly observe SDK-internal HTTP retries.

D4A must freeze the OpenAI SDK's actual runtime `max_retries` value. With the expected current value:

```text
max_retries = 2
```

each logical generation call has at most:

```text
1 initial HTTP attempt + 2 retry attempts = 3 HTTP attempts
```

Therefore the campaign has a theoretical SDK transport-attempt upper bound of:

```text
45 × 3 = 135 HTTP attempts
```

Terminology in all D4 evidence must remain distinct:

```text
logical_generation_calls
sdk_max_retries
physical_http_attempt_upper_bound
```

Do not report `logical_generation_calls` as an observed physical HTTP-request count.

D4 does not add lower-level HTTP instrumentation merely to count attempts.

---

# 17. Execution Ordering

Future D4B must run in exactly this order:

```text
1. D4-C01
2. D4-L01 T1
3. D4-L01 T2
4. D4-L01 T3
5. D4-L01 T4
6. D4-L02 T1
7. D4-L02 T2
8. D4-L03
9. D4-L04
```

Concurrency:

```text
1
```

Do not reorder based on early results.

Semantic failure does not stop the population unless continuing would destroy required case state.

Infrastructure/configuration failure stops the campaign immediately.

---

# 18. Crash-Safe Campaign State / No Resume / No Selective Rerun

D4B uses two local evidence files:

```text
workspace/evaluations/d4-live-acceptance/d4-live-v1.state.json
workspace/evaluations/d4-live-acceptance/d4-live-v1.jsonl
```

A new campaign may start only when **both paths are absent**.

A zero-length pre-existing file is not treated as a fresh campaign.

## Pre-live sequence

Before credentials are read or a real provider/client is constructed:

1. run all provider-free integrity/source/dependency/checkpoint interlocks;
2. require both state and journal paths to be absent;
3. generate one campaign identifier;
4. atomically create the state file with:

```text
experiment_version
campaign_id
production_baseline
live_harness_checkpoint
status = STARTED
logical_generation_calls = 0
```

Only after the durable `STARTED` sentinel exists may the harness load credentials and construct the real provider.

## Interruption semantics

Once a `STARTED` state exists:

- automatic resume is forbidden;
- selective rerun is forbidden;
- appending to another campaign is forbidden;
- merging rows across campaigns is forbidden.

If execution stops after `STARTED` for any reason—including authentication/configuration failure before the first completed turn—the campaign becomes:

```text
WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_INCONCLUSIVE
```

The journal may legitimately contain zero completed turn rows.

Preserve partial evidence.

Do not resume.

Do not rerun only failed cases.

A fresh campaign requires independent review and a new explicit live authorization.

---

# 19. Outcome Taxonomy

Every turn receives exactly one outcome.

## `DIRECT_CORRECT`

The request is accepted without scientist correction and the final persisted/rendered artifact satisfies all deterministic gold.

## `CORRECT_AFTER_CLARIFICATION`

An initial ambiguity fails safely with zero mutation and the frozen clarification produces the correct artifact.

## `SAFE_ACTIONABLE_FAILURE`

The system rejects an impossible/unsafe request, does not mutate the artifact, and returns a bounded actionable reason.

## `DETECTED_INCORRECT_OUTPUT`

The model/provider proposes invalid work but deterministic safety/validation prevents persistence. This is safe but does **not** satisfy a positive case.

## `UNDETECTED_INCORRECT_OUTPUT`

The system reports/persists success but deterministic scientific grading finds the artifact incorrect.

This is release-blocking.

## `UNINTENDED_MUTATION`

A failed/ambiguous request or accepted sparse revision changes state outside the frozen allowed set.

This is release-blocking.

## `INFRASTRUCTURE_INCONCLUSIVE`

Authentication, provider transport, rate limit, timeout exhaustion, configuration failure, interrupted population, or call-cap exhaustion prevents a valid semantic result.

---

# 20. Deterministic Grading

Provider output never grades itself.

## CBL

D4-C01 must use unchanged:

```text
scripts/verify_cbl_packet.py
```

and the direct D3-style canonical assertions.

## LAS positive sequence

Use:

```text
scripts/verify_las_revision.py
```

with D4-specific before/after contracts for the new values.

Every accepted revision must prove:

- required semantic change;
- exact allowed-change surface;
- prohibited paths unchanged;
- persistence;
- reload;
- real render.

## Ambiguity / failures

Capture bytes immediately before the turn.

A safe failure requires:

```text
changed = false
post_bytes == pre_bytes
canonical post-state == canonical pre-state
no prohibited new object
```

The grader, verifier, and renderer must not mutate the acceptance artifact.

---

# 21. Scientist-Visible Success Criteria

D4 passes only if all are true:

## Positive construction

```text
D4-C01 = DIRECT_CORRECT
CBL-01..CBL-09 PASS
```

## Successive revision

All four D4-L01 turns:

```text
DIRECT_CORRECT
```

with cumulative preservation and successful render after every turn.

## Clarification

```text
D4-L02 T1 = SAFE_ACTIONABLE_FAILURE
D4-L02 T2 = CORRECT_AFTER_CLARIFICATION
```

## Negative safety

```text
D4-L03 = SAFE_ACTIONABLE_FAILURE
D4-L04 = SAFE_ACTIONABLE_FAILURE
```

## Population-wide invariants

```text
UNDETECTED_INCORRECT_OUTPUT = 0
UNINTENDED_MUTATION = 0
WellPlot-side provider/model fallback = 0
requested-model drift = 0
call cap exceeded = 0
infrastructure inconclusive turns = 0
```

A safely detected model error in a positive case still means D4 acceptance failed because the user did not receive the requested artifact.

---

# 22. Latency / Retry / Usage Evidence

D4 must measure what is actually observable and label derived bounds separately.

Per logical generation call:

- logical call index;
- operation type;
- requested provider/model;
- request temperature;
- request max-output-token setting;
- backend-observed latency;
- input tokens if returned;
- output tokens if returned;
- total tokens if returned;
- success/failure category.

Per scientist turn:

- total wall-clock duration;
- logical generation-call count;
- structured logical-call count;
- program logical-call count;
- worker repair count;
- worker count;
- success/failure;
- render duration.

Population:

- total logical generation calls;
- frozen SDK `max_retries`;
- physical HTTP-attempt upper bound;
- total reported tokens;
- median and maximum turn latency;
- total repairs;
- turns with repair;
- provider failure count.

D4 does not claim to observe exact physical HTTP-attempt count through `CountingBackend`.

No monetary cost threshold is frozen in D4 unless a rate card is separately frozen before D4B authorization.

Token/latency evidence is descriptive in this gate.

Scientific correctness and mutation safety are decision-bearing.

---

# 23. Evidence Journal

Future live raw evidence stays local under:

```text
workspace/evaluations/d4-live-acceptance/
```

Canonical campaign-state file:

```text
d4-live-v1.state.json
```

Canonical turn journal:

```text
d4-live-v1.jsonl
```

Case-local artifacts may be retained under case directories.

The state file contains bounded campaign-lifecycle evidence such as:

- experiment version;
- campaign ID;
- production baseline;
- live harness checkpoint;
- status;
- logical-generation-call count.

The JSONL must contain bounded turn evidence only:

- experiment version;
- campaign ID;
- production baseline;
- live harness checkpoint;
- case ID;
- turn ID;
- execution index;
- request SHA-256;
- starting artifact SHA-256;
- ending artifact SHA-256;
- render SHA-256 where applicable;
- requested provider/model labels;
- result status;
- apply status;
- outcome taxonomy;
- diagnostics codes/stages;
- worker metrics;
- logical-call/usage/latency aggregates;
- frozen SDK retry setting;
- physical HTTP-attempt upper bound;
- verifier requirement statuses;
- diff/grader status.

Do not store:

- API keys;
- headers;
- environment dumps;
- absolute local data paths;
- raw provider responses;
- raw generated programs;
- hidden reasoning.

The committed final result records hashes of the local state/journal evidence, not local source data.

---

# 24. Harness Integrity and Runtime Provenance

D4 has two distinct checkpoint identities.

## Frozen production baseline

```text
production_baseline =
2c8e851fcd8b315e5d1861652a97984202db7488
```

This is the accepted D3 production behavior.

## Future accepted harness checkpoint

```text
live_harness_checkpoint =
<future independently accepted D4A SHA>
```

D4B runs from the exact D4A checkpoint, not directly from the D3 commit.

Before credentials are read or the `STARTED` state is created, D4B provider-free preflight must authenticate:

- `git HEAD == live_harness_checkpoint`;
- clean Git working tree;
- exact case-population fixture hash;
- exact gold/grader fixture hash;
- exact live harness source hash;
- all three local source hashes;
- source channel preconditions;
- both campaign state/journal paths absent;
- exact `uv.lock` SHA-256;
- installed `openai` package version equals the D4A-frozen version;
- actual runtime OpenAI SDK `max_retries` equals the D4A-frozen value;
- requested provider/model configuration equals `openai / gpt-5.4`.

D4A must also freeze hashes at both checkpoints for all authorized production components relevant to the live path, including at minimum:

- planner;
- workflow;
- capability/report/section safety layers;
- enrichment;
- report worker;
- section worker;
- repair coordinator;
- provider backend/client loader;
- direct notebook adapter;
- reconciler/executor/persistence surfaces;
- CBL/LAS verifiers.

D4B must prove the authorized production components at `live_harness_checkpoint` are byte-identical to their versions at `production_baseline`.

D4A harness/scripts/tests/docs may differ from D3.

Production behavior may not.

The current repository lock resolves:

```text
openai == 2.34.0
```

D4A must freeze the observed provider-free runtime version rather than relying only on this prose.

Any checkpoint, production hash, dependency version, retry setting, source, or working-tree mismatch yields:

```text
WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_INCONCLUSIVE
```

before provider construction.

The harness must fail before credentials are read if any frozen artifact differs.

---

# 25. Credential Boundary

Credentials use the existing production loader.

D4 evidence may record only:

```text
credential_source = configured
```

or equivalent bounded state.

Do not print, hash, serialize, or inspect the secret value.

D4A provider-free tests must use fake credentials/clients only.

---

# 26. Expected D4A Implementation Scope

Subject to independent design acceptance, expected provider-free harness files are:

```text
scripts/nlp_d4_live_acceptance.py
tests/test_nlp_d4_live_acceptance.py
tests/fixtures/nlp_d4_live_cases.json
tests/fixtures/nlp_d4_live_gold.json
docs/nlp-d4-live-harness-result.md
```

No production file is expected to change.

The cases file contains scientist requests and non-secret case metadata.

The gold file contains deterministic evaluator expectations.

The live provider receives only normal production context and the scientist request; evaluator gold must never be included in provider prompts.

---

# 27. D4A Provider-Free Tests

The future harness must prove without inference:

- exact nine-turn schedule;
- exact 45 logical-generation-call hard cap;
- logical call 46 rejected before delegation;
- no wrapper retries;
- frozen OpenAI SDK version;
- frozen SDK `max_retries`;
- correct physical HTTP-attempt upper-bound derivation;
- planner request temperature is exactly `0.0`;
- report/section/repair request temperatures are omitted/`None`;
- max-output-token settings are omitted/`None`;
- requested provider/model are exactly `openai / gpt-5.4`;
- no WellPlot-side provider/model fallback path;
- source preflight occurs before backend construction;
- source hashes/channels recorded without source bytes entering evidence;
- request hashes frozen;
- known D1-D3 exact request duplicates rejected;
- production-baseline and live-harness-checkpoint identities remain distinct;
- authorized production hashes at the harness checkpoint equal the D3 production baseline;
- dirty/mismatched harness checkpoint prevents execution;
- dependency/retry mismatch prevents execution;
- existing state file prevents execution;
- existing journal prevents execution;
- `STARTED` state is written atomically before credential/provider construction;
- a synthetic crash after `STARTED` and before first turn cannot be resumed;
- credentials are not accessed before all provider-free interlocks and durable `STARTED` state creation;
- raw provider/program text is absent from evidence rows;
- expected case ordering;
- positive and negative grader behavior using deterministic fake results;
- terminal summary derivation from synthetic complete/incomplete populations;
- no production mutation by harness preparation.

D4A itself must make zero endpoint/provider/model calls.

---

# 28. Terminal D4 Decisions

Only three top-level decisions are permitted:

```text
WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_PASSED
WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_FAILED
WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_INCONCLUSIVE
```

## PASSED

All criteria in Section 21 pass.

## FAILED

The population is complete and infrastructure-valid, but one or more semantic/scientific/safety criteria fail.

Examples:

- a positive case fails safely;
- wrong scientific artifact;
- wrong source/channel;
- unexpected mutation;
- ambiguity is silently resolved;
- missing source/channel is substituted;
- requested artifact cannot be rendered.

## INCONCLUSIVE

The population cannot be validly completed because of infrastructure/configuration/evidence integrity.

No semantic threshold may convert an infrastructure run into FAILED.

---

# 29. Failure Does Not Authorize Research

A valid `FAILED` result closes that D4 campaign.

It may motivate a separately scoped bounded engineering issue.

It does **not** authorize:

- prompt tuning during the campaign;
- model switching;
- another holdout;
- another model comparison;
- replaying only failures;
- changing graders after seeing results;
- reopening Semantic IR research.

A new live campaign requires a new reviewed design/authorization.

---

# 30. Release Boundary

Even:

```text
WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_PASSED
```

does not itself switch production routing or publish a release.

It establishes evidence for a later explicit release/promotion decision.

Production promotion remains separately governed.

# 32. D4 Design Rework 002 — Real LAS Population Correction

Status:

```text
WELLPLOT-NLP-D4-DESIGN-REWORK-002 / PROVIDER_FREE_REVIEW_PENDING
```

This section is the authoritative replacement for the LAS-specific portions of
Sections 7, 8, 11, 12, 13, and 14 above. It does not authorize D4A
implementation, provider construction, credentials, or live inference. The
CBL population and all non-source D4 controls remain unchanged.

## 32.1 Source decision

The original `CBL_Main_REV1.las` contract is superseded because the real file
does not contain `GR`, `CALI`, or `RT`. The selected real source is:

```yaml
path: workspace/data/30-23a-3 8117_d.las
basename: 30-23a-3 8117_d.las
size: 5987785
sha256: 7e6c69c65713dc33303362ab91b767eb06371fd24a31856add8650e6d3bee1a9
parse: PASS
```

The complete channel inventory observed through the repository LAS loader is:

```text
CAL, CALI, CGR, DRHO, DT, DTL, GR, GRD, ILD, ILM, MSFL,
NPHI, PEF, POTA., RHOB, SFLU, SP, THOR, URAN
```

The source depth range is `336.5..10242.5 FT`. The proposed ambiguity windows
are valid and intentionally share the `9300 ft` boundary sample. With the
observed 0.5-ft sampling, each inclusive window contains 1,801 samples; the
shared boundary is deliberate and does not create an ambiguous section because
the section identities and window assignments are explicit:

```yaml
upper:
  minimum_ft: 8400
  maximum_ft: 9300
  observed_samples: 1801
lower:
  minimum_ft: 9300
  maximum_ft: 10200
  observed_samples: 1801
```

The source is external, local, gitignored, and must not be committed or copied
into Git. The source contract is intentionally mnemonic-exact:

```yaml
GR: present
CALI: present
ILD: present
ILM: present
MSFL: present
NPHI: present
RT: absent
```

No `ILD`, `ILM`, or `MSFL` value is an alias for `RT` in this contract.

## 32.2 Revised LAS seed

The LAS seed is one fully enumerated canonical document backed by the selected
source. D4A must construct this mapping exactly; it must not inherit unspecified
track, binding, style, or reference state from another example:

```yaml
document:
  title: Original Well Log Report
  subtitle: null
  remarks: []
  sections:
    - id: main
      title: Main Log
      subtitle: null
      source:
        basename: 30-23a-3 8117_d.las
        format: las
      tracks:
        - id: depth
          title: Depth
          kind: reference
          width_mm: 16.0
          position: 1
          reference:
            axis: depth
            define_layout: true
            unit: ft
            scale_ratio: 200
            major_step: 50
            secondary_grid:
              display: true
              line_count: 5
          bindings: []
        - id: gr
          title: Gamma Ray
          kind: normal
          width_mm: 28.0
          position: 2
          style:
            color: '#b71c1c'
            line_style: solid
            line_width: 0.8
          bindings:
            - id: main.gr.GR.1
              kind: curve
              channel: GR
              label: Gamma Ray
              scale: {kind: linear, minimum: 0.0, maximum: 100.0, reverse: false}
              style:
                color: '#b71c1c'
                line_style: solid
                line_width: 0.8
          fills: []
        - id: porosity
          title: Neutron Porosity
          kind: normal
          width_mm: 28.0
          position: 3
          style:
            color: '#1b5e20'
            line_style: solid
            line_width: 0.8
          bindings:
            - id: main.porosity.NPHI.1
              kind: curve
              channel: NPHI
              label: Neutron Porosity
              scale: {kind: linear, minimum: 0.0, maximum: 45.0, reverse: false}
              style:
                color: '#1b5e20'
                line_style: solid
                line_width: 0.8
          fills: []
  report_defaults:
    page: default
    depth_range: full_source
    output: case_local_only
  compatibility_mirrors: deterministic_only
  absent_optional_fields: null
```

The complete seed contract is exactly three tracks in positions 1–3, two
scalar curve bindings with the IDs shown above, no fills, no remarks, no
subtitle, and no Resistivity QC track. The renderer's `default` page and
`full_source` depth range are host defaults, while `case_local_only` output is
never part of the scientist-visible semantic acceptance state. Any compatibility
mirror generated by canonical persistence is deterministic and included in the
before/after preservation projection. The seed must not preload the later ILD
QC track or GR fill. Gold is derived from this exact seed before any future
provider construction.

## 32.3 Revised LAS requests and gold

The CBL request remains byte-for-byte unchanged. The four L01 requests retain
their successive-revision semantics; L01-T3 now uses the real `ILD` channel and
its established logarithmic scale. L02 preserves the two-section ambiguity and
clarification. L03 tests explicit missing-source custody even though `NPHI` is
available in the valid source. L04 tests the absence of `RT` and forbids
substitution by `ILD`, `ILM`, or `MSFL`.

```yaml
D4-L01:T1: "Rename this report \"Formation Integrity Review\". Do not alter the plotted sections."
D4-L01:T2: "In Main Log, set the Gamma Ray curve to a linear 5–125 scale. Leave its label and styling unchanged."
D4-L01:T3: "Append a 30 mm normal track named \"Resistivity QC\" to Main Log. Plot ILD on it as \"Resistivity QC\" with a logarithmic 0.2–2000 scale."
D4-L01:T4: "On Main Log's GR track, fill from the Gamma Ray curve to its lower scale boundary with #f2e8a0 at 20% opacity; preserve everything else."
D4-L02:T1: "In Main Log, change the Gamma Ray curve to a linear 20–110 scale."
D4-L02:T2: "Apply that 20–110 linear Gamma Ray scale change only to Main Log – Upper."
D4-L03:C01: "In Main Log, add a 24 mm normal track titled \"Neutron QC\" and plot NPHI from missing_neutron.las on it with a linear 0–45 scale."
D4-L04:C01: "In Main Log, add a 24 mm normal track titled \"Resistivity Alias QC\" and plot RT from \"30-23a-3 8117_d.las\" on it with a logarithmic 0.2–2000 scale."
```

Expected outcomes remain `DIRECT_CORRECT` for all four L01 turns,
`SAFE_ACTIONABLE_FAILURE` for L02-T1, `CORRECT_AFTER_CLARIFICATION` for
L02-T2, and `SAFE_ACTIONABLE_FAILURE` for L03 and L04. L03 must not fall back
from `missing_neutron.las` to the valid source. L04 must not create a track or
binding and must not substitute `ILD`, `ILM`, `MSFL`, or any other channel for
the requested `RT`.

## 32.4 Recomputed request identities

Normalized hashes use the existing D4 newline/trailing-space normalization. The
following nine values are frozen by this rework and must be reproduced by D4A:

```yaml
D4-C01:C01: 5ef3a1e528b2e539dcd895ec09767547151a7706eff911a99cc050c61d7d8f3c
D4-L01:T1: 0ffe99d4e0131f2649370730e913cd5147f73dccff24ed0f2d1ce928b2f41a34
D4-L01:T2: 866ff67469139034c2062f1c668283c5532d0fc69fd711ed8e55e6c71d12d5f8
D4-L01:T3: 49405cb494cc3cead9cc015c99ef6e0e048583d716be3421930c39d995b95136
D4-L01:T4: 0819dd6cb0964cc61752c96682aa4fa2b8924c6a47bb57e7897bd0b5ec52557b
D4-L02:T1: 6bc23defbb254104f567c7a3c2caf33b77ad06f6d0dd124c3dc9b796f3fda541
D4-L02:T2: eee91c864757d6a4d8f23d906928964318868c8063f5e61e3afba4c794ee32c9
D4-L03:C01: ee73de7b557d7f624125cb2c469ce0df1d27c9a6a6c0a21545f28bee98d3d237
D4-L04:C01: bb38915973039b15a8b266b7ca2b7ad6faed2599eb8d8465d60bee662dce7ed6
```

The population remains exactly five cases, nine turns, one attempt per turn,
concurrency one, and the original execution order. The logical-call budget
remains `11 + 20 + 7 + 2 + 5 = 45`; any changed worker envelope stops D4A for
design review. All configuration, custody, evidence, retry, checkpoint,
production-identity, and terminal-decision controls remain unchanged.

## 32.5 Governance transition

The previous D4A authorization is suspended and cannot be resumed against this
amended population:

```yaml
WELLPLOT-NLP-D4A-AUTH-001: SUSPENDED / SUPERSEDED-PENDING-DESIGN-REWORK
D4A implementation: NOT AUTHORIZED
D4B live inference: NOT AUTHORIZED
provider_calls: 0
endpoint_calls: 0
model_calls: 0
```

After independent acceptance of this design rework, a new D4A implementation
authorization must be issued from its exact accepted checkpoint. This document
is the design-only handoff and stops for independent closure review.

---

# 31. D4 Design Decision

```text
WELLPLOT-NLP-D4-DESIGN-001
```

Reworked under:

```text
WELLPLOT-NLP-D4-DESIGN-REWORK-001
```

Selected approach:

```text
one current release-candidate configuration
five frozen integrated cases
nine scientist turns
real local DLIS + LAS sources
one attempt per turn

45 logical generation calls maximum
OpenAI SDK retry policy frozen separately
physical HTTP attempts represented only as an upper bound

planner temperature fixed at 0.0
worker/repair temperature omitted

requested provider/model provenance only
no unsupported remote snapshot claim

crash-safe STARTED campaign sentinel
no automatic resume

separate D3 production baseline and future D4A harness checkpoint
production-byte identity required
runtime OpenAI version + retry policy frozen

final-artifact and zero-mutation grading
no model comparison
no harness retry
```

The scientific population remains unchanged from the initial D4 design.

D4A implementation remains unauthorized until independent closure review accepts this reworked design.

Live inference remains unauthorized until:

1. D4 design acceptance;
2. provider-free D4A harness implementation;
3. independent D4A harness review;
4. explicit D4B live-execution authorization.

D4 production promotion is not authorized by any of those gates.

Current status:

```text
D4A HARNESS IMPLEMENTATION: NOT AUTHORIZED
D4B LIVE INFERENCE: NOT AUTHORIZED
PRODUCTION PROMOTION: NOT AUTHORIZED
```

Stop for independent D4 design closure review.
