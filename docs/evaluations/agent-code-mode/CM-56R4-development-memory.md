# CM-56R4 Development Memory

## Status

- Slice: planner/provider failure forensics
- Baseline: `755f59e`
- Pre-live diagnostic checkpoint: `096c8a7`
- Production changes: none
- Live matrix: incomplete; `7/20` rows flushed
- Live decision: `INCONCLUSIVE_PROVIDER_INFRA`
- CM-57: blocked

## Purpose

CM-56R3 stopped at `STOP_PLANNER_RELIABILITY` after three terminal planner
failures and one source ambiguity in the frozen CM-56 matrix. CM-56R4 is a
diagnostic-only slice to distinguish provider response shape, JSON parsing,
Pydantic schema validation, planner semantic validation, and source-plan shape.
It does not repair or reinterpret any failure.

## Frozen Controls

- Cases: `reverse_scale` and `source_selection` from the unchanged CM-56 corpus.
- Attempts: ten sequential attempts per case, twenty total.
- Provider: controlled local llama.cpp `qwen3.6-35b-a3b`.
- Planner temperature: `0.0`.
- Maximum output tokens: `16384`.
- Request timeout: `900` seconds.
- Thinking: disabled by the existing local provider configuration.
- Corpus SHA-256: `4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e`.

The runner uses the same rich case source summary as the CM-56R3 diagnostic
helper. Before live execution, the difference from the production workflow is
recorded explicitly: the helper includes channel mnemonic/kind facts, while
the production workflow summary currently includes source labels and empty
channel arrays. This is scope context, not a production correction.

## Forensic Boundary

An evaluation-only proxy wraps the same real asynchronous client used by the
production `OpenAICompatibleBackendV2`. It forwards request arguments
unchanged, returns the exact provider response object, and captures only safe
metadata. Content is hashed and inspected transiently; raw provider content is
not written to JSONL or committed.

Each underlying call records finish reason, message shape, content size/hash,
JSON parse metadata, sanitized Pydantic error locations/types, semantic-plan
validation status, and a safe semantic error code. Call roles are derived from
the bounded sequence as `initial`, `invalid_response_retry`, or
`semantic_correction`.

The independent checks do not alter production behavior:

```text
provider response
  -> json.loads
  -> SemanticPlan.model_validate
  -> validate_semantic_plan
```

No repair, retry, fallback, prompt, schema, planner, enricher, provider, typed
worker, graph, or corpus change is part of CM-56R4.

## Hard Stop

Freeze this diagnostic code before the live matrix. After the live attempt,
record aggregate evidence and stop. Do not begin remediation or CM-57 in this
slice.

## Live Evidence

The live runner used the controlled local llama.cpp endpoint with the frozen
Qwen configuration and the unchanged CM-56 corpus. It flushed seven rows before
the eighth request stopped producing HTTP response headers for longer than the
configured 900-second request window. The process was then interrupted after
the external wait; this is not classified as a Wellplot provider category
because no response or adapter error existed to inspect.

- Raw evidence: `/tmp/cm56r4-live-qwen.jsonl`
- Raw SHA-256: `59fb4fa55362fc1056d3b449b4172c3c93ff1e222dc6ce08be12167b24013a6c`
- Completed rows: `7/20`
- `reverse_scale`: `7/10` completed; all seven were
  `REVERSE_PLAN_SUCCESS`, one structured call each, with valid JSON, Pydantic,
  and semantic-plan validation.
- `source_selection`: `0/10` completed.
- Typed-worker calls: `0`.
- Raw content committed: no.

## Validation

- Focused forensic tests: `13 passed`.
- Full suite: `1568 passed, 10 failed, 2 skipped, 11 subtests passed`.
- The ten failing node IDs match the documented baseline/unrelated worktree
  failures; CM-56R4 added its thirteen tests to the passing count.
- Ruff check and format check passed.
- JSON validation passed for the contract and live summary.
- `git diff --check` passed.

The partial result demonstrates that the forensic path can capture successful
planner responses, but it cannot distinguish the source-selection failure
classes until the provider completes the first case. The authorized decision
is therefore `INCONCLUSIVE_PROVIDER_INFRA`, not a planner/schema/source
finding. No remediation, retry policy, provider change, or CM-57 work follows
from this partial run.
