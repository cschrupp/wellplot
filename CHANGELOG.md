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

The `0.1.0` section below is drafted for the first production PyPI release.
Replace `Draft` with the publication date when the release is promoted.

## [0.1.0] - Draft

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
