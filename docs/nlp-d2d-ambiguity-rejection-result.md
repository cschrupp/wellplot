# WellPlot NLP D2D Result

## Status

```yaml
authorization: WELLPLOT-NLP-D2D-AUTH-001
baseline: c1e2e72ad4d53c87e39819c3467b95e72da66f77
branch: delivery/nlp-d2d-ambiguity-rejection
provider_calls: 0
endpoint_calls: 0
real_model_calls: 0
production_files_changed: 0
decision: WELLPLOT_NLP_D2D_IMPLEMENTATION_COMPLETE_REVIEW_PENDING
```

This result records the bounded D2D implementation and deterministic evidence. It
does not claim independent acceptance or authorize D2E, D3, or D4.

## Public Path

All three cases enter through:

```text
DirectNotebookSession.revise()
-> deterministic planner
-> capability/report/section safety layers
-> deterministic enrichment
-> section worker when applicable
-> private program dry run
-> notebook projection
-> unchanged logfile validation and render
-> D0 LAS verifier
```

The test uses a deterministic planner and deterministic worker doubles. No
provider, endpoint, or model request is made.

## Rejection Evidence

| Case | Deterministic result | Workers | Terminal diagnostic |
| --- | --- | ---: | --- |
| A: ambiguous existing section | `compile_failed`, unchanged | 0 | `enrichment.section_hint_ambiguous`: The existing-section hint matched multiple inspected sections. |
| B: missing explicit source | `compile_failed`, unchanged | 0 | `enrichment.source_missing`: A source hint did not match an explicit host candidate. |
| C: unavailable channel in selected source | `compile_failed`, unchanged | 1 failed section worker | `program.dry_run_error`: `channel_missing: No source channel matches 'NPHI'.` |

For every case, `success=false`, `changed=false`, `apply_status=compile_failed`,
and `submitted_intent=null`. The persisted logfile bytes and reloaded canonical
document remain unchanged. The rejected document reloads and renders to a
non-empty PDF.

Case C retains the intended distinction between host identity and worker context:

```yaml
host_candidate_id: source-1
host_source_label: fixture.las
host_canonical_basename: fixture.las
worker_candidate_id: source-1
worker_inspected_channels: [CALI, CBL, GR, RT, VDL]
NPHI_in_worker_inventory: false
```

The worker receives the bounded candidate ID and inspected channel inventory;
the canonical path remains host-owned and is not serialized into the worker
payload.

Case C made two bounded generation attempts: one initial generation and one
repair. Both attempted only `NPHI`; neither introduced an available channel.
The final worker evidence contains one `program.dry_run_error` diagnostic and
no submitted intent.

## D0 Evidence

Each rejection uses:

```yaml
required_changes: {}
allowed_change_paths: []
expected_outcome: rejected
execution_evidence:
  accepted: false
  persisted: true
  rendered: true
```

The frozen verifier reports the following for Cases A, B, and C:

```yaml
LAS-01: PASS
LAS-07: PASS
LAS-08: PASS
LAS-09: PASS
workflow: PASS
```

Change requirements are intentionally not exercised for rejected revisions.

The mutation sentinel independently changes the section title after a rejected
workflow. It produces:

```yaml
LAS-07: FAIL
LAS-08: FAIL
workflow: FAIL
```

so rejection status cannot conceal unrelated canonical mutation.

## Validation

Focused D2D suite:

```text
5 passed
```

The D0-D2C delivery tests plus the specified adjacent suites completed with:

```text
217 passed
1 reproduced pre-existing failure
```

The reproduced failure is
`tests/test_direct_notebook.py::test_project_session_uses_example_seed_and_declared_sources_only`.
It fails because the existing example seed references the absent repository
fixture `workspace/data/30-23a-3 8117_d.las`; it is unrelated to D2D and no
production source changed.

Full repository suite:

```text
2548 passed
36 failed
10 skipped
11 subtests passed
```

The 36 full-suite failures match the established pre-D2D baseline. No failure
is attributable to the D2D files or to a production change. Ruff check,
formatting, Python compilation, and `git diff --check` pass for the D2D files.

## Scope Boundary

Only these files are authorized for this D2D implementation:

```text
tests/test_nlp_d2d_ambiguity_rejection.py
docs/nlp-d2d-ambiguity-rejection-result.md
```

No production source, existing test, verifier, planner, enrichment, worker,
renderer, source-loader, or authoring-reconciliation file is changed by D2D.

D2E, D3, and D4 remain unauthorized pending independent review.
