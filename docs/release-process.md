# Release Process

This document describes the current release workflow for `wellplot`.

The workflow is designed to be safe by default:

- it always builds and verifies artifacts first
- it only publishes when explicitly requested
- TestPyPI and PyPI publishing are split into separate gated jobs

## Workflow file

- `.github/workflows/release.yml`

## Workflow inputs

The manual workflow accepts:

1. `publish_target`
   - `verify-only`
   - `testpypi`
   - `pypi`
2. `expected_version`
   - optional version guard such as `0.1.0`
   - if provided, the workflow checks it against `src/wellplot/_version.py`

## What the workflow does

The `build` job always runs first:

1. checks out the repository
2. sets up Python and `uv`
3. optionally verifies the requested version
4. runs `uv build`
5. creates a clean virtual environment
6. installs the built wheel into that clean environment
7. verifies the `wellplot` console entry point
8. runs `scripts/smoke_installed_wheel.py`
9. uploads the built artifacts for later publish jobs

Publishing jobs only run when selected:

- `publish-testpypi`
  - runs only when `publish_target=testpypi`
  - publishes with GitHub OIDC trusted publishing
  - expects a GitHub environment named `testpypi`
- `publish-pypi`
  - runs only when `publish_target=pypi`
  - publishes with GitHub OIDC trusted publishing
  - expects a GitHub environment named `pypi`

## Repository setup required before publishing

Before the workflow can publish, configure trusted publishing on both package indexes.

Recommended setup:

1. Create the project on TestPyPI.
2. Create the project on PyPI.
3. Configure trusted publishing on both indexes for:
   - owner: `cschrupp`
   - repository: `wellplot`
   - workflow: `release.yml`
4. Create GitHub environments:
   - `testpypi`
   - `pypi`
5. Add required reviewers to the `pypi` environment.

## Local preflight before a release run

Run the local validation path first:

```bash
uv run ruff check .
uv run python -m unittest discover -s tests -v
uv build
uv venv /tmp/wellplot-release-check
uv pip install --python /tmp/wellplot-release-check/bin/python dist/*.whl
/tmp/wellplot-release-check/bin/wellplot --help
MPLBACKEND=Agg /tmp/wellplot-release-check/bin/python scripts/smoke_installed_wheel.py
```

## TestPyPI rehearsal

Recommended rehearsal sequence:

1. Confirm the package version in `src/wellplot/_version.py`.
2. Run the local preflight checks.
3. Trigger the `Release` workflow manually with:
   - `publish_target=testpypi`
   - `expected_version=<current version>`
4. After publication, install from TestPyPI in a fresh environment and smoke test the package.

Example install command after a successful TestPyPI publish:

```bash
python -m venv /tmp/wellplot-testpypi
/tmp/wellplot-testpypi/bin/pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  wellplot
```

Completed rehearsal status as of 2026-04-11:

- the `Release` workflow successfully published `wellplot 0.1.0` to TestPyPI
- a fresh install from TestPyPI succeeded in a clean virtual environment
- `wellplot --help` and the installed-wheel smoke test both passed against the TestPyPI artifact

## PyPI release

Only promote to PyPI after a successful TestPyPI rehearsal.

Recommended PyPI sequence:

1. confirm the version and update `CHANGELOG.md` for the release
2. run the `Release` workflow with:
   - `publish_target=pypi`
   - `expected_version=<current version>`
3. verify a fresh PyPI install

## Current boundary

This repository now has:

- CI coverage for build and installed-wheel smoke testing
- a manual release workflow
- a TestPyPI-first release path
- a successful TestPyPI rehearsal for `wellplot 0.1.0`

What remains is the first production PyPI release and ongoing workflow maintenance.
