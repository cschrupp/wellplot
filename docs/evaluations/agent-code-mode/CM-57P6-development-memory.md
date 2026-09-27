# CM-57P6 Development Memory

## Status

CM-57P6 is a provider-free, evaluation-only diagnostic harness for the
non-empty report work-unit invariant. The pre-live implementation is complete;
live inference remains unauthorized pending independent review.

```yaml
experiment: CM-57P6
baseline: f33f3bba228d10bbdb08818653fba83b051b18a9
branch: eval/mcp-stabilization
provider_calls: 0
production_changes: 0
live_inference: NOT_STARTED
production_adoption: NOT_AUTHORIZED
CM-57D: BLOCKED
```

## Purpose

CM-57P6 isolates the state in which a `ReportTask` is present but selects no
report capability. P5 exposed that state as a repeatable planner-contract
failure. The diagnostic compares the exact P5 RC control with two evaluation-
only interventions:

- `RCV`: the production response schema plus a validator-only invariant.
- `RCS`: an experimental response schema requiring non-empty report capability
  IDs, followed by conversion to the production `SemanticPlan`.

Neither arm infers `report.standard`, modifies a plan in the host, or changes
the production planner. Both preserve the production two-call correction
budget.

## Frozen Inputs

The twelve-case manifest references only the P5 corpus and contains three
target empty-report cases, five report-pass controls, and four section-only
sentinels. Each case is run twice, in fixed `RC`, `RCV`, `RCS` order, for 24
shared rows and 72 planner executions. Future live execution would require
72-144 provider calls and zero worker/program calls.

P5 evidence anchors:

```yaml
p5_checkpoint: aea88a0611804b88bf1694448283cd5818977c55
p5_summary_sha256: 16bda565e0687b6d7e9d3e9c2b6e053111355fb85ee97bfc6f34ffffbac0810d
p5_raw_sha256: b9ce5e164d98ff18586d01ee561d83e43da023afca2f63b95de0170f8fb97cb2
p5_corpus_sha256: 29e85998481ce9bcc6eab9ecb7959d470cefbf3a84e5273309c6004aacae334d
p5_script_sha256: 3170c970d2ad4298f87c09cb106237d015356e4a5854095e3f889ba139bc600e
source_summary_sha256: ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e
```

The P6 manifest is frozen at:

```yaml
manifest_version: cm57p6.report-invariant.v1
manifest_sha256: 123af939d720cc7b7480445d9d421773b91c85b2615d8103e0d943ece1b4d10f
```

## Schema Boundary

The RCS model is constructed from the production planner models and changes
only `ReportTask.capability_ids`:

```yaml
production:
  default: []
  required: false
experimental:
  minItems: 1
  required: true
  default: absent
```

The canonical response-schema hashes are:

```yaml
production_schema_sha256: 3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3
nonempty_report_schema_sha256: 404357b174380f169c651147d988a02e8c6057bce451d18e295e85c3849af936
```

Provider-free tests require the normalized schema difference to be limited to
that field. RCS delegates the experimental response model, converts its
validated result with `model_dump()` and production `SemanticPlan` validation,
and retains the normal single invalid-response retry rather than adding one.

## Evidence Safety

Rows retain bounded plan facts, diagnostics, schema hashes, call kinds, and
provider categories only. They do not retain full prompts, provider prose,
API keys, hidden reasoning, or host paths. The live output path is
`/tmp/cm57p6-report-invariant-qwen.jsonl` and must be absent or zero length
before any future provider construction.

Population integrity is fail-closed for row count, case/attempt coverage,
arm set, checkpoint, provenance, prompt/schema hashes, P5 target reproduction,
and infrastructure failures. It also requires every contemporaneous RC attempt
to reproduce the manifest's historical classification, report-task presence,
and report capability IDs. A historical `PLANNER_CONTRACT_OK` row must retain
`final_contract_ok`; otherwise the entire population is inconclusive rather
than allowing a joint RC/candidate failure to disappear from regression
counts. Terminal planner results provide no semantic facts; pairwise semantic
tables count them as `UNAVAILABLE`.

## Frozen Decisions

The only permitted future classifications are:

```text
REPORT_INVARIANT_BOTH_VALIDATED
REPORT_INVARIANT_SCHEMA_VALIDATED
REPORT_INVARIANT_VALIDATOR_VALIDATED
REPORT_INVARIANT_PARTIAL_RECOVERY
REPORT_INVARIANT_NO_RECOVERY
REPORT_INVARIANT_REGRESSION
INCONCLUSIVE_REPORT_INVARIANT_BISECT
```

Inconclusive has precedence over all candidate outcomes. A candidate is fully
viable only if all six target rows recover, no target remains empty, no
contemporaneous RC-pass control regresses, and there are no terminal or
infrastructure failures. Full validation would remain mechanism evidence, not
permission to change production or start CM-57D. P5 is exposed and cannot be
reused as a future promotion holdout.

## Validation

The provider-free CLI reports `PRELIVE_READY`, zero provider calls, zero worker
calls, isolated schemas, exact RC/RCV request equivalence, and successful RCS
conversion. Focused tests cover manifest integrity, schema behavior, bounded
semantic correction, invalid-response retry, path-free provenance, decision
precedence, unavailable transitions, and JSON-safe reporting.

Hard stop: do not run live inference, modify production planner behavior, add
prompt instructions, select a production mechanism, or begin CM-57D without a
separate live authorization.

## Live Result

Live execution was authorized only at checkpoint
`439bdfafa39c5cd0d3d478f20eecd6c722d907ec` and completed once with 24/24
rows. The raw JSONL is preserved outside the repository with 24 rows and SHA
`98ba7fe6937a9653ed77f729c71f1f2539ddf8224a931eae5869ae88c6fe4c0f`.

```yaml
decision: REPORT_INVARIANT_BOTH_VALIDATED
RCV_target_recoveries: 6/6
RCS_target_recoveries: 6/6
RCV_control_regressions: 0
RCS_control_regressions: 0
RCV_final_passes: 20/24
RCS_final_passes: 20/24
total_provider_calls: 78
worker_program_calls: 0
terminal_failures: 0
infrastructure_failures: 0
repeatability: 12/12 stable per arm
```

RC reproduced all six target empty-report failures and all ten report-pass
control rows. RCV used six bounded semantic corrections, one per target
attempt, and recovered every target. RCS recovered every target on its initial
structured response; it had no invalid-response retries or schema failures.
The four section sentinels retained their contemporaneous RC outcomes in both
candidate arms, including the two intentionally unrelated residual failures.

This is mechanism evidence only. It does not authorize changing the
production planner, adopting either invariant mechanism, beginning CM-57D, or
reusing the exposed P5 corpus as a promotion holdout.
