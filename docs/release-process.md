# Release Process

This document describes the maintainer release workflow for `wellplot`.

`wellplot` is already published on PyPI. Normal users install it with:

```bash
python -m pip install wellplot
```

The workflow below is for maintainers preparing future releases.

## Workflow File

- `.github/workflows/release.yml`

## Workflow Inputs

The manual workflow accepts:

1. `publish_target`
   - `verify-only`
   - `testpypi`
   - `pypi`
2. `expected_version`
   - optional version guard such as `0.3.0`
   - if provided, the workflow checks it against `src/wellplot/_version.py`

## What The Workflow Does

The `build` job always runs first:

1. checks out the repository
2. sets up Python and `uv`
3. optionally verifies the requested version
4. runs `uv build`
5. creates a clean virtual environment for the base wheel
6. installs the built wheel into that clean environment
7. verifies the `wellplot` console entry point
8. runs `scripts/smoke_installed_wheel.py`
9. creates a second clean virtual environment for MCP verification
10. installs the built wheel plus `mcp>=1,<2`
11. reruns `scripts/smoke_installed_wheel.py` with MCP support enabled
12. uploads the built artifacts for later publish jobs

Publishing jobs only run when selected:

- `publish-testpypi`
  - runs only when `publish_target=testpypi`
  - publishes with GitHub OIDC trusted publishing
  - expects a GitHub environment named `testpypi`
- `publish-pypi`
  - runs only when `publish_target=pypi`
  - publishes with GitHub OIDC trusted publishing
  - expects a GitHub environment named `pypi`

## Repository Setup

Trusted publishing should remain configured on both package indexes.

Current expected claims:

- owner: `cschrupp`
- repository: `wellplot`
- workflow: `release.yml`
- production environment: `pypi`
- rehearsal environment: `testpypi`

Required GitHub environments:

- `testpypi`
- `pypi`

The `pypi` environment should keep production protections or reviewers enabled.

## Local Preflight Before A Release Run

Run the local validation path first:

```bash
uv run ruff check .
uv run pytest tests/test_mcp_service.py tests/test_mcp_server.py tests/test_pipeline.py tests/test_cli.py tests/test_public_api.py
uv run --with mcp pytest tests/test_mcp_server.py
uv run --group docs mkdocs build --strict
uv build
uv venv /tmp/wellplot-release-check
uv pip install --python /tmp/wellplot-release-check/bin/python dist/*.whl
/tmp/wellplot-release-check/bin/wellplot --help
MPLBACKEND=Agg /tmp/wellplot-release-check/bin/python scripts/smoke_installed_wheel.py
uv venv /tmp/wellplot-release-check-mcp
uv pip install --python /tmp/wellplot-release-check-mcp/bin/python dist/*.whl "mcp>=1,<2"
MPLBACKEND=Agg /tmp/wellplot-release-check-mcp/bin/python scripts/smoke_installed_wheel.py
```

## Maintenance Release Sequence

1. Confirm the package version in `src/wellplot/_version.py`.
2. Update `CHANGELOG.md` for the release.
3. Run the local preflight checks.
4. Trigger the `Release` workflow with:
   - `publish_target=verify-only`
   - `expected_version=<current version>`
5. Rehearse on TestPyPI when the workflow, metadata, optional dependencies, or
   MCP verification path changed in a risky way.
6. Trigger the `Release` workflow with:
   - `publish_target=pypi`
   - `expected_version=<current version>`
7. Verify a fresh PyPI install.

Production install verification:

```bash
python -m venv /tmp/wellplot-pypi-check
/tmp/wellplot-pypi-check/bin/pip install wellplot
/tmp/wellplot-pypi-check/bin/wellplot --help
```

Experimental MCP install verification:

```bash
python -m venv /tmp/wellplot-pypi-check-mcp
/tmp/wellplot-pypi-check-mcp/bin/pip install "wellplot[mcp]"
/tmp/wellplot-pypi-check-mcp/bin/python scripts/smoke_installed_wheel.py
```

Optional TestPyPI install verification:

```bash
python -m venv /tmp/wellplot-testpypi
/tmp/wellplot-testpypi/bin/pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  wellplot
```

## Release History Boundary

The first public PyPI release has been completed. Future work is maintenance:

- keep the release workflow passing on supported Python versions
- keep trusted publishing claims aligned with repository and environment names
- update the changelog before each release
- verify the public PyPI install after each release
- keep the optional MCP smoke path working whenever the experimental MCP
  surface changes
