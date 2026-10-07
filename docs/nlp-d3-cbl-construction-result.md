# WellPlot NLP D3 CBL Construction Result

## Status

```text
WELLPLOT-NLP-D3-IMPLEMENTATION-COMPLETE-REVIEW-PENDING
```

Authorization:

```text
WELLPLOT-NLP-D3-AUTH-001
WELLPLOT-NLP-D3-DATA-SCOPE-AMEND-002
```

Implementation checkpoint parent:

```text
770778555427ee8150beb291d87b7dbaa8820b9d
```

This record reports implementation evidence only. Independent review and D3
acceptance have not been claimed.

## Data

```yaml
data_mode: LOCAL_EXTERNAL_GITIGNORED
files_committed: NO
main_path: workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis
main_size: 111573216
main_sha256: 3ceb9100fd654d710155672a50a9e0f24ce9705db6ef8e424140f29bd02131f7
repeat_path: workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis
repeat_size: 3294924
repeat_sha256: a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640
```

Both files were parsed through the existing `wellplot.io.dlis.load_dlis`
loader before the integrated test. The observed files contain the required
scalar channels `ECGR_STGC`, `TT`, `TENS`, `MTEM`, `STIT`, `TDSP`, `VSEC`, and
`CBL`, plus array channel `VDL`.

If neither authorized local file is present, the integrated test skips with
the explicit external-data message. If exactly one is present, it fails. A
present pair must match the fixed size and SHA-256 values above.

## Request and path

The construction request is the normalized content of
`tests/fixtures/agentic_cbl/frozen_prompt.txt`, changing only the two staged
DLIS source path lines to `CBL_Main.dlis` and `CBL_Repeat.dlis`.

```yaml
normalized_request_sha256: 16c038a70b16ee745966bb016f2d291500f223c4d46e4cc7a5f09922877ee188
public_call: DirectNotebookSession.run
mode: reconstruct
planner_calls: 1
report_worker_calls: 1
section_worker_calls: 2
worker_repairs: 0
provider_calls: 0
endpoint_calls: 0
model_calls: 0
```

The test uses one valid scaffold containing only `main_pass` and `repeat_pass`
sections with empty 50 mm `combo` anchor tracks. It proves that the scaffold
does not already satisfy the CBL verifier before the one-shot construction.
The deterministic report and section backends assert their actual serialized
task payloads and host-grounded source/channel context before returning
controlled SDK programs.

## Acceptance evidence

The one-shot test is required to prove:

```text
persisted logfile: PASS
reload:            PASS
real render:       PASS, non-empty PDF
CBL-01..CBL-09:    PASS
```

The final CBL verifier remains `scripts/verify_cbl_packet.py`; it is not
modified by D3. The authoritative test is
`tests/test_nlp_d3_cbl_construction.py`.

## Verification

```yaml
d3_focused_non_integrated: 49 passed, 1 deselected
d0_d2e_adjacent: 93 passed
full_suite: 2545 passed, 36 failed, 21 skipped, 11 subtests passed
known_baseline_failures: 36 reproduced; no D3-attributable failure identified
ruff: PASS
format: PASS
compileall: PASS
git_diff_check: PASS
provider_endpoint_model_calls: 0
```

The full-suite failures are the established repository baseline set, including
historical evidence and protected-history checks that are expected to fail in
this descendant. The D3 integrated test passed in the final full-suite run.
The D3 render emitted two existing matplotlib warnings about more than twenty
open figures; the rendered PDF was non-empty and the verifier still returned
CBL-01 through CBL-09 as PASS.

## Scope

Authorized implementation files are limited to the capability additions,
their focused tests, the D3 acceptance test, and this result record. No
planner, enrichment, report-worker, workflow, notebook adapter, canonical
schema, reconciler, renderer, or provider route was changed for D3.

No D4 work or production routing promotion is authorized by this record.
