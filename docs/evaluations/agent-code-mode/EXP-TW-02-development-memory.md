# EXP-TW-02 Development Memory

## Status

Complete as a deterministic compiler experiment. Stop before EXP-TW-03 and
provider generation.

## Baseline

EXP-TW-00 `a31ff70`; EXP-TW-01 `6f9a2d6`.

## Compiler Boundary

`compile_section_draft()` enforces the sequence:

```text
SectionDraft structural validation
        -> EXP-TW-00 Gate A semantic validation
        -> canonical AuthoringDocumentIntent
```

The compiler preserves source selection, section title, ordered track titles
and kinds, ordered channels, curve/raster binding kinds, and repeated bindings.
It does not deduplicate, reorder, infer, repair, or substitute semantic data.

The output reuses the existing `AuthoringDocumentIntent`,
`AuthoringSectionIntent`, `AuthoringTrackIntent`, and typed binding intent
models. Host-owned section/track/binding identities and source provenance are
created only in the compiler output. They are absent from `SectionDraft` and
the normalized review projection.

The canonical intent boundary was selected because the TW-01 schema
deliberately omits renderer/layout values such as track widths. The compiler
does not invent those values to force an executable program representation.

## Validation

- Both golden drafts compile successfully.
- Repeated compilation is identical.
- Track order, titles, curve/raster kinds, channel order, and `CBL, CBL`
  multiplicity survive compilation.
- Gate-A-invalid drafts fail before canonical intent construction.
- Structurally invalid and downstream-unrepresentable values fail explicitly.
- Normalized compiler projections contain no paths or provider concepts.
- EXP-TW-00, EXP-TW-01, and EXP-TW-02 focused tests pass.
- Ruff, formatting, JSON validation, and `git diff --check` pass.
- Production package delta: `0`.

## Scope Evidence

Provider calls, prompts, adapters, retries, repair, graph/orchestration,
planner/enricher changes, rendering, and production integration: `0`.

## Decision

PROCEED to review EXP-TW-02. Stop before EXP-TW-03 until separately
authorized.
