# CM-56R4 Development Memory

## Status

- Slice: planner/provider failure forensics
- Baseline: `755f59e`
- Pre-live diagnostic checkpoint: pending
- Production changes: none
- Live matrix: not run
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
- Corpus SHA-256: `4ebae0b37defbdf38bcbf443f3332ed930b5d260bffc283473405cafdb4ea327e`.

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

Freeze this diagnostic code before the live matrix. After the twenty live rows,
record aggregate evidence and stop. Do not begin remediation or CM-57 in this
slice.
