# CM-52 Development Memory

## Scope

CM-52 moves the notebook-facing `ProjectSession` path from the local stdio MCP
authoring loop to the proven direct Code Mode v2 session. The explicit
`AgenticMcpClient` path remains MCP-backed, and the default engine remains v1.

- **Slice base SHA:** `16d3896`
- **Implementation commit:** `3ad6a80` (`Route notebook sessions through Code Mode v2`)
- **Production LOC delta:** `+564 / -3`
- **Test LOC delta:** `+295 / -18`
- **Runtime behavior delta:** notebook build/revise now composes the v2
  `AgentSession` directly, applies only a privately reconciled and validated
  intent, then persists accepted state through the existing service layer.

## Implementation

`create_project_session()` now constructs `DirectNotebookSession`, which owns
the v2 planner, deterministic enrichment, report/section workers, async
provider-v2 backend, and `CodeModeCompileFacade` composition. The existing
`ProjectSession` fields and public method signatures remain unchanged, so
notebook callers continue to receive `AuthoringResult`.

The adapter preserves the notebook envelope without fabricating v1 evidence:
`tool_trace`, `plan`, and phase summaries are empty; `submitted_intent` is the
canonical v2 intent JSON; and `report_facts` contains only bounded engine,
compilation, apply, success, change, and rollback facts. Prompts, generated
programs, provider objects, source paths, and LangGraph state are not exposed.

The run path seeds exactly one draft with `create_logfile_draft`, loads only
declared source candidates as opaque `source-N` values, compiles through v2,
and applies through a private `AuthoringService` transaction followed by
reconciliation, execution, validation, and accepted persistence. Failed
compilation, reconciliation, execution, or validation cannot persist partial
state. Revision operates on the existing file and preserves it on failure.

Rendering and heading helpers use the deterministic Python service functions
directly. They do not construct an MCP runtime or call MCP tools. The
compatibility `max_rounds` arguments remain API-only; the v2 planner, workers,
and bounded repair coordinator retain their fixed call limits.

## Validation

- Direct notebook and agentic-notebook tests: `8 passed`.
- Combined notebook/agent tests: `80 passed, 2 failed`; the failures are the
  pre-existing legacy `_server_command()` and `_server_env()` test calls in
  `tests/test_agent.py`, outside the CM-52 path.
- CM-51 MCP/agentic regression selection: `211 passed, 2 skipped, 11 subtests passed`.
- Ruff check over changed production and test files: passed.
- Ruff format check over the new direct adapter, notebook module, and new
  focused tests: passed. The legacy `tests/test_agent.py` retains its baseline
  formatting drift and was not reformatted as unrelated churn.
- `git diff --check`: passed.

## Boundaries

CM-52 does not change `AgenticMcpClient`, MCP schemas or routing, provider-v2
contracts, the Code Mode graph, persistence authority, renderer behavior,
source discovery, default engine selection, retries, or legacy deletion. The
direct notebook adapter intentionally duplicates the already-approved v2 host
composition rather than refactoring the CM-51 MCP host in this slice.

The direct route requires the same provider credentials and endpoint settings
as the v2 MCP composition. Relative notebook paths remain rooted under the
configured project/server root. `AuthoringSession` and `LocalStdioMcpRuntime`
remain available for the explicit MCP-backed compatibility path and are not
constructed by `create_project_session()`.

## Decision

```text
CM-51 MCP cutover        complete
CM-52 notebook cutover   complete
CM-53 default v2 engine  blocked pending separate authorization
```

**PROCEED / STOP:** CM-52 is implemented, committed, and ready to push. Stop
before CM-53 planning or default-engine changes.
