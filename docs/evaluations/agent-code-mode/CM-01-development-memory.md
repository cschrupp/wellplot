# CM-01 Development Memory

## Scope

CM-01 makes the approved Code Mode dependency direction executable through
static AST checks. It creates two inert package markers:

- `wellplot.authoring_program`, the future provider-independent program
  boundary;
- `wellplot.agent.code_mode`, the provisional home of future v2 orchestration.

The latter name is intentionally a boundary decision rather than a topology
decision. It does not add a graph, provider integration, LangGraph code, MCP
code, public export, routing, feature flag, compatibility shim, or registry
construction.

## Rules Established

- `authoring_program` and `capabilities` may not depend on `wellplot.agent`,
  LangGraph, external MCP, or `wellplot.mcp`.
- `agent.code_mode` may not depend on MCP or the identified legacy agent
  compiler and tool-loop modules. It may use LangGraph in a later authorized
  slice because it is the v2 orchestration boundary.
- Authoring and domain roots may not depend on `wellplot.agent`.
- All checks parse production source through `ast`; they cover `import` and
  `from ... import ...`, including resolved relative imports.

## Validation

Validation completed before the CM-01 commit:

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q tests/test_agent_v2_architecture.py`
  passed: `5 passed in 0.23s`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check src/wellplot/authoring_program/__init__.py src/wellplot/agent/code_mode/__init__.py tests/test_agent_v2_architecture.py`
  passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check src/wellplot/authoring_program/__init__.py src/wellplot/agent/code_mode/__init__.py tests/test_agent_v2_architecture.py`
  passed: `3 files already formatted`.
- `git diff --check` passed.

## Runtime And Production Delta

- Runtime behavior delta: zero.
- Public API delta: zero.
- Provider, MCP, LangGraph, routing, and capability delta: zero.
- Production code consists only of two docstring-only marker modules: `+11`
  lines in total (six in `authoring_program`, five in `agent.code_mode`).

## Deferrals

CM-02 owns the reachability graph and the explicit classification of legacy
modules. CM-01 does not decide what is deletable, remove legacy code, add Code
Mode implementation modules, or change any production route.

## Decision

**PROCEED to CM-02 only after this slice is committed and pushed.**
