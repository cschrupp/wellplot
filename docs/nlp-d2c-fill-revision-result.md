# WellPlot NLP D2C Fill Revision

## Status

`IMPLEMENTATION_COMPLETE / INDEPENDENT_REVIEW_PENDING`

Authorization: `WELLPLOT-NLP-D2C-AUTH-001`

Implementation baseline: `c435c729ec550be029f432b727abffacbd0d68c2`

Scope amendments: `WELLPLOT-NLP-D2C-SCOPE-AMEND-001` and
`WELLPLOT-NLP-D2C-SCOPE-AMEND-002`

Provider, endpoint, and real model calls: `0`

## Request and public path

Frozen request:

```text
In the Main Log section, on the GR track, fill from the Gamma Ray curve to its lower scale limit using light gray (#d9d9d9) at 25% opacity.
```

The acceptance test enters through:

```python
DirectNotebookSession.revise(
    feedback=FROZEN_D2C_REQUEST,
    logfile_path=fixture,
)
```

The exercised route is the real notebook adapter, deterministic enrichment,
grounded `ProgramSectionCompiler`, canonical reconciliation/application,
persistence, reload, rendering, and the frozen D0 LAS verifier. The report
compiler is a fail-if-called double; the section backend is deterministic and
provider-free.

## Implementation

The section worker now advertises the bounded `fill.curve` capability and the
existing `wp.fill(track, binding[, other_binding])` vocabulary. The worker
instruction and validation remediation mention only grounded fill creation;
fill update/removal behavior was not added.

The canonical-to-legacy authoring projection now preserves track-local fills
through the legacy binding-level envelope, including an optional validated
`fill_id`. Multiple fills targeting one binding fail closed because that legacy
envelope cannot represent them unambiguously. The strict logfile schema accepts
`fill_id` only as a non-empty string and continues to reject unknown fill
properties.

Observed allocator-owned fill identity after persistence/reload:

```text
main.gr.fill.gr-lower-fill
```

The identity is observed evidence, not the scientific request value.

## Acceptance evidence

Starting state:

```text
section: main / Main Log
tracks: depth, cbl, vdl, gr, cali, rt
GR binding: main.gr.GR.3 / GR
GR fills: 0
```

Final state contains one fill on the existing `gr` track:

```text
kind: to_lower_limit
binding_id: main.gr.GR.3
color: #d9d9d9
alpha: 0.25
```

Frozen D0 results:

```text
LAS-01  PASS
LAS-06  PASS
LAS-07  PASS
LAS-09  PASS
```

The canonical semantic diff is exactly:

```text
/sections/0/tracks/3/fills/0
/extensions/compatibility/legacy_document/bindings/channels/2/fill
/sections/0/tracks/3/bindings/0/extensions/compatibility/legacy_binding/fill
```

The last two paths are deterministic legacy compatibility mirrors. No other
track, binding, scale, source route, report, header, remark, page, depth,
output, annotation, or presentation state changed.

Persistence evidence writes the revised logfile, reloads it with
`load_authoring_document()`, validates the canonical fill and preserved GR
binding, and renders a non-empty PDF.

The worker receives the actual structured request payload and verifies the
grounded existing-curve inventory contains:

```text
track_id=gr
binding_id=main.gr.GR.3
channel=GR
```

Only after that inspection does the deterministic backend emit the fill
program. The report worker is not called.

## Adversarial coverage

- An invented `main.gr.GR.404` binding fails at the worker boundary and does
  not persist a mutation.
- A real `main.cali.CALI.4` binding used on the GR track fails cross-track
  validation and leaves the document unchanged.
- The successful intent contains one existing-section fragment and one fill;
  it contains no report, track, curve, raster, annotation, or removal
  mutation.
- A controlled fill plus an unrelated GR binding style mutation produces
  `LAS-06 PASS`, `LAS-07 FAIL`, and workflow failure.

## Verification

The focused D2C/worker/adapter/schema suite passed:

```text
83 passed
```

The D0 through D2C delivery suite passed:

```text
47 passed
```

The relevant authoring, enrichment, section-worker, reconciler, executor, and
notebook suite reported:

```text
221 passed
1 reproduced baseline/environment failure
```

The reproduced failure is
`tests/test_direct_notebook.py::test_project_session_uses_example_seed_and_declared_sources_only`;
it requires the absent fixture
`workspace/data/30-23a-3 8117_d.las` and is outside the D2C changed files.

Full-suite results and static-check results are recorded in the implementation
handoff after completion. The full suite reported:

```text
2543 passed
36 failed
10 skipped
11 subtests passed
```

An exact baseline checkout at `c435c729ec550be029f432b727abffacbd0d68c2`
reported the same 36 failure IDs (`2532 passed, 36 failed, 10 skipped,
11 subtests passed`). The additional passing tests are D2C coverage; no new
D2C-attributable failures were introduced. Ruff check, format check, Python
compilation, and `git diff --check` pass. No provider, endpoint, or real model
call is authorized or performed by this slice.

## Scope boundary

Changed production files are limited to the authorized worker, authoring
projection, and logfile schema boundaries. D2D, D2E, D3, D4, planner redesign,
provider experiments, and production NLP promotion remain unauthorized.
