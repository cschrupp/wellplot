# CM-22 Development Memory

## Scope

CM-22 migrates the structural capability surface while keeping execution and
orchestration unchanged. It adds exact identity adoption and sparse structural
updates to `IntentBuilder`, then exposes v2 contracts for
`section.log_plot` and the four fixed-kind track capabilities.

- **Migration baseline SHA:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Slice base SHA:** `3bebd28`
- **Scope:** section/track static arguments, builder selection/update methods,
  v2 handlers, pure tests, and evidence documentation.

## Structural Contract

Each structural argument model requires an explicit operation:

- `create` allocates a new identity from an advisory `id_hint`;
- `select` adopts a host-resolved canonical identity only;
- `update` requires a host-resolved target and at least one mutable field.

Pydantic defaults do not become authoring defaults for revisions. Omitted
fields remain omitted. Track operations require `section_id`; update targets
also require `track_id`. Section and track identity fields cannot be changed by
an update.

`select_section` and `select_track` are exact identity adoption methods. They
do not search titles, inspect the current document, resolve aliases, or perform
fuzzy matching. Typed CM-13 handles remain the only way to call structural
updates, and parent ownership is validated before accumulation.

The four track capabilities do not accept a free-form `kind` argument:

```text
track.normal      -> normal
track.reference   -> reference
track.array       -> array
track.annotation  -> annotation
```

The handlers compile through `IntentBuilder` and return the existing
`AuthoringDocumentIntent`. They do not manufacture a second structural IR.

## Compatibility And Boundaries

- Existing v1 artifact models, compilers, planning descriptors, and worker
  descriptors remain unchanged.
- `report.standard` v2 remains available from CM-21.
- Current-document existence and semantic target validity remain the concern of
  CM-15 dry-run/reconciliation, not capability handlers.
- No bindings, fills, annotation objects, interpreter registration, fluent
  syntax, provider, planner, LangGraph, MCP, routing, persistence, rendering,
  or legacy deletion changes were made.

## Validation

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q
  tests/test_authoring_program_structural.py
  tests/test_authoring_program_report.py tests/test_capability_registry.py
  tests/test_authoring_program_intent_builder.py` passed: `28 passed`.
- The combined CM-10 through CM-16, CM-20, CM-21, and CM-22 regression set
  passes after the final slice validation.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check` over changed Python
  files passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check` over
  changed Python files passed.
- `git diff --check` passed.

## Runtime And Production Delta

- Production addition: exact structural adoption, sparse section/track update
  methods, five static v2 contracts, and five deterministic host handlers.
- Interpreter registration, provider behavior, planner behavior, graph/MCP
  routing, persistence, rendering, notebook behavior, and legacy deletion
  delta: zero.

## Limitations And Deferrals

CM-22 handlers cannot verify target existence without execution context. They
therefore validate identity shape and structural ownership only; later dry-run
or reconciliation supplies current-document semantics. The handlers also do
not share a model-facing execution context or expose fluent receiver syntax.
CM-23 owns curve and raster bindings.

## Decision

**STOP after CM-22. Proceed to CM-23 only after this slice is committed and
pushed.**

**PROCEED / STOP:** PROCEED to review and commit CM-22; STOP before CM-23.
