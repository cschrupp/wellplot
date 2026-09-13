# CM-00 Development Memory

## Scope

CM-00 established the documentation and evidence boundary for the Code Mode
migration. It did not change production code, dependencies, provider settings,
prompts, MCP contracts, or runtime routing.

The frozen v1 reference is `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c` on
`mcp-stabilization`. The authoritative migration contract is
[`wellplot_agentic_code_mode_migration_plan.md`](../../wellplot_agentic_code_mode_migration_plan.md).

## Decisions

- The existing LangGraph graph-authoring implementation remains the operational
  v1 reference until a later approved migration slice routes production work to
  Code Mode v2.
- `docs/agent-code-mode-architecture.md` is the architectural boundary for v2:
  Program IR and its validator remain provider-independent, the executor does
  not depend on MCP or provider code, and Code Mode cannot import v1 runtime
  orchestration.
- `docs/evaluations/agent-code-mode/` distinguishes structural, deterministic,
  live reproducible, historical observational, and unavailable evidence. A
  provider anecdote is not a release baseline.
- Every future Code Mode slice must create and commit its own development
  memory before push. The memory captures the handoff; the JSON scorecard
  remains the machine-readable record.

## Evidence

- Captured structural inventory: 37 agent Python modules, 22 graph modules,
  20,602 agent lines, 4,338 graph lines, 17 stable MCP tools, 10 built-in
  capabilities, and two agentic MCP entry points. The complete inventory is in
  `CM-00-baseline.json`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q --maxfail=1` completed
  with `1 failed, 66 passed in 6.33s`. The known pre-existing failure is
  `AgentTests.test_server_command_prefers_sibling_entry_point`, caused by
  `_server_command()` requiring `server_module`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check src tests`
  reports 17 pre-existing files requiring formatting. CM-00 deliberately did
  not reformat unrelated runtime or test code.
- No live provider run was claimed as reproducible evidence. The frozen CBL
  compile-only replay and Code Mode architecture guard have not run because
  they belong to later slices.

## Deferred Work

CM-01 may add only the Code Mode AST import-invariant guard described by the
migration plan. It must not add the v2 runtime package, a feature flag,
provider integration, a program interpreter, or a new capability. The known
v1 test and formatting baseline conditions are not CM-01 cleanup work.
