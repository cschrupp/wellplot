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
| CM-01 Architecture guards | Complete (`d928261`) | AST import-invariant tests protect empty v2 package boundaries |
| CM-02 Reachability inventory | Complete (`7ab6780`) | Legacy reachability/deletion inventory committed |
| CM-03 Dual-engine evaluation | Complete (`5182d9c`) | Comparable v1/v2 result records supported without a v2 runtime route |
| CM-10 Program contracts and errors | Complete (`a5aec78`) | Pure source, diagnostic, artifact, result, and typed-error contracts pass |
| CM-11 AST policy validator | Complete (`5883a0a`) | Static grammar and adversarial allowlist tests pass without execution |
| CM-12 Restricted interpreter | Complete pending commit | Generic registry dispatch, dynamic budgets, and execution journal tests pass |
| CM-13 through CM-14 Program kernel | Not started | SDK and compile-only intent tests pass |
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

## CM-02 Inventory Boundary

CM-02 uses a static AST import graph rooted at public package, MCP, notebook,
and project-script entry points. The machine-readable inventory preserves a
deterministic shortest path for each seed that reaches a module. Current
reachability and migration classification are separate facts: a currently
reachable module can still be marked `replace` or `delete-after-cutover`, and
an unreachable module is not thereby authorized for deletion.

The inventory excludes direct `TYPE_CHECKING` and `typing.TYPE_CHECKING` bodies
from runtime reachability. It does not claim to resolve dynamic imports, plugin
entry points, or string-based module loading. No CM-02 result authorizes
caller refactoring or deletion; CM-03 and later slices consume this evidence.

## CM-03 Dual-Engine Evidence Boundary

The existing evaluation harness accepts `--engine v1` and `--engine v2`, with
`v1` as the compatibility default. Every task result records its engine and a
stable metrics object containing `program_chars`, `program_ast_nodes`,
`program_calls`, `program_repairs`, `dynamic_schema_chars`, and
`legacy_core_reached`. An unavailable measurement is the explicit string
`not_available`; it is distinct from an absent field, `null`, or a measured
zero.

CM-03 does not implement Code Mode execution. A live `v2` request returns one
`not_implemented` record per active task with the same task and fixture IDs as
the v1 suite. This happens before fixture preflight, provider creation, or an
import of `wellplot.agent.notebook`; it cannot run the legacy engine with a v2
label. The provider matrix retains provider summaries, adds engine summaries,
and pairs v1/v2 evidence by task ID, fixture, provider, and model. Missing
counterparts are represented as `null`, and `not_implemented` is excluded from
the pass-at-one denominator.

## CM-10 Program Contract Boundary

CM-10 introduces only pure, strict Authoring Program contracts and the
semantic error taxonomy in `wellplot.authoring_program`. Program source remains
verbatim until the parser exists. A compiled `ProgramArtifact` carries the
existing canonical `AuthoringDocumentIntent` directly, rather than a new
operation, statement, SDK-call, or desired-state representation.

The execution-result model requires explicit evidence: success requires an
artifact and cannot include error diagnostics; failure requires diagnostics and
cannot include an artifact. The seven program error categories convert
deterministically to concise diagnostics with stable `program.*` codes, an
optional source span, and an optional remediation hint. No raw Python
exception, traceback, provider object, persistence result, or MCP response is
part of the public contracts.

CM-10 adds no grammar, AST validation, interpreter, SDK, capability handler,
provider, LangGraph, MCP, route, feature flag, or legacy deletion. CM-11 owns
syntax and policy validation; CM-12 owns interpretation; CM-14 owns intent
compilation; CM-15 owns dry-run semantics.

## CM-11 Static Grammar Boundary

CM-11 parses source only with `ast.parse` and validates a closed AST allowlist.
It never executes, evaluates, imports from generated source, resolves runtime
attributes, calls callbacks, or generates bytecode. Its only output is the
validated `ast.Module` consumed by the future CM-12 interpreter.

The initial language permits expression method calls, one-name assignments,
literals and literal containers, keyword arguments, public one-attribute
access on `wp` or a previously introduced handle, bounded literal/local-literal
`for` loops, and boolean or literal-equality `if` conditions. A flat tuple loop
target remains allowed for the resistivity example in the migration plan. Calls
cannot chain and source cannot introduce arbitrary bare functions, imports,
private names, dynamic iteration, mutation, operators, comprehensions, async
syntax, or any AST node outside the allowlist.

One immutable `ProgramPolicyLimits` object carries the initial static budgets:
source characters, AST nodes, statements, calls, loop iterations, and nesting.
Oversize inputs yield `ProgramLimitError`; parsing errors yield
`ProgramSyntaxError`; unsupported syntax yields `ProgramPolicyError`; and
unknown or private names yield `ProgramNameError`. AST location conversion is
centralized in `grammar.py`; it maps Python AST offsets into the existing
1-based source-span model without attempting Unicode grapheme normalization.

CM-11 adds no interpreter, SDK handles, capability semantics, intent
generation, dry-run, provider, LangGraph, MCP, route, feature flag, or legacy
deletion. CM-12 owns all source-to-behavior interpretation.

## CM-12 Restricted Interpreter Boundary

CM-12 interprets only `AuthoringProgram` source after it has passed the CM-11
parser and static validator. The public entry point does not accept raw ASTs.
It executes the existing closed grammar directly by AST node type and never
uses `exec`, `eval`, source imports, Python builtins lookup, or dynamic
attribute dispatch.

The execution substrate is capability-neutral. A `RuntimeHandle` is only an
opaque `(token, kind)` identity. Root and handle methods resolve through
immutable explicit registries, not through a Python object carried by a handle.
Callbacks receive isolated recursively validated runtime values and must return
the same restricted value universe: scalar values, list/tuple values,
string-keyed dictionaries, and runtime handles. Unexpected callback failures
and unsupported returns become typed compact program diagnostics.

CM-12 applies independent actual-work budgets for dispatched calls, leaf loop
iterations, materialized runtime value items, and journal entries. Nested
loops count leaf iterations globally: a three-by-three nested loop records nine
iterations rather than two independent loop lengths. The generic journal is
deterministic trace evidence only; it is not an authoring operation IR or
canonical application state. Loop target bindings are lexical and temporary.

CM-12 adds no Wellplot SDK handles, IDs, capabilities, intent construction,
AuthoringService integration, transactions, persistence, provider, LangGraph,
MCP, routing, feature flags, or legacy deletion. CM-13 owns real deterministic
handles and IDs; CM-14 owns `AuthoringDocumentIntent` construction.
