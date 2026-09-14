# CM-14 Development Memory

## Scope

CM-14 introduces a compile-only `IntentBuilder` that translates narrow,
explicit Code Mode SDK calls into the existing canonical
`AuthoringDocumentIntent`. It is the first pure source-to-intent bridge after
the CM-10 through CM-13 program kernel layers.

- **Migration baseline SHA:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Slice base SHA:** `1708905`
- **Scope:** canonical intent accumulation, explicit report/section/track/
  curve/raster/fill/annotation construction, CM-13 ownership validation,
  pure interpreter integration tests, architecture evidence, and documentation.

## Decisions And Invariants

- `IntentBuilder` stores only canonical intent fragments. It does not create or
  retain an `AuthoringDocumentSpec`, a document clone, a reconciliation plan,
  an operation model, or an application-service transaction.
- The builder consumes identities from CM-13 handles. `HandleBuilder` remains
  responsible for allocation, adoption, provenance, type, and parent checks;
  CM-14 adds public validation accessors so the SDK can use that authority
  without reaching into CM-13 private implementation details.
- The initial SDK surface is explicit and narrow. It does not expose generic
  Pydantic-shaped `payload` or `**kwargs` APIs. Existing canonical intent
  models validate every accepted fragment before it enters the accumulator.
- The initial annotation method creates only a narrow text annotation. Broader
  annotation, report, grid, header, source-data, and rendering vocabulary is
  intentionally deferred to later capability slices.
- The CM-12 generic callback signature remains unchanged. The interpreter
  integration path uses root calls with explicit typed operands, for example
  `wp.track(section, ...)` and `wp.curve(track, ...)`. This keeps parent
  validation explicit and avoids altering generic runtime dispatch to support
  fluent syntax prematurely.
- `intent()` returns a freshly validated `AuthoringDocumentIntent`. Equivalent
  program source, initial reservations, and builder setup produce byte-stable
  JSON serialization.
- A CM-13 allocator defect was found during this slice: `allocate_section()`
  reserved the section ID but did not initialize its local track namespace.
  The correction is covered by a focused allocation test and preserves the
  reservation-set allocation contract.

## Validation

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q
  tests/test_authoring_program_intent_builder.py
  tests/test_authoring_program_identity.py
  tests/test_authoring_program_interpreter.py
  tests/test_authoring_program_validator.py
  tests/test_authoring_program_models.py
  tests/test_agent_v2_architecture.py` passed: `109 passed in 1.36s`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check` over CM-13/CM-14
  changed Python files passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check` over the
  same five Python files passed: `5 files already formatted`.
- `git diff --check` passed.

## Runtime And Production Delta

- `AuthoringService` execution: zero.
- Reconciliation, persistence, rendering, source inspection, providers,
  LangGraph, MCP, routes, feature flags, notebook APIs, and legacy deletion:
  zero.
- Production additions are one pure builder module and CM-13 public validation
  accessors. No runtime route invokes Code Mode.

## Limitations And Deferrals

CM-14 does not dry-run the compiled intent against an authoring context or
document. It does not validate source channel availability, track-kind
compatibility, report layout semantics, rendering constraints, or current
document state. It does not execute a canonical intent through
`AuthoringService`.

CM-15 owns private dry-run semantic validation. CM-20 and later slices own
capability descriptors, richer SDK calls, and capability handlers. No provider,
graph, MCP, routing, feature-flag, or legacy-deletion work is authorized here.

## Decision

**STOP after CM-14. Proceed to CM-15 only after this slice is committed and
pushed.**
