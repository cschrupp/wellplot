# CM-13 Development Memory

## Scope

CM-13 establishes deterministic canonical identity allocation and immutable
typed ownership handles. It bridges the generic CM-12 runtime to future SDK
values without constructing document state or canonical intent.

- **Migration baseline SHA:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Slice base SHA:** `a9f2d3a`
- **Scope:** reservation-based identity allocation, typed identity handles,
  provenance and parent validation, CM-12 typed-handle compatibility, pure
  tests, and migration evidence documentation.

## Decisions And Invariants

- Identity allocation is reservation-set driven. A base is selected if free;
  otherwise the first free numeric suffix is selected. Existing identities only
  occupy their exact value. An adopted `.7` does not advance an unseen counter
  or consume `.2` through `.6`.
- Section IDs are document-wide. Track IDs are scoped to an existing section.
  Binding IDs are document-wide and derive from normalized section, track, and
  source channel when available, with `id_hint` only as fallback. Stable IDs
  mean identical reservation and creation order, not permutation-independent
  assignment for indistinguishable duplicate requests.
- `slugify_id_hint` is locale-independent and deterministic: ASCII NFKD
  normalization, lowercase alphanumeric components, hyphen-separated runs,
  and a fixed fallback for empty values. Adopting an existing canonical ID
  never slugifies or renames it.
- `ReportHandle`, `SectionHandle`, `TrackHandle`, `BindingHandle`,
  `FillHandle`, and `AnnotationHandle` are frozen value objects. They contain
  only identity, ownership-path, and opaque per-builder provenance strings.
  They contain no document fragments, callbacks, host objects, capabilities,
  or pending operations.
- `HandleBuilder` only allocates/adopts identity, issues handles, and validates
  type, builder provenance, issued identity, and parent ownership. It has no
  authoring methods, capability dispatch, canonical intent, or document state.
- Adoption is idempotent, preserves exact canonical IDs, and registers
  occupancy without replacement allocation. Foreign, wrong-typed, forged, and
  wrong-parent handles are converted to existing typed program errors.
- CM-12 now accepts registered immutable typed `RuntimeHandle` subclasses via
  `isinstance` plus an internal trusted-type registry. The registry dispatcher
  remains explicit; arbitrary subclasses and lookalikes remain invalid runtime
  values and cannot smuggle host objects through the execution boundary.
- Generic fill and annotation allocation is intentionally structural. Domain
  naming conventions, curve relationships, and annotation semantics are
  deferred to CM-14 and capability slices.

## Validation

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q
  tests/test_authoring_program_identity.py
  tests/test_authoring_program_interpreter.py
  tests/test_authoring_program_validator.py
  tests/test_authoring_program_models.py
  tests/test_agent_v2_architecture.py` passed: `102 passed in 1.73s`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check` over the CM-10
  through CM-13 source and test files passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check` over the
  same nine Python files passed: `9 files already formatted`.
- `git diff --check` passed.

## Runtime And Production Delta

- Wellplot authoring methods, capability dispatch, document mutation/state,
  canonical intent, AuthoringService, persistence, reconciliation, provider,
  LangGraph, MCP, routing, notebook, and legacy-deletion delta: zero.
- Production additions are deterministic identity and ownership values only.

## Limitations And Deferrals

CM-13 is not a Wellplot authoring SDK. It does not define `section.track`,
`track.curve`, report operations, capability arguments, or an operation model.
It does not assemble `AuthoringDocumentIntent`, validate source data, or run a
dry-run. The generic typed handles are future SDK operands, not a document
representation.

CM-14 owns the capability-neutral SDK-to-intent builder. CM-15 owns dry-run
semantics. No new syntax, provider, graph, MCP, routing, or deletion work is
authorized by this slice.

## Decision

**STOP after CM-13. Proceed to CM-14 only after this slice is committed and
pushed.**
