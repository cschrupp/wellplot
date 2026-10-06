# WellPlot NLP D2D Result

## Status

```yaml
authorization: WELLPLOT-NLP-D2D-AUTH-001
rework: WELLPLOT-NLP-D2D-REWORK-001
scope_amendment: WELLPLOT-NLP-D2D-SCOPE-AMEND-001
baseline: cd26c74fadf1e65bcb49925ee20dc229a644b0fa
branch: delivery/nlp-d2d-ambiguity-rejection
provider_calls: 0
endpoint_calls: 0
real_model_calls: 0
production_files_changed: 1
production_file: src/wellplot/agent/code_mode/enrichment.py
decision: WELLPLOT_NLP_D2D_REWORK_COMPLETE_REVIEW_PENDING
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

Frozen requests:

```yaml
case_a: In the Main Log section, change the Gamma Ray curve scale to 10–100.
case_b: In the Main Log section, add a normal track titled "Neutron" and plot NPHI from missing.las on it.
case_c: In the Main Log section, add a normal track titled "Neutron", 28 mm wide, and plot NPHI from fixture.las on it labeled "Neutron" with a linear scale from 0 to 45.
```

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

The host boundary binds `source-1` to the `fixture.las` label and canonical-path
basename. The worker boundary receives that same candidate ID with the inspected
channel inventory; canonical paths and source labels remain host-owned and are
not serialized into the worker payload.

Case C made two bounded generation attempts: one initial generation and one
repair. Both attempted only `NPHI`; neither introduced an available channel.
The final worker evidence contains one `program.dry_run_error` diagnostic and
no submitted intent.

The scope amendment also verifies that the missing-source rejection is not
caused by the generic source-format label. For the fixture candidate, the
deterministic projection is:

```yaml
candidate_id: source-1
filename: fixture.las
stem: fixture
raw_labels: [fixture.las, fixture, las]
source_format: las
effective_identity_labels: [source-1, fixture.las, fixture, fixture.las, fixture]
generic_source_format_label_excluded: PASS
missing_las_matched_candidate: NO
diagnostic: enrichment.source_missing
worker_count: 0
new_enrichment_regression: PASS
```

The duplicate filename/stem values are retained by the existing lexical
projection. Only the generic normalized format label `las` is excluded; the
lexical matcher itself is unchanged.

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

Focused amendment and D2D suites:

```text
21 passed
```

The D0-D2D delivery tests completed with:

```text
52 passed
```

The adjacent suites completed with:

```text
95 passed
1 reproduced pre-existing failure
```

The reproduced failure is
`tests/test_direct_notebook.py::test_project_session_uses_example_seed_and_declared_sources_only`.
It fails because the existing example seed references the absent repository
fixture `workspace/data/30-23a-3 8117_d.las`; it is unrelated to D2D and no
production source changed.

Full repository suite:

```text
2549 passed
36 failed
10 skipped
11 subtests passed
```

The 36 full-suite failures match the established pre-D2D baseline. No failure
is attributable to the D2D files or to a production change. Ruff check,
formatting, Python compilation, and `git diff --check` pass for the D2D files.

## Scope Boundary

The amendment authorized these five files:

```text
src/wellplot/agent/code_mode/enrichment.py
tests/test_code_mode_enrichment.py
tests/test_nlp_d2d_ambiguity_rejection.py
docs/nlp-d2d-ambiguity-rejection-design.md
docs/nlp-d2d-ambiguity-rejection-result.md
```

The production correction is limited to filtering an exact normalized
source-format label from candidate lexical identity labels. No other source
loader, matcher, verifier, planner, worker, renderer, or reconciliation
behavior changed.

D2E, D3, and D4 remain unauthorized pending independent review.
