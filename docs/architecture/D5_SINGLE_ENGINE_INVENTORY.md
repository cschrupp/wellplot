# D5 Single-Engine Inventory

Status: `D5-0R1 / INVENTORY CORRECTION ONLY`

Branch: `d5/single-engine-convergence`

Starting candidate: `73fe0e581c32523349d75bd3390cc4d8088c4b89`

Inventory base: `2e878c5b5c6d149dce4b5d8ce8b34429e3277cbe`

## Scope and decision boundary

This document corrects the repository map so that D5-1 can make the canonical
ownership decision. It does not select a replacement schema, change routing,
delete code, or authorize a convergence refactor.

The target is one canonical execution path for production and experiments:

```text
natural-language request
        -> one planner / semantic router
        -> one model-facing semantic contract family
        -> one deterministic semantic lowerer
        -> AuthoringDocumentIntent
        -> one reconciliation / execution path
        -> AuthoringService
        -> canonical persisted document
        -> persistence / reload / rendering
```

`single engine` does not mean one schema for every layer. A model-facing
contract, `AuthoringDocumentIntent`, and the canonical persisted document may
remain different representations when each has a distinct responsibility and
there is one deterministic lowering path between them. It does mean that
multiple competing planners, worker contracts, lowerers, or execution paths
must not remain the long-term owners of the same responsibility.

No classification below authorizes deletion. `RETIRE` and `MOVE-PRIMITIVE` are
candidate D5-2 dispositions only; D5-1 must freeze ownership first.

## Evidence and provenance

The inventory distinguishes current implementation use from evidence that
supports a concept:

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| `EXP-TW-00` through `EXP-TW-08` | Typed-worker schema and provider-boundary experiments | That `typed_delivery.py` is the current canonical production worker |
| `CM-55` through `CM-59` | Code Mode planner, safety, context, worker, and runtime contracts | That every CM implementation is a single surviving engine |
| Semantic-IR V2/V2R records | Structured semantic and evaluation contracts | That Semantic IR is the current public runtime contract |
| D0-D2E delivery records | Public-path acceptance of the D1-D2E fixture compositions | Typed-delivery execution: those tests inject `ProgramSectionCompiler` and, for report work, `ReportProgramCompiler` |
| D4R1 provider-free rehearsal | Typed-delivery route behavior with a deterministic backend | Live Qwen capability: it did not use the live provider |
| Run-005 live campaign | Typed-delivery route behavior under Qwen and the frozen live harness | A model-semantic verdict independent of structured-response boundary failures |

Evaluation scripts, fixtures, graders, and live evidence remain evidence
assets. They are not additional runtime engines and must not determine
production routing.

## Verified runtime compositions

### Direct Notebook / typed-delivery composition

`src/wellplot/agent/direct_notebook.py` constructs:

```text
DirectNotebookSession
    -> AgentSession
    -> CodeModeCompileFacade
    -> CodeModeGraphDependencies
       -> SemanticPlanner
       -> SemanticEnricher + LogfileSourceLoader
       -> TypedDeliveryReportCompiler
       -> TypedDeliverySectionCompiler
    -> reconcile_authoring()
    -> AuthoringExecutor / execute_authoring_plan()
    -> AuthoringService
    -> persistence / validation / render
```

This is the composition used by the D4R1/D4R2 typed harnesses. It is not the
composition exercised by the D1-D2E acceptance tests, which replace the worker
dependencies with program compilers.

### MCP agentic composition

`src/wellplot/mcp/agentic_server.py` constructs the same facade and graph
dependency type, but injects:

```text
create_agentic_mcp_server()
    -> CodeModeCompileFacade
    -> CodeModeGraphDependencies
       -> SemanticPlanner
       -> SemanticEnricher + LogfileSourceLoader
       -> ReportProgramCompiler
       -> ProgramSectionCompiler
    -> AgentSession
    -> GraphAuthoringMcpOperations
```

Therefore MCP is currently a program-generation composition, not the typed
delivery composition. The shared facade does not make the worker contracts
equivalent.

### Explicit v1 composition

`src/wellplot/agent/routing.py` exposes `AuthoringEngine = Literal["v1", "v2"]`
and defaults to `v2`. Selecting `v1` constructs `AuthoringSession` from
`src/wellplot/agent/core.py`, preserving the older MCP/tool-oriented loop.
Selecting `v2` constructs the direct notebook session. This selector is a
reachable compatibility boundary, not proof that both engines should remain.

### D1-D2E acceptance composition

The D1-D2E tests use `DirectNotebookSession`, but their fixtures explicitly
inject `ProgramSectionCompiler` and, where report work is required,
`ReportProgramCompiler`. Their evidence therefore validates the program-worker
composition through the public adapter, not `typed_delivery.py`.

### D4R1/D4R2 live composition

The D4R1 provider-free typed rehearsal and Run-005 use the typed-delivery
composition. Run-005 recorded 19 logical calls across 9 turns. The retained
call evidence included 10 successful planner calls and 2 planner failures, 2
successful report-worker calls, and 5 section-worker failures. All 7 retained
failures were classified only as `invalid_response`; the evidence does not
retain enough subtype information to distinguish malformed JSON, schema
decoder incompatibility, missing fields, union selection, Pydantic-only
validation, Python-only validators, or semantic failure.

## Responsibility inventory

The classification is a D5-0R1 decision-preparation disposition, not a D5-1
architecture decision.

| Responsibility | Current implementations | Runtime callers | Input -> output | Evidence lineage | Unique capability | Overlap / duplication | Candidate canonical owner | Candidate retire/delete path | Reusable primitives to move first | Unresolved issue | Classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Public adapter | `ProjectSession`/`create_project_session`; `DirectNotebookSession`; `AuthoringSession`; MCP operations; CLI/API helpers | Notebook, v1/v2 routing, MCP, CLI/API | Request, document/source paths -> result, diagnostics, persistence/render evidence | D0-D4, agent/MCP tests, notebooks | Compatibility surfaces and host-specific lifecycle | Several public entry points expose overlapping authoring operations | One shared v2 adapter boundary with thin notebook/MCP/CLI adapters | Retire v1/core and duplicate MCP orchestration after parity and compatibility review | Result envelopes, deterministic render/persist helpers | Which compatibility surfaces must remain public | UNRESOLVED |
| Provider backend | v2 clients in `agent/providers`; legacy provider adapters; program-output wrappers | Direct notebook, MCP, v1/core | Config, credential, timeout -> structured/program backend | CM-57P9, SR7, D4 readiness | Backend transport and bounded retry/error projection | Separate v1/v2 clients and program/typed response assumptions | One provider abstraction with explicit structured-response modes | Retire duplicate adapters after request/error parity | Provider errors, request metadata, identity diagnostics | Whether one backend can support both selected contract and migration compatibility | UNRESOLVED |
| Planner | `code_mode/planner.py`; `agent/graph/planner.py`; free-form planning in `core.py` | Direct notebook, MCP Code Mode, graph/core route | Request plus context -> semantic plan/work units | EXP-TW, CM-57, D4 planner evidence | Task decomposition and deterministic routing gates | Multiple plan/state vocabularies | `SemanticPlanner` candidate | Retire graph/core planners after adapter parity | Plan diagnostics and capability metadata | Final plan schema and report/section ownership | UNRESOLVED |
| Planning schema | `SemanticPlan`, `ReportTask`, `SectionTask`; graph models/report tasks/state; legacy tool schemas | Corresponding planners/workflows/workers | Request/context -> ordered tasks and constraints | CM-55-CM-59, D0-D4 routing tests | Explicit task ordering, capabilities, and current-document context | Parallel task and state models encode overlapping concepts | One tagged plan/task family | Retire graph/legacy schemas after migration | Enum/capability metadata and diagnostic types | Whether graph state can consume the selected plan without context loss | UNRESOLVED |
| Context/enrichment | `SemanticEnricher`, `LogfileSourceLoader`; `resolve_authoring_context`; graph source/context projections; legacy inspect tools | Direct notebook, MCP Code Mode, v1/core | Host document/source -> grounded candidates, channels, section/report context | D1-D2D grounding, CM-58 safety | Deterministic source custody and channel grounding | Multiple projections of source and document context | Shared host-owned enrichment and canonical context resolver | Retire graph/legacy projections after provenance parity | Source identity models, channel inventory, normalization helpers | One context contract for typed and program migration | UNRESOLVED |
| Report semantics | `TypedDeliveryReportCompiler`; `ReportProgramCompiler`; graph report worker | Direct notebook, MCP, graph tests | Report task/context/request -> report intent or restricted program | TW-08, CM report work, D2A, D4R1 | Report-owned content and sparse report mutation | Separate typed/program/graph response contracts | One tagged report-action contract, exact form pending | Retire program/graph report workers after parity | Report intent models and diagnostics | Whether program execution provides unique report behavior | UNRESOLVED |
| Section semantics | `typed_delivery.py`; `section_semantics.py`; `typed_section_worker.py`; `semantic_section_compiler.py`; `ProgramSectionCompiler`; graph section worker | Direct notebook, MCP, D1-D2E tests, D4R1/D4R2 | Section task/context/request -> section intent or program | TW-08, CM-56/57, D1-D2E program tests, D4R1 typed evidence, Run-005 | Section mutation variants and grounded ownership | At least four overlapping section contracts; typed and program paths differ | One tagged section-action contract derived from validated lineage | Retire program/graph/historical workers after parity | `IdAllocator`, diagnostics, metrics, context normalization | Run-005 boundary failure subtype and contract shape | UNRESOLVED |
| Revision semantics | `AuthoringDocumentIntent`; task/context models; `SemanticIRV2/V2R`; graph intents; MCP operation models | Reconciler, workers, program interpreter, evaluation scripts | Partial desired state -> owned semantic mutations | SI V2/V2R, SR1-SR6, D1-D2E, D4 | Intent ownership and relational mutation semantics | Multiple semantic IRs and lower intents encode overlapping mutations | `AuthoringDocumentIntent` as lower intent; model-facing contract unresolved | Retire duplicate runtime IRs after explicit lowering/evidence decision | Identity allocation, reference topology, diagnostic types | Whether SI V2/V2R remain research-only or become the model-facing contract | UNRESOLVED |
| Fill semantics | `CurveFillSpec`, `AuthoringFillIntent`, create/update requests, `wp.fill()` | Reconciler, executor, service, workers, D2C | Binding relation -> canonical fill and compatibility projection | D2C and authoring model/service tests | Binding-owned fill relation and persistence identity | Typed/program payloads duplicate fill fields | Canonical authoring fill models plus one lowerer | Retire duplicate worker-local fill DTOs after contract selection | Fill identity and binding lookup helpers | Exact model-facing representation | KEEP |
| Semantic validation | Canonical Pydantic models; typed worker response models; logfile schema; program grammar/runtime validation | Adapters, workers, reconciler, service, persistence, tests | Untrusted payload/document -> validated object or bounded failure | TW-08, SR7 P0, D0-D4, CM tests | Layer-specific structural and canonical validation | Worker validators and runtime validators overlap but have different boundaries | Layered validation with canonical models authoritative | Retire duplicate semantic checks only after equivalence tests | Error taxonomy and normalized diagnostics | Which constraints belong in decoder schema versus host validators | KEEP |
| Semantic lowerer | Typed delivery compilers; program/report compilers; semantic section and SI compilers; legacy branch compiler | Code Mode graph, graph route, MCP, evaluation | Worker response/IR/program -> intent/submissions/program result | TW/CM, SI, D1-D2E, SR7 | Deterministic conversion into lower authoring operations | Multiple lowerers with different input contracts | One deterministic lowerer into `AuthoringDocumentIntent` | Retire alternate lowerers after output-equivalence and migration coverage | Intent builders, IDs, diagnostics, metrics | Which contract supplies the canonical input | UNRESOLVED |
| Workflow/orchestration | `code_mode/workflow.py` + facade; `agent/graph/workflow.py`; `agent/core.py`; MCP orchestration | Direct notebook, MCP, v1/core | Request -> plan, enrichment, workers, merged intent/result | CM-56-CM-59, D0-D4, D4R1 | Bounded fan-out, safety, custody, and merge ordering | Three orchestration families and two Code Mode worker compositions | Code Mode workflow/facade with one selected worker family | Retire legacy graph/core orchestration after adapter parity | State projections, diagnostics, retry accounting | Whether MCP and notebook can share lifecycle without semantic forks | UNRESOLVED |
| State | `CodeModeGraphState`, `CodeModeWorkerState`, `WorkerOutcome`; legacy graph state/models; LangGraph state | Corresponding workflows/facades | Serializable work state -> worker outcomes, diagnostics, merged intent | CM graph tests, D0-D4 custody tests | Worker custody and deterministic result aggregation | Parallel state vocabularies | One Code Mode state family | Retire legacy state after workflow migration | Diagnostic and metrics models | Required state for report/section contract and evidence | UNRESOLVED |
| Identity allocation | `authoring_program.ids.IdAllocator`; handle builders; typed/lower intent ID logic | Program workers, semantic compilers, typed delivery, reconciliation | Existing context + new object request -> stable local identities | D0-D4, authoring program tests, typed delivery imports | Collision-safe local identity allocation | Utility is embedded in historical program package | Neutral authoring identity module | Move utility, then retire package runtime separately | `IdAllocator` and identity normalization | Canonical identity ownership and alpha-renaming rules | MOVE-PRIMITIVE |
| Reconciliation | `reconcile_authoring()` and `AuthoringReconciliationPlan`; `authoring_context.py` | Direct notebook, MCP/agentic, graph executor/verifier, tests | Partial intent + canonical doc + channels -> ordered safe operations or issues | D1-D2D, SR4, reconciler tests | Ownership, grounding, preservation, fail-closed mutation plan | Typed submissions and graph execution can bypass or wrap it | `reconcile_authoring()` | Retire bypass paths after parity and safety proof | Context resolution and operation models | Whether every worker route can lower here without loss | KEEP |
| Execution | `AuthoringExecutor`/`execute_authoring_plan`; `execute_typed_submissions`; graph executor and MCP operations | Direct notebook, typed route, graph/MCP, tests | Validated plan/submissions -> private/service document mutation | D1-D2D, authoring executor tests | Verified mutation and rollback/persistence boundary | Multiple execution surfaces can mutate canonical documents | `UNRESOLVED: AuthoringExecutor boundary` | Retire direct graph/MCP mutation paths after parity | Operation models, validation, mutation guards | Typed submission executor may be adapter or duplicate | UNRESOLVED |
| Authoring service | `AuthoringService` | Reconciler/executor, direct notebook, graph executor, MCP, tests | Validated authoring spec + operations -> canonical document | D1-D2D, service tests, MCP contracts | Canonical document mutation and validation | Some MCP/service helpers duplicate CRUD access | `AuthoringService` | Retire duplicate CRUD helpers after call-site migration | Canonical models and persistence mapping | Public API compatibility requirements | KEEP |
| Persistence | `authoring.py`, `logfile.py`, MCP service helpers, API serialization | Notebook, v1/core, MCP, API, tests | Canonical document <-> logfile/YAML/JSON | D1-D2D, schema/persistence tests | Legacy logfile compatibility and reload | Multiple adapters project the same canonical state | Shared authoring/logfile mapping boundary | Retire duplicate serializers after round-trip parity | Mapping and compatibility extension helpers | Which compatibility fields remain contractual | KEEP |
| Rendering | `api/render.py`; matplotlib, plotly, base/defaults; MCP helpers | Notebook, MCP, API, D0-D4 tests | Validated document -> image/PDF/plot | D0-D4, renderer/API tests | Output backends, not semantic engines | Multiple renderers are legitimate adapters | Existing render API/renderer registry | None currently identified | Renderer configuration only | No material D5 issue identified | KEEP |
| Evaluation/verification | `AuthoringService.validate`; logfile validators; D0-D4 harnesses/graders; SI/SR scripts | Runtime result assembly, tests, research runs, local CI | Document/output/evidence -> validation and acceptance result | D0-D4, SR7, SI/SR, CM/TW records | Scientific measurement and regression evidence | Research graders can be mistaken for runtime routing | Evidence-only D0-D5/SI/SR harness layer | Never route production through it; retire obsolete harnesses independently | Sanitized diagnostics and artifact hashing | Common evidence schema without runtime coupling | EVIDENCE-ONLY |

## Semantic duplication audit

The following answers the required question: what production semantic capability
would be lost if each candidate disappeared? A `none` answer means the
capability is represented elsewhere and the implementation is a retirement
candidate after migration proof.

| Component | Unique capability not represented elsewhere | Decision-preparation finding |
| --- | --- | --- |
| `section_semantics.py` | Typed section draft and host-side semantic validation helpers; concepts overlap with typed delivery and older drafts | No clearly unique long-term capability; compare validators before retirement |
| `typed_section_worker.py` | Historical typed section-worker boundary and conversion through `semantic_section_compiler.py` | No unique current public composition identified; evidence/compatibility only unless a missing contract is found |
| `semantic_section_compiler.py` | Deterministic validation/lowering for `SectionSemanticDraft` | Useful lowering may be salvageable; semantic vocabulary duplicates other drafts |
| `semantic_ir_v2.py` | Frozen semantic topology and deterministic SI-V2 qualification contract | Unique research/evaluation contract, not established as runtime owner |
| `semantic_ir_v2_compiler.py` | Lowering of SI-V2 to accepted semantic results | Unique research compiler; no proven production-only capability |
| `semantic_ir_v2r.py` | Revision-oriented SI-V2R representation and contract | Unique research contract; not current public runtime owner |
| `semantic_ir_v2r_compiler.py` | Deterministic SI-V2R conversion and revision semantics | Unique research compiler; production replacement requires a D5-1 decision |
| `typed_delivery.py` | Revision-specific typed delivery modes and lowering used by D4R1/D4R2 | Unique current typed route, but vocabulary duplicates TW/CM drafts; not canonical by default |
| `program_worker.py` | Restricted executable section programs, dry-run, repair, and program metrics | Unique compatibility/runtime behavior today; retirement requires a replacement and migration evidence |
| `report_worker.py` | Restricted executable report programs and report-specific program safety | Unique compatibility/runtime behavior today; retirement requires a replacement and migration evidence |
| `authoring_program/*` | Program grammar/interpreter/runtime plus shared IDs, diagnostics, metrics, inspection, and builders | Runtime is a historical engine candidate; shared primitives must move before package retirement |
| `agent/graph/*` | Legacy graph state/workers/executor/verifier composition | No unique semantic capability established beyond alternate orchestration; compatibility callers must be mapped |
| `code_mode/workflow.py` / `facade.py` | Current host-owned bounded graph lifecycle and stable compile-result projection | Strong convergence candidate, but worker contract remains unresolved |
| `direct_notebook.py` | Public notebook lifecycle, deterministic source context propagation, persistence/reload/render boundary | Adapter capability is unique and should remain thin; worker composition is not unique |
| `mcp/agentic_server.py` | MCP server construction and MCP-specific operations boundary | MCP transport is unique; its program-worker composition is not |

## Model-facing contract and Run-005 finding

Run-005 must be recorded as a boundary result, not as a standalone model
capability verdict:

```text
typed section worker: 0 successful / 5 invalid_response
```

The live evidence does not distinguish all relevant failure classes:

- malformed JSON;
- decoder/schema incompatibility;
- incomplete or missing required fields;
- wrong tagged/union branch;
- Pydantic canonical validation failure;
- Python-only `model_validator` failure;
- semantically wrong but structurally valid output.

The next implementation slice should improve sanitized diagnostics at the
provider/worker boundary before another live campaign. It must preserve the
separation between decoder validity, host validation, semantic correctness,
and deterministic reconciliation. Run-005 does not establish that Qwen is
incapable of WellPlot section semantics.

The model-facing contract should eventually use explicit tagged variants where
the response has mutually exclusive actions. That is a D5-1 decision, not a
D5-0R1 implementation. The accepted TW/CM evidence must be compared with
`typed_delivery.py`; no new contract is created here.

## Lower-engine finding

The strongest currently shared deterministic lower path is:

```text
AuthoringDocumentIntent
    -> reconcile_authoring()
    -> AuthoringExecutor / execute_authoring_plan()
    -> AuthoringService
    -> canonical AuthoringDocumentSpec
    -> persistence / render
```

Program interpretation, graph executor paths, and typed submissions are
competing or wrapping paths. None may be deleted in D5-0R1, and their exact
relationship to this lower path must be settled in D5-1.

## Final convergence matrix

This matrix prepares the D5-1 decision. Each row has one candidate owner; an
owner is `UNRESOLVED` where the evidence is insufficient to choose safely.

| Responsibility | Candidate canonical owner | Competing paths to retire | Unique unresolved issue |
| --- | --- | --- | --- |
| Public adapter | `UNRESOLVED: shared v2 host boundary` | v1/core, duplicate MCP orchestration | Compatibility contract for notebook, MCP, CLI |
| Provider backend | `UNRESOLVED: one provider abstraction` | legacy provider adapters, mode-specific wrappers | Structured-output and error taxonomy parity |
| Planner | `UNRESOLVED: SemanticPlanner candidate` | graph planner, core free-form planner | Plan/task contract |
| Planning schema | `UNRESOLVED: tagged SemanticPlan family` | graph task/state schemas, legacy tool schemas | Migration without context loss |
| Context/enrichment | `UNRESOLVED: shared host enrichment` | graph context projections, legacy inspect tools | One provenance-preserving context contract |
| Report semantics | `UNRESOLVED: one tagged report action` | program and graph report workers | Report content ownership and compatibility |
| Section semantics | `UNRESOLVED: one tagged section action` | typed/program/graph/historical workers | Run-005 boundary contract and decoder shape |
| Revision semantics | `UNRESOLVED: AuthoringDocumentIntent lower contract` | SI runtime candidates, graph intents, duplicate DTOs | Model-facing versus lower intent boundary |
| Fill semantics | `CurveFillSpec`/`AuthoringFillIntent` | worker-local fill DTOs | Exact model-facing payload |
| Semantic validation | Layered canonical + boundary validators | duplicated worker/runtime checks | Decoder versus host-validator ownership |
| Semantic lowerer | `UNRESOLVED: one deterministic lowerer` | typed/program/SI/branch compilers | Common input contract |
| Workflow/orchestration | `UNRESOLVED: Code Mode facade/workflow` | legacy graph and core loops | Worker family and lifecycle parity |
| State | `UNRESOLVED: Code Mode state family` | legacy graph state | Evidence and retry custody fields |
| Identity allocation | Neutral authoring identity module | `authoring_program.ids` package location | Migration compatibility |
| Reconciliation | `reconcile_authoring()` | bypassing graph/MCP execution paths | All routes must lower here |
| Execution | `UNRESOLVED: AuthoringExecutor boundary` | typed submission and graph executors | Mutation safety and result parity |
| Authoring service | `AuthoringService` | duplicate CRUD/service helpers | Public compatibility surface |
| Persistence | Shared authoring/logfile mapping boundary | duplicate serializers | Legacy compatibility fields |
| Rendering | Existing render API/renderer registry | none currently identified | No material D5 issue |
| Evaluation/verification | Evidence-only D0-D5/SI/SR harness layer | runtime routing through harnesses | Common evidence schema without coupling |

## D5-0R1 handoff state

```yaml
runtime_compositions_verified: 5
responsibilities_classified: 20
KEEP: 6
MOVE-PRIMITIVE: 1
RETIRE: 0
EVIDENCE-ONLY: 1
UNRESOLVED: 12
production_code_changed: NO
tests_changed: NO
provider_model_calls: 0
```

The next step is D5-1: a decision record that freezes one owner for every
unresolved row. D5-2 may then converge implementation and retire duplicates,
with capability-preserving tests. No D5-1 or D5-2 work is authorized by this
inventory correction.
