# CM-55 Development Memory

## Slice

- Baseline: `fdbaf44`
- Implementation: `a818676`
- Slice: CM-55 deterministic typed section models and compiler
- Status: complete; production routing remains unchanged
- Next boundary: CM-56 real planner/enricher shadow or A/B validation

CM-55 promotes the CM-54 contract into production code without adding
provider generation, prompts, repair, graph nodes, routing, or persistence.
The implementation stops at static semantic validation and sparse canonical
intent construction.

## Implemented Boundary

The production flow is:

```text
SectionSemanticDraft
    -> static structural validation
    -> ResolvedSectionContext validation
    -> host IdAllocator reservations
    -> sparse AuthoringDocumentIntent
```

The models are strict, immutable, whitespace-stripping Pydantic models with
`extra="forbid"`. Track discriminator fields are required and have no schema
defaults:

```text
normal     -> curve bindings only
reference  -> curve bindings only
array      -> raster bindings only and requires x_scale
```

Binding kind fields retain defaults because they are not used to select a
track union branch; this is an explicit CM-55 design choice and is not claimed
as a TW-08 discriminator result.

The production contract uses generic worker-local `semantic_id` values. The
experimental CBL role vocabulary is not part of the production model. Source
selection remains an opaque candidate ID, and canonical paths enter only the
host-side `AuthoringDataSource` intent after source validation.

## Compiler Invariants

- Existing-section revision is rejected explicitly; CM-55 implements the
  validated new-section reconstruction boundary only.
- Selected sources and exact source-scoped channels are required.
- Curve channels must be scalar and raster channels must be array-valued.
- Track and per-track binding semantic IDs must be unique.
- Track, binding, and channel order are preserved.
- Repeated same-channel bindings remain separate canonical binding instances.
- Canonical section, track, and binding IDs are allocated by the host
  `IdAllocator`; semantic IDs are only allocation hints/correlation handles.
- Omitted semantic scales and presentation fields remain omitted from sparse
  intent so downstream defaults are not converted into explicit user intent.
- No styles, widths, grids, labels, fills, annotations, or renderer policy are
  invented by the compiler.

The compiler does not reconcile, execute, render, persist, call providers, or
repair invalid output.

## Evidence

The focused CM-55 suite covers:

- required track discriminator schema behavior;
- strict extra-field and branch-shape rejection;
- array scale requirements and identity validation;
- unchanged TW-02R golden semantic replay for `main_pass` and `repeat_pass`;
- deterministic output and host-owned identity allocation;
- ordering and repeated-channel preservation;
- linear, log, and tangential scales;
- generic, VDL, and waveform raster profiles;
- sample-axis propagation;
- source, channel, scalar/array, duplicate-identity, and revision validation;
- path-free worker models and sparse omission behavior.

Validation:

```text
16 focused CM-55 tests passed
69 adjacent architecture/Code Mode tests passed
Ruff check passed
Ruff format --check passed
git diff --check passed
```

## Deferred Work

CM-55 does not claim typed support for annotations, fills, curve overlays on
array tracks, complete style/grid/label semantics, all subtitle/depth-window
requests, or existing-section revision. These remain visible in the CM-54
representability matrix. CM-56 must measure real planner/enricher input
sufficiency before any expansion or section-worker cutover.

No provider calls, prompts, retries, repair, planner changes, enrichment
changes, graph changes, routing changes, MCP changes, notebook changes, or
legacy deletions occurred.

Production routing still uses the existing program section worker. CM-57
remains the cutover gate, and CM-58 remains the unchanged public/default-route
acceptance gate.
