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
| CM-12 Restricted interpreter | Complete (`a9f2d3a`) | Generic registry dispatch, dynamic budgets, and execution journal tests pass |
| CM-13 Deterministic identities | Complete (`1708905`) | Reservation-based IDs and typed ownership-handle tests pass |
| CM-14 Canonical intent builder | Complete (`66f06ef`) | Explicit SDK calls compile to canonical intent without execution |
| CM-15 Private semantic dry run | Complete (`ea2d115`) | Canonical intent reconciles, executes, and validates against an isolated document copy |
| CM-16 Bounded inspection facade | Complete (`f37284d`) | Fixed immutable projections provide scoped worker context without document discovery |
| CM-20 CapabilitySpec v2 bridge | Complete (`873fd14`) | Additive v2 arguments/handler contracts coexist with unchanged v1 declarations |
| CM-21 Report capability migration | Complete (`3bebd28`) | `report.standard` v2 arguments compile through explicit host SDK methods |
| CM-22 Structural capability migration | Complete (`9ae45b3`) | Section and fixed-kind track v2 arguments compile through host-owned structural methods |
| CM-23 Curve/raster binding migration | Complete (`4966b60`) | Curve and raster v2 arguments compile through host-owned binding methods |
| CM-24 Fills and annotations | Complete (`0423f7e`) | v2 leaf capabilities compile through plugin-owned handlers |
| CM-25 Plugin extensibility proof | Complete (`5646c60`) | External test-only capability registers and executes through generic contracts |
| CM-30 Provider v2 protocol | Complete (`e207550`) | Async typed provider contract works without `agent.core` |
| CM-31 OpenAI structured transport | Complete (`1dbf49d`) | One native Responses parse call validates a static plan fixture |
| CM-32 OpenAI program transport | Complete (`1329c62`) | One native Responses text call returns bounded program source |
| CM-33 OpenAI-compatible provider transport | In progress | Explicit-capability Chat Completions adapter implements the v2 protocol |
| CM-34 Bounded program repair | Not started | One bounded correction remains observable in traces/evals |
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

## CM-13 Identity And Handle Boundary

CM-13 allocates canonical identity through explicit reservation sets, never a
hidden counter. Document sections are in one document-wide namespace; tracks
are local to each section; bindings are document-wide. Allocation selects a
requested normalized base when it is free, otherwise the first available
numeric suffix (`base`, `base.2`, `base.3`). Reserving an existing high suffix
does not consume lower free suffixes. Identical reservation and creation order
therefore produces identical canonical identities.

New binding bases derive from normalized section, track, and source channel
when available; an `id_hint` is only an advisory fallback seed. Adoption keeps
the exact supplied canonical identity and reserves it idempotently without
allocating a replacement. Fill and annotation IDs are generic structural leaf
identities only; CM-14 owns their domain-specific naming semantics.

`ReportHandle`, `SectionHandle`, `TrackHandle`, `BindingHandle`, `FillHandle`,
and `AnnotationHandle` are frozen identity values. They carry provenance and
parent path metadata, not mutable document fragments, callbacks, capabilities,
or Python host objects. The identity builder rejects wrong types, foreign
builders, unknown issued identities, and incorrect parent relationships using
existing typed program errors.

CM-12 accepts these explicitly registered immutable `RuntimeHandle`
subclasses through the unchanged registry dispatcher. It still does not use
dynamic attribute lookup, and arbitrary handle subclasses or lookalike objects
remain invalid runtime values.

CM-13 adds no Wellplot authoring methods, capability dispatch, document state,
intent construction, AuthoringService integration, persistence, reconciliation,
provider, LangGraph, MCP, routing, feature flags, or legacy deletion. CM-14
owns canonical `AuthoringDocumentIntent` construction.

## CM-14 Canonical Intent Builder Boundary

CM-14 connects the restricted program kernel to the existing canonical
`AuthoringDocumentIntent`. `IntentBuilder` accumulates only immutable,
revalidated desired-state fragments; it does not hold an `AuthoringDocumentSpec`
or simulate reconciliation, mutations, persistence, rendering, or an
application service.

The initial explicit SDK surface covers report title/subtitle, sections,
tracks, scalar curves, rasters, curve fills, and narrow text annotations.
It accepts typed CM-13 handles and delegates every identity, provenance, and
parent ownership check to `HandleBuilder`. CM-14 consumes canonical IDs from
those handles; it never allocates, rewrites, or infers an identity itself.

CM-12's callback contract intentionally remains receiver-independent in this
slice. The SDK therefore uses explicit root calls such as
`wp.track(section, ...)` and `wp.curve(track, ...)`, passing typed handles as
ordinary restricted-program values. This keeps the ownership operand visible
to the callback without changing the generic interpreter registry solely for
fluent syntax.

Each accepted SDK value is first constructed with the existing canonical intent
models. Repeated `intent()` calls return fresh equivalent
`AuthoringDocumentIntent` values and preserve section, track, and child call
order where the canonical model represents order. There is no Code Mode
operation IR, shadow desired-state model, generic payload passthrough, or
capability-specific execution in this slice.

CM-14 adds no `AuthoringService` execution, dry-run, reconciliation,
persistence, rendering, source inspection, provider, LangGraph, MCP, routing,
feature flag, or legacy deletion. CM-15 owns private semantic dry-run
execution; CM-20 and later capability slices own broader SDK vocabulary and
capability handlers.

## CM-15 Private Semantic Dry-Run Boundary

CM-15 adds `ProgramRuntime`, the Wellplot-specific execution boundary beneath
CM-14. It accepts already compiled canonical intent and does not reparse,
reinterpret, or reconstruct program source. For every run it creates an
`AuthoringService` from a deep canonical clone of the caller's current
`AuthoringDocumentSpec`, then calls `reconcile_authoring`,
`execute_authoring_plan`, and `AuthoringService.validate` in that order.

All authoring context is supplied explicitly by the caller: current document,
optional scaffold and defaults, available channels, channel aliases, and header
aliases. CM-15 does not inspect files or sources, acquire project state, or
infer missing context. The input document remains unchanged whether execution
succeeds or fails, and the private post-execution document never leaves the
runtime.

Success returns a `ProgramArtifact` containing the exact CM-14 intent. Failure
returns no artifact and one or more compact `ProgramDryRunError` diagnostics.
Canonical reconciliation issue codes and messages remain available when the
plan is not ready; unexpected implementation exceptions and execution details
are reduced to stable program-facing messages without tracebacks or host
objects.

CM-15 intentionally depends only on canonical domain/authoring modules:
`wellplot.model`, `wellplot.authoring_context`, `wellplot.authoring_reconciler`,
`wellplot.authoring_executor`, and `wellplot.authoring_service`. It adds no
agent, MCP, provider, LangGraph, source inspection, persistence, renderer,
notebook, routing, feature-flag, or legacy-deletion dependency. CM-16 owns
the next execution integration work.

## CM-16 Bounded Read-Only Inspection Boundary

CM-16 adds `AuthoringInspectionFacade` as a host-side context preparation API.
It accepts a caller-owned canonical document and explicit section-keyed channel
facts, then returns fixed immutable projections. It is not registered in the
restricted interpreter and cannot be invoked by generated programs.

The public surface is intentionally fixed:

- `document_summary()` returns report name, title, subtitle, and ordered section
  IDs.
- `sections()` returns ordered section ID, title, subtitle, depth range, track
  IDs, and track kinds without nested tracks.
- `tracks(section_id)` returns ordered track ID, title, kind, width, and binding
  IDs for one selected section.
- `bindings(section_id, track_id)` returns ordered binding ID, binding kind, and
  source channel for one section-scoped track.
- `header_slots()` returns ordered slot ID, semantic key, and label only; it
  does not expose current values or nested header layout.
- `channels(section_id)` returns only explicit caller-supplied mnemonic, kind,
  unit, and compact shape metadata for one existing section.

Document-derived projections preserve canonical order. External channels are
sorted by `(mnemonic, kind, unit)` using case-insensitive lexical comparison.
The facade never infers section-to-source relationships, accepts global
channel context, reads files, exposes paths or sample values, or provides
arbitrary query, field-selection, dump, or document access methods. Unknown
sections and section-local tracks produce the existing typed `ProgramNameError`.

CM-16 adds no capability knowledge, program-time inspection calls, provider,
planner, LangGraph, MCP, routing, persistence, rendering, source discovery,
or legacy deletion. CM-20 owns the next capability-plugin contract.

## CM-20 CapabilitySpec v2 Boundary

CM-20 extends the existing capability declaration with an optional Code Mode
contract while preserving the v1 artifact/compiler contract and all existing
planning and worker descriptor methods. A declaration is v1-only when neither
`arguments_model` nor `handler` is supplied. It supports v2 only when both are
supplied; partial pairs fail at construction.

The separate `code_mode_worker_descriptor()` contains only deterministic
declarative data: capability identity, category, description, aliases,
allowed parents, source constraints, worker hints, examples, and the JSON
schema generated directly by the declared Pydantic `arguments_model`. It never
contains the host handler, compiler, callable representation, signature,
module path, or memory address. Existing `planning_descriptor()` and
`worker_descriptor()` shapes remain unchanged for the current graph.

CM-20 validates capability aliases for non-empty values, case-insensitive
duplicates, and redundant capability-ID aliases. It does not execute handlers,
register them with the interpreter, migrate built-ins, or alter registry
lookup, planner, graph, provider, MCP, routing, persistence, rendering, or
legacy-deletion behavior. CM-21 owns the first real capability migration.

## CM-21 Report Capability Boundary

CM-21 migrates only `report.standard` to the additive v2 capability contract.
Its static `ReportStandardArgs` model contains sparse, explicit fields for
report title/subtitle, semantic general-header fields, service titles, detail
fields, remarks, page, depth, and output settings. Omitted collections and
settings mean no update; unknown fields and empty supplied collections are
rejected before compilation.

The host handler validates those arguments and routes them through explicit
`IntentBuilder` methods (`set_header_field`, `set_service_title`,
`set_detail_field`, `add_remark`, `update_page`, `update_depth`, and
`update_output`). It returns the existing `AuthoringDocumentIntent` directly.
Header semantic keys remain subject to the existing deterministic header-slot
reconciliation and alias context. No fuzzy path lookup or generic arbitrary
field setter is introduced.

Fluent receiver syntax such as `report.set(...)` and `report.add_remark(...)`
is explicitly deferred. `ReportHandle` remains an identity-only host token;
CM-21 does not add handle-method registration, interpreter changes, provider
guidance, planner routing, LangGraph, MCP, persistence, rendering, or legacy
deletion. The v1 report artifact/compiler and existing descriptor shapes remain
unchanged. CM-22 owns the next capability migration.

## CM-22 Structural Capability Boundary

CM-22 migrates `section.log_plot` and the four fixed-kind track capabilities:
`track.normal`, `track.reference`, `track.array`, and `track.annotation`. Their
static v2 contracts make `create`, `select`, and `update` explicit operations.
Create uses an advisory hint with the CM-13 allocator; select and update adopt
host-resolved canonical IDs. No handler searches the current document or
performs fuzzy identity resolution.

`IntentBuilder.select_section` and `select_track` adopt exact identities into
typed CM-13 handles. `update_section` and `update_track` merge only supplied
mutable fields, preserving omitted state and rejecting identity/parent moves.
Track capability handlers fix the canonical kind by capability function rather
than accepting a free-form kind argument. The result remains the existing
`AuthoringDocumentIntent` with no structural operation IR.

CM-22 validates structural ownership and argument shape only. Whether an
adopted target exists in a supplied current document remains a later dry-run or
reconciliation concern. No bindings, fills, annotation objects, interpreter
registration, fluent syntax, provider, planner, LangGraph, MCP, routing,
persistence, rendering, or legacy deletion is included. CM-23 owns curve and
raster bindings.

## CM-23 Binding Capability Boundary

CM-23 migrates `binding.curve` and `binding.raster` to additive v2 contracts.
Both capabilities use explicit `create`, `select`, and `update` operations.
Create allocates a binding identity from the CM-13 allocator; select and update
adopt an exact host-resolved binding identity without searching the current
document or resolving aliases.

Curve bindings own channel, label, independent scalar scale, and line style.
Raster bindings own channel, label, raster profile, normalization and explicit
color limits, colorbar, and sample-axis settings. Parent capability and source
kind restrictions remain declarative registry metadata: curve bindings require
normal or reference tracks and LAS/DLIS sources, while raster bindings require
array tracks and DLIS sources.

Handlers compile directly to the existing `AuthoringDocumentIntent` through
`IntentBuilder`. They do not add a binding IR, inspect source data, validate
current-document existence, register interpreter methods, or change provider,
planner, LangGraph, MCP, routing, persistence, rendering, or legacy deletion
behavior. CM-24 owns fills and annotations.

## CM-24 Fill And Annotation Capability Boundary

CM-24 migrates `fill.curve` and `annotation.typed` to additive v2
capabilities. Curve fills support the five canonical kinds:
`between_curves`, `between_instances`, `to_lower_limit`, `to_upper_limit`, and
`baseline_split`. The handler validates the kind-specific binding targets and
the required baseline or crossover configuration before compiling through
`IntentBuilder`.

Typed annotations support all five canonical variants: `interval`, `text`,
`marker`, `arrow`, and `glyph`. Both capabilities use explicit `create`,
`select`, and `update` operations. Creation allocates a host-owned identity;
selection adopts an exact identity; updates preserve that identity. Fill outer
fields are sparse, while baseline and crossover nested objects are complete
replacement values. Annotation updates replace the complete typed payload.

The handlers use identity adoption only and do not inspect documents, resolve
source channels, or infer parent compatibility. Declarative registry metadata
continues to require curve fills under normal tracks and typed annotations under
annotation tracks. The result remains the existing
`AuthoringDocumentIntent`; no fill/annotation operation IR is introduced.

CM-24 adds no interpreter registration, fluent syntax, provider, planner,
LangGraph, MCP, routing, persistence, rendering, or legacy deletion behavior.
CM-25 owns the next separately authorized migration slice.

## CM-25 Plugin Extensibility Boundary

CM-25 proves the capability registry is an execution plugin boundary without
changing production code. A test-only external-looking capability declares its
own v1 artifact/compiler and v2 argument model/handler, registers in a fresh
`CapabilityRegistry`, resolves by canonical ID and alias, exposes planning,
worker, and Code Mode descriptors, and executes through the registry-held
validate-then-handler contract to produce an exact
`AuthoringDocumentIntent`.

The synthetic capability is not included in `create_builtin_registry()` and
does not import graph, MCP, provider, LangGraph, or interpreter modules. The
protected workflow, planner, section worker, and interpreter files have no
dependency on the fixture. CM-25 therefore proves extensibility over the
existing canonical authoring domain; it does not claim that a new canonical
document object kind can be introduced without domain-model changes.

CM-25 adds no production capability registration, registry execution API,
workflow or planner branch, program-worker branch, interpreter change,
provider, LangGraph, MCP, routing, persistence, rendering, or legacy deletion.
CM-30 owns the next separately authorized provider/planner migration.

## CM-30 Provider Protocol Boundary

CM-30 adds the provider-neutral asynchronous generation contract at
`wellplot.agent.providers.base`. It defines explicit structured and program
generation requests, typed per-call results, `ProviderMetrics`, stable failure
categories, and a `ModelBackendProtocol`. Structured generation returns a
value validated through the supplied Pydantic model; program generation returns
plain source text without parsing or interpreting it.

The contract exposes no SDK request/response objects, messages schema, tool
calls, streaming, retry or fallback policy, endpoint configuration,
authentication model, reasoning controls, or provider-specific output knobs.
`ProviderRequestError` exposes only a stable category, explicitly safe message,
deterministic retryability, and optional integer status code. Concrete adapters
must not serialize raw exceptions, requests, responses, credentials, or prompt
contents through this boundary.

CM-30 is proven with a fake backend that implements the protocol structurally,
validates a recorded response through the supplied model, returns per-call
metrics, preserves program text, and reports typed validation and timeout
failures. Current OpenAI, OpenAI-compatible, local, and other provider
adapters remain unchanged. CM-31 owns the first live provider transport.

## CM-31 Native OpenAI Structured Transport

CM-31 adds `agent.providers.openai_v2.OpenAIStructuredBackend` as a separate,
structured-only transport. It delegates one request to the injected async
OpenAI Responses `responses.parse` method, passes the requested Pydantic model
as `text_format`, and passes the provider-neutral per-call timeout at the SDK
call boundary. It returns only the parsed model and normalized reported usage
metrics; it does not replay tools, stream, retry, repair JSON, or implement
plain program generation.

The adapter maps refusal, missing or invalid parsed output, timeout, transport,
rate-limit, authentication, provider rejection, and configuration failures to
the CM-30 stable categories with adapter-authored redacted messages. It has no
dependency on `agent.core`, legacy provider loops, MCP, LangGraph, or existing
concrete adapters. The OpenAI optional dependency floor is `>=1.66.0`, the
first verified release used for the async Responses `parse` contract in this
slice. Existing OpenAI and OpenAI-compatible authoring adapters remain
unchanged; CM-32 owns plain program transport.

## CM-32 Native OpenAI Program Transport

CM-32 adds `agent.providers.openai_program_v2.OpenAIProgramBackend` for one
ordinary async OpenAI Responses `responses.create` call. The transport passes
only the model, prompts, explicit optional generation settings, and per-request
timeout; it does not use `text_format`, function tools, tool replay, retries,
repair calls, or execution. `OpenAIBackendV2` composes the unchanged CM-31
structured backend and the CM-32 program backend to provide the full
`ModelBackendProtocol` surface without making either leaf transport claim the
other operation.

The program boundary performs envelope checks only: raw source or exactly one
strict Python fenced block, empty/prose/ambiguous envelope rejection, negative
JSON object/array classification, Python syntax parseability, completion and
tool-call checks, and the shared CM-11 16,000-character source limit. It does
not inspect AST node policy, receivers, calls, loops, budgets, or semantic
validity. The existing restricted parser and validator remain authoritative
downstream. Refusals remain `provider_rejected`; malformed, truncated,
tool-call, JSON, syntax-invalid, and oversized output remain
`invalid_response`. Existing provider error and usage semantics are preserved.

## CM-33 OpenAI-Compatible Provider Transport

CM-33 adds `agent.providers.openai_compat_v2.OpenAICompatibleBackendV2` as a
parallel v2 adapter over one injected Chat Completions client. Structured
generation is available only when the adapter is explicitly configured with
`structured_output="json_schema"`; otherwise it raises a configuration error
before making a provider call. The supported path sends one strict JSON Schema
response format derived from the supplied Pydantic model, validates the returned
JSON locally, and never downgrades to JSON mode or plain output.

Plain program generation uses one sparse Chat Completions request with no tools
or functions and shares CM-32's program-envelope validator and CM-11 source
limit. The max-token parameter spelling is also explicit at construction time:
`max_completion_tokens` or `max_tokens`; the adapter never probes or retries
with another spelling. Completion status, refusal, tool-call, malformed choice,
JSON, syntax, and length failures map to the CM-30 stable categories with
redacted adapter-authored messages and normalized Chat usage metrics.

The adapter does not import the legacy compatible-provider loop, `agent.core`,
MCP, LangGraph, planner, or worker modules. It implements both provider-v2
operations directly; no OpenAI fallback, retry policy, routing, or repair is
introduced. CM-34 owns bounded program repair.
