###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################

# Changelog

This changelog tracks public release notes for the `wellplot` distribution.

The entries below track public PyPI releases of the `wellplot` distribution.

## [0.6.0] - 2026-08-10

The deterministic authoring contract and provider-neutral agent workflow are
now the release baseline for the MCP surface.

### Added

- Typed authoring models, context resolution, generic defaults, dependency-
  ordered reconciliation, and read-after-write phase verification.
- Deterministic header archetype ingestion and matching header-value filling,
  duplicate bindings, raster bindings, annotations, page settings, and
  explicit style/scale editing through the shared authoring service.
- Agent-side request coverage, operation-plan metadata, defaults provenance,
  structured run state, blocked-phase reporting, and optional phase previews.
- Canonical LAS and experimental CBL/VDL notebook workflows with release-gate
  documentation, cross-domain acceptance fixtures, and open-world generic
  track construction checks.

### Changed

- Natural-language authoring submits typed desired state to deterministic MCP
  operations instead of allowing the provider to invent packet structure.
- Defaults remain generic and subordinate to explicit user values; packet
  assets are scaffolds or regression fixtures, not hidden authoring authority.
- Generic form completion covers uncatalogued scalar, reference, array, and
  annotation tracks; family conventions remain optional and report their
  provenance when selected.

### Notes

- MCP remains local stdio-first and provider-neutral. Remote transport,
  persistent memory, and credentialed live-provider acceptance remain deferred
  or manual release activities.

## [0.3.0] - 2026-04-28

Experimental MCP support is now part of the public `wellplot` distribution.
This release folds the planned scoped-preview and writable-authoring MCP slices
into one publishable version.

### Added

- Optional `wellplot[mcp]` install extra and `wellplot-mcp` stdio entry point
  for local MCP clients.
- MCP tools for logfile validation, inspection, generic preview rendering,
  explicit section/track/window PNG previews, explicit file rendering, example
  bundle export, and canonical logfile YAML validation/format/save flows.
- Packaged MCP resources for the logfile schema and curated production example
  bundles, plus guided prompts for logfile review, preview, and example-based
  starts.
- Public MCP user documentation covering installation, client registration,
  server-root policy, workflow usage, and API reference.

### Changed

- Release verification now smoke-tests both the base installed wheel and a
  clean environment with the optional MCP dependency enabled.
- Maintainer release guidance now includes MCP-specific preflight checks and a
  TestPyPI rehearsal recommendation for releases that change the MCP surface or
  verification path.

### Fixed

- Scoped section and track previews now preserve implicit bindings for
  single-section savefiles, preventing filtered render failures during MCP
  preview calls.

### Notes

- MCP remains experimental in this release.
- `format_logfile_text(...)` and `save_logfile_text(...)` normalize the logfile
  through the canonical serializer path; comments, anchors, and template
  indirection are not preserved in the returned YAML text.

## [0.1.0] - 2026-04-22

Initial public release of `wellplot` as an open-source Python toolkit for
building printable and interactive well-log layouts from LAS, DLIS, and
programmatic datasets.

### Added

- Typed dataset and document models for scalar, array, and raster channels plus
  physically sized page, track, header, footer, marker, zone, and annotation
  specifications.
- YAML logfile and template pipeline with schema validation, inheritance, and
  report composition support for `heading`, `remarks`, `log_sections`, and
  `tail`.
- Static and interactive rendering backends with Matplotlib PDF output,
  Plotly interactive figures, partial section/track/window renders, and
  notebook-friendly PNG/SVG byte rendering.
- Optional LAS and DLIS ingestion adapters, including DLIS VDL/WF1-style array
  support and derived raster sample-axis handling.
- Curve rendering controls for crossover fills, baseline and limit fills,
  header fill indicators, reference-track overlays, reference-track local
  events, curve callouts, and annotation-track objects.
- Programmatic API surfaces for dataset creation, alignment, merge, unit
  conversion, report composition, YAML serialization, and render entry points.
- CLI commands for logfile validation and rendering.
- Production-oriented example packets, workflow documentation, and generated
  walkthrough notebooks for the example set.

### Changed

- The public package identity is now `wellplot` for imports, distribution
  metadata, and the `wellplot` console entry point.
- Documentation has been reorganized around user workflows, reference pages,
  production examples, and release/publishing guidance.
- Release validation now includes built-wheel smoke testing, clean install
  verification, and a gated TestPyPI-to-PyPI workflow.

### Quality

- Repo-wide lint and docstring enforcement now passes across `src/`, `tests/`,
  and `examples/`.
- Build metadata, SPDX licensing, project URLs, and import-contract tests were
  tightened in preparation for the first public package release.

### Notes

- The example notebooks still use repository-local bootstrapping for imports.
  After the first published package flow is stable, update them to prefer
  installed-package-first recipes.
- The production example packets document public-data and IP-use remarks and
  should remain the canonical starting point for end-user examples.
