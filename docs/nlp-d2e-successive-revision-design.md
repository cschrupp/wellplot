# WellPlot NLP D2E — Integrated Successive LAS Revision Design

## Status

`DESIGN_ONLY / IMPLEMENTATION_NOT_AUTHORIZED`

Design authorization: `WELLPLOT-NLP-D2E-DESIGN-001`

Input baseline: `2ac0724747074a2626f79efa06ef5b8b9ee7914b` (`WELLPLOT_NLP_D2D_ACCEPTED`)

Design branch: `delivery/nlp-d2e-successive-revision-design`

This document freezes the D2E design only. It authorizes no production edit, no test implementation, no provider or endpoint call, no model inference, and no D3/D4 work.

## Delivery Requirement

D2E closes the integrated `LAS-REVISE` sequence required by the NLP completion plan.

D1 through D2D independently proved the individual revision capabilities:

- `LAS-02` — report-title mutation;
- `LAS-05` — existing-curve scale mutation;
- `LAS-03` / `LAS-04` — track plus grounded curve creation;
- `LAS-06` — grounded fill creation;
- `LAS-08` — fail-closed ambiguity / unavailable source / unavailable channel behavior;
- `LAS-01`, `LAS-07`, and `LAS-09` — grounding, preservation, persistence, reload, and rendering around those verticals.

D2E does **not** add another authoring capability.

Its acceptance object is one evolving persisted logfile subjected to successive public natural-language revisions.

The required invariant is:

```text
S0
  -> accepted revision 1 -> S1
  -> accepted revision 2 -> S2
  -> accepted revision 3 -> S3
  -> accepted revision 4 -> S4
  -> rejected revision   -> S4 exactly
```

Every accepted request must read the state persisted by all prior accepted requests. A later revision may not reconstruct from the original fixture, forget prior mutations, or overwrite unrelated accepted state.

## Why D2E Exists

Passing D1, D2A, D2B, and D2C independently does not prove successive revision correctness.

A system can pass isolated tests while still failing an actual notebook workflow if it:

- plans against stale state;
- rebuilds from the original fixture on each call;
- loses a prior report mutation during a section mutation;
- loses a prior scale mutation while appending a track;
- loses a newly added track when adding a fill;
- rejects an invalid later request only after partially rewriting the document;
- persists one revision but supplies stale worker context to the next revision.

D2E is therefore a state-continuity acceptance slice, not another feature slice.

## Architectural Basis

The current public adapter already reloads the logfile on every `DirectNotebookSession.revise()` call through `_load_document_context()`.

The compile graph then receives that current canonical document and projects:

- a bounded planner `current_document_summary`;
- current section identities;
- current track/binding identities;
- current existing-curve presentation state;
- currently declared source/channel context.

Accepted revisions are applied through the private canonical authoring transaction and persisted back to the same logfile before the next call.

Therefore the expected D2E implementation is an integrated acceptance test over the existing D1-D2D path. No production change is expected.

If the integrated sequence exposes stale-state, overwrite, or persistence behavior that violates this design, implementation must STOP for a scope amendment instead of repairing production opportunistically.

---

# Frozen Starting Fixture — S0

Construct one deterministic test-local logfile from:

```text
create_mcp_fixture_paths(...).single_logfile
```

The fixture must combine the already accepted D1 and D2A starting conditions without adding any new scientific semantics.

Before the first public revision, establish and verify:

```text
report title:
  Original Well Log Report

section:
  id: main
  title: Main Log

ordered tracks:
  depth, cbl, vdl, gr, cali, rt

track count:
  6

GR curve:
  binding_id: main.gr.GR.3
  channel: GR
  scale: linear 0 to 100
  reverse: false

GR fills:
  0

existing CALI curve:
  binding_id: main.cali.CALI.4
  channel: CALI

Caliper QC track:
  absent

declared source:
  fixture.las
```

The title setup and GR-scale setup are test-fixture preparation only.

The resulting S0 logfile must load through the normal logfile/canonical path and render before the sequence starts.

Do not modify a committed fixture asset.

---

# Frozen Successive Revision Sequence

D2E must execute exactly the following five scientist requests, in this order, against the **same logfile** and through the **same DirectNotebookSession instance**.

## Step 1 — S0 -> S1 — D2A Report Title

Frozen request:

```text
Change the report title to "Gamma Ray Quality Control Review".
```

Required transition:

```text
/title:
Original Well Log Report
->
Gamma Ray Quality Control Review
```

Immediate permitted semantic-change roots:

```text
/title
/extensions/compatibility/legacy_document/header/title
```

Required public result:

```text
success = true
changed = true
apply_status = persisted
```

Expected graph ownership:

```text
report workers  = 1
section workers = 0
worker_count    = 1
failed_workers  = 0
```

The planner call must be revision mode and its current document summary must show the S0 title before this mutation.

After persistence/reload:

- the target title is present;
- the GR scale remains 0-100;
- the original six tracks remain unchanged;
- no fill exists.

Render S1 to a real non-empty PDF.

Run the frozen D0 verifier for the S0 -> S1 transition and require:

```text
LAS-01 PASS
LAS-02 PASS
LAS-07 PASS
LAS-09 PASS
workflow_status PASS
```

## Step 2 — S1 -> S2 — D1 Existing GR Scale

Frozen request:

```text
Change the Gamma Ray curve scale to a linear scale from 10 to 100.
```

Required transition:

```text
GR / main.gr.GR.3
linear 0-100
->
linear 10-100
reverse=false
```

Immediate permitted semantic-change roots:

```text
/sections/0/tracks/3/bindings/0/scale
/extensions/compatibility/legacy_document/bindings/channels/2/scale
/sections/0/tracks/3/bindings/0/extensions/compatibility/legacy_binding/scale
```

Required continuity evidence before the worker emits its program:

- planner `current_document_summary.title` equals `Gamma Ray Quality Control Review`;
- the grounded existing-curve inventory identifies the exact GR track/binding;
- the grounded GR inventory reports the pre-step scale as linear 0-100.

Required public result:

```text
success = true
changed = true
apply_status = persisted
```

Expected graph ownership:

```text
section workers = 1
report workers  = 0
worker_count    = 1
failed_workers  = 0
```

After persistence/reload:

- the D2A report title remains unchanged;
- GR is linear 10-100;
- the original six tracks remain;
- no fill exists.

Render S2 to a real non-empty PDF.

Run the frozen D0 verifier for S1 -> S2 and require:

```text
LAS-01 PASS
LAS-05 PASS
LAS-07 PASS
LAS-09 PASS
workflow_status PASS
```

## Step 3 — S2 -> S3 — D2B Caliper QC Track + Grounded CALI Curve

Frozen request:

```text
In the Main Log section, add a new normal track titled "Caliper QC" at the end, 28 mm wide, and plot the CALI curve on it labeled "Caliper QC" with a linear scale from 6 to 12.
```

Required transition:

- append exactly one seventh normal track;
- title `Caliper QC`;
- width `28` mm;
- one new scalar curve using inspected channel `CALI`;
- label `Caliper QC`;
- scale linear 6-12, reverse=false.

Immediate permitted semantic-change roots:

```text
/sections/0/tracks/6
/extensions/compatibility/legacy_document/layout/log_sections/0/tracks/6
/extensions/compatibility/legacy_document/bindings/channels/5
```

Required continuity evidence before the worker emits its program:

- planner summary still contains the accepted S1 report title;
- the worker receives current inspected `CALI` scalar source context;
- the worker's grounded existing-curve inventory shows the GR binding at linear 10-100, proving it is operating on S2 rather than S0/S1.

Required public result:

```text
success = true
changed = true
apply_status = persisted
```

Expected graph ownership:

```text
section workers = 1
report workers  = 0
worker_count    = 1
failed_workers  = 0
```

After persistence/reload:

- the report title remains the D2A title;
- GR remains linear 10-100;
- the original first six tracks remain in their original order;
- the seventh track is Caliper QC with its grounded CALI curve;
- GR still has no fill.

The new track and binding IDs are allocator-owned. Do not freeze them as scientist-specified values. Capture their observed canonical identities for later continuity checks.

Render S3 to a real non-empty PDF.

Run the frozen D0 verifier for S2 -> S3 and require:

```text
LAS-01 PASS
LAS-03 PASS
LAS-04 PASS
LAS-07 PASS
LAS-09 PASS
workflow_status PASS
```

## Step 4 — S3 -> S4 — D2C Grounded GR Fill

Frozen request:

```text
In the Main Log section, on the GR track, fill from the Gamma Ray curve to its lower scale limit using light gray (#d9d9d9) at 25% opacity.
```

Required transition:

exactly one fill is added to the existing GR track with:

```text
kind       = to_lower_limit
binding_id = main.gr.GR.3
color      = #d9d9d9
alpha      = 0.25
```

Immediate permitted semantic-change roots:

```text
/sections/0/tracks/3/fills/0
/extensions/compatibility/legacy_document/bindings/channels/2/fill
/sections/0/tracks/3/bindings/0/extensions/compatibility/legacy_binding/fill
```

Required continuity evidence before the worker emits its program:

- planner summary still contains the accepted D2A title;
- grounded GR inventory shows linear 10-100;
- grounded existing-curve inventory also contains the S3 Caliper QC CALI binding using the observed S3 binding identity;
- the Caliper QC curve remains linear 6-12.

That worker evidence is required to prove the S3 persisted structural mutation became input context for S4.

Required public result:

```text
success = true
changed = true
apply_status = persisted
```

Expected graph ownership:

```text
section workers = 1
report workers  = 0
worker_count    = 1
failed_workers  = 0
```

After persistence/reload:

- title remains the D2A title;
- GR scale remains 10-100;
- the seven-track order is unchanged;
- the S3 Caliper QC track/binding is unchanged;
- exactly one requested GR fill exists.

The fill ID remains allocator-owned. Capture and prove that its non-empty identity survives persistence/reload; do not treat the ID itself as a scientific expected value.

Render S4 to a real non-empty PDF.

Run the frozen D0 verifier for S3 -> S4 and require:

```text
LAS-01 PASS
LAS-06 PASS
LAS-07 PASS
LAS-09 PASS
workflow_status PASS
```

## Step 5 — S4 -> S4 — D2D Missing Explicit Source Rejection

Frozen request:

```text
In the Main Log section, add a normal track titled "Neutron" and plot NPHI from missing.las on it.
```

The deterministic planner must preserve:

```text
existing_section_hint = Main Log
source_hints = (missing.las,)
```

Required continuity evidence before invocation:

- the exact S4 bytes are captured;
- the exact S4 canonical document is captured;
- all four prior accepted semantic changes are present.

The planner summary must still contain the accepted D2A title.

Expected path:

```text
DirectNotebookSession.revise()
-> Main Log resolves uniquely
-> current explicit source inventory
-> missing.las matches no candidate
-> enrichment.source_missing
-> zero workers
-> compile_failed
-> no submitted intent
-> zero mutation
```

Required public result:

```text
success = false
changed = false
apply_status = compile_failed
submitted_intent = None
```

Required diagnostic:

```text
stage = enrichment
code  = enrichment.source_missing
```

Expected graph ownership:

```text
worker_count       = 0
successful_workers = 0
failed_workers     = 0
report workers     = 0
section workers    = 0
```

After rejection require:

```text
post-rejection bytes     == S4 bytes
post-rejection canonical == S4 canonical
```

The title, GR scale, Caliper QC track/binding, and GR fill must all remain present and identical.

Render the unchanged post-rejection S4 logfile to a real non-empty PDF.

Run the frozen D0 rejected-workflow verifier and require:

```text
LAS-01 PASS
LAS-07 PASS
LAS-08 PASS
LAS-09 PASS
workflow_status PASS
```

---

# Single-Session / Single-Artifact Contract

The primary D2E acceptance test must use:

- one test-local logfile path;
- one `DirectNotebookSession` instance;
- five successive calls to `revise()`;
- no reconstruction call between revisions;
- no fixture rewrite/reset after S0;
- no direct mutation of the logfile between public revision calls.

Snapshots may be copied **only for evidence** after each public call.

The test must fail if any helper recreates the fixture between steps.

This is essential: D2E accepts continuity of one evolving artifact, not five isolated repetitions of prior tests.

---

# Deterministic Planner / Worker Design

D2E must make zero provider, endpoint, or real-model calls.

A deterministic routing planner may dispatch one of the five already accepted semantic plans by exact request identity.

It must record all five planner calls.

Required planner evidence:

```text
call count = 5
mode for every call = revise
request order = exact frozen sequence
```

Current-document summary evidence must show:

```text
Step 1 planner sees:
  title = Original Well Log Report

Steps 2-5 planners see:
  title = Gamma Ray Quality Control Review
```

A deterministic report backend may emit only the accepted D2A title program.

A deterministic section backend may emit only the already accepted D1, D2B, and D2C programs.

The D2D missing-source step must fail before any worker dispatch.

Expected successful worker sequence across the first four calls:

```text
Step 1: report
Step 2: section
Step 3: section
Step 4: section
```

Step 5 dispatches none.

No repair is expected for Steps 1-4. Any unexpected repair must be reported as evidence and independently reviewed rather than silently ignored.

---

# Immediate Transition Verification

For each accepted transition, create an evidence-only before snapshot immediately before the public call and grade the post-call logfile with the frozen `scripts/verify_las_revision.py`.

Do not modify the verifier.

Each transition must retain the exact narrow accepted change roots from its source slice.

No ignored paths are allowed.

The sequence test must additionally assert that all earlier accepted state is identical across each later transition unless that exact state is the current requested target.

Examples:

- S1 title must survive S1 -> S2, S2 -> S3, and S3 -> S4.
- S2 GR scale must survive S2 -> S3 and S3 -> S4.
- S3 Caliper QC track/binding must survive S3 -> S4.
- S4 must survive the rejected fifth request exactly.

---

# Cumulative S0 -> S4 Acceptance

D2E must also grade the complete accepted sequence as one cumulative S0 -> S4 transition using the frozen D0 verifier.

The cumulative acceptance must require all positive LAS mutation dimensions:

```text
LAS-02 report title
LAS-03 added track
LAS-04 added CALI binding
LAS-05 GR scale
LAS-06 GR fill
```

and must permit differences only within the union of the already accepted mutation roots:

```text
/title
/extensions/compatibility/legacy_document/header/title

/sections/0/tracks/3/bindings/0/scale
/extensions/compatibility/legacy_document/bindings/channels/2/scale
/sections/0/tracks/3/bindings/0/extensions/compatibility/legacy_binding/scale

/sections/0/tracks/6
/extensions/compatibility/legacy_document/layout/log_sections/0/tracks/6
/extensions/compatibility/legacy_document/bindings/channels/5

/sections/0/tracks/3/fills/0
/extensions/compatibility/legacy_document/bindings/channels/2/fill
/sections/0/tracks/3/bindings/0/extensions/compatibility/legacy_binding/fill
```

The cumulative D0 acceptance must assert final scientific values rather than merely checking that some difference exists.

Required cumulative result:

```text
LAS-01 PASS
LAS-02 PASS
LAS-03 PASS
LAS-04 PASS
LAS-05 PASS
LAS-06 PASS
LAS-07 PASS
LAS-09 PASS
workflow_status PASS
```

`LAS-08` is supplied by the final rejected S4 -> S4 request.

Together, the cumulative accepted-sequence verdict plus final rejection must establish integrated evidence for all:

```text
LAS-01 through LAS-09
```

without adding a new verifier.

## Cumulative Preservation Boundary

At minimum, the cumulative acceptance must prohibit unrelated mutation under:

```text
/subtitle
/header
/remarks
/page
/depth
/output
/sections/0/data_source
/sections/0/tracks/0
/sections/0/tracks/1
/sections/0/tracks/2
/sections/0/tracks/4
/sections/0/tracks/5
```

The allowlist remains authoritative for all other paths: any S0 -> S4 difference outside the accepted union is a D2E failure.

---

# Final S4 Scientific State

Before the rejection step, and again after it, the canonical document must establish:

```text
report title:
  Gamma Ray Quality Control Review

section:
  main / Main Log

tracks:
  original six in original order
  plus one seventh Caliper QC track

GR:
  binding main.gr.GR.3
  linear scale 10-100
  reverse=false
  exactly one lower-limit fill
  fill color #d9d9d9
  fill alpha 0.25

existing CALI:
  main.cali.CALI.4 remains unchanged

new Caliper QC:
  kind normal
  width 28
  exactly one CALI curve
  label Caliper QC
  linear scale 6-12
  reverse=false
```

No second Caliper QC track, duplicate added fill, accidental NPHI binding, or unrelated report/section mutation may exist.

---

# Rendering Contract

D2E must render the actual evolving logfile:

- once for S0 before the sequence;
- once after each accepted state S1, S2, S3, S4;
- once after the rejected fifth request.

Every render must be a real non-empty output file.

A final render alone is insufficient because D2 requires persistence/render after each accepted revision.

---

# Expected Production Scope

Repository inspection at the frozen D2D baseline finds no known D2E production gap.

The existing public path already:

- reloads the current logfile on every revision;
- feeds the current canonical document into planning/enrichment/workers;
- persists accepted mutations;
- short-circuits failed compilation before application;
- renders persisted state.

Therefore future D2E implementation authorization should initially permit only:

```text
tests/test_nlp_d2e_successive_revision.py
docs/nlp-d2e-successive-revision-result.md
```

No production files are expected to change.

Existing D1/D2A/D2B/D2C/D2D tests remain immutable validation evidence and must not be edited merely to share helpers.

If implementation discovers that the integrated sequence requires a production or existing-test change, STOP and request a scope amendment.

---

# Mandatory Adversarial Assertions

The primary integrated test must contain assertions that prevent false acceptance:

## A. No reset between steps

Record the logfile inode/path identity as appropriate for the test environment and, more importantly, prove every next public call starts from the canonical state written by the previous call.

No helper may recopy `single_logfile` after S0.

## B. Planner stale-state detection

If Step 2 or later receives `Original Well Log Report` in its current-document summary, fail.

## C. Worker stale-state detection

- D2B worker must observe GR scale 10-100.
- D2C worker must observe GR scale 10-100 **and** the S3 Caliper QC curve identity.

If either worker observes only baseline S0 state, fail before emitting its program.

## D. Duplicate-application detection

After each step enforce exact object multiplicity:

```text
Caliper QC tracks after S3/S4 = 1
GR requested fills after S4 = 1
```

## E. Rejection rollback/no-op detection

The final missing-source request must not merely produce an error; it must prove exact byte and canonical identity with pre-rejection S4.

---

# Explicit Non-Goals

D2E does not authorize:

- new mutation types;
- move/reorder semantics;
- fill update/removal;
- between-curve fill;
- header-slot mutation beyond the already accepted report title;
- clarification UI;
- fuzzy source/target selection;
- planner redesign;
- worker redesign;
- reconciliation redesign;
- persistence redesign;
- renderer changes;
- helper extraction/refactor solely to reduce test duplication;
- live provider/model inference;
- D3 CBL construction;
- D4 live acceptance.

D2E may repeat accepted deterministic worker programs as test evidence. It must not reinterpret D1-D2D as permission to expand those capabilities.

---

# STOP Conditions For Future Implementation

STOP and request architecture/scope review if the integrated sequence appears to require:

- any production source edit;
- any modification to an existing D1-D2D acceptance test;
- changing the D0 verifier;
- recreating/resetting the logfile between steps to make the test pass;
- weakening a prior preservation invariant;
- accepting a new collateral canonical diff;
- hard-coding persistence state into production;
- dispatching a worker for the final missing-source rejection;
- provider/model calls;
- D3 or D4 work.

A D2E failure is an integration defect to diagnose, not automatic permission for broader refactoring.

---

# Future Validation Expectations

A future D2E implementation must run:

```text
tests/test_nlp_d2e_successive_revision.py
```

plus the complete delivery regression:

```text
D0 / D1 / D2A / D2B / D2C / D2D / D2E
```

and adjacent suites covering:

- direct notebook session;
- Code Mode facade/session/workflow;
- report worker;
- section program worker;
- enrichment/source grounding;
- authoring context/reconciliation/execution;
- logfile persistence;
- renderer.

Then run the full repository suite.

Also require:

```text
Ruff
formatting check
Python compilation/import validation
git diff --check
```

Provider, endpoint, worker-provider, and real-model calls must remain zero.

Historical/environment failures must be classified separately from new D2E-attributable failures.

---

# Future Implementation Handoff

A future D2E implementation checkpoint must report:

```text
D2E IMPLEMENTATION COMPLETE

Authorization:
<future authorization>

Branch:
<implementation branch>

HEAD:
<exact SHA>

Parent / baseline:
<accepted D2E design SHA>

Changed files:
<exact list>

Production changes:
0

Sequence logfile:
<single path identity / fixture lineage>

S0:
title:
GR scale:
track ids:
GR fills:
source:

STEP 1 — REPORT TITLE
request:
planner summary before:
workers:
public result:
immediate D0:
render:
S1 preservation snapshot:

STEP 2 — GR SCALE
request:
planner summary before:
worker observed GR identity/scale:
workers:
public result:
immediate D0:
render:
S2 cumulative snapshot:

STEP 3 — CALIPER QC TRACK/CURVE
request:
planner summary before:
worker observed current GR scale:
worker CALI source grounding:
workers:
public result:
observed new track id:
observed new binding id:
immediate D0:
render:
S3 cumulative snapshot:

STEP 4 — GR FILL
request:
planner summary before:
worker observed GR scale:
worker observed S3 Caliper QC binding:
workers:
public result:
observed fill id:
immediate D0:
render:
S4 cumulative snapshot:

CUMULATIVE S0 -> S4
LAS-01:
LAS-02:
LAS-03:
LAS-04:
LAS-05:
LAS-06:
LAS-07:
LAS-09:
workflow_status:
canonical diff paths:

STEP 5 — MISSING SOURCE REJECTION
request:
planner source hint:
diagnostic:
workers:
public result:
byte identity with S4:
canonical identity with S4:
D0 LAS-01:
D0 LAS-07:
D0 LAS-08:
D0 LAS-09:
workflow_status:
render:

Integrated LAS-01..LAS-09:
PASS/FAIL

Focused tests:
<result>

D0-D2E delivery regression:
<result>

Adjacent suites:
<result>

Full suite:
<result and failure classification>

Ruff / format / compile / git diff --check:
<result>

Provider calls:
0
Endpoint calls:
0
Worker provider calls:
0
Real model calls:
0

D3/D4:
NOT AUTHORIZED
```

Do not claim independent acceptance in the implementation result document.

---

# Design Decision

`WELLPLOT-NLP-D2E-DESIGN-001`

Selected approach: one deterministic, single-session, single-logfile successive-revision workflow composing the already accepted D2A, D1, D2B, D2C, and D2D missing-source behaviors.

The sequence intentionally proves both directions of state continuity:

1. **forward accumulation** — each accepted change becomes input state for later revisions;
2. **failure preservation** — the final rejected request leaves the complete accumulated artifact unchanged.

Evidence class: `INTEGRATED ACCEPTANCE`.

Expected production changes: none.

Reversible: yes. This design itself changes no production behavior.

Next gate: independent review and explicit approval of this D2E design. D2E implementation remains unauthorized until both occur. D3 and D4 remain unauthorized.
