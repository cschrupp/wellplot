# CM-57P1 Development Memory

## Authority And Boundary

CM-57P1 implements the accepted CM-57C-R3 planner capability contract from
baseline `b34c544a40780eb96d8ca45f220f3ed6ae9be4b8`. The accepted design
checkpoint is `b34c544a40780eb96d8ca45f220f3ed6ae9be4b8` and the historical
CM-57C decision remains `GENERALIZATION_PIPELINE_FAILURE`.

The production implementation is limited to
`src/wellplot/agent/code_mode/planner.py`. Focused planner tests and this
development record are the only other implementation-slice changes. Provider
calls and live inference are `0`; the active route remains
`ProgramSectionCompiler`; the typed worker remains inactive; CM-57P2 is not
started and CM-57D remains blocked.

## Implemented Contract

The existing `CapabilitySpec.allowed_parents` field is now retained by the
Code Mode planner-safe catalog. No registry, built-in declaration, capability
metadata, worker descriptor, argument schema, handler, compiler, or runtime
field was added to the planner payload.

The planner prompt now states generically that:

- each work unit selects the complete set of required capability types;
- capability IDs identify types rather than requested object instances;
- each capability ID appears at most once;
- selected capabilities with allowed parents require an appropriate selected
  parent through the structural hierarchy; and
- unrequested capabilities must not be added.

`validate_semantic_plan()` now performs generic deterministic checks after
canonical identifier resolution:

```text
duplicate_capability
missing_capability_parent
```

Duplicate IDs are not deduplicated. Parent IDs are not injected. Multiple
allowed-parent choices remain model-owned. Immediate-parent checking is
bounded and transitively effective because each selected parent is validated in
the same task.

Existing unknown, noncanonical, category, missing-section, report-task, and
unresolved-requirement behavior remains unchanged. The SectionTask,
ReportTask, and SemanticPlan schemas are unchanged, as is the one-correction
planner budget.

## Provenance

The accepted implementation checkpoint records these deterministic anchors:

```text
planner prompt SHA:       5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18
planner source SHA:       0189b290ef4f76bdd776fe2612c454809ff77725379def7d8c5a98d9ae165413
catalog projection SHA:   b1b9c85db961cb8b97f1c8b6f914a6a75f5bf57cf49ca4413c64d35311b80d37
```

The canonical planner catalog projection is restricted to:

```text
id
category
description
allowed_parents
planning_hints
schema_version
```

The planner catalog contains no worker semantic metadata or benchmark data.

## Tests And Evidence Boundary

Focused planner tests: `50 passed`.

Focused planner, capability-registry, plugin-extensibility, and workflow
regressions: `70 passed`. The frozen CM-57A/CM-57B/CM-57C/CM-57IB
deterministic selection also passed `70 tests` with `PYTHONPATH=.`.

The focused tests cover catalog parent visibility, catalog leakage, initial
versus correction catalog parity, generic prompt language, duplicate
section/report capabilities, missing raster/curve parents, valid
normal/reference/raster and mixed closure, basic sections, order-independent
validation, unmodified correction plans, bounded second failures, mixed
report-plus-section plans, unresolved requirements, and a synthetic plugin
capability graph.

No Qwen, OpenRouter, or CM-57C live run is part of P1. Passing deterministic
tests proves implementation fidelity only; it does not establish planner model
reliability. CM-57P2 must provide the planner-only causal evaluation before any
end-to-end rerun.

The full suite completed with `1760 passed, 12 failed, 3 skipped, 11
subtests passed, 2 warnings`. The failures were outside the P1 change boundary:
known agent/helper and schema-budget failures, missing external R6 evidence, and
unrelated graph-report/section test worktree changes. No P1-focused or adjacent
planner failure was observed.

## Explicit Non-Goals

P1 does not modify typed-worker semantics, reverse handling, sample-axis
minimum/maximum mapping, unrequested raster defaults, routing, workflow
topology, enrichment, compiler behavior, capability declarations, registry
implementation, persistence, MCP, notebook behavior, or public cutover.
