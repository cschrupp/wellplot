# Installation

`wellplot` is published on PyPI. Most users should install the package into a
normal Python environment with `pip`.

## Base Install

```bash
python -m pip install wellplot
```

This installs the core renderer, YAML support, NumPy, Matplotlib, and schema
validation dependencies.

## Optional Extras

Install only the adapters and runtime features you need:

```bash
python -m pip install "wellplot[las]"
python -m pip install "wellplot[dlis]"
python -m pip install "wellplot[pandas]"
python -m pip install "wellplot[interactive]"
python -m pip install "wellplot[notebook]"
python -m pip install "wellplot[units]"
```

Common combinations:

```bash
python -m pip install "wellplot[las,notebook]"
python -m pip install "wellplot[dlis,notebook]"
python -m pip install "wellplot[las,dlis,pandas,notebook,interactive,units]"
```

If you want every optional dependency exposed by the package metadata:

```bash
python -m pip install "wellplot[all]"
```

## Verify The Install

```bash
wellplot --help
python - <<'PY'
import wellplot
print(wellplot.__version__)
PY
```

## Running Repository Examples

The package can be installed from PyPI, but the bundled example files and public
sample data live in the repository. To run the production examples exactly as
documented, clone the repository and run commands from the repository root.

```bash
git clone https://github.com/cschrupp/wellplot.git
cd wellplot
python -m pip install "wellplot[las,dlis,notebook]"
wellplot validate examples/production/forge16b_porosity_example/full_reconstruction.log.yaml
```

## Contributor Environment

Contributors use `uv` for reproducible dependency resolution and local checks.
This is not required for normal installed-package usage.

```bash
uv sync
uv run ruff check .
uv run python -m unittest discover -s tests -v
```

Build the local documentation:

```bash
uv sync --group docs
uv run mkdocs build --strict
```

Build and smoke-test a local wheel:

```bash
uv build
python -m venv .smoke-venv
./.smoke-venv/bin/pip install --upgrade pip
./.smoke-venv/bin/pip install dist/*.whl
./.smoke-venv/bin/wellplot --help
MPLBACKEND=Agg ./.smoke-venv/bin/python scripts/smoke_installed_wheel.py
```

## Python Version

`wellplot` targets Python `>=3.11`.
