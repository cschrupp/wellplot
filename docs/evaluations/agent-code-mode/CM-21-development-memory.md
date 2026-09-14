# CM-21 Development Memory

## Scope

CM-21 migrates the existing `report.standard` capability to the additive v2
capability contract. It proves sparse report arguments can compile through
explicit host-side SDK methods into the existing canonical
`AuthoringDocumentIntent` without introducing a report worker schema, fluent
receiver methods, or a new execution layer.

- **Migration baseline SHA:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Slice base SHA:** `873fd14`
- **Scope:** static report arguments, explicit builder methods, v2 handler,
  pure tests, and architecture/evidence documentation.

## Contract

`ReportStandardArgs` is a strict sparse model with optional fields for:

- report `title` and `subtitle`;
- semantic `header_fields`;
- stable `service_titles`;
- semantic `detail_fields`;
- identified `remarks`;
- canonical `page`, `depth`, and `output` patches.

The argument model rejects unknown fields and empty supplied collections.
Header keys are passed as canonical semantic slot requests and are resolved by
the existing deterministic reconciliation/alias context. No fuzzy paths or
generic arbitrary setters were added.

`compile_report_standard()` validates the static arguments, creates an
isolated `IntentBuilder`, calls only these explicit methods, and returns the
canonical intent:

```text
set_header_field
set_service_title
set_detail_field
add_remark
update_page
update_depth
update_output
```

`ReportHandle` remains an identity-only host token. Fluent syntax such as
`report.set(...)` and `report.add_remark(...)` is intentionally deferred; no
CM-12 interpreter handle-method registration was changed.

## Compatibility And Boundaries

- The existing v1 `ReportArtifact`, `_compile_report`, planning descriptor,
  and worker descriptor remain in place.
- `report.standard` is the first built-in capability with both v1 and v2
  declarations, but no graph or registry routing changes were made.
- The handler imports only the authoring-program builder and canonical models.
- There is no provider, planner, LangGraph, MCP, filesystem, persistence,
  rendering, service, or legacy-code dependency.
- `AuthoringDocumentIntent` remains the only durable desired-state IR.

## Validation

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q
  tests/test_authoring_program_report.py tests/test_capability_registry.py
  tests/test_authoring_program_intent_builder.py` passed: `18 passed`.
- The CM-10 through CM-16 regression set, capability tests, architecture
  checks, report tests, and worker-contract tests passed: `180 passed`.
- The unrelated untracked `tests/test_graph_report_worker.py` was not changed;
  its current worktree assertions fail because they require
  `stream_response is False` while the existing worker passes `True`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check` over changed Python
  files passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check` over
  changed Python files passed.
- `git diff --check` passed.

## Runtime And Production Delta

- Production addition: one static report capability argument model, one
  deterministic host handler, and explicit report-fragment builder methods.
- Existing v1 graph behavior, provider behavior, interpreter registration,
  notebook behavior, MCP behavior, persistence, rendering, and routing delta:
  zero.
- Fluent model-facing report receivers and capability execution routing remain
  absent.

## Limitations And Deferrals

CM-21 does not register report methods with the restricted interpreter, expose
`report.set(...)` syntax, add a report worker, or decide how v2 capability
handlers receive graph execution context. It does not migrate section, track,
binding, fill, or annotation capabilities. CM-22 owns the next capability
migration.

## Decision

**STOP after CM-21. Proceed to CM-22 only after this slice is committed and
pushed.**

**PROCEED / STOP:** PROCEED to CM-22; CM-21 committed and pushed.
