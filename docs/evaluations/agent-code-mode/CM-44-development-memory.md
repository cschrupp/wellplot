# CM-44 Development Memory

## Scope

CM-44 adds the bounded report Code Mode worker after the frozen CM-43R2 gate
returned `PROCEED`. It does not change public routing, graph orchestration,
MCP, persistence, rendering, provider adapters, or legacy code.

- **Slice base SHA:** `f938b8b`
- **Implementation commit:** `9de218f` (`Add bounded report Code Mode worker`)
- **Runtime behavior delta:** the new worker is not registered in a public
  route; existing v1 and v2 section behavior is unchanged.

## Report Worker Contract

```text
ReportTask + bounded ReportContext + AuthoringDocumentSpec
    -> ReportProgramCompiler
    -> one generate_program()
    -> restricted program interpreter
    -> report-only AuthoringDocumentIntent
    -> private ProgramRuntime dry run
    -> ProgramExecutionResult
```

The worker exposes only primitive-valued report calls through the existing
`IntentBuilder` runtime:

```text
wp.report(title, subtitle)
wp.header_field(report, key, value, unit, label)
wp.service_title(report, slot_id, value, unit, presentation options)
wp.detail_field(report, key, value, unit, label)
wp.remark(report, remark_id, title, text, presentation options)
wp.page(report, size, dimensions, orientation, continuous)
wp.depth(report, unit, scale)
wp.output(report, backend, output_path, dpi)
wp.tail(report, enabled)
```

The worker context includes only the semantic `ReportTask`, selected report
capability descriptors, and immutable header-slot identities (`slot_id`, key,
and label). It excludes current values, layout internals, section data,
source paths, filesystem state, and full document serialization. Programs do
not construct Pydantic objects directly.

## Report-Only Gate

The post-interpretation gate accepts only report-wide title/subtitle, header,
page, depth, output, tail, and remarks fields. It rejects:

- sections and all global curve/raster/fill/annotation collections;
- every removal, including report-scoped removals; and
- an empty `wp.report()` program or any other empty report patch.

The shared interpreter still owns the complete SDK registry for compatibility
with the section worker, so this explicit report-only gate remains mandatory.
The report worker creates a fresh builder for every initial or repaired
candidate and uses `ProgramRuntime` against a private document copy.

## Repair and Provider Boundary

Initial provider failures propagate without fabricated program evidence. A
candidate that reaches the interpreter or private dry run receives the same
bounded `ProgramRepairCoordinator` used by CM-42/CM-43R2. The worker does not
add a retry loop, semantic validator, provider branch, or repair policy of its
own.

## Validation

- CM-44-focused tests: `23 passed`.
- Code Mode/provider/authoring regression selection: `178 passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.

No live provider request was made. The tests use deterministic fake backends;
live A/B evidence remains the CM-43/CM-43R2 evidence and is unchanged.

## Boundaries and Deferrals

CM-44 does not implement report revision selection/update semantics, report
worker registration, LangGraph routing, MCP integration, persistence,
rendering, public notebook/API cutover, legacy deletion, or graph parity.
CM-45 owns the next separately authorized integration slice.

**PROCEED / STOP:** CM-44 is implemented and evidenced in separate commits.
Stop before CM-45 implementation until separately authorized.
