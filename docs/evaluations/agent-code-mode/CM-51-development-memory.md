# CM-51 Development Memory

## Scope

CM-51 migrates the opt-in agentic MCP edge from the legacy graph/compiler path
to the proven direct Code Mode v2 Python service. The stable deterministic MCP
surface, notebook path, default engine, and legacy implementation remain
unchanged.

- **Slice base SHA:** `fd85a22`
- **Implementation commits:** `e6643d0` (`Migrate agentic MCP edge to Code Mode v2`)
  and `aa6864b` (`Harden CM-51 MCP evidence tests`)
- **Production LOC delta:** `+229`
- **Test LOC delta:** `+372`
- **Runtime behavior delta:** opt-in agentic MCP now constructs and invokes the
  v2 planner/enricher/workers through `AgentSession`; successful results are
  privately reconciled, executed, validated, and persisted. Stable MCP and
  default routing are unchanged.

## MCP Boundary

`GraphAuthoringMcpOperations` now owns only:

```text
AgentSession
server root
```

The two tool names and their arguments remain unchanged:

```text
build_plot_from_request(logfile_path, request)
revise_plot_from_request(logfile_path, request)
```

`GraphAuthoringToolResult` retains its exact field set. v2 does not expose a
semantic plan, generated program, provider response, LangGraph state, or source
paths through that result; `plan_summary` remains present for wire compatibility
and is `None` on this path.

## Host-Owned Composition

The explicit agentic server now constructs:

```text
provider-v2 backend
    -> SemanticPlanner
    -> SemanticEnricher + neutral logfile source loader
    -> ReportProgramCompiler / ProgramSectionCompiler
    -> CodeModeCompileFacade
    -> AgentSession
    -> GraphAuthoringMcpOperations
```

OpenAI uses `AsyncOpenAI` with `OpenAIBackendV2`. OpenAI-compatible providers
use `AsyncOpenAI` with explicit JSON Schema support through
`OpenAICompatibleBackendV2`. Credential lookup preserves explicit values,
environment variables, ignored local key files, and the loopback placeholder
behavior without importing the legacy provider adapters.

The MCP edge resolves only logfile-declared sources. Equivalent declarations
are deduplicated by canonical `(path, format)` and receive opaque candidate IDs
such as `source-1`; canonical section IDs are never used as source identity.
`LogfileSourceLoader` projects only bounded dataset metadata and channel facts
into `LoadedSource`. It does not discover files or retain samples in worker
context.

## Apply Transaction

The MCP edge does not mutate the caller document or apply directly to the
session result. The transaction is:

```text
load canonical logfile
    -> AgentSession.build()/revise()
    -> failed result: no apply or persistence
    -> fresh private AuthoringService clone
    -> reconcile_authoring()
    -> blocked: discard, no persistence
    -> execute_authoring_plan()
    -> execution failure: discard private clone, rolled_back=True
    -> validate private document
    -> persist accepted canonical document only when changed
```

Successful no-op results report `success=true, changed=false`.
Successful mutations report `success=true, changed=true`.
Compile and reconciliation failures report `rolled_back=false`; execution or
post-execution validation failures report `rolled_back=true`.

## Trace And Isolation

The existing `AgentRunTrace` remains the diagnostic location. CM-51 adds only
bounded events for compile evidence, apply status, changed/rollback state, and
safe error codes. Traces do not retain prompts, generated programs, provider
objects, full plans, LangGraph state, or canonical source paths.

Static architecture guards prohibit `wellplot.mcp.agentic` from importing the
legacy graph/core/execution path and prohibit `agentic_server` from composing
legacy graph or provider adapters. No `AgentSession` behavior was changed.

## Validation

- CM-51 focused MCP/architecture tests: `24 passed`.
- Code Mode and architecture regression selection: `88 passed`.
- Stable MCP, MCP service/runtime/wire, agentic, notebook, and architecture
  regression selection: `209 passed, 2 skipped, 11 subtests passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.

Coverage includes unchanged tool arguments and result fields, build/revise
dispatch, declared-source-only candidate projection, opaque IDs, neutral source
loading, real session/facade/graph integration with a fake provider, private
execution rollback, persistence gating, caller immutability, bounded trace
evidence, async provider composition, and legacy dependency guards.

## Boundaries And Deferrals

CM-51 does not migrate notebooks, change `AgentSession`, expose visual
correction, change stable MCP tools, change rendering, switch the default
engine, add retries/fallbacks, or delete legacy code. The v2 MCP route is
explicitly opt-in and provider configuration remains host-owned.

**PROCEED / STOP:** CM-51 is implemented, committed, pushed, and closed.
Proceed to CM-52 planning only. Do not change notebook routing or default-engine
selection in this slice.
