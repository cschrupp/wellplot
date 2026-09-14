# CM-31 Development Memory

## Scope

CM-31 adds the first concrete Code Mode provider transport without routing the
planner or changing the legacy authoring adapters.

- **Slice base SHA:** `9533a34`
- **Implementation commit:** `1dbf49d`
- **Implementation scope:** one async OpenAI Responses structured parse call,
  typed result handling, per-call timeout, usage normalization, and redacted
  stable provider failures.
- **Dependency decision:** raise the `agent` and `all` optional dependency
  floor to `openai>=1.66.0`. The async Responses `parse` signature with
  `text_format` and request-level `timeout` was verified against the upstream
  `openai-python` v1.66.0 source.

## Implementation

- Added `OpenAIStructuredBackend` in
  `src/wellplot/agent/providers/openai_v2.py`.
- Injected the client so tests do not require credentials or network access.
- Kept the component structured-only; it does not claim the complete CM-30
  `ModelBackendProtocol` because plain program generation is CM-32 scope.
- Added focused fake-client tests for one-call behavior, exact Pydantic model
  forwarding, optional arguments, timeout propagation, usage availability,
  refusal, malformed output, parsing validation, failure categories, redaction,
  and missing capability configuration.
- Added an architecture guard preventing legacy orchestration, MCP, LangGraph,
  and concrete legacy provider imports.

## Validation

- Focused CM-31/provider contract/architecture tests: `28 passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.
- `uv lock`: passed; lockfile contains only the intended OpenAI floor update.
- Broader tracked Code Mode selection: `273 passed, 2 failed`; both failures
  are pre-existing `tests/test_graph_section_submission.py` assertions outside
  CM-31 and no files in those failures were changed.

## Boundaries and Risks

- No live OpenAI request was made. The transport is proven with an injected
  fake Responses resource only.
- No retry/fallback policy, endpoint/auth configuration, streaming, tool calls,
  planner, program worker, LangGraph, MCP, routing, or legacy deletion is part
  of CM-31.
- CM-31 does not decide how provider capability discovery or selection works;
  later provider/planner slices own that concern.

## Decision

**PROCEED / STOP:** CM-31 is committed and pushed as `1dbf49d`.
STOP before CM-32 implementation until separately authorized.
