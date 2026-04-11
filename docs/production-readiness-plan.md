# Production Readiness Plan

## Purpose

This document defines the next major development phase for `wellplot` after the initial rendering and programmatic API milestones.

The goals of this phase are:

1. Create proper user documentation suitable for publication on GitHub Pages.
2. Normalize copyright and license notices across the codebase.
3. Raise code quality to production level with explicit Python/PEP compliance targets.
4. Finalize the project as a reusable Python library and prepare it for publication.

## Baseline Observations

### Current license state

The repository currently ships with:

- `LICENSE`: Apache License 2.0
- `pyproject.toml`: `License :: OSI Approved :: Apache Software License`
- docs already reference `Apache-2.0`

This means the repository is currently Apache-2.0 licensed, not GPL.

A GPL-style header must therefore **not** be copied into the codebase as-is. If we keep Apache-2.0, the file header text must match Apache-2.0 terms.

### Current documentation state

The repository already contains internal/project docs:

- `README.md`
- `docs/decision-log.md`
- `docs/programmatic-api-plan.md`
- `docs/rendering-workings.md`
- `docs/roadmap.md`

These are useful for development, but they are not yet a complete end-user documentation site.

### Current packaging state

The project already has a working package skeleton:

- `pyproject.toml`
- `src/` layout
- console script entry point
- optional dependency groups

This is a good base, but it is not yet a fully polished publishable library.

## Guiding Decisions

### 1. Apache-2.0 is the confirmed license

The project license is confirmed as Apache-2.0. Production work should proceed on that basis.

Required action:

- keep Apache-2.0
- add Apache-compatible copyright headers
- do **not** introduce GPL boilerplate
- keep `LICENSE`, `pyproject.toml`, headers, and docs aligned

### 2. Prefer concise file headers over large boilerplate blocks

For maintainability, every source file should not carry a full long-form license body.

Recommended header format for Python source files:

```python
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
```

Optional extended form, adjusted from the example style to match Apache-2.0:

```python
#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
# 
# Copyright (C) 2026 Carlos Schrupp
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
```

Recommendation:

- use the short SPDX form as the repo default
- use the longer Apache block only if we explicitly decide the extra verbosity is worth it

### 3. Treat documentation as a product surface

The project now has enough scope that docs should be organized for users, not only contributors.

The documentation site should answer:

- what the library is
- how to install it
- how to use YAML workflows
- how to use the Python API
- how to render full and partial outputs
- how to ingest numpy/pandas data
- how to author layouts, headings, remarks, and tails
- how to publish or integrate results into notebooks

### 4. Production quality means targeted compliance, not blind rule chasing

We do **not** need to satisfy every PEP uniformly in a bureaucratic way.

We **do** need to comply with the Python conventions that materially improve:

- readability
- maintainability
- packaging correctness
- API stability
- documentation quality
- static analysis

## Workstreams

## Workstream A: User Documentation Site

### Goal

Publish proper user-facing documentation on GitHub Pages.

### Recommendation

Use **MkDocs + Material for MkDocs** for the first production docs site.

Reason:

- simpler GitHub Pages deployment than a custom stack
- strong navigation/search out of the box
- works well with Markdown
- low friction for example-heavy projects
- easier than Sphinx for fast iteration unless we later require heavy API autodoc features

Alternative:

- Sphinx remains viable if we later want deeper API reference generation and intersphinx-heavy docs
- for this phase, MkDocs is the pragmatic option

### Documentation structure

Recommended top-level sections:

1. `Getting Started`
2. `Installation`
3. `Concepts`
4. `YAML Workflow`
5. `Python API`
6. `Datasets`
7. `Rendering`
8. `Report Pages`
9. `Examples`
10. `Contributing`
11. `Reference`

### Minimum docs content for first release

1. Overview and positioning
- what `wellplot` does
- supported data sources
- static rendering vs programmatic rendering

2. Installation
- minimal install
- optional extras: `las`, `dlis`, `pandas`, `interactive`, `all`

3. Quick start
- YAML example
- Python API example
- notebook example

4. Core concepts
- dataset
- document
- section
- track
- binding
- report pages

5. User guides
- ingest LAS/DLIS
- add computed channels from numpy/pandas
- build a document programmatically
- render a PDF
- render a section/window/track
- export YAML

6. Reference pages
- page options
- track types
- fill modes
- callouts
- annotation tracks
- report block fields

7. Example gallery
- curated examples with screenshots/PDF links
- avoid synthetic nonsense; prefer coherent demos

### GitHub Pages rollout tasks

1. Add `mkdocs.yml`
2. Create `docs/site/` or equivalent docs-site content layout
3. Migrate or cross-link existing internal docs
4. Add GitHub Actions workflow for Pages build/deploy
5. Add version-independent base docs first; versioning can come later

## Workstream B: Copyright and License Headers

### Goal

Make copyright and licensing explicit and consistent.

### Scope

Apply headers to:

- `src/**/*.py`
- `tests/**/*.py`
- `examples/**/*.py`

Do **not** add headers to:

- generated artifacts
- notebooks by default
- YAML examples unless explicitly desired
- vendored/third-party files

### Header standard

Default header:

```python
# Copyright (C) 2026 wellplot contributors
# SPDX-License-Identifier: Apache-2.0
```

### Required consistency tasks

1. Confirm copyright owner string
- use `Carlos Schrupp`
- update only if a future legal entity replaces the personal copyright holder

2. Keep these aligned:
- `LICENSE`
- `pyproject.toml`
- headers
- `README.md`
- documentation site

3. Add a `NOTICE` file only if needed for Apache attribution workflow

### Implementation strategy

1. write a header-insertion script
2. exclude generated or external files
3. run once and review diff carefully
4. enforce for new files via lint/pre-commit later if desired

## Workstream C: Python Style and PEP Compliance

### Goal

Bring the codebase to production-grade Python conventions.

### Priority PEPs / standards

These are the practical standards we should target.

#### PEP 8

Scope:

- naming
- whitespace
- import order
- line length consistency
- comment formatting
- module/class/function layout

Current enforcement foundation:

- Ruff already runs

Recommended expansion:

- enable more Ruff rules gradually instead of doing a one-shot style explosion

#### PEP 257

Scope:

- module docstrings where needed
- public class/function docstrings
- consistent imperative style
- clear parameter/return descriptions for public APIs

Priority:

- public API modules first
- builders, dataset helpers, render helpers, serializers, key model objects

#### PEP 484 / typing discipline

Scope:

- meaningful type hints on public APIs
- avoid `Any` leakage in outward-facing interfaces
- tighten internal helpers over time

Priority:

- public API first
- serialization layer second
- builder/render layer third

#### PEP 526

Scope:

- variable annotations where they clarify nontrivial state
- especially builder internals and structured mapping assembly

#### PEP 621

Scope:

- project metadata in `pyproject.toml`
- keep package metadata complete and correct

Already partly done, but needs polishing.

#### Packaging compatibility PEPs already relevant

- PEP 517/518: build backend and build-system config
- PEP 440: versioning discipline

### Comment/docstring expectations

We should specifically audit for:

1. comments that restate code instead of explaining intent
2. missing public docstrings
3. inconsistent terminology between YAML and API
4. stale comments after refactors
5. mixed comment style across modules

### Recommended linting expansion

Current Ruff selection is narrow.

Recommended staged expansion:

Phase C1:
- keep current rules
- add docstring rules gradually
- add selected simplification and bug-risk rules

Phase C2:
- add stricter naming and annotation rules where signal is good
- only after initial cleanup

Suggested approach:
- enable new rule groups one at a time
- clean repo
- lock them in

### Production-quality audit checklist

1. Public API docstrings complete
2. Clear exceptions and error messages
3. No misleading comments
4. No dead code in public paths
5. No obvious duplication in builders/serializers
6. Stable names for exported API surface
7. Tests for main public workflows

## Workstream D: Library Hardening and Publishability

### Goal

Turn the repository into a clean publishable Python library.

### Packaging tasks

1. Verify package metadata
- description
- authors/maintainers
- license
- classifiers
- keywords
- project URLs

2. Add missing project URLs in `pyproject.toml`
- homepage
- documentation
- source
- issues

3. Review extras naming and installation guidance

4. Confirm sdist/wheel contents
- include YAML renderer defaults
- include docs assets only if intended
- exclude generated files

5. Add package-level version policy
- use semver-like discipline under PEP 440
- decide whether version remains static or generated

### Public API hardening

1. define supported imports from `wellplot`
2. define supported imports from `wellplot.api`
3. avoid exposing unstable internals accidentally
4. document deprecation policy before breaking changes

### CI/release tasks

1. add full CI matrix
- lint
- unit tests
- build wheel/sdist
- smoke import

2. add release workflow
- build artifacts
- publish to TestPyPI first
- then PyPI

3. add pre-release checklist
- docs build
- examples run
- package build check
- install from built wheel

## Workstream E: Release Documentation and Examples

### Goal

Ship with coherent examples, not just feature fragments.

### Required example set

1. YAML quickstart example
2. Programmatic API quickstart example
3. Dataset ingestion example with pandas
4. Partial render example for notebooks
5. End-to-end example combining:
- ingestion
- computed channel
- merge/alignment
- render
- serialization

### Example quality rule

Examples must be:

- coherent
- purposeful
- representative of real workflows
- not decorative or misleading

## Proposed Execution Order

## Phase 0: Governance

1. Record Apache-2.0 as the project license in the release checklist.
2. Use `Carlos Schrupp` as the copyright owner in file headers.
3. Decide exactly which file classes get headers.

## Phase 1: Docs foundation

1. add MkDocs scaffold
2. create GitHub Pages deployment
3. create user-doc skeleton
4. migrate README into docs landing flow

## Phase 2: License headers

1. implement header insertion script
2. apply to source/tests/examples
3. verify exclusions
4. review diff manually

## Phase 3: Style/PEP audit

1. baseline Ruff/format pass
2. comment cleanup audit
3. public docstring pass
4. typing pass on public API
5. expand Ruff rule set in stages

## Phase 4: Packaging hardening

1. metadata cleanup
2. public API review
3. wheel/sdist validation
4. CI release workflow

## Phase 5: Publish rehearsal

1. build locally
2. install from wheel in clean environment
3. run smoke examples
4. publish to TestPyPI
5. verify install and docs links

## Phase 6: Public release

1. publish docs site
2. publish package
3. tag release
4. announce supported entry points and examples

## Definition of Done

This phase is complete when all of the following are true:

1. A user can browse complete documentation on GitHub Pages.
2. The package can be installed cleanly from a built wheel.
3. Public API surfaces are documented and tested.
4. Licensing is internally consistent and visible in source headers.
5. Style/docstring/comment standards are enforced at an agreed level.
6. Release automation exists and works on a dry run.

## Immediate Next Action

The correct first implementation step is **Phase 0**:

1. apply `Carlos Schrupp` as the copyright owner string
2. confirm short-vs-long Apache header policy
3. then scaffold the documentation site

The license itself is already settled as Apache-2.0.
