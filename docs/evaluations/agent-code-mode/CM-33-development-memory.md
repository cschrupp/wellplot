# CM-33 Development Memory

## Scope

CM-33 adds an isolated OpenAI-compatible Chat Completions provider-v2 adapter
without changing the legacy provider or introducing routing.

- **Slice base SHA:** `97e7b19`
- **Implementation scope:** one compatible v2 adapter, explicit structured
  capability configuration, explicit max-token parameter selection, shared
  program-envelope validation, metrics, and stable redacted failures.

## Contract

```text
OpenAICompatibleBackendV2
    structured_output="json_schema" | None
    max_tokens_parameter="max_completion_tokens" | "max_tokens"
```

`structured_output="json_schema"` is required for structured generation.
Unsupported configuration fails before provider dispatch. The adapter sends
one strict Pydantic-derived JSON Schema request and validates the returned JSON;
it never probes, downgrades to JSON mode, or falls back to OpenAI.

Program generation sends one sparse Chat Completions request without tools or
functions. Raw source and one strict Python fence use the CM-32 envelope rules
and the shared CM-11 source limit. Chat choice, completion, refusal, tool-call,
usage, and provider-error handling remain transport-specific while using the
CM-30 error and metrics contracts.

## Validation

- Focused CM-33/CM-32/CM-31/provider-contract/architecture tests: `63 passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.

## Boundaries and Risks

- No live compatible-provider request was made. Tests use an injected fake Chat
  Completions client.
- No provider fallback, probing, JSON-mode downgrade, retry, repair, planner,
  program worker, interpreter, LangGraph, MCP, routing, or legacy deletion is
  part of CM-33.
- The legacy `openai_compat.py` adapter remains unchanged and is not imported.

## Decision

**PROCEED / STOP:** Implementation is ready for the isolated CM-33 commit.
After evidence finalization, stop before CM-34 implementation.
