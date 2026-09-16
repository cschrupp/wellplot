# CM-53 Development Memory

## Scope

CM-53 makes Code Mode v2 the default for the ambiguous host authoring entry
points while preserving the v1 implementation as an explicit compatibility
route. The selector is host-owned and lazy; it does not change the agentic MCP
route, deterministic MCP, CLI rendering/validation, providers, graph nodes,
persistence, or legacy implementation behavior.

- **Slice base SHA:** `9d94642`
- **Implementation commit:** `cea9f7a` (`Make v2 the default authoring engine`)
- **Production delta:** `+160 / -12` across `routing.py`, `core.py`, and
  `notebook.py`
- **Test delta:** `+163 / -1` across the routing and compatibility tests
- **Runtime behavior delta:** the default `create_project_session()`,
  `run_authoring_request()`, and `revise_authoring_request()` paths select v2;
  `engine="v1"` selects the unchanged legacy MCP/provider tool loop.

## Routing Contract

```text
engine omitted       -> v2
engine="v2"          -> direct Code Mode session
engine="v1"          -> AuthoringSession.from_local_mcp()
all other values     -> ValueError
```

The selector accepts no aliases, environment override, provider-driven choice,
or automatic fallback. A v2 failure remains a v2 failure. `max_rounds` remains
accepted for compatibility; v2 receives it once but does not translate it into
additional generation, repair, graph, or visual-correction attempts.

The shared notebook protocol covers run, revise, rendering, and deterministic
heading helpers. `ProjectSession` does not know which engine implements those
methods. Results receive `report_facts["engine"]` through an immutable
dataclass projection, and a mismatched implementation-reported engine is
rejected rather than overwritten.

`server_root=None` for the v2 helper path resolves to the current working
directory, matching the legacy `LocalStdioMcpRuntime` default. Provider names
remain orthogonal to engine selection; the core helpers continue to accept
`openai` and `openai_compat`, while notebook-only `ollama` normalization stays
in the notebook boundary.

## Validation

- CM-53 routing/notebook/agent focused selection: `92 passed, 2 deselected`.
- Agentic MCP and architecture regression selection: `26 passed`.
- Ruff check over changed production and test files: passed.
- Ruff format check over `routing.py`, `notebook.py`, and the new routing test:
  passed.
- `git diff --check`: passed.
- The two excluded tests are the known baseline `_server_command()` and
  `_server_env()` signature failures documented before CM-53; the full selected
  run reports them unchanged when included.

The deterministic evidence exercises strict selector values, default-v2
construction, explicit-v1 construction, v1 result tagging, v2 failure without
legacy fallback, and preservation of the compatibility round-budget argument.

## Boundaries And Deferrals

CM-53 does not add an engine parameter to `AuthoringSession`, `AgentSession`,
`DirectNotebookSession`, `AgenticMcpClient`, or either MCP server. It does not
add an environment-based engine switch, runtime deprecation warning, dual
execution, provider fallback, public schema changes, legacy deletion, or the
CM-60 reachability/import gate.

The required CM-43R2 live acceptance must still be recorded through the
default public route before CM-53 can be marked transition-closed. The live
case and provider/settings fingerprint remain unchanged; deterministic tests
alone do not close that gate.

## Decision

```text
CM-53 routing implementation       complete (`cea9f7a`)
v2 default host selection           complete
explicit v1 transition path        complete
automatic fallback                 0
dual execution                     0
provider/graph/MCP changes         0
legacy deletion                    0
default-route live acceptance      pending
CM-60+                             blocked
```

**PROCEED / STOP:** The implementation is committed and ready to push. Stop
before the final CM-53 transition decision until the unchanged CM-43R2 live
acceptance is rerun through the default public entry point.
