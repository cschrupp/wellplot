# SI-V2R Live Qualification Scope

## Status

```yaml
experiment: SI-V2R-LQ0
accepted_v2r_baseline: d896a7e9a634bffe15c6f39ed156dc52c17b2bed
reference_preservation_correction: 7dc5833cb800300cc9c3b45930745c84337f0b79
provider_calls: 0
endpoint_calls: 0
worker_program_calls: 0
live_inference: NOT_STARTED
```

This record freezes the provider-facing qualification design for the accepted
SI-V2R contract. LQ0 implements and verifies the harness only; it does not
authorize live inference or production adoption.

## Objective

The future qualification asks whether `qwen3.6-35b-a3b` can map the frozen 24
CM-59A natural-language requests into `SemanticIRV2R`, preserving report and
section ownership plus section-owned reference semantics. Generated V2R intent
is graded directly, lowered deterministically to `CompiledSemanticPlanV2R`,
and only then passed through CM58.1, CM58.2, and CM58.3.

Structured validity, V2R semantic correctness, deterministic lowering, and
downstream safety remain separate measurements. CM58 cannot improve the V2R
semantic score.

## Frozen Population

The future run uses the unchanged CM-59A request corpus:

```yaml
cases: 24
families: 6
cases_per_family: 4
attempts_per_case: 2
executions: 48
concurrency: 1
maximum_provider_calls: 96
```

The V2R gold fixture is grader-only. It is never serialized into a provider
prompt, request metadata, retry prompt, or provider object.

## Frozen Controls

```yaml
model: qwen3.6-35b-a3b
temperature: 0.0
max_output_tokens: 16384
max_tokens_parameter: max_tokens
timeout_seconds: 900
mode: reconstruct
current_document_summary: {}
endpoint: http://192.168.2.140:8888/v1
endpoint_identity_sha256: 23afb5ebf67063154bcf02ada6d25b2c929250b14c6a4cad06e8649d087bc980
```

Each execution permits one initial structured call and at most one generic
structural retry. Semantic repair, third calls, and automatic reruns are not
part of the experiment.

## Lifecycle Boundary

The dedicated harness exposes provider-free pre-live validation, a guarded
future live lifecycle, and provider-free finalization:

```text
--prelive
  local corpus/gold/schema/hash/leakage/orchestration checks only

--live
  checkout and artifact guards
  -> PRE endpoint fingerprint
  -> 48 sequential executions
  -> POST endpoint fingerprint

--finalize
  preserved JSONL and fingerprints only; no provider or endpoint activity
```

Reserved artifacts are `/tmp/si-v2r-live.jsonl`,
`/tmp/si-v2r-endpoint-pre.json`, `/tmp/si-v2r-endpoint-post.json`, and
`/tmp/si-v2r-summary.json`. Non-empty artifacts are rejected before PRE.

## Hard Stop

LQ0 ends at `PRELIVE_READY` or a bounded pre-live rejection. Live inference,
provider construction, endpoint probing, production routing, planner changes,
worker changes, and CM58 changes remain unauthorized until independent review
of this checkpoint.
