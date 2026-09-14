# CM-40 Development Memory

## Scope

CM-40 adds a static semantic planner for the Code Mode v2 path without changing
the v1 graph planner or any runtime routing.

- **Slice base SHA:** `b9e8640`
- **Implementation commit:** `a9f4a21`
- **Implementation scope:** frozen `ReportTask`, `SectionTask`, and
  `SemanticPlan` contracts; one-call structured planning; host-side capability
  validation; focused contract tests.

## Contract

```text
semantic request + compact document summary + static capability catalogue
    -> SemanticPlanner
    -> ModelBackendProtocol.generate_structured(SemanticPlan)
    -> validated semantic work units
```

The static schema contains no `component_id`, `target_id`,
`parent_component_id`, `binding_id`, `section_id`, `source_path`,
`source_format`, `slot_id`, `data_source`, or `components` fields. An
`existing_section_hint` is advisory natural-language context only. Section-task
list order does not define document order or execution order.

The host validates canonical capability IDs and report/section category usage
against the static `CapabilityRegistry`. It does not construct runtime
`Literal` fields, resolve parent relationships, discover sources, normalize
paths, or mutate a document. Provider failures and invalid capability choices
remain observable; there is no planner retry, repair, fallback, or second
planner.

The existing `ReconstructionPlan` and `ReconstructionPlanner` remain the v1
path and were not modified.

## Validation

- CM-40-focused tests: `30 passed`.
- Adjacent Code Mode/provider/capability regression selection: `105 passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.

## Boundaries and Risks

- No live provider request was made; tests use a fake provider-v2 backend.
- No source/target enrichment, source discovery, channel inspection, header
  slot resolution, worker integration, program generation, LangGraph routing,
  MCP, persistence, mutation, or legacy deletion is part of CM-40.
- The v2 planner currently lives beside the v1 planner so existing graph
  behavior remains unchanged until a later explicitly authorized cutover.

## Decision

**PROCEED / STOP:** CM-40 is implemented and evidenced in separate commits.
Stop before CM-41 deterministic source/target enrichment until separately
authorized.
