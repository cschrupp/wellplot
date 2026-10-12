# D5 Single-Engine Inventory

Status: `D5-0 / INVENTORY ONLY`

Branch: `d5/single-engine-convergence`

Inventory base: `2e878c5b5c6d149dce4b5d8ce8b34429e3277cbe`

## Scope

This document inventories the current WellPlot NLP and authoring production
implementations. It does not select a final implementation, delete code,
change routing, or authorize a convergence refactor.

The target under review is one shared engine for production and future
experimentation:

```text
natural-language request
        -> one semantic planning boundary
        -> one canonical typed representation
        -> one deterministic lowering path
        -> AuthoringDocumentIntent
        -> reconciliation and execution
        -> AuthoringService
        -> canonical document
        -> persistence / reload / rendering
```

The current repository does not yet satisfy that target. The lower authoring
boundary is substantially shared, but multiple public routes, planners,
semantic representations, worker families, and graph orchestrators coexist.

## Evidence basis

The inventory was derived from source imports, runtime composition, public
entry points, tests, and committed evaluation records. The important evidence
lineages are:

- `EXP-TW-00` through `EXP-TW-08`: typed-worker and schema development.
- `CM-56` through `CM-59`: Code Mode semantic, safety, and runtime work.
- Semantic-IR V2/V2R records under `docs/evaluations/agent-code-mode/semantic-ir-v2/`.
- D0-D4 delivery records under `docs/` and `tests/test_nlp_d*.py`.
- The accepted lower authoring path exercised by D1-D2D and the D4 provider-free
  harnesses.

Evaluation scripts and live evidence are evidence of behavior, not additional
production engines. They must remain segregated from the eventual runtime
surface.

## Inventory matrix

| Responsibility | Current implementation(s) | Runtime callers | Produces / consumes | Evidence lineage | Known production use |
| --- | --- | --- | --- | --- | --- |
| Public entry / adapters | `ProjectSession` and `create_project_session()` in `src/wellplot/agent/notebook.py`; `DirectNotebookSession` in `src/wellplot/agent/direct_notebook.py`; legacy `AuthoringSession` in `src/wellplot/agent/core.py`; MCP server and agentic MCP operations; CLI/API helpers | Notebook users, `wellplot.agent`, `mcp/agentic_server.py`, legacy agent callers, CLI | User request plus document/source paths; returns result, diagnostics, persistence and render evidence | D0-D4 public notebook tests; `tests/test_agent.py`; MCP tests; notebook examples | Direct notebook v2 is the active NLP route. v1 and MCP/legacy routes remain callable and therefore are production-relevant compatibility paths |
| Provider construction | v2 provider clients in `src/wellplot/agent/providers/_v2_client.py`, `openai_v2.py`, `openai_compat_v2.py`, and `providers/base.py`; legacy provider adapters in `core.py` and provider modules | `direct_notebook._build_agent_session()`; `mcp/agentic_server.py`; legacy `AuthoringSession` | Provider/model configuration, credentials, timeout and backend implementing structured/program generation | CM-57P9 endpoint work; SR7 configuration/harness records; D4 endpoint/readiness records | v2 direct notebook and agentic MCP paths; legacy provider path remains available |
| Planner | v2 `SemanticPlanner` in `src/wellplot/agent/code_mode/planner.py`; legacy graph planner in `src/wellplot/agent/graph/planner.py`; free-form legacy agent planning in `src/wellplot/agent/core.py` | `CodeModeGraphDependencies`; `mcp/agentic_server.py`; graph workflow; legacy agent loop | Request and bounded document/source summary -> semantic work plan | EXP-TW/CM planner records; CM-57 planner diagnostics; D4 typed route | v2 `SemanticPlanner` is used by the direct notebook route. Graph and core planners remain alternate runtime paths |
| Planning schema | v2 `SemanticPlan`, `ReportTask`, `SectionTask`; graph task/state models in `src/wellplot/agent/graph/models.py`, `report_tasks.py`, and `state.py`; legacy MCP/tool request schemas | Corresponding planners, workflows, workers and tests | Strict plan decomposition, task capabilities, order and current-document context | CM-55 through CM-59; D0-D4 task routing tests | v2 plan is active; graph and legacy schemas remain active through their adapters |
| Enrichment / context | v2 `SemanticEnricher` and `LogfileSourceLoader` in `src/wellplot/agent/code_mode/`; canonical `resolve_authoring_context()` and `authoring_context.py`; graph `source_context.py` and `context_projection.py`; legacy inspect/summarize tools | v2 compile graph, direct notebook adapter, graph workflow, MCP/core workflows | Host-inspected document, source candidates, channel inventories and grounded section/report context | D1-D2D source grounding and fail-closed tests; CM-58 safety records | v2 enrichment is active and owns source/channel grounding for the direct route; alternate context projections remain |
| Report semantic worker / schema | v2 `TypedDeliveryReportCompiler` and `DeliveryReportResponse` in `typed_delivery.py`; program `ReportProgramCompiler` in `report_worker.py`; graph report worker in `agent/graph/report_worker.py` | v2 workflow dispatch; graph workflow; D2A tests; MCP agentic operations | Report task/context + request -> report-owned `AuthoringDocumentIntent` fragment or restricted program | TW-08 typed schema; D2A report revision; CM report-worker records | Typed v2 report worker is the direct notebook implementation. Program and graph workers remain compatibility/research paths |
| Section semantic worker / schema | v2 `TypedDeliverySectionCompiler` and `DeliverySectionResponse`; program `ProgramSectionCompiler` in `program_worker.py`; historical `TypedSectionWorker`, `semantic_section_compiler.py`; graph section worker | v2 workflow dispatch; D1-D2D public path; graph workflow; direct compiler tests | Section task/context + request -> section-owned intent fragment or executable program | TW-08; CM-56/57; D1-D2D acceptance tests | Typed v2 section worker is active in the direct notebook route. Older program and graph workers remain callable |
| Revision semantic representation | Canonical `AuthoringDocumentIntent` and intent models in `src/wellplot/model/intent.py`; v2 task/context models; `SemanticIRV2` and `SemanticIRV2R`; legacy graph intents and MCP operations | Reconciler, typed delivery, program interpreter, graph executor, tests/evaluation scripts | Partial desired authoring state, references, ownership and semantic mutations | Semantic-IR V2/V2R evidence; SR1-SR6 ownership decisions; D1-D2D intent tests | `AuthoringDocumentIntent` is the lower canonical intent. Semantic IR V2/V2R are qualification/research representations and are not the sole runtime contract |
| Fill representation | `CurveFillSpec` and related canonical models in `src/wellplot/model/authoring.py`; `AuthoringFillIntent`; `CreateFillRequest`/`UpdateFillRequest`; `wp.fill()` program API | Reconciler, executor, service, typed/program section compilers, D2C path | Binding-owned fill relation -> canonical fill and compatibility projection | D2C design/implementation records; authoring model/service tests | Canonical authoring/service path and typed v2 fill creation are active |
| Typed validation | Pydantic canonical models in `src/wellplot/model/authoring.py` and `model/intent.py`; strict worker response models in `typed_delivery.py`; logfile schema validation | Public adapters, workers, reconciler, service, persistence, tests | JSON/model payload -> validated typed object or bounded failure | TW-08 schema records; SR7 grader contract; D0-D4 verifier tests | Active across v2 and lower authoring path; multiple worker-specific validators coexist |
| Semantic compiler / lowerer | v2 typed delivery compilers; restricted program compilers in `program_worker.py` and `report_worker.py`; `semantic_section_compiler.py`; `semantic_ir_v2_compiler.py` and `semantic_ir_v2r_compiler.py`; legacy `branch_compiler.py` | v2 graph, graph workflow, evaluation scripts, MCP operations | Worker response/IR/program -> `AuthoringDocumentIntent`, operation submissions, or program execution result | TW/CM semantic compiler records; SR7 semantic-equivalence contract; D1-D2D tests | Typed delivery is active in direct v2. Program and IR compilers remain alternate/research implementations |
| Executable / program representation | `AuthoringProgram`, `ProgramSource`, `ProgramMetrics`, diagnostics in `src/wellplot/authoring_program/models.py`; interpreter, `ProgramRuntime`, `IntentBuilder`, validator and inspection facade | Program workers and program-mode tests | Restricted source text -> parsed/validated/dry-run intent fragment and metrics | CM-44 through CM-59; D1-D2C program-path tests | Active for program-worker compatibility and bounded Code Mode support; not required by the typed-only target |
| Workflow / orchestration | v2 LangGraph `build_compile_graph()` in `code_mode/workflow.py` plus `CodeModeCompileFacade`; legacy graph workflow in `agent/graph/workflow.py`; legacy monolithic orchestration in `agent/core.py`; MCP agentic orchestration | Direct notebook, agentic MCP server, legacy notebook/agent paths | Planning -> safety -> enrichment -> worker fan-out -> merge; or legacy tool loop | CM-56 through CM-59; D0-D4 integrated paths | v2 compile graph is the current direct notebook route. Graph/core orchestration remains production-callable |
| Graph state | `CodeModeGraphState`, `CodeModeWorkerState`, `WorkerOutcome` in `code_mode/state.py`; legacy `GraphState`/state models in `agent/graph/state.py`; LangGraph `StateGraph` | Corresponding workflow builders and facades | Serializable execution state, work units, diagnostics and merged intent | CM graph tests; D0-D4 worker custody tests | Both v2 and legacy graph state machines are active in their respective routes |
| Reconciliation | `reconcile_authoring()` and `AuthoringReconciliationPlan` in `src/wellplot/authoring_reconciler.py`; contextual resolution in `authoring_context.py` | `DirectNotebookSession._apply_result()`; `mcp/agentic.py`; graph executor/verifier; tests | Partial intent + existing canonical document + available channels -> ordered deterministic operations or fail-closed issues | D1-D2D; SR4 ownership contract; authoring reconciler tests | Shared lower-layer production owner and strongest convergence candidate |
| Operation execution | `AuthoringExecutor` / `execute_authoring_plan()`; typed `execute_typed_submissions()` in `agent/operation_executor.py`; graph executor/report-worker execution; MCP operations | Direct notebook, graph route, MCP agentic route, tests | Reconciliation operations or typed submissions -> verified mutations on a private/service document | D1-D2D persistence and preservation tests; authoring executor tests | Shared canonical executor is active; typed submission and graph execution are parallel operation surfaces |
| Canonical authoring service | `AuthoringService` in `src/wellplot/authoring_service.py` | Reconciler/executor, direct notebook, graph executor, MCP operations, tests | Validated `AuthoringDocumentSpec` plus CRUD operations and validation | D1-D2D; authoring service tests; MCP tool contract tests | Active shared mutation owner |
| Persistence | `load_logfile()`/mapping adapters in `src/wellplot/authoring.py` and `src/wellplot/logfile.py`; persistence helpers in `src/wellplot/mcp/service.py`; serialization in `src/wellplot/api/serialize.py` | Direct notebook, legacy/core route, MCP operations, API and tests | Canonical document <-> legacy logfile YAML/JSON plus compatibility extensions | D1-D2D persistence/reload evidence; logfile schema tests | Active shared boundary; legacy logfile compatibility is required |
| Rendering | `src/wellplot/api/render.py`; renderer implementations in `src/wellplot/renderers/matplotlib.py`, `plotly.py`, and base/defaults; MCP render helpers | Notebook/direct session, MCP service, API, D0-D4 acceptance tests | Validated canonical/logfile document -> image/PDF/plot output | D0-D4 render evidence; renderer/API tests | Active production capability; multiple renderer backends are output adapters, not semantic engines |
| Verification / evaluation | `AuthoringService.validate()`; logfile schema validators; D0 acceptance verifier; D1-D4 harnesses and graders in `scripts/` and `tests/`; semantic comparison/evaluation scripts | Public session result assembly, delivery tests, research harnesses, CI/local test runs | Document/output -> validation, preservation, workflow and scientific acceptance evidence | D0-D4 frozen contracts; SR7 P0/P1 evaluation lineage; CM/TW records | Canonical validation is production. D0-D4/SR7 harnesses are development/evaluation only and must not become runtime routing |

## Runtime route map

### Current direct notebook v2 route

The currently selected notebook route is:

```text
ProjectSession / DirectNotebookSession
    -> AgentSession
    -> CodeModeCompileFacade
    -> Code Mode LangGraph
       -> SemanticPlanner
       -> deterministic safety layers
       -> SemanticEnricher / LogfileSourceLoader
       -> TypedDeliveryReportCompiler or TypedDeliverySectionCompiler
       -> typed intent merge
    -> reconcile_authoring
    -> AuthoringExecutor
    -> AuthoringService
    -> persistence / validation / render
```

`src/wellplot/agent/routing.py` still exposes an explicit `v1`/`v2` selector,
although `v2` is the default. `DirectNotebookSession._apply_result()` is the
important public integration boundary: it supplies grounded channel context to
the canonical reconciler before private execution and persistence.

### Legacy and alternate routes

- `AuthoringSession` and the large `agent/core.py` implement the older
  MCP/tool-oriented loop and remain reachable through the v1 selector.
- `src/wellplot/agent/graph/` contains a separate planner, graph state,
  report worker, section worker, executor and verifier route used by the
  agentic MCP server and graph tests.
- `src/wellplot/agent/code_mode/program_worker.py` and `report_worker.py`
  implement restricted executable-program workers alongside the current typed
  delivery workers.
- `SemanticIRV2`/`SemanticIRV2R` and their compilers are valuable semantic
  research/evaluation contracts, but their coexistence with `SemanticPlan`,
  typed delivery responses, program sources, and canonical intents means the
  repository currently has more than one semantic boundary.

## Responsibility ownership findings

1. The canonical lower owner is already identifiable: `AuthoringService`,
   `reconcile_authoring()`, `AuthoringExecutor`, persistence adapters, and
   rendering form the most reusable deterministic core.
2. The best current production convergence candidate is the direct v2 typed
   route because it is the route exercised by D1-D2D through the public
   notebook API and has explicit source grounding, typed worker responses,
   safety layers, and bounded diagnostics.
3. The repository still has duplicate semantic/planning owners above that
   core: legacy v1/core, graph workers, typed workers, program workers, and
   Semantic-IR compilers. They cannot be deleted safely from inventory alone.
4. D4 and SR7 scripts, fixtures, live evidence, and graders are not runtime
   engine components. They should remain segregated as qualification assets and
   should not determine production routing.
5. Production and experimentation can share the same selected engine without
   sharing mutable evidence or test-only behavior. Experiments should inject a
   backend/configuration at the provider boundary and retain the same typed
   context, compiler, reconciler, executor, persistence, and renderer path.

## D5-0 conclusion

No pruning is authorized by this inventory. Before D5-1 implementation, the
project needs an explicit decision record that freezes:

- the single public engine boundary;
- the canonical semantic representation exposed by that boundary;
- whether typed delivery or restricted program generation is the sole worker
  contract;
- the retirement/compatibility policy for v1, graph, Semantic-IR, and program
  routes;
- the test/evaluation boundary that prevents D4/SR7 harness code from entering
  production execution.

The inventory supports a narrow next step, not a broad rewrite: prove the
selected direct v2 typed route against the required notebook/MCP/CLI adapters,
then retire or quarantine redundant routes only after dependency and behavior
coverage is demonstrated. Any future implementation should be a separate
bounded D5 slice with its own decision record and acceptance criteria.

## Evidence classification

- Shared deterministic authoring lower half: `ESTABLISHED` by current source
  structure and repeated D0-D4 exercise.
- Direct v2 typed route as the convergence candidate: `EMPIRICALLY_SUPPORTED`
  by D1-D2D public-path evidence; not yet a final architecture decision.
- One engine for production and experiments: `ADAPTED` from the existing
  provider-boundary and typed-worker structure; D5 must still define the
  retirement boundary.
- Exact pruning set: `NOT DECIDED` in D5-0. No deletion is justified by the
  inventory alone.
