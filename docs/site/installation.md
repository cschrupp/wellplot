# Installation

This page currently describes installation from the repository and development environment.

It is not yet a final published-package installation guide.

## Base install

Use `uv` to create or update the environment:

```bash
uv sync
```

## Common extras

LAS support:

```bash
uv sync --extra las
```

DLIS support:

```bash
uv sync --extra dlis
```

Pandas dataset adapters:

```bash
uv sync --extra pandas
```

Interactive backend:

```bash
uv sync --extra interactive
```

All extras:

```bash
uv sync --all-extras
```

## Development environment

Project lint and tests:

```bash
uv sync
uv run ruff check .
uv run python -m unittest discover -s tests -v
```

## Documentation toolchain

To build the user documentation locally:

```bash
uv sync --group docs
uv run mkdocs build --strict
```

## Wheel smoke test

To verify the built package installs and runs outside the editable development environment:

```bash
uv build
python -m venv .smoke-venv
./.smoke-venv/bin/pip install --upgrade pip
./.smoke-venv/bin/pip install dist/*.whl
./.smoke-venv/bin/wellplot --help
MPLBACKEND=Agg ./.smoke-venv/bin/python scripts/smoke_installed_wheel.py
```

## Python version

The project currently targets Python `>=3.11`.
