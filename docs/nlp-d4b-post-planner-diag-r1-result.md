# D4B Post-Planner Diagnostic R1

## Decision

`WELLPLOT-NLP-D4B-POST-PLANNER-DIAG-R1`

This bounded diagnostic separates the frozen D4 CBL planner result from the
downstream deterministic execution path. It does not create or resume a D4B
campaign.

Evidence class: `EMPIRICALLY_SUPPORTED`.

## Boundary

- Starting checkpoint: `95d0e51caee82c2b0844c0e08dc8dd91a67b7759`
- Branch: `diagnostic/nlp-d4b-post-planner-r1`
- Frozen CBL turn: `D4-C01:C01`
- Provider-free Stage A: exact CBL adapter path with deterministic planner and
  program backends
- Stage B: one live planner-only call against the frozen local Qwen endpoint
- Worker calls: prohibited and observed as zero
- Run-003 state/journal: pre-existing, preserved, and not modified

Run-003 evidence remains untouched. Its preserved state and journal hashes are
recorded by the preceding diagnostic and were not rewritten by this slice.

## Stage A

The first provider-free execution reached the real graph and exposed a narrow
CBL safety defect: the mixed CBL/VDL request was classified as
`raster_only_scalar_structure_ambiguous` because `cbl` was absent from the
curve-signal vocabulary. The section leaf safety vocabulary now recognizes
`cbl` as a curve signal.

The same execution then exposed a second deterministic classification defect:
the frozen request uses `depth = reference`, but the capability safety phrase
matching did not recognize that spelling. The capability predicate now accepts
that exact normalized phrase. No planner or worker behavior was otherwise
changed.

The repaired provider-free path completed:

```text
D4CampaignAdapter.execute_turn
  -> CBL scaffold
  -> DirectNotebookSession.run
  -> real AgentSession / LangGraph
  -> capability, report, and section safety
  -> deterministic enrichment
  -> deterministic dispatch construction
  -> persistence and real render
```

Stage A result: `PASS`.

Before the actual provider request, three diagnostic-harness setup defects
were encountered and corrected without delegation: relative repository-root
normalization, use of the backend helper from its actual module, and matching
the `CountingBackend` cap to its two-call ledger. Each stopped before provider
construction or request delegation. No provider request was retried after a
provider response, and the final Stage B result contains one actual provider
request.

The focused provider-free test also verifies the frozen CBL request projects
both explicit curve and raster intent. The focused/regression result was
`118 passed, 1 deselected`; the deselected test is the frozen D4 contract
attestation, which correctly rejects this diagnostic checkout after the
authorized production safety corrections changed its frozen source hash.

## Stage B

The planner-only diagnostic used the frozen request, current-document summary,
and the same provider-safe source-summary shape as the real graph. It used the
local `llama.cpp` OpenAI-compatible endpoint and the frozen model identifier.
No worker backend was constructed for execution and no campaign state or
journal was written.

```yaml
stage_b: PASS
planner_calls: 1
operation: structured
outcome: success
failure_category: null
latency_ms: 131405.14673100552
input_tokens: 2156
output_tokens: 2529
total_tokens: 4685
```

The validated plan contained:

```yaml
report_task: present
report_capability_ids: []
report_requirements: 29
report_constraints: 3
section_tasks: 2
section_capabilities:
  - section.log_plot
  - track.normal
  - track.reference
  - track.array
  - binding.curve
  - binding.raster
section_requirements_each: 15
section_constraints_each: 3
unresolved_requirements: 0
```

Provider-free replay completed capability safety, report-boundary safety,
section-leaf safety, deterministic enrichment, and dispatch construction.
Replay result: `PASS`.

The replay projected one report worker unit and two section worker units, but
invoked none of them. This diagnostic therefore establishes planner output and
deterministic downstream admissibility only; it does not establish a complete
CBL model-generated execution.

## Exception taxonomy

Post-`STARTED` generic exceptions no longer receive the provider-specific
`provider_execution_failed` label. The bounded harness taxonomy now uses
`execution_internal_error` for unexpected internal execution exceptions while
preserving explicit provider failures as provider failures. A regression test
covers this distinction.

## Validation and custody

```yaml
provider_calls: 1
endpoint_calls: 1
model_calls: 1
worker_calls: 0
campaign_state_created: false
campaign_journal_created: false
preserved_run003_state_sha256: f8d1a7ac986808a871769f51452dbb3aebd1261ebf447a636e5790efbfc3b09c
preserved_run003_journal_sha256: 37b37a0946e5058d162df04a45f0fe4feefa81f2b07e289672c6b3459b283d37
Run-003_modified: false
```

The local credential was read ephemerally for the single authorized planner
request and was not printed or persisted. No prompt, response payload, header,
credential, or host path was retained in diagnostic output.

Static validation passed for the changed source, diagnostic script, and tests:
Ruff, formatting, Python compilation, and `git diff --check`.

## Stop condition

This slice stops after the planner-only result. No D4B campaign was started,
no worker/model generation was performed for a worker, and no D4B RUN-004 or
production promotion is authorized by this record.
