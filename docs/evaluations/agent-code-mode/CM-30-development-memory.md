# CM-30 Development Memory

## Scope

CM-30 establishes the provider-neutral asynchronous contract required by later
Code Mode planner and program-generation slices. It intentionally does not
migrate a live provider.

- **Slice base SHA:** `68124fe`
- **Implementation commit:** `e207550`
- **Scope:** typed generation requests/results, per-call metrics, redacted
  provider errors, fake/recorded backend tests, and the provider-boundary
  architecture guard.

## Contract

`ModelBackendProtocol` exposes exactly two asynchronous operations:

```text
generate_structured(request, response_model)
generate_program(request)
```

Structured generation returns `StructuredGenerationResult[T]`, where the fake
backend validates the recorded payload through the supplied Pydantic model.
Program generation returns `ProgramGenerationResult` containing plain source
text unchanged. Both results carry immutable per-call `ProviderMetrics`.

`ProviderRequestError` uses stable categories:

```text
configuration, authentication, timeout, rate_limit, transport,
provider_rejected, invalid_response, validation
```

Its public representation contains only category, explicitly safe message,
deterministic retryability, and optional integer status code. Raw exceptions,
provider objects, request/response payloads, credentials, and prompt contents
are excluded.

## Boundaries

- `src/wellplot/agent/providers/base.py` has no dependency on `agent.core`,
  graph, MCP, LangGraph, concrete provider SDKs, or the authoring interpreter.
- Existing OpenAI and OpenAI-compatible adapters remain unchanged.
- No retry, fallback, streaming, tool-call, authentication, endpoint, or
  provider-specific configuration layer is included.
- No planner, program worker, LangGraph, MCP, routing, or public runtime cutover
  is included.
- CM-31 owns the first live provider transport.

## Validation

- Focused provider-contract and architecture tests passed: `12 passed`.
- Complete Code Mode regression selection passed: `170 passed`.
- Ruff check over changed Python files passed.
- Ruff format check over changed Python files passed.
- `git diff --check` passed.

## Decision

**PROCEED / STOP:** PROCEED to CM-31 planning; CM-30 committed and pushed.
STOP before CM-31 implementation until separately authorized.
