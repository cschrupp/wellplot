# Release And Publishing

This page documents the maintainer workflow for building and publishing
`wellplot`.

It is intentionally separate from the normal user workflows because it describes
package-release operations, not day-to-day dataset or rendering usage.

## Scope

The current release path is designed to be safe by default:

- build artifacts first
- verify the installed wheel in a clean environment
- publish only when explicitly requested
- keep TestPyPI and PyPI as separate gated targets

## Workflow File

- `.github/workflows/release.yml`

## Manual Inputs

The GitHub Actions workflow accepts two important inputs:

1. `publish_target`
   - `verify-only`
   - `testpypi`
   - `pypi`
2. `expected_version`
   - optional version guard such as `0.1.0`
   - checked against `src/wellplot/_version.py`

## Build Job

The build job always runs, even when the workflow is only being used as a
verification rehearsal.

It performs these steps:

1. check out the repository
2. install Python and `uv`
3. optionally verify the requested version
4. run `uv build`
5. create a clean virtual environment
6. install the newly built wheel into that clean environment
7. verify the `wellplot` console entry point
8. run `scripts/smoke_installed_wheel.py`
9. upload artifacts for the later publish job

## Publishing Targets

### `verify-only`

Use this when you want to validate the release pipeline without publishing
anything.

### `testpypi`

Use this for rehearsals and installer validation against a real package index.

Expected setup:

- GitHub environment named `testpypi`
- trusted publishing configured on TestPyPI

### `pypi`

Use this only after a successful TestPyPI rehearsal.

Expected setup:

- GitHub environment named `pypi`
- trusted publishing configured on PyPI
- environment protections or reviewers for the production release path

## Required Repository Setup

Before the publish jobs can work, configure trusted publishing on both package
indexes for:

- owner: `cschrupp`
- repository: `wellplot`
- workflow: `release.yml`

Also create these GitHub environments:

- `testpypi`
- `pypi`

## Local Preflight

Run the local checks first:

```bash
uv run ruff check .
uv run pytest
uv build
uv venv /tmp/wellplot-release-check
uv pip install --python /tmp/wellplot-release-check/bin/python dist/*.whl
/tmp/wellplot-release-check/bin/wellplot --help
MPLBACKEND=Agg /tmp/wellplot-release-check/bin/python scripts/smoke_installed_wheel.py
```

## Recommended Release Sequence

1. confirm the package version in `src/wellplot/_version.py`
2. update the repository `CHANGELOG.md` entry for the release
3. run the local preflight checks
4. trigger the GitHub Actions workflow with `publish_target=testpypi`
5. install from TestPyPI in a fresh environment and smoke test the package
6. only after that, trigger the workflow again with `publish_target=pypi`

Example TestPyPI install:

```bash
python -m venv /tmp/wellplot-testpypi
/tmp/wellplot-testpypi/bin/pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  wellplot
```

## Current Status

The repository currently has:

- CI coverage for build and installed-wheel smoke testing
- a manual release workflow
- a TestPyPI-first publication path
- a successful TestPyPI rehearsal for `wellplot 0.1.0`

What remains is the first production PyPI release and later maintenance of the
release workflow as the library surface evolves.
