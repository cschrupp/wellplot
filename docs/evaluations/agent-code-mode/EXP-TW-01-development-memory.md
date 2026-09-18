# EXP-TW-01 Development Memory

## Status

Complete as a schema-only experimental slice. Stop before EXP-TW-02 and
provider generation.

## Baseline

EXP-TW-00 commit `a31ff70`.

## Purpose

Define the smallest typed semantic response that represents the frozen CBL
section tasks while leaving program mechanics to a later compiler experiment.

## Schema

The experimental schema contains:

- `SectionDraft`: title, optional subtitle, opaque source candidate, ordered tracks.
- `TrackDraft`: semantic track kind, title, ordered bindings.
- `CurveBindingDraft`: scalar curve channel.
- `RasterBindingDraft`: array raster channel.

All models are frozen and reject unknown fields. Source and channel validity
remain host-side Gate A checks against the selected `ResolvedSectionContext`.

The schema contains no canonical paths, renderer settings, layout coordinates,
matplotlib concepts, provider fields, prompts, handles, executable calls, or
compiler instructions.

## Fixtures and Tests

- Golden drafts are manually authored for `main_pass` and `repeat_pass`.
- Both drafts reuse the EXP-TW-00 corpus and pass its Gate A scorer.
- JSON serialization and Pydantic JSON round-trip preserve track order and the
  repeated `CBL, CBL` bindings.
- Negative tests cover unknown source, unavailable channel, scalar/array
  mismatch, collapsed repeated binding, and reordered tracks.
- Schema serialization and fixture content are checked for prohibited concepts.

## Validation

- Focused EXP-TW-01 tests pass.
- Ruff check and format checks pass for the new script and tests.
- JSON validation passes for the golden fixture.
- `git diff --check` passes.
- Production package delta: `0`.
- Provider calls, prompts, compiler generation, retries, graph changes, and
  production integration: `0`.

## Decision

PROCEED to review EXP-TW-01. Stop before EXP-TW-02 until separately
authorized.
