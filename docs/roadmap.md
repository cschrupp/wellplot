# wellplot Roadmap

Last updated: 2026-04-22

## Scope Summary

Build and mature an open-source Python toolkit for high-quality well-log display from LAS/DLIS with:

- print-first PDF generation
- interactive viewing
- template-driven layout control

Decision history is tracked in `docs/decision-log.md`.

## Current Baseline

- YAML templates define page, depth axis, tracks, styles, annotations.
- The programmatic API is now available through:
  - `wellplot.api.dataset`
  - `wellplot.api.builder`
  - `wellplot.api.render`
  - `wellplot.api.serialize`
- Logfile config is now track-first:
  - `document.layout.log_sections[*].tracks` defines layout
  - `document.bindings.channels[*]` assigns channels to tracks
- Legacy `auto_tracks` flow has been removed from the MVP path.
- Physical layout engine computes page windows and track frames.
- Track taxonomy is explicit with compatibility aliases:
  - `reference` (`depth` alias), `normal` (`curve` alias), `array` (`image` alias), `annotation`.
- Reference tracks can define layout axis values (unit/scale/steps) and render reference labels inside track bounds.
- Matplotlib renderer supports:
  - printable output
  - continuous single-page PDF
  - depth grid + markers/zones
  - structured track header object slots
  - fixed-height curve and array property groups in track headers
  - curve-owned fills:
    - `between_curves`
    - `between_instances`
    - `to_lower_limit`
    - `to_upper_limit`
    - `baseline_split`
  - track-header fill indicators that reflect actual fill semantics
  - in-track curve callouts with edge avoidance and curve-aware placement
  - section-relative repeated callouts from top/bottom anchors
  - reference-track scalar overlay modes (`curve`, `indicator`, `ticks`)
  - reference-track-local event objects for non-channel markers
  - reference-track headers that keep the layout scale row while exposing overlay properties
  - annotation-track `interval`, `text`, `marker`, `arrow`, and `glyph` rendering
  - annotation-track dedicated label lanes and collision-aware label placement for marker/arrow labels
  - array-lane raster controls (`colorbar`, `sample_axis`, waveform overlay)
  - waveform-only array rendering profile
  - VDL density rendering with grayscale amplitude mapping
  - DLIS-derived raster sample-axis metadata with savefile overrides
- Plotly renderer provides interactive visualization baseline.
- Synthetic example exists for fast iteration (`examples/synthetic_demo.py` + `examples/triple_combo.yaml`).
- Log-file schema validation is implemented (JSON Schema + CLI `validate`).
- YAML template/savefile inheritance is implemented for reusable log designs.
- Section placeholders exist in YAML for report composition:
  - `layout.heading`
  - `layout.remarks`
  - `layout.log_sections`
  - `layout.tail`
- Programmatic dataset workflows now support:
  - computed-channel ingestion from numpy lists/arrays
  - pandas `Series` / `DataFrame` adapters
  - index sorting, unit conversion, reindexing, and dataset merge helpers
  - partial renders for section/track/window scopes
  - notebook-friendly PNG/SVG byte rendering
  - YAML round-trip helpers for normalized documents and report mappings
- Report packets now include:
  - shared heading/tail report blocks
  - fixed-row `open_hole` and `cased_hole` detail tables
  - first-page `remarks` sections
- User documentation foundation is now in place:
  - MkDocs + Material site scaffold under `docs/site`
  - Read the Docs primary build configuration under `.readthedocs.yaml`
  - GitHub Pages mirror deployment workflow under `.github/workflows/docs.yml`
  - workflow-oriented guides for installation, concepts, datasets, examples, report pages,
    rendering, and the Python API
  - expanded reference pages for:
    - Python API
    - YAML logfile structure
    - report pages
- Production hardening is underway:
  - Apache-2.0 SPDX headers applied across source, tests, and examples
  - `pydocstyle` rollout completed across `src/`, `tests/`, and `examples/`
  - `ANN` enforcement now passes repo-wide across `src/`, `tests/`, and `examples/`
  - package metadata now includes keywords, project URLs, SPDX license expression, and dynamic
    version sourcing
  - the top-level package and `wellplot.api` public surfaces are covered by import-contract
    tests
  - local `uv build` validation succeeds for both sdist and wheel
- Data source routing is section-first with optional root fallback:
  - `layout.log_sections[*].data.source_path`
  - `layout.log_sections[*].data.source_format`

## MVP Architecture Gaps (layout/bindings model, 2026-03-10)

Needed next to complete the intended workflow:

- Render all `layout.log_sections` sequentially in one output artifact (implemented for matplotlib).
- Refine report composition beyond the current `heading` / `remarks` / `tail` baseline.
- Allow per-section depth windows and per-section page/layout settings.
- Add section-aware bindings (`binding.section`) in rendering, not only schema/validation.
- Add track-level default element properties to reduce binding repetition (style/scale/header display).
- Add validation for unbound required tracks and optional strict mode for empty tracks.
- Add CLI/report diagnostics that summarize section coverage and binding coverage.

## Completed Phase: Programmatic API and Dataset Ingestion (2026-04-11)

This phase is no longer planned work. It is now part of the project baseline.

Delivered goals:

- researchers can add computed channels from numpy/pandas back into `WellDataset`
- logs can be composed in Python without hand-authoring YAML
- full and partial renders are available for notebook workflows
- YAML remains a first-class serialization format without being the only authoring surface

Delivered public modules:

- `wellplot.api.dataset`
- `wellplot.api.builder`
- `wellplot.api.render`
- `wellplot.api.serialize`

Detailed checklist:

- [docs/programmatic-api-plan.md](programmatic-api-plan.md)

Delivered status:

- implemented:
  - dataset-ingestion API
  - pandas/Series/DataFrame adapters
  - dataset alignment helpers:
    - `sort_index(...)`
    - `convert_index_unit(...)`
    - `reindex_to(...)`
  - dataset merge/update conveniences:
    - `rename_channel(...)`
    - `merge(..., collision="error|replace|rename|skip")`
    - provenance `merge_history`
  - in-memory composition/render bridge
  - partial render API for section/track/window scopes
  - notebook byte outputs for PNG/SVG previews
  - YAML round-trip helpers for `LogDocument` and report mappings
  - serialization convenience wrappers:
    - `save_document(...)` / `load_document_yaml(...)`
    - `save_report(...)` / `load_report(...)`
  - builder/report persistence helpers:
    - `LogBuilder.save_yaml(...)`
    - `ProgrammaticLogSpec.to_yaml(...)`
    - persisted section `source_path` / `source_format`
  - notebook examples for dataset ingestion and layout rendering
  - coherent end-to-end workflow example:
    - [examples/api_end_to_end_demo.py](examples/api_end_to_end_demo.py)
- remaining polish that now belongs to production hardening:
  - dataset provenance/collision polish beyond the current merge-history baseline
  - notebook-first end-to-end demo parity if we decide to maintain full `.ipynb` coverage

## Current Phase: Production Readiness and Release Hardening (2026-04-11)

This is now the active phase.

Core goals:

- turn the project into a clean publishable Python library
- keep the public API stable and explicitly tested
- publish user documentation on Read the Docs with GitHub Pages as a mirror
- raise code quality with staged, enforceable linting and documentation rules

Current status:

- implemented:
  - MkDocs + Material documentation scaffold
  - Read the Docs primary hosted documentation
  - GitHub Pages mirror deployment workflow
  - workflow-oriented user docs under `docs/site/`
  - expanded user reference docs for the Python API, YAML logfile schema, and report pages
  - Apache-2.0 SPDX file headers across source, tests, and examples
  - repo-wide `pydocstyle` rollout
  - repo-wide `ANN` rollout across `src/`, `tests/`, and `examples/`
  - package metadata cleanup:
    - SPDX license expression
    - project URLs
    - keywords
    - dynamic version sourcing from package code
  - package identity transition completed:
    - source package renamed from `well_log_os` to `wellplot`
    - distribution name is now `wellplot`
    - console entry point is now `wellplot`
    - imports, tests, examples, notebooks, and user docs were rewritten to the new public name
  - public import-contract tests for `wellplot` and `wellplot.api`
  - local wheel/sdist build verification with `uv build`
  - clean install smoke testing from the built wheel
  - CI coverage for lint, tests, extras, build, and installed-wheel smoke validation
  - manual release workflow with gated `verify-only`, `testpypi`, and `pypi` paths
  - first real TestPyPI rehearsal completed for `wellplot 0.1.0`:
    - GitHub Actions publish to TestPyPI succeeded
    - fresh TestPyPI install in a clean virtual environment succeeded
    - `wellplot --help` and the installed-wheel smoke test both passed
  - first public PyPI release completed for `wellplot 0.1.0`
  - generated example notebooks and production example docs now prefer
    installed-package usage over repo-local `src/` bootstrapping
- next:
  - keep pruning stale comments and filling public API docstring gaps where they still exist
  - keep expanding user docs depth while the public library surface stabilizes
  - review and refactor the example set into clearer end-user guides instead of
    development-oriented validation demos

## CBL Parity Gaps (from comparison test, 2026-03-09)

Compared against `workspace/renders/CBL_log_example.Pdf`, the current renderer is missing:

- Cover/disclaimer/contents pages and report-style front matter.
- Richer remarks/notes layouts for the lower half of the first report page.
- Parameter-table sections (channel processing, depth zone, tool control).
- Advanced annotation packing for very dense tracks beyond the current dedicated-label-lane model.
- Composite lane logic with custom legend/table blocks.
- Multi-page report composition mode (in addition to continuous strip mode).
- Richer visual theming and table/border styles for commercial-style output.
- Final-user calibration workflow for vendor-specific micro-time origin/width differences in VDLs.

## Curve Properties Matrix (Techlog Comparison, 2026-03-09)

Implementable now (already in project):

- Horizontal limits (`min`/`max`) and scale type (`linear`/`log`) per curve.
- Inversion (`reverse`) per curve.
- Curve line color, thickness, style, opacity.
- Multi-curve track overlays with independent per-curve scaling.
- Per-curve header rows (name + scale/limits + unit).
- Per-curve header display toggles
  (`show_name`, `show_unit`, `show_limits`, `show_color`, `wrap_name`).
- Optional header `divisions` object for per-track scale ticks in a dedicated header line.
- Value-label mode with step, number format, precision, alignment, font.
- Header typography and frame styling through `render.matplotlib.style`.
- Baseline curve-wrap mode with per-segment color
  (`bindings.channels[*].wrap.enabled`, `bindings.channels[*].wrap.color`) for repeat-style display.
- Curve fill modes:
  - `between_curves`
  - `between_instances`
  - `to_lower_limit`
  - `to_upper_limit`
  - `baseline_split`
- Track-header fill indicators that preview the rendered fill behavior.
- In-track curve callouts with section-relative repetition from top/bottom anchors.

Near-term additions (next phases):

- Points/symbol mode (`marker` type, size, optional color-by-variable).
- Vertical thresholds and advanced repeat/wrap controls (count, offset, style).
- Per-curve decimation/display optimization policy.
- Per-curve number formatting for header limits (separate from label mode).
- Per-callout priority/required rules for dense tracks.
- Page-relative callout repetition mode, if needed alongside the current section-relative mode.

Longer-term / UI-centric:

- Full variable-management metadata blocks (family/alias/version history).
- Interactive graphical editing and audit/history panel.
- Per-curve reference-window controls (top/base limits in alternate units).

## Development Plan

### Phase A: Production Hardening (current)

- Keep package metadata, docs, and public exports aligned.
- Continue staged lint/docstring tightening where signal remains high.

### Phase B: Rendering Quality

- Improve default typography and spacing for print fidelity.
- Add richer depth column behavior (interval labels, optional callout lanes).
- Add configurable reference-value placement/alignment policies inside track (left/center/right, collision handling).
- Improve raster controls (color limits, interpolation presets, palettes).
- Add explicit micro-time calibration helpers/presets for VDL sample-axis tuning.
- Add configurable track border styles and divider systems.

### Phase C: Interactive Viewer Maturity

- Expand interactive controls (track visibility, zoom presets, annotations).
- Add synchronized depth cursor and track crosshair behavior.
- Support export/import of viewer state from templates.
- Add UI-ready edit model for reference-track properties (header toggles, number format, grids).

### Phase D: I/O and Standardization

- Harden LAS and DLIS adapters for real-world edge cases.
- Verify dependency licenses and document compatibility notes.
- Define template schema versioning and migration notes.
- Add explicit schema blocks for `reference`, `array`, and `annotation` track-specific configs.

### Phase E: Packaging and Ecosystem

- Maintain the published package through the rehearsed PyPI release flow.
- Expand docs with API reference and cookbook-style templates.
- Publish contributor guide and architecture notes.
- Prepare roadmap for web service/UI packaging.

## Immediate Next Tasks

- Maintain release hardening:
  - keep PyPI trusted publishing and post-release install verification healthy
  - clean up remaining workflow maintenance noise such as action runtime deprecation warnings
- Expand user documentation from the current workflow-first baseline:
  - Python API reference pages
  - YAML/report-schema reference pages
  - cookbook-style examples tied to real workflows
- Continue staged code-quality tightening:
  - remove `ANN` per-file ignores from `tests/` and `examples/` over time
  - keep filling docstrings on stable public surfaces
  - continue stale comment cleanup where refactors have moved the code
- Revisit remaining rendering/model polish after the release baseline is secure:
  - dataset provenance/collision refinements
  - per-section layout overrides if needed
  - track-level binding defaults and stricter empty-track validation
  - additional reference/array examples where they improve the user docs rather than just
    showcase isolated features
- Add annotation-track polish beyond the current object baseline:
  - richer label-lane contracts
  - optional repacking rules for dense interval/text/glyph compositions
- Add a paginated report mode for mixed pages + log strips.
- Add style tokens/themes for branded tables, headers, and borders.
- Add a schema reference page for YAML keys (especially `track_header.objects`).
- Add visual regression checks for header slot layout and non-overlap.
- Tune default header `line_units` and font scaling against real CBL examples.
- Add one more end-to-end sample with multiple image tracks + overlays.
- Add savefile examples for VDL micro-time tuning against vendor outputs.

## Working Principles

- Treat each visual element as a typed object, not ad-hoc text.
- Preserve physically meaningful layout dimensions.
- Keep model decisions explicit and test-backed.
- Prefer stable defaults, then add opt-in complexity.
