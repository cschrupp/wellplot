# CM-32 Development Memory

## Scope

CM-32 completes the OpenAI provider-v2 surface for plain Code Mode program
generation without integrating a planner or worker.

- **Slice base SHA:** `fdbde64`
- **Implementation commit:** `1329c62`
- **Implementation scope:** one async Responses text call, strict program
  envelope extraction, shared source-length limit, metrics, stable failures,
  and a composed full-protocol backend.

## Contract

The provider path is deliberately split:

```text
OpenAIStructuredBackend  -> CM-31 structured generation
OpenAIProgramBackend     -> CM-32 plain program generation
          \             /
           OpenAIBackendV2
                 -> ModelBackendProtocol
```

`OpenAIProgramBackend` calls `responses.create` exactly once and reads
`response.output_text`. It never sends `text_format`, tools, or function
definitions. `OpenAIBackendV2` delegates both operations to leaf transports
sharing the injected client and model; neither leaf is presented as the full
protocol by itself.

Envelope validation accepts raw source or one strict Python fenced block
with no surrounding prose. It rejects empty/prose/mixed output, multiple or
unterminated fences, JSON objects/arrays, syntax-invalid text, incomplete
responses, tool-call output, and oversized source. `ast.parse` is used only for
syntax classification. The CM-11 validator is not called and remains the sole
authority for restricted grammar, safety policy, and semantic validity.

The output limit is imported from
`DEFAULT_PROGRAM_POLICY_LIMITS.max_source_chars`; CM-32 does not create a
second configurable policy.

## Validation

- Focused CM-32/CM-31/provider-contract/architecture tests: `53 passed`.
- Tracked Code Mode regression selection: `288 passed, 2 failed`. The two
  failures are the pre-existing `reconstruct` and `revise` assertions in
  `tests/test_graph_section_submission.py`; neither file is part of CM-32.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.

## Boundaries and Risks

- No live OpenAI request was made. All transport behavior uses injected fake
  Responses clients.
- No provider retry/fallback, planner, program worker, parser policy,
  interpreter, LangGraph, MCP, routing, or legacy deletion is part of CM-32.
- Existing CM-31 structured behavior remains covered unchanged by its focused
  tests.

## Decision

**PROCEED / STOP:** CM-32 is committed and pushed as `1329c62`. Stop before
CM-33 implementation until separately authorized.
