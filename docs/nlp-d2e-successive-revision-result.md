# WellPlot NLP D2E Result

## Status

```yaml
authorization: WELLPLOT-NLP-D2E-AUTH-001
design_baseline: de663d7d8fd999a7a924035ba4465334aeaff37c
branch: delivery/nlp-d2e-successive-revision
provider_calls: 0
endpoint_calls: 0
real_model_calls: 0
worker_provider_calls: 0
production_files_changed: 0
decision: WELLPLOT_NLP_D2E_IMPLEMENTATION_COMPLETE_REVIEW_PENDING
```

This record reports deterministic implementation evidence only. It does not
claim independent acceptance and does not authorize D3 or D4.

## Single-Artifact Sequence

The primary test uses one `DirectNotebookSession`, one persisted logfile path,
and one evolving canonical artifact:

```text
S0
-> D2A title revision
-> D1 GR scale revision
-> D2B Caliper QC track and CALI curve
-> D2C GR fill
-> D2D missing-source rejection
-> exactly unchanged S4
```

The exact request order is recorded by the deterministic planner. Later planner
calls receive the persisted report title from the preceding accepted revision;
the section workers receive the current grounded curve inventory from the same
persisted logfile.

## S0

```yaml
title: Original Well Log Report
section_id: main
section_title: Main Log
track_ids: [depth, cbl, vdl, gr, cali, rt]
track_count: 6
gr_binding_id: main.gr.GR.3
gr_channel: GR
gr_scale: linear 0..100 reverse=false
existing_cali_binding_id: main.cali.CALI.4
gr_fill_count: 0
caliper_qc_track: ABSENT
declared_source: fixture.las
render: non-empty PDF
```

S0 was rendered before any revision.

## Step 1: S0 -> S1

```yaml
request: 'Change the report title to "Gamma Ray Quality Control Review".'
planner_title_seen: Original Well Log Report
worker_kind: report
worker_count: 1
successful_workers: 1
public_result: persisted / success / changed
state: title = Gamma Ray Quality Control Review; six original tracks; GR 0..100
D0: LAS-01 PASS, LAS-02 PASS, LAS-07 PASS, LAS-09 PASS
workflow_status: PASS
render: non-empty PDF
```

The report backend generated exactly one sparse title program and no section
worker was used.

## Step 2: S1 -> S2

```yaml
request: Change the Gamma Ray curve scale to a linear scale from 10 to 100.
planner_title_seen: Gamma Ray Quality Control Review
worker_kind: section
worker_count: 1
successful_workers: 1
worker_observed_gr: main.gr.GR.3 / GR / linear 0..100 before update
public_result: persisted / success / changed
state: title preserved; GR scale = linear 10..100 reverse=false
D0: LAS-01 PASS, LAS-05 PASS, LAS-07 PASS, LAS-09 PASS
workflow_status: PASS
render: non-empty PDF
```

## Step 3: S2 -> S3

```yaml
request: In the Main Log section, add a new normal track titled "Caliper QC" at the end, 28 mm wide, and plot the CALI curve on it labeled "Caliper QC" with a linear scale from 6 to 12.
planner_title_seen: Gamma Ray Quality Control Review
worker_kind: section
worker_count: 1
worker_observed_gr: main.gr.GR.3 / GR / linear 10..100
source_grounding: source-1 contains scalar CALI
observed_caliper_track_id: caliper-qc
observed_caliper_binding_id: main.caliper-qc.CALI
public_result: persisted / success / changed
state: seven tracks; Caliper QC is the sole new track and CALI curve
D0: LAS-01 PASS, LAS-03 PASS, LAS-04 PASS, LAS-07 PASS, LAS-09 PASS
workflow_status: PASS
render: non-empty PDF
```

The track and binding identities were captured after execution and are not
part of the scientist request.

## Step 4: S3 -> S4

```yaml
request: In the Main Log section, on the GR track, fill from the Gamma Ray curve to its lower scale limit using light gray (#d9d9d9) at 25% opacity.
planner_title_seen: Gamma Ray Quality Control Review
worker_kind: section
worker_count: 1
worker_observed_gr: main.gr.GR.3 / GR / linear 10..100
worker_observed_caliper: caliper-qc / main.caliper-qc.CALI / CALI / Caliper QC / linear 6..12
observed_fill_id: main.gr.fill.gr-lower-fill
public_result: persisted / success / changed
state: title, scale, Caliper QC, and one GR lower-limit fill preserved
D0: LAS-01 PASS, LAS-06 PASS, LAS-07 PASS, LAS-09 PASS
workflow_status: PASS
render: non-empty PDF
```

The fill identity remained unchanged after a second persisted-document reload.

## Cumulative S0 -> S4

The cumulative verifier ran against the S0 snapshot and final S4 logfile. The
accepted canonical diff was exactly the union of the four successful revisions:

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

```yaml
LAS-01: PASS
LAS-02: PASS
LAS-03: PASS
LAS-04: PASS
LAS-05: PASS
LAS-06: PASS
LAS-07: PASS
LAS-08: NOT_CHECKABLE
LAS-09: PASS
workflow_status: PASS
```

The cumulative preservation contract excludes the existing five tracks other
than the requested GR scale, along with source routing, header, remarks, page,
depth, and output state.

## Step 5: S4 -> S4 Rejected Missing Source

```yaml
request: In the Main Log section, add a normal track titled "Neutron" and plot NPHI from missing.las on it.
planner_source_hints: [missing.las]
diagnostic_stage: enrichment
diagnostic_code: enrichment.source_missing
worker_count: 0
public_result: compile_failed / failure / unchanged
byte_identity: exact S4 bytes preserved
canonical_identity: exact S4 canonical document preserved
NPHI_bindings: 0
eighth_track: ABSENT
second_fill: ABSENT
D0: LAS-01 PASS, LAS-07 PASS, LAS-08 PASS, LAS-09 PASS
workflow_status: PASS
render: non-empty PDF
```

The generic source-format label cannot resolve `missing.las`; no report or
section worker is dispatched. The final render is a distinct post-rejection
S4 render.

## Integrated Verdict

The four accepted transitions and the rejected fifth transition compose the
integrated result without modifying the D0 verifier:

```yaml
LAS-01..LAS-09: PASS
forward_accumulation: PASS
failure_preservation: PASS
planner_calls: 5
report_backend_generations: 1
section_backend_successful_generations: 3
```

No repair was required. No backend was called for Step 5.

## Validation

```text
Focused D2E: 1 passed
D0-D2E delivery: 53 passed
Adjacent suites: 353 passed, 1 reproduced known baseline failure, 11 subtests passed
Full suite: 2550 passed, 36 reproduced known baseline failures, 10 skipped, 11 subtests passed
New D2E-attributable failures: 0
Unclassified failures: 0
Ruff: PASS
Formatting: PASS
Compilation/import: PASS
git diff --check: PASS
Provider calls: 0
Endpoint calls: 0
Real model calls: 0
Worker provider calls: 0
```

## Scope

Only these files are authorized for D2E implementation:

```text
tests/test_nlp_d2e_successive_revision.py
docs/nlp-d2e-successive-revision-result.md
```

Production files remain unchanged. D3 and D4 remain unauthorized pending
independent review.
