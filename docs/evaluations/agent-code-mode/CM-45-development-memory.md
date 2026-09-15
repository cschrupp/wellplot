# CM-45 Development Memory

## Scope

CM-45 adds the isolated Code Mode v2 compile graph after the CM-44 report
worker. It coordinates the existing semantic planner, deterministic enrichment,
report worker, and section worker without changing public routing or the legacy
graph.

- **Slice base SHA:** `5ed4234`
- **Implementation commit:** `23fdba4` (`Build isolated Code Mode v2 compile graph`)
- **Production LOC delta:** `+494/-2` in the implementation commit
- **Runtime behavior delta:** compile-only; no public route, persistence,
  rendering, apply, MCP, provider-adapter, or legacy-graph behavior changed.

## Graph Contract

```text
request + canonical document + source candidates
    -> SemanticPlanner
    -> SemanticEnricher
    -> dynamic Send fan-out
    -> ReportProgramCompiler / ProgramSectionCompiler
    -> compact WorkerOutcome reducer
    -> deterministic plan-order validation and sort
    -> all-success gate
    -> local v2 intent merge
    -> AuthoringDocumentIntent
```

`CodeModeGraphDependencies` keeps the planner, enricher, report compiler, and
section compiler outside graph state. The graph state contains only JSON-safe
request, document, source-candidate, settings, plan, enriched-context,
diagnostic, outcome, and merged-intent values. A worker receives only its own
task and task-local context; it cannot see sibling sections or the full
enriched context.

Report-only plans are valid with `report_task` and an empty `section_tasks`
tuple. An empty plan is rejected, and the planner prompt explicitly forbids a
dummy section task for report-only work.

## Worker Outcomes And Merge

Each dispatched unit must produce exactly one frozen `WorkerOutcome` containing
only its kind, plan order, success flag, optional intent fragment, diagnostics,
and metrics. Generated program source and complete execution-result objects are
not placed in graph state. Provider failures are converted at the worker
boundary to safe provider diagnostics; arbitrary programming errors continue to
propagate.

The merge node rejects missing, duplicate, or unexpected outcomes. Failed
workers leave the initialized empty merged-intent sentinel and prevent any
merged output. Successful fragments are sorted by plan order, checked again for
report/section boundary violations, and rejected when section identities
duplicate. The merge is local and uses `AuthoringDocumentIntent`; it does not
import or call the legacy graph compiler.

## LangGraph Compatibility Boundary

The repository's optional LangGraph dependency currently supports this dynamic
fan-out reliably through its synchronous `invoke` path. The graph nodes bridge
their existing async planner/enricher/worker APIs with bounded synchronous
wrappers; the graph itself does not introduce another provider or retry loop.
The installed runtime also requires reducer channels to be initialized at graph
invocation, so callers must provide empty `worker_outcomes`, `diagnostics`, and
`merged_intent` values. Dynamic worker payloads are unannotated at the graph
node boundary to keep task-local `Send` fields isolated from shared channels.

Outcome and diagnostic reducer entries are canonical JSON strings because the
current runtime does not reliably reduce dynamic dictionary elements. They are
validated back into frozen models at the merge boundary. These are runtime
compatibility constraints for this isolated graph, not provider-specific
workarounds. Async public invocation and route integration are deferred to the
later graph-integration slices.

## Validation

- CM-45-focused planner/workflow tests: `14 passed`.
- Adjacent Code Mode/provider/authoring regression selection: `186 passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.
- Legacy `src/wellplot/agent/graph/workflow.py`: unchanged.

The tests cover report-only, section-only, report-plus-multiple-section
planning, reversed asynchronous worker completion, atomic failure, duplicate
section identities, strict outcome fields, and absence of generated source from
graph evidence.

## Boundaries And Deferrals

CM-45 does not add public routing, notebook/API cutover, MCP integration,
persistence, rendering, apply execution, revision workers, legacy graph
changes, or legacy deletion. It does not decide async public graph invocation;
the current sync-invoke compatibility boundary is recorded for the next
integration slice.

**PROCEED / STOP:** CM-45 is implemented and evidenced in separate commits.
Stop before CM-46 implementation until its graph-integration and parity scope
is separately authorized.
