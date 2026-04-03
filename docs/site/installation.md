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

## Python version

The project currently targets Python `>=3.11`.
