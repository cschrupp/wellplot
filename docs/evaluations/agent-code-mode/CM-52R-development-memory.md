# CM-52R Development Memory

## Scope

CM-52R hardens the direct notebook cutover without changing its architecture.
It validates the session timeout before provider construction and completes the
authorized notebook evidence gate. The direct v2 route, explicit MCP-backed
client, v1 default engine, provider contracts, graph, and persistence authority
remain unchanged.

- **Slice base SHA:** `cfcc98b`
- **Implementation commit:** `07534a1` (`Harden CM-52 notebook cutover`)
- **Production LOC delta:** `+4 / -1`
- **Test LOC delta:** `+302 / -4`
- **Runtime behavior delta:** explicit timeout values are validated by the
  strict `AgentSessionConfig` before any async provider client is constructed;
  omitted timeout continues to use the session default of `120.0`.

## Corrections

`DirectNotebookSession` no longer uses truthiness to select the session timeout.
An explicit `0`, `False`, non-finite number, or non-numeric value is rejected
before `_provider_backend()` runs. An omitted timeout uses `120.0` for the
session while leaving transport construction's omitted-timeout behavior
unchanged.

The focused evidence now covers both seed modes, declared-source-only opaque
`source-N` candidates, absence of neighboring-file discovery, relative source
association persistence, unchanged deterministic seeds after failed builds,
direct rendering and heading helpers, display of an actual v2-projected
`AuthoringResult`, and a real deterministic
`AgentSession -> CodeModeCompileFacade -> v2 graph` notebook path.

## Validation

- CM-52R focused suite: `15 passed`.
- Exact legacy failure tests on baseline `16d3896`: `2 failed` with missing
  `server_module` and `extra_environment` arguments.
- Exact legacy failure tests on current branch: `2 failed` with the identical
  two `TypeError` signatures; no CM-52R production file is involved.
- CM-51 MCP/agentic regression selection: `211 passed, 2 skipped, 11 subtests passed`.
- Ruff check over CM-52R production and focused test files: passed.
- Ruff format check over CM-52R production and focused test files: passed.
- `git diff --check`: passed.

The focused service tests emit one existing matplotlib warning about
`AutoMinorLocator` on logarithmic scales; it does not fail the suite.

## Boundaries

CM-52R does not change `ProjectSession` signatures, source resolution policy,
MCP composition, `AgenticMcpClient`, provider-v2 adapters, Code Mode graph
topology, repair limits, rendering service behavior, default routing, or legacy
deletion. No unrelated worktree files were staged.

## Decision

```text
CM-52 notebook cutover   complete
CM-52R hardening         complete
CM-53 default v2 engine  blocked pending separate authorization
```

**PROCEED / STOP:** CM-52R is implemented, committed, and ready to push. Stop
before CM-53 planning or default-engine changes.
