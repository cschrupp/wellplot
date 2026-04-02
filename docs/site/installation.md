# Installation

## Base install

```bash
uv sync
```

## Common optional extras

LAS / Welly:

```bash
uv sync --extra las
```

DLIS:

```bash
uv sync --extra dlis
```

Pandas adapters:

```bash
uv sync --extra pandas
```

All extras:

```bash
uv sync --all-extras
```

## Documentation toolchain

To build the user documentation locally:

```bash
uv sync --group docs
```
