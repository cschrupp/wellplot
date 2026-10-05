# WellPlot NLP D2B — Add Track + Grounded Curve Design

## Status

`DESIGN_ONLY / IMPLEMENTATION_NOT_AUTHORIZED`

Design authorization: `WELLPLOT-NLP-D2B-DESIGN-001`

Input baseline: `8ac569c1d5687f51a35e2e11980edf4816e10943` (`WELLPLOT_NLP_D2A_ACCEPTED`)

Design branch: `delivery/nlp-d2b-track-curve-design`

This document freezes the next bounded delivery vertical after D2A. It authorizes no production implementation, no provider or endpoint call, no model inference, and no D2C/D2D/D2E/D3/D4 work.

## Delivery Requirement

D2B advances the structural revision requirements:

- `LAS-01` — ground against the existing document;
- `LAS-03` — add one track to an existing section;
- `LAS-04` — add one source-grounded curve/binding to that new track;
- `LAS-07` — preserve all unrelated semantic state;
- `LAS-09` — persist, reload, validate, and render successfully.

D2B does not attempt fill creation, ambiguity UX, unavailable-source policy, report/header mutation, or a complete LAS revision sequence.

## Architectural Basis

The accepted D1 production path already established revision-mode section targeting, exact existing-object grounding, canonical reconciliation, persistence, reload, and rendering.

The current production section path already contains the operations required by D2B:

- `ProgramSectionCompiler` explicitly allows an existing-section task to add requested new child tracks;
- the restricted SDK exposes `wp.track(section, ...)` and `wp.curve(track, ...)`;
- `IntentBuilder.add_track()` creates a typed track under the selected section;
- `IntentBuilder.add_curve()` creates a scalar curve binding under that track;
- source/channel values are checked against the deterministic enrichment context;
- canonical reconciliation creates the track before its binding;
- partial desired-state collections do not redefine or reorder omitted existing siblings.

Therefore D2B must reuse the existing section-worker and canonical authoring path. It must not create a second structural-mutation engine.

## Frozen Scientist Request

Exact natural-language request:

```text
In the Main Log section, add a new normal track titled "Caliper QC" at the end, 28 mm wide, and plot the CALI curve on it labeled "Caliper QC" with a linear scale from 6 to 12.
```

The request is intentionally explicit about:

- the existing section target;
- track form;
- track title;
- append position;
- track width;
- source channel;
- curve label;
- curve scale kind and limits.

No host-side scientific inference is needed.

## Frozen Starting Fixture

Use a deterministic logfile derived from the repository-contained LAS-backed fixture family:

`create_mcp_fixture_paths(...).single_logfile`

The canonical starting section is expected to be:

```text
section id    = main
section title = Main Log
```

Its six existing tracks, in canonical order, are:

```text
0 depth
1 cbl
2 vdl
3 gr
4 cali
5 rt
```

The section's declared LAS source is the fixture `fixture.las`. Deterministic source inspection must expose `CALI` as a scalar channel.

The starting document already contains a CALI binding on the existing `cali` track. D2B deliberately adds a second binding of the same source channel on a new track. This verifies that stable binding identity is independent of channel mnemonic and that repeated source-channel bindings remain legal.

The test must prove the starting fixture has exactly one section and exactly six tracks before invoking the revision.

## Frozen Expected Semantic Transition

Canonical before state:

```text
/sections/0/id = "main"
/sections/0/title = "Main Log"
/sections/0/tracks length = 6
```

Canonical after state must retain those six tracks unchanged and append exactly one seventh track:

```text
/sections/0/tracks/6/title    = "Caliper QC"
/sections/0/tracks/6/kind     = "normal"
/sections/0/tracks/6/width_mm = 28
```

The new track must contain exactly one new curve binding:

```text
/sections/0/tracks/6/bindings/0/kind    = "curve"
/sections/0/tracks/6/bindings/0/channel = "CALI"
/sections/0/tracks/6/bindings/0/label   = "Caliper QC"
/sections/0/tracks/6/bindings/0/scale/kind    = "linear"
/sections/0/tracks/6/bindings/0/scale/minimum = 6
/sections/0/tracks/6/bindings/0/scale/maximum = 12
```

The generated track and binding IDs need not be user-visible or frozen as semantic values. They must be valid, stable canonical identities allocated through the existing authoring-program identity machinery.

No pre-existing section, track, binding, source route, scale, style, report field, remark, page/depth/output setting, fill, annotation, or presentation value may change.

If normal compatibility serialization mirrors the new track or binding into `extensions.compatibility.legacy_document`, the implementation handoff must identify each exact mirror path. Those paths may be proposed as additional D0 allowed-change paths only when independently justified by the persisted canonical diff. They must not be broadly ignored.

## Public Path Requirement

The acceptance test must enter through the real notebook-facing revision API:

```python
DirectNotebookSession.revise(
    feedback=(
        'In the Main Log section, add a new normal track titled "Caliper QC" '
        'at the end, 28 mm wide, and plot the CALI curve on it labeled '
        '"Caliper QC" with a linear scale from 6 to 12.'
    ),
    logfile_path=<fixture>,
)
```

Expected integrated route:

```text
existing persisted WellPlot document
        +
natural-language structural revision
        ↓
DirectNotebookSession.revise()
        ↓
revision-mode planner with current-document context
        ↓
one SectionTask targeting "Main Log"
        ↓
deterministic source enrichment
        ↓
inspected fixture.las channel inventory including CALI
        ↓
existing ProgramSectionCompiler
        ↓
restricted section program
        ↓
target existing section
        ↓
create one new normal track
        ↓
create one CALI curve binding beneath it
        ↓
canonical reconciliation
        ↓
track CREATE before binding CREATE
        ↓
canonical execution / validation
        ↓
persist
        ↓
reload
        ↓
real render
        ↓
frozen D0 LAS verifier
```

The report worker must not be dispatched for this D2B request.

## Deterministic Planner and Worker Evidence

D2B implementation and validation must make zero real provider/model calls.

A deterministic fake planner may return exactly one section task with:

- `existing_section_hint="Main Log"`;
- capabilities `section.log_plot`, `track.normal`, `binding.curve`;
- requirements preserving the exact scientist request.

The section worker backend may return the minimal restricted program equivalent to:

```python
report = wp.report()
section = wp.target_section(report)
track = wp.track(
    section,
    id_hint="caliper_qc",
    kind="normal",
    title="Caliper QC",
    width_mm=28,
)
wp.curve(
    track,
    channel="CALI",
    id_hint="caliper_qc",
    label="Caliper QC",
    scale_minimum=6,
    scale_maximum=12,
    scale_kind="linear",
    reverse=False,
)
```

The exact expected scientific values belong only in deterministic test/backend evidence and D0 acceptance specifications. Production prompts/runtime code must not hard-code this D2B answer.

The fake backend must assert, before returning its program, that its actual worker request contains:

- an existing-section target;
- the exact inspected `CALI` channel mnemonic in the bounded source/channel context;
- the section-worker SDK needed for track and curve creation.

This assertion is required evidence that `CALI` reached the worker from deterministic source inspection rather than from an unverified test-side assumption.

## Source-Grounding Contract

D2B must preserve the existing grounding rule:

> A new binding may reference only a channel supplied by inspected source context for the targeted section.

The system must not:

- derive a channel name from prose;
- fuzzy-match a nonexistent scientific channel;
- trust an arbitrary binding channel emitted by the backend;
- reuse the existing CALI binding itself as proof that the source currently contains CALI;
- silently substitute another source/channel.

The accepted path must use the current section's declared source, deterministic source inspection, and canonical `available_channels` validation.

## Ordering Contract

The new track must be appended after the six existing tracks.

D2B does not authorize general track insertion or move semantics.

The implementation must verify:

```text
before track ids:
depth, cbl, vdl, gr, cali, rt

after first six track ids:
depth, cbl, vdl, gr, cali, rt
```

and the seventh track must be the new `Caliper QC` track.

This is compatible with the reconciler's existing partial-collection rule: omitted siblings retain their relative order and new objects are created independently.

## D0 Acceptance Specification

The frozen D0 verifier remains the independent acceptance authority.

The D2B acceptance specification should exercise both structural dimensions.

At minimum:

```text
before_assertions:
  /sections/0/id == "main"
  /sections/0/title == "Main Log"
  /sections/0/tracks length_at_least 6

required_changes:

  LAS-03:
    before:
      /sections/0/tracks length_at_least 6
    after:
      /sections/0/tracks length_at_least 7
      /sections/0/tracks/6/title == "Caliper QC"
      /sections/0/tracks/6/kind == "normal"
      /sections/0/tracks/6/width_mm == 28

  LAS-04:
    before:
      /sections/0/tracks length_at_least 6
    after:
      /sections/0/tracks/6/bindings/0/kind == "curve"
      /sections/0/tracks/6/bindings/0/channel == "CALI"
      /sections/0/tracks/6/bindings/0/label == "Caliper QC"
      /sections/0/tracks/6/bindings/0/scale/kind == "linear"
      /sections/0/tracks/6/bindings/0/scale/minimum == 6
      /sections/0/tracks/6/bindings/0/scale/maximum == 12

allowed_change_paths:
  /sections/0/tracks/6
  <only exact deterministic compatibility mirror paths observed in evidence>

prohibited_change_paths:
  /title
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
  /sections/0/tracks/3
  /sections/0/tracks/4
  /sections/0/tracks/5

expected_outcome:
  accepted
```

Because the frozen D0 verifier's `length_at_least` operator does not prove an exact count, the D2B integration test must additionally assert exact canonical counts:

```text
before tracks = 6
after tracks  = 7
new track bindings = 1
```

Required final D0 results:

```text
LAS-01  PASS
LAS-03  PASS
LAS-04  PASS
LAS-07  PASS
LAS-09  PASS
```

Unexercised LAS dimensions may remain `NOT_CHECKABLE`.

## Preservation Contract

Before/after canonical comparison must establish that:

- the document still contains exactly one section;
- the existing section identity/title/subtitle/source routing are unchanged;
- the first six tracks retain identity, order, type, width, bindings, scales, styles, fills, annotations, and presentation;
- all pre-existing binding identities and channels remain unchanged;
- report/header/remarks/page/depth/output state is unchanged;
- no existing fill or annotation appears, disappears, or changes;
- only the appended track and its new binding are new semantic content.

D0 `LAS-07` remains authoritative for the canonical preservation verdict.

## Persistence and Render Contract

After the accepted revision:

1. the public API must persist the result without manual repair;
2. canonical reload must produce exactly seven tracks;
3. the first six tracks must remain unchanged;
4. the seventh track must satisfy the frozen D2B track/binding assertions;
5. canonical validation must succeed;
6. a real render/export must succeed;
7. output must exist and be non-empty;
8. D0 execution evidence may credit `LAS-09` only from observed persistence/render success.

Dry-run-only success is insufficient.

## Required Adversarial Coverage

### Ungrounded channel attempt

A controlled deterministic worker program must attempt to create the same new track but bind a nonexistent channel such as:

```text
NOT_A_CHANNEL
```

Required behavior:

- private section compilation/reconciliation fails closed;
- the public revision does not persist a partial track;
- canonical before/after state remains unchanged;
- the failure is not credited as D2D/`LAS-08` acceptance; it is only a D2B source-grounding regression.

### Existing-sibling preservation

A controlled acceptance mutation that adds the requested new track/binding but also changes one pre-existing track field must produce:

```text
LAS-03 PASS
LAS-04 PASS
LAS-07 FAIL
workflow_status FAIL
```

This mutation belongs only in deterministic test evidence.

### Worker ownership isolation

For the accepted D2B request:

- section worker is invoked;
- report worker is not invoked;
- submitted intent targets exactly the selected existing section;
- submitted intent contains exactly one newly created track with one curve binding;
- no report-wide mutation is emitted.

## Preferred Implementation Scope

The design expectation is that D2B may require no production change because the necessary section-worker, track, curve, source-grounding, reconciliation, and public apply machinery already exist.

A future implementation authorization should initially allow only:

```text
tests/test_nlp_d2b_track_curve_revision.py
docs/nlp-d2b-track-curve-revision-result.md
```

plus fixture-local deterministic test construction if necessary.

No production file is pre-authorized by this design.

If the end-to-end test exposes a concrete integration defect, implementation must STOP and return:

```text
D2B BLOCKED
<exact boundary>
<exact missing context/contract>
<smallest proposed production file set>
```

A production-scope amendment may then be reviewed independently.

## Explicit Non-Goals

D2B does not authorize:

- report/header mutation;
- track insertion or arbitrary reordering;
- moving/removing existing tracks;
- updating an existing curve;
- raster binding creation;
- fill creation;
- annotation creation;
- ambiguity UX;
- missing-source user-flow behavior beyond existing fail-closed validation;
- planner redesign;
- typed-worker or V2R promotion;
- renderer redesign;
- source-inspection redesign;
- live-provider experimentation;
- D2C, D2D, D2E, D3, or D4 work.

## STOP Conditions For Future Implementation

Stop and return for architecture review if D2B appears to require:

- a new structural mutation engine;
- bypassing `ProgramSectionCompiler`;
- changing canonical authoring schemas;
- weakening exact channel grounding or `available_channels` validation;
- host-side scientific target/channel guessing;
- new track-order semantics beyond append;
- renderer behavior changes;
- persistence-format redesign;
- provider/model calls;
- broad fill/ambiguity work;
- more than the smallest bounded integration correction needed to reuse the existing D1 section-revision spine.

## Future Implementation Handoff Contract

A future D2B implementation checkpoint must report:

```text
D2B IMPLEMENTATION COMPLETE

Authorization:
<future implementation authorization ID>

Branch:
<implementation branch>

HEAD:
<exact SHA>

Parent / starting baseline:
<authorized D2B baseline>

Changed files:
<exact list>

Natural-language request:
In the Main Log section, add a new normal track titled "Caliper QC" at the end, 28 mm wide, and plot the CALI curve on it labeled "Caliper QC" with a linear scale from 6 to 12.

Public API path exercised:
<exact call>

Existing section:
main / Main Log

Inspected source:
<source identity>

Grounded channel:
CALI

Before track ids:
<exact ordered ids>

After track ids:
<exact ordered ids>

New track:
<canonical id / kind / title / width>

New binding:
<binding id / kind / channel / label / scale>

Frozen D0 result:
LAS-01:
LAS-03:
LAS-04:
LAS-07:
LAS-09:

Canonical semantic diff:
<exact paths>

Persistence evidence:
<details>

Render evidence:
<details>

Ungrounded-channel regression:
<result>

Focused tests:
<result>

Adjacent tests:
<result>

Full suite:
<result and classification of new failures>

Provider calls:
0

Endpoint calls:
0

Real model calls:
0

Production files changed:
0

D2C/D2D/D2E/D3/D4:
NOT AUTHORIZED
```

## Design Decision

`WELLPLOT-NLP-D2B-DESIGN-001`

Selected approach: prove one appended normal track plus one inspected-source CALI curve binding through the already accepted existing-section revision spine.

Evidence class: `ADAPTED` — D1's existing-section mutation path is extended to new structural children using already-present deterministic authoring primitives.

Reversible: yes. This design authorizes no implementation and no production modification.

Next gate: independent review of this design, followed only then by an explicit D2B implementation authorization.
