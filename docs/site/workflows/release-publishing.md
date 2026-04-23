# Release And Publishing

This page documents the maintainer workflow for building and publishing
`wellplot`.

It is intentionally separate from normal user workflows because it describes
package-release operations, not day-to-day dataset or rendering usage.

## Current Status

`wellplot` is live on PyPI. Normal users should install it with:

```bash
python -m pip install wellplot
```

The release workflow remains useful for maintenance releases, version checks,
artifact validation, and optional TestPyPI rehearsals when the publishing
process changes.

## Scope

The release path is designed to be safe by default:

- build artifacts first
- verify the installed wheel in a clean environment
- publish only when explicitly requested
- keep TestPyPI and PyPI as separate manual targets

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

Use this for optional rehearsals and installer validation against a real package
index without updating the production PyPI project.

Expected setup:

- GitHub environment named `testpypi`
- trusted publishing configured on TestPyPI

### `pypi`

Use this for production releases to the public PyPI project.

Expected setup:

- GitHub environment named `pypi`
- trusted publishing configured on PyPI
- environment protections or reviewers for the production release path

## Repository Setup

Trusted publishing should remain configured on both package indexes for:

- owner: `cschrupp`
- repository: `wellplot`
- workflow: `release.yml`

Required GitHub environments:

- `testpypi`
- `pypi`

## Local Preflight

Run the local checks first:

```bash
uv run ruff check .
uv run python -m unittest discover -s tests -v
uv build
uv venv /tmp/wellplot-release-check
uv pip install --python /tmp/wellplot-release-check/bin/python dist/*.whl
/tmp/wellplot-release-check/bin/wellplot --help
MPLBACKEND=Agg /tmp/wellplot-release-check/bin/python scripts/smoke_installed_wheel.py
```

## Maintenance Release Sequence

1. confirm the package version in `src/wellplot/_version.py`
2. update `CHANGELOG.md` for the release
3. run the local preflight checks
4. trigger the GitHub Actions workflow with `publish_target=verify-only`
5. use `publish_target=testpypi` if you want an index-level rehearsal
6. trigger the workflow with `publish_target=pypi` for the production release
7. verify a fresh PyPI install

Production install verification:

```bash
python -m venv /tmp/wellplot-pypi-check
/tmp/wellplot-pypi-check/bin/pip install wellplot
/tmp/wellplot-pypi-check/bin/wellplot --help
```

Optional TestPyPI install verification:

```bash
python -m venv /tmp/wellplot-testpypi
/tmp/wellplot-testpypi/bin/pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  wellplot
```
