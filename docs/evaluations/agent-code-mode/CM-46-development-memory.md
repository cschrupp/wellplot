# CM-46 Development Memory

## Scope

CM-46 integrates the existing Code Mode v2 graph behind an internal async host
facade. It resolves the CM-45 event-loop boundary and adds deterministic
result/parity evidence without adding a public route or changing the legacy
graph.

- **Slice base SHA:** `c91afad`
- **Implementation commit:** `dba0635` (`Add async Code Mode compile facade`)
- **Production LOC delta:** `+313/-14` in the implementation commit
- **Runtime behavior delta:** internal v2 async compilation is now invocable;
  public routing, persistence, rendering, apply, MCP, and legacy behavior are
  unchanged.

## Native Async Boundary

```text
CodeModeCompileFacade.compile(...)
    -> graph.ainvoke(...)
    -> async plan node
    -> async enrichment and Send dispatch
    -> async report/section workers
    -> async deterministic merge
    -> CodeModeCompileResult
```

The facade owns graph construction and initializes the internal reducer
channels (`worker_outcomes`, `diagnostics`, and `merged_intent`). Callers do not
invoke `build_compile_graph()` or know about LangGraph state encoding. The
workflow contains no `asyncio.run()` bridge. The focused test invokes the
facade from inside an already-running event loop and exercises real async
dynamic fan-out.

## Stable Host Result

`CodeModeCompileResult` is a frozen, strict Pydantic contract containing only:

- `success`;
- an optional canonically validated `AuthoringDocumentIntent`;
- ordered generic `CompileDiagnostic` values;
- ordered `CompileWorkerEvidence` values; and
- measured `CompileMetrics` aggregates.

The outward result does not expose the semantic plan, enriched context, source
candidates or paths, LangGraph state, reducer JSON strings, generated program
source, or worker intent fragments. Worker evidence carries kind, plan order,
success, diagnostics, and program metrics. Aggregate nesting depth is the
maximum worker depth; the other program metrics are summed. Provider-wide token
and latency totals are intentionally not invented because the graph does not
retain complete planner/provider accounting.

Success is valid only when graph invocation completed, every expected worker
succeeded, and the merged intent exists and validates canonically. A normal
worker failure returns no merged intent but retains complete ordered worker
evidence. Planner provider failures, enrichment failures, and worker outcome
diagnostics are normalized to safe host diagnostics. Unexpected graph invariant
errors still raise and are not disguised as normal compilation failures.

## Deterministic Parity Evidence

The focused fixtures cover exact canonical intent equality for:

```text
report only
single section
report plus two sections
```

The parity test instantiates the unchanged legacy compile graph with
deterministic legacy fakes and compares its canonical report-plus-sections
result with the v2 facade's deterministic fakes. The report-only fixture is a
deliberate v2-only planner shape because the legacy `ReconstructionPlan`
requires at least one section. No fuzzy similarity or weakened acceptance is
used.

## Validation

- CM-46-focused facade/workflow tests: `17 passed`.
- Adjacent Code Mode/provider/authoring regression selection: `197 passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.
- Legacy `src/wellplot/agent/graph/workflow.py`: unchanged.

The tests also cover report-only and section-only graph shapes, reversed worker
completion, aggregate metrics, absence of source/program leakage, worker and
provider failures, planner and enrichment failures, and propagation of an
unexpected graph invariant.

## Boundaries And Deferrals

CM-46 does not add a production engine switch, public Python/notebook/MCP
route, persistence, rendering, apply execution, revision worker, legacy graph
change, or legacy deletion. It does not claim report revision parity or public
cutover readiness.

**PROCEED / STOP:** CM-46 is implemented and evidenced in separate commits.
Stop before CM-47 implementation until graph parity and cutover preparation are
separately authorized.
