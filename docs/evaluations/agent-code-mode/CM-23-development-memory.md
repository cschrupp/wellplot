# CM-23 Development Memory

## Scope

CM-23 migrates the primary scientific binding capabilities to additive Code
Mode contracts: `binding.curve` and `binding.raster`. The slice preserves the
CM-22 identity boundary and compiles directly to the existing
`AuthoringDocumentIntent`.

- **Slice base SHA:** `9ae45b3`
- **Scope:** typed binding arguments, builder creation/adoption/update methods,
  v2 capability handlers, pure CBL/VDL tests, and architecture evidence.

## Contract

Both binding capabilities use explicit `create`, `select`, and `update`
operations. Creation allocates identities through CM-13. Selection and update
adopt exact host-resolved identities and do not inspect the current document,
search aliases, or infer target properties.

Curve bindings support channel, label, independent scale, and line style.
Raster bindings support channel, label, raster profile, normalization and
explicit color limits, colorbar, and sample-axis settings. Registry metadata
continues to declare the required parent capability and source kind:

```text
binding.curve  -> track.normal / track.reference; LAS / DLIS
binding.raster -> track.array; DLIS
```

The handlers return canonical intent fragments. Actual target existence and
source compatibility remain dry-run/reconciliation concerns because the v2
handler boundary has no document or source-inspection context.

## Boundaries

- Existing v1 artifact models, compilers, and descriptors remain unchanged.
- No fills, annotations, interpreter registration, fluent syntax, provider,
  planner, LangGraph, MCP, routing, persistence, rendering, or legacy deletion
  changes are included.
- CM-24 owns fill and annotation capability migration.

## Validation

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q
  tests/test_authoring_program_bindings.py tests/test_authoring_program_structural.py
  tests/test_authoring_program_report.py tests/test_authoring_program_intent_builder.py
  tests/test_capability_registry.py tests/test_agent_v2_architecture.py` passed:
  `37 passed`.
- The complete Code Mode regression selection
  `tests/test_authoring_program_*.py`, `tests/test_capability_registry.py`, and
  `tests/test_agent_v2_architecture.py` passed: `151 passed`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check` over changed Python
  files passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check` over changed
  Python files passed.
- `git diff --check` passed.

## Decision

**PROCEED / STOP:** PROCEED to review and commit CM-23; STOP before CM-24.
