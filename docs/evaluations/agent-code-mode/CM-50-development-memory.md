# CM-50 Development Memory

## Scope

CM-50 adds the direct async Python boundary for the already-proven Code Mode
v2 compile facade. `AgentSession` accepts an injected compiler and host-owned
canonical inputs, maps `build()` to reconstruction and `revise()` to revision,
and returns a stable public projection without applying or retaining the result.

- **Slice base SHA:** `3475434`
- **Implementation commits:** `dd2bb6e` (`Add direct Code Mode Python session`)
  and `7496553` (`Harden CM-50 session validation`)
- **Production LOC delta:** `+448`
- **Test LOC delta:** `+303`
- **Runtime behavior delta:** direct v2 Python compilation is available;
  MCP, notebook routing, persistence, rendering, defaults, and legacy behavior
  are unchanged.

## Public Boundary

The public import surface is additive:

```python
from wellplot.agent import (
    AgentSession,
    AgentSessionConfig,
    AgentSessionResult,
    AgentSourceConfig,
)
```

`AgentSession` receives an already constructed v2 compiler. It does not know
how providers, planners, workers, source loaders, or allowed roots are built.
`AgentSessionConfig` contains only provider-neutral execution limits, and
`AgentSourceConfig` converts explicitly supplied host references into the
internal enrichment contract without resolving paths, opening files, or
discovering candidates.

CM-50R aligns those execution limits with the provider request contract:
timeouts and temperatures must be finite numeric values, and
`max_output_tokens` must be a real positive integer. Build and revise both
retain the direct-Python MCP tripwire.

The public flow is:

```text
host document and source references
    -> AgentSession.build()/revise()
    -> injected CodeModeCompileFacade
    -> AgentSessionResult
```

Successful results expose the canonical intent returned by the compiler.
Failed results never expose an intent. The session does not mutate the input
document, persist output, render output, or retain mutable canonical state.

## Result Projection

The public result projects only mode, success, canonical intent, safe
diagnostics, ordered worker evidence, and aggregate metrics. Aggregate and
per-worker metric models remain distinct. `inspection()` returns JSON-safe
bounded evidence with `intent_present`; it excludes prompts, generated
programs, repair material, LangGraph state, source paths, and provider objects.

Facade failures remain bounded unsuccessful results. Unexpected programming
and graph invariant exceptions are not caught or converted into fabricated
diagnostics.

## Direct Python Isolation

`session.py` has no imports from the MCP, notebook, or legacy orchestration
modules. The focused runtime test fails if `LocalStdioMcpRuntime.open_session`
is touched by either public method. Existing legacy exports remain present,
and no `AgentSession` export is added to top-level `wellplot`.

## Validation

- CM-50/CM-50R focused session and architecture tests: `25 passed`.
- Full Code Mode and architecture regression selection: `86 passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.

Coverage includes build/revise mode mapping, host-injected compiler calls,
source conversion, safe result projection, failure-without-intent invariants,
input immutability, no session-owned document state, bounded inspection,
finite and strict configuration validation, public imports, and symmetric MCP
isolation.

## Boundaries And Deferrals

CM-50 does not add provider factories or credentials, filesystem discovery,
source loading, document application, persistence, rendering, visual-QA
exposure, notebook migration, MCP migration, default-engine switching, or
legacy deletion. Existing `wellplot.agent` legacy exports remain unchanged
apart from additive CM-50 names.

**PROCEED / STOP:** CM-50R is implemented and evidenced. CM-50 is closed.
Stop before CM-51
MCP cutover, CM-52 notebook migration, or CM-53 default-engine selection until
each is separately authorized.
