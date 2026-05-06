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
python -m pip install "wellplot[mcp]"
python -m pip install "wellplot[agent]"
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

## Experimental MCP Install

Install the MCP surface only when you need agent-driven logfile workflows:

```bash
python -m pip install "wellplot[mcp]"
```

Verify that the stdio entry point was installed:

```bash
python - <<'PY'
import shutil

path = shutil.which("wellplot-mcp")
print(path)
if path is None:
    raise SystemExit("wellplot-mcp entry point was not installed")
PY
```

Launch behavior:

- `wellplot-mcp` starts a stdio server and stays attached to the client session
- the server root is the current working directory when the process starts
- logfile paths, referenced source data, saved YAML files, export directories,
  and render outputs must all resolve inside that root

Typical client registration:

```json
{
  "mcpServers": {
    "wellplot": {
      "command": "wellplot-mcp",
      "cwd": "/absolute/path/to/job-root"
    }
  }
}
```

## Experimental Agent Install

Install the public host-side authoring API when you want Python code to drive
local `wellplot-mcp` sessions through a supported hosted model provider:

```bash
python -m pip install "wellplot[agent]"
```

Current provider support:

- OpenAI
- OpenAI-compatible endpoints through `provider="openai_compat"` plus
  `base_url=...`

Credential guidance:

- prefer `OPENAI_API_KEY` in the shell for OpenAI sessions
- for notebooks, prompt once with `getpass()` and keep the key only in the
  current kernel
- use `.env.local` in the job or repository root when you want a local
  persistent secret file that stays out of version control
- for loopback-compatible endpoints such as `http://localhost:11434/v1`,
  `wellplot.agent` injects a placeholder token automatically when no key is
  configured

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
uv run pytest tests/test_mcp_service.py tests/test_mcp_server.py tests/test_pipeline.py tests/test_cli.py tests/test_public_api.py
uv run --with mcp pytest tests/test_mcp_server.py
```

Build the local documentation:

```bash
uv sync --group docs
uv run --group docs mkdocs build --strict
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
