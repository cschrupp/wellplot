# Package Rename Plan: `well_log_os` to `wellplot`

Last updated: 2026-04-11

## Status

Completed in the codebase on 2026-04-11:

- Stage 1: Package Identity Switch
- Stage 2: Public Surface Rewrite

Still optional or pending:

- Stage 3: Repository and Docs Identity Cleanup
- Stage 4: Post-Rename Release Rehearsal

## Decision Summary

The library should ship under the public name `wellplot`.

Current state:

- the published package identity in the codebase is now `wellplot`
- the top-level Python import is now `wellplot`
- the CLI entry point is now `wellplot`
- repository URLs still point to the current GitHub repository name `well-log-os`

Availability checks completed on 2026-04-11:

- PyPI direct project checks for `wellplot`, `wellview`, and `wellstudio` returned `404`
- GitHub owner namespace `cschrupp/` has no existing `wellplot`, `wellview`, or `wellstudio` repository
- pre-rename local runtime import check showed:
  - `wellplot`: missing
  - `well_log_os`: present from `src/well_log_os/__init__.py`
- pre-rename repository text scan showed no existing `wellplot` references yet

Conclusion:

- `wellplot` is clear enough to use as the public import and distribution name
- `wellview` is too crowded on GitHub
- `wellstudio` is better kept for a future application or interactive platform layer

## Migration Strategy

Use a pre-release hard cut.

Reasoning:

- the project has not been published to PyPI yet
- there is no external installed-user base to protect
- keeping both `well_log_os` and `wellplot` would add avoidable maintenance and documentation clutter

That means:

- rename the Python package to `wellplot`
- rename the distribution to `wellplot`
- rename the console script to `wellplot`
- update docs, examples, tests, and internal metadata in the same change window
- do not keep a long-lived compatibility shim unless a concrete migration need appears

## Rename Surface

Current impact scan on 2026-04-11:

- `src/`: 7 files mention `well_log_os`
- `tests/`: 13 files mention `well_log_os`
- `examples/`: 14 files mention `well_log_os`
- `docs/` + `README.md`: 13 files mention `well_log_os`

Primary rename targets:

- package directory:
  - `src/well_log_os/` -> `src/wellplot/`
- package metadata:
  - `pyproject.toml`
- public imports:
  - tests, examples, docs, notebooks
- CLI commands:
  - `well-log-os` -> `wellplot`
  - `python -m well_log_os.cli` -> `python -m wellplot.cli`
- project text:
  - README title and usage examples
  - documentation titles and reference paths
  - schema titles and docstrings that expose the old package name

## Staged Implementation Checklist

### Stage 1: Package Identity Switch

Goal:

- make `wellplot` the only supported package identity before the first public release rehearsal

Changes:

- rename `src/well_log_os/` to `src/wellplot/`
- update `pyproject.toml`:
  - `[project].name = "wellplot"`
  - script entry point to `wellplot = "wellplot.cli:main"`
  - dynamic version source to `wellplot._version.__version__`
  - package-data target to `wellplot.renderers`
  - Ruff first-party setting to `wellplot`
- regenerate package metadata artifacts as needed

Validation:

- `uv run ruff check .`
- `uv run python -m unittest discover -s tests -v`
- `uv build`
- installed-wheel smoke test using the renamed CLI and import path

Implemented on 2026-04-11.

### Stage 2: Public Surface Rewrite

Goal:

- make all documented imports and commands consistent with the new package identity

Changes:

- update every repo import from `well_log_os` to `wellplot`
- update README usage blocks
- update docs pages under `docs/` and `docs/site/`
- update notebooks and examples
- update any test assertions that hardcode package/module names

Validation:

- import-contract tests still pass under `wellplot`
- example scripts still run
- docs snippets match the actual runtime interface

Implemented on 2026-04-11.

### Stage 3: Repository and Docs Identity Cleanup

Goal:

- align packaging, docs, and repository naming

Changes:

- rename repository if desired:
  - `well-log-os` -> `wellplot`
- update project URLs in `pyproject.toml`
- update GitHub Pages path if repository name changes
- update badges, release workflow text, and documentation URLs

Validation:

- docs deploy to the correct URL
- release workflow references the right package and repository names

### Stage 4: Post-Rename Release Rehearsal

Goal:

- prove the renamed library can be built, installed, documented, and published cleanly

Changes:

- run the first real TestPyPI rehearsal using `wellplot`
- verify wheel install from TestPyPI in a clean virtual environment
- confirm console script, imports, and docs examples all use `wellplot`

Validation:

- `pip install wellplot` works from TestPyPI
- `wellplot --help` works
- notebook and API examples import `wellplot` successfully

## Things Not To Do

- do not keep `well_log_os` as a permanent parallel public API unless a real migration case appears
- do not rename only the distribution while keeping the old import path
- do not update docs first and postpone code/package changes, because that creates false instructions
- do not run the first public TestPyPI rehearsal before the package identity is settled

## Recommended Order Relative To The Roadmap

Recommended immediate sequence:

1. run the first real TestPyPI rehearsal for `wellplot`
2. decide whether to rename the GitHub repository from `well-log-os` to `wellplot`
3. if the repository name changes, update project URLs and docs deployment paths
4. resume the remaining production-readiness tasks

This keeps the first public package rehearsal aligned with the final library name instead of creating
avoidable cleanup after publication.
