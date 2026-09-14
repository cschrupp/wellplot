# CM-24 Development Memory

## Scope

CM-24 migrates the v2 leaf capabilities for curve fills and typed annotations.
The slice preserves the CM-23 identity boundary and compiles directly to the
existing `AuthoringDocumentIntent`.

- **Slice base SHA:** `f062f82`
- **Implementation commit:** `0423f7e`
- **Scope:** five fill kinds, five typed annotation variants, builder
  create/select/update methods, capability handlers, pure unit tests, and
  architecture evidence.

## Contract

`fill.curve` supports `create`, `select`, and `update` for:

```text
between_curves, between_instances, to_lower_limit, to_upper_limit,
baseline_split
```

`annotation.typed` supports `create`, `select`, and `update` for:

```text
interval, text, marker, arrow, glyph
```

Creation allocates an identity through the host-owned handle builder. Selection
and update adopt exact identities without document lookup. Fill outer fields use
sparse updates; nested baseline and crossover objects are complete replacement
values. Annotation updates replace the complete typed payload while preserving
the annotation identity.

The existing parent declarations remain authoritative:

```text
fill.curve       -> track.normal
annotation.typed -> track.annotation
```

Handlers do not inspect documents or sources and do not infer target existence.
Dry-run and reconciliation remain responsible for current-document existence
and compatibility.

## Boundaries

- Existing v1 artifact models, compilers, and descriptor shapes remain
  unchanged.
- No fills/annotations operation IR, interpreter registration, fluent syntax,
  provider, planner, LangGraph, MCP, routing, persistence, rendering, or
  legacy deletion changes are included.
- CM-25 owns the next separately authorized slice.

## Validation

Validation evidence:

- Focused fill/annotation and existing capability tests passed: `23 passed`.
- Complete Code Mode regression selection passed: `157 passed`.
- Ruff check over changed Python files passed.
- Ruff format check over changed Python files passed.
- `git diff --check` passed.

## Decision

**PROCEED / STOP:** PROCEED to CM-25; CM-24 committed and pushed. STOP before
CM-25 implementation until separately authorized.
