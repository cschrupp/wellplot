# Wellplot Code Mode Architecture Contract

- **Status:** Approved target architecture; v2 is not implemented or production-routed.
- **Migration authority:** [Code Mode migration plan](wellplot_agentic_code_mode_migration_plan.md)
- **Frozen v1 reference:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c` (`f03f76b`) on `mcp-stabilization`

## Purpose

Code Mode replaces the model-facing v1 pattern of request-specific, deeply nested
structured artifacts with a constrained Wellplot Authoring SDK. Models will write
small Wellplot programs; a Wellplot-owned parser and interpreter will convert
them into `AuthoringDocumentIntent` fragments. The existing canonical authoring,
reconciliation, validation, persistence, rendering, and verification layers
remain the only mutation authority.

This document is the concise implementation contract. The migration plan is the
normative slice-by-slice specification and evidence record.

## Coexistence Status

| Engine | Status during CM-00 through early CM slices | Routing |
|---|---|---|
| v1 structured graph | Operational production/reference implementation; frozen except critical correctness fixes | Current route |
| v2 Code Mode | Approved target under construction | Not production-routed |

v1 is not deprecated during CM-00. Deprecation requires the later A/B gate;
deletion requires the reachability and removal gates defined by the plan.

## Dependency Direction

```text
rendering and domain models
        ^
authoring service and reconciliation
        ^
authoring_program and capability plugins
        ^
agent planner, program workers, and LangGraph workflow
        ^
Python API, notebook helpers, and MCP edge
```

Forbidden reverse dependencies:

- `authoring_program` must not import LangGraph or MCP.
- capability plugins must not import LangGraph or MCP.
- authoring/domain modules must not import the agent package.
- the v2 graph must not import `wellplot.agent.core`, legacy tool contracts, or
  legacy operation-loop modules.
- internal graph nodes must not call Wellplot MCP servers or MCP mutation tools.

## Architectural Invariants

- `AuthoringService` and canonical models remain the sole mutation and
  persistence authority.
- `AuthoringDocumentIntent` remains the only durable, provider-neutral desired
  state IR.
- Model programs are transient input. They never edit YAML, renderer objects,
  or persisted files directly.
- The v2 worker path uses static command and capability argument models. It
  must not create request-specific output schemas with runtime `create_model`,
  `Literal`, or runtime unions to force document construction.
- The host allocates canonical IDs for new objects. Models may supply readable
  hints but do not establish identity correctness.
- Capabilities own their static argument model and deterministic handler. Adding
  a capability must not require a LangGraph topology or central worker-routing
  change.
- The graph remains capability-agnostic and uses bounded generation/repair.
- v1 and v2 mechanisms must not be casually combined. A transitional adapter
  requires an explicit migration slice, deterministic acceptance evidence, and
  a removal path for superseded complexity.

## Security And Sandbox Invariants

- Generated programs are parsed and interpreted by Wellplot; they are never
  passed to `exec`, `eval`, or Python bytecode compilation for execution.
- Initial syntax is allowlisted and budgeted for source size, AST nodes,
  statements, calls, loops, nesting, and created objects.
- Generated programs cannot import modules, access files, use the network,
  spawn processes, inspect runtime internals, mutate arbitrary attributes, or
  access dunder names.
- Programs produce in-memory intent fragments only. Parsing, policy validation,
  SDK argument validation, capability validation, and dry-run validation all
  precede merge and persistence.

## Boundary Roles

### LangGraph

LangGraph coordinates a small planner, deterministic source/context resolution,
parallel report and section program workers, and intent merging. It does not
encode domain capability branches or execute MCP calls.

### MCP

MCP is an external edge protocol. Stable deterministic MCP remains
provider-free; high-level agentic MCP calls the same internal Python session as
notebooks. MCP is not an internal transport for graph nodes.

### Capability Plugins

Each capability exposes a descriptor, static argument model, deterministic
handler, validation behavior, and examples or documentation required by its
worker. Plugins create or revise only their allowed `AuthoringDocumentIntent`
fragment through the SDK runtime.

## Migration Status

| Phase | Status | Exit condition |
|---|---|---|
| CM-00 Freeze and evidence | Complete (`cf51935`) | Baseline record, evidence format, and historical v1 labels prepared with no runtime changes |
| CM-01 Architecture guards | Complete pending commit | AST import-invariant tests protect empty v2 package boundaries |
| CM-02 Reachability inventory | Not started | Legacy reachability/deletion inventory committed |
| CM-03 Dual-engine evaluation | Not started | Comparable v1/v2 result records supported |
| CM-10 through CM-14 Program kernel | Not started | Restricted parser, validator, interpreter, SDK, and dry-run tests pass |
| CM-20 through CM-24 Capability plugins | Not started | v2 capabilities compile through plugin-owned handlers |
| CM-30 through CM-34 Provider and planner | Not started | Provider-neutral small semantic planner path works |
| CM-40 through CM-44 Graph cutover | Not started | Program workers pass A/B and CBL acceptance gates |
| CM-50 through CM-52 Public cutover | Not started | Python/notebook/MCP opt-in v2 path is verified |
| CM-60 through CM-62 Legacy deletion | Not started | Reachability gate authorizes removals |
| CM-70 through CM-73 Release hardening | Not started | Security, live-eval, and release gates pass |

## CM-00 Scope Boundary

CM-00 permits only migration documentation and evidence scaffolding. It must
not add source/runtime packages, program parsing or interpretation, SDK
builders, v2 capability plugins, provider interfaces, LangGraph v2 nodes,
feature flags, routing changes, legacy deletions, architecture tests,
production imports, dependencies, prompts, or agent behavior changes.

The CM-00 evidence record and scorecard format live in
[`docs/evaluations/agent-code-mode/`](evaluations/agent-code-mode/).

## CM-01 Guard Scope

CM-01 establishes two inert package boundaries:

- `wellplot.authoring_program` for the future restricted program parser,
  validator, interpreter, and SDK;
- `wellplot.agent.code_mode` for future v2 orchestration.

Both packages are docstring-only markers in CM-01 and are not public API. The
AST guard forbids `authoring_program` and `capabilities` from importing the
agent package, LangGraph, or MCP. It forbids `agent.code_mode` from importing
MCP or the identified legacy agent compiler and tool-loop modules, but it does
not prohibit a future Code Mode orchestration layer from importing LangGraph.

The guard also protects the existing domain and authoring roots from importing
the agent package. It does not decide deletion eligibility; CM-02 owns the
reachability graph and legacy deletion inventory.
