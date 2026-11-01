# ADR Candidate: NLP-to-Canonical Authoring Architecture

```yaml
decision_id: WELLPLOT-NLP-CANONICAL-AUTHORING-ARCH-001
status: DESIGN CANDIDATE / PENDING INDEPENDENT REVIEW
design_spec: docs/architecture/WELLPLOT_NLP_CANONICAL_AUTHORING_ARCHITECTURE_REMEDIATION.md
reference_checkpoint: 6f0ef73d2a73b1a01d40767264e8dea0bbad3b45
implementation_authorized: false
provider_calls: 0
endpoint_calls: 0
model_calls: 0
scientific_execution: false
C02_exposure: 0
```

## Decision Requested

Accept, adapt, replace, or reopen the proposed architecture for a single
canonical NLP-to-authoring path. This record is a review candidate, not an
accepted architecture decision and not an implementation authorization.

The proposed direction is:

```text
scientist request
  -> existing SemanticPlanner / one canonical graph
  -> verified, request-local semantic operation inventory
  -> host-compiled scoped work contracts
  -> existing canonical report/section workers
  -> strictly validated sparse semantic patches
  -> existing deterministic lowering to AuthoringDocumentIntent
  -> existing merge, reconcile_authoring, AuthoringExecutor, AuthoringService
  -> canonical YAML, reload and applicable render verification
```

The planner may propose user meaning, target clues, conditional semantics,
and presentation-order constraints. It must not emit canonical IDs, paths,
CRUD instructions, or host execution dependencies. The host independently
binds request-local references to request obligations and a current document /
source snapshot. Workers may return only typed semantics for those authorized
references. The host remains the sole authority for identity, source
resolution, mutation, dependency order, validation, persistence, and rendering.

## Scope and Evidence

The product scope is intuitive natural-language well-log authoring against a
validated existing document, with canonical YAML as persisted source of truth.
The proposed change concerns semantic contracts and their ownership, not the
deterministic authoring engine.

Evidence basis:

- `EMPIRICALLY_SUPPORTED`: the D5-5J baseline and accepted Code-Mode contracts
  establish one planner/worker graph, request-span obligations, bounded
  correction, host-owned grounding, deterministic lowering, and preservation.
- `EMPIRICALLY_SUPPORTED`: binding smoke `d5-binding-smoke-6f0ef73d-002` at
  this checkpoint returned `SMOKE_CONTRACT_FAIL`. Its sealed evidence records
  one planner call, one section-worker call, a schema-valid response with eight
  track entries against a two-track work contract, zero missing handles, six
  unexpected handles, and no lowering. The captured DTO digest is
  `5598fc7655ead59f6df02e9b9f1293f97e98ce187583c4d50f3ee6fa062288fa`; the
  terminal digest is
  `60e3b597a932e640a16f17b11454a751e28a9a08f9cfe91ee2415b0b64baef65`.
  Local custody was independently verified after the run. This is a contract
  mismatch observation, not evidence of scientific model quality.
- `ADAPTED`: the proposed operation inventory and scoped patch contracts adapt
  compiler-style intermediate validation to an LLM proposal boundary while
  retaining WellPlot's typed authoring service as the execution authority.
- `NOVEL` pending review: the exact split between planner-proposed operation
  inventory, host-compiled work contracts, and worker patch payload needs a
  minimal non-duplicative representation. A00 does not decide its concrete
  schema.

## External Evidence and Limits of Analogy

- The JSON Schema project describes schemas as structural/type constraints
  and explicitly notes that complex formats commonly need a separate semantic
  validation phase. This supports the existing structural-then-semantic
  boundary; it does not establish that the proposed operation vocabulary is
  correct for WellPlot. See the [JSON Schema validation overview](https://json-schema.org/understanding-json-schema/about)
  and [specification](https://json-schema.org/specification).
- Pydantic's v2 API provides JSON Schema generation and model validation
  primitives. The repository lock pins Pydantic 2.13.3; schema behavior must
  be tested against that locked version and the actual provider schema subset,
  not inferred from examples alone. See [Pydantic JSON Schema](https://pydantic.dev/docs/validation/2.5/concepts/json_schema/)
  and [Pydantic model validation](https://github.com/pydantic/pydantic/blob/main/docs/concepts/models.md).
- LangGraph documents graph nodes, message passing, and parallel activation
  within super-steps. This supports retaining the current explicit fan-out and
  join model; it does not require adding a ReAct loop or authorize mutations
  from worker nodes. The repository locks LangGraph 1.2.11. See the
  [LangGraph Graph API overview](https://langchain-ai.github.io/langgraph/concepts/low_level/).
- Database transaction documentation is only an analogy for isolation and
  atomic visibility. WellPlot persists YAML/files, not PostgreSQL rows, so
  database guarantees do not prove file-level atomicity. The private-candidate,
  publication, rollback, and reload behavior must be established from WellPlot
  source and tests. See [PostgreSQL transaction processing](https://www.postgresql.org/docs/current/transactions.html)
  and its [concurrency-control overview](https://www.postgresql.org/docs/18/mvcc.html).

Evidence classification: typed schemas and explicit graph boundaries are
`ESTABLISHED`; applying them as request-scoped semantic patches over the
existing WellPlot authoring service is `ADAPTED`; the exact operation-inventory
schema and snapshot/query protocol remain `NOVEL` until reviewed and tested.
No external source establishes that this specific design will improve model
success. That remains a future, separately bounded empirical question after
deterministic contract defects are closed.

## Current Implementation Map

| Responsibility | Current canonical owner | Current behavior / gap | Candidate disposition |
| --- | --- | --- | --- |
| Planner wire contract | `src/wellplot/agent/code_mode/planner.py`: `_PlannerWirePlan`, `_PlannerWireSectionTask`, `SemanticPlan`, `_canonical_plan_from_wire()` | One wire-to-canonical conversion; planner returns scoped goals, capabilities, requirements and constraints, not a typed operation inventory. | `ADAPT IN PLACE`; preserve one conversion and one `SemanticPlan`. |
| Request authority | `src/wellplot/agent/code_mode/obligations.py`: `compile_request_contract()`; `planner.py`: `_attach_compiled_requirements()`, `_attach_request_obligations()` compatibility helper | Host extracts request-span obligations, binds scopes, and attaches provenance after conversion. | `KEEP`; remains the only request-fact authority and provenance attachment. |
| Planner validation/correction | `SemanticPlanner.plan()`, `_validate_extraction_coverage()`, `validate_semantic_plan()` | Exact scope binding and bounded correction; duplicate-scope consolidation is narrowly handled within the existing planner correction ceiling. | `KEEP / ADAPT`; no second planner or correction loop. |
| Graph topology | `src/wellplot/agent/code_mode/workflow.py`: `build_compile_graph()`, `dispatch_workers()`, `merge_v2_intents()` | Plan, deterministic safety, enrichment, report/section fan-out, canonical workers, successful-fragment merge. | `KEEP`; no alternate orchestration. |
| Document/source context | `src/wellplot/agent/code_mode/enrichment.py`: `SemanticEnricher`, `ResolvedSectionContext`; `src/wellplot/agent/inspection.py`: `AuthoringInspectionFacade`; `source_loader.py` | Host supplies bounded summaries, source candidates, channel facts, and existing-object context. | `KEEP / ADAPT`; clarify snapshot identity and inspection state; do not add file or shell access. |
| Section work contract | `src/wellplot/agent/code_mode/worker_contracts.py`: `SectionWorkContract`, `build_section_work_contract()`, `validate_section_action_contract()` | Obligations become exact track/binding requirements; multiple requested tracks currently select `reconstruct`, whose response cardinality includes the full section and conflicts with sparse-add scope. | `ADAPT`; compile operation identity, exact changed-object set, preservation and target/source facts before worker call. |
| Section worker | `src/wellplot/agent/code_mode/typed_section_worker.py`; sole canonical `CanonicalSectionWorker` | Action-specific structured response, contract validation, grounding, host application, one existing correction protocol, lowering. | `ADAPT IN PLACE`; accept only scoped sparse proposals; no parallel worker or second repair mechanism. |
| Report worker | `src/wellplot/agent/code_mode/canonical_workers.py` | Existing sparse report semantics with separate ownership checks. | `KEEP / ADAPT` only where new report operation refs require it; no report/section ownership bleed. |
| Semantic lowering | `semantic_actions.py`, `semantic_section_compiler.py`, `canonical_workers.py` | Validated action models are deterministically mapped to provider-neutral intent fragments. | `KEEP / CONSOLIDATE`; one canonical lowering path. |
| Desired state | `src/wellplot/model/intent.py`: `AuthoringDocumentIntent` and typed report/section/track/binding intents | Partial desired state distinguishes omission, set, clear, and removal. | `KEEP`; worker output is not YAML or a second authoring document model. |
| Reconciliation / CRUD | `authoring_reconciler.py`: `reconcile_authoring()`; `authoring_executor.py`: `AuthoringExecutor`; `authoring_service.py`: `AuthoringService` | Host plans typed, dependency-aware operations and applies them through validated CRUD. | `KEEP`; host computes CRUD dependencies and IDs. |
| Apply/persist/verify | `src/wellplot/agent/direct_notebook.py`, `logfile.py`, existing validators/renderers | Canonical flow stages a candidate, reconciles, executes, verifies preservation, serializes/reloads and renders where applicable. | `KEEP`; strengthen request-level publication guarantees only if source audit proves a gap. |
| Retired compiler | Historical `TypedSectionCompiler` / `TypedSectionGenerationResult` consumers were retired on this lineage. | Must not be revived as a second executable path. | `RETIRED`; keep retirement attestation/regressions. |

## Candidate Decisions

1. **One engine.** Keep the existing shared composition root, LangGraph, planner,
   canonical workers, deterministic lowerer, `AuthoringDocumentIntent`,
   reconciler, executor, service, YAML loader, and renderer. No shadow compiler,
   second planner, alternate executor, direct model-authored YAML, or
   evaluation-only route.
2. **Typed operation intent, not CRUD.** Propose a bounded inventory of
   request-local semantic operation references and types. The host verifies
   completeness, ownership, conditions, targets, values, and source evidence.
   A worker cannot add, delete, reassign, or change operation types.
3. **Single canonical plan boundary.** Extend the existing planner wire contract
   and canonical `SemanticPlan` in place, or provide an explicitly accepted
   compatible evolution. There must remain exactly one conversion into
   `SemanticPlan`, followed by exactly one deterministic attachment of host
   request obligations. A separate durable semantic IR is out of scope.
4. **Sparse worker output.** One worker response may encode multiple authorized
   semantic changes for one report/section scope. Existing state is preserved
   by host obligations; the worker must not re-emit it. A full-section action
   cannot masquerade as a sparse addition.
5. **Two order domains.** User-requested presentation order is semantic input
   and requires request provenance. CRUD/dependency order is computed by the
   host from the reconciler and is never planner authority.
6. **Prefetch first, optional bounded reads.** Reuse existing inspection and
   enrichment. Read-only queries are permitted only if accepted design sets
   their scope, budgets, snapshot binding, data minimization, and denial
   behavior. No general ReAct loop, shell, network, or worker-controlled file
   access.
7. **Atomic request publication.** Keep operations on a private candidate and
   publish only after all request-level validation/preservation gates pass.
   Do not overstate per-operation `AuthoringService` atomicity as whole-request
   atomicity; verify the existing candidate/persistence boundary.
8. **Corrections.** Preserve the accepted single correction mechanism and
   call ceiling. Correct only typed validation violations; no silent host
   repair, no new semantic retry loop, and no retry for programming errors.

## Invariant-Preservation Matrix

| Baseline invariant | Status under this candidate | Required implementation proof (not authorized in A00) |
| --- | --- | --- |
| K-01 one canonical engine | Preserved | Reachability/attestation proves existing composition and worker graph only; retired compiler remains absent. |
| K-02 typed model/host ownership | Adapted, not weakened | DTOs contain request-local semantic references only; host owns canonical IDs, source paths, resolution, mutation and rendering. |
| K-03 schema-valid is not semantically correct | Preserved | Valid-but-wrong operation sets/values fail deterministic contract tests before lowering. |
| K-04 safety contains damage but does not repair meaning | Preserved | No automatic semantic substitution or field completion; invalid patch leaves source/public document unchanged. |
| K-05 immutable historical evidence | Preserved | No rewriting Authority F, D5 smoke, C02, or prior terminal/custody. New test fixtures are synthetic and separately versioned. |
| K-06 smoke before science | Preserved | A12 requires a separately authorized exact-checkpoint engineering smoke; scientific authority remains distinct. |
| K-07 canonical live root | Preserved | Any future live operation uses `/home/user/projects/well_log_os`, never a temp worktree. |
| R-01 provider-visible sufficiency | Strengthened | Each operation's scored fact has request/source provenance; unknown/uninspected/unavailable remain distinct. |
| R-02 schema/Python parity | Preserved and extended | Exact provider schema and Python models accept/reject the same contract; wire-valid/Python-invalid counterexamples covered. |
| R-03 explicit discriminators | Preserved | Operation type, target scope, and branch selectors are required where needed; defaults do not authorize mutation. |
| R-04 capability closure | Preserved | Existing host closure remains explicit and tests continue to pass; no planner or worker bypass. |
| R-05 revision/source inventories | Strengthened | Bounded immutable snapshot includes addressable existing state and source inspection state; ambiguity fails closed. |
| R-06 bounded correction/preservation | Preserved | One existing correction route; preserve sibling operations and all unrelated content, with pre/post projection checks. |
| R-07 causal grading | Preserved | Stage and owner are explicit; negative tests assert exact failure class and no publication. |
| R-08 controlled empirical changes | Preserved | Deterministic contract repair uses provider-free regression proof; new model claims require separate fresh authorization/population. |
| T-03 single correction path | Preserved | Any patch correction is routed through the existing `ValidationIssueSet`/`RepairContract` path only. |
| Full-capture privacy policy | Preserved | Full validated DTO capture remains explicit opt-in, private, bounded, screened best-effort, and separately retained/deleted; raw HTTP is never stored. |

## Proposed Migration and Dependencies

| Slice | Scope and primary code surfaces | Dependency / gate | A00 acceptance evidence |
| --- | --- | --- | --- |
| A00 | This specification, ADR, baseline matrix, roadmap and review packet. | Current design gate. | Independent architecture review; no source delta. |
| A01 | Synthetic fixtures/gold in tests; existing planner/work-contract/action/reconciler tests. | A00 accepted. | Sparse two-addition positive; full eight-track response negative; preservation and duplicate negatives. |
| A02 | `planner.py`, `obligations.py`, planner schemas/prompts/tests. | A01 fixtures and accepted OD-01. | One canonical conversion; operation coverage and request-span provenance. |
| A03 | `enrichment.py`, `inspection.py`, `source_loader.py`, snapshot models/tests. | A00 accepted; can progress alongside A02 after interface review. | Bounded source/document state; inspected/uninspected/unavailable distinctions; no mutation. |
| A04 | `worker_contracts.py`, existing report contract, scope/source binding tests. | A02 + A03. | Exact authorized operation multiset and scope, no cardinality-based `RECONSTRUCT`. |
| A05 | `typed_section_worker.py`, existing action schemas and worker tests. | A04. | Sparse multi-operation output; 8-track proposal rejected before lowering; existing correction only. |
| A06 | `canonical_workers.py`, report action schema/tests. | A04; preserve report boundary. | Sparse ordered report operations, exact slot ownership, no bleed. |
| A07 | `semantic_actions.py`, `semantic_section_compiler.py`, `AuthoringDocumentIntent`. | A05/A06. | One mapping into canonical intent; no duplicate IR/lowerer. |
| A08 | `workflow.py`, `merge_v2_intents`, `direct_notebook.py`, reconciler/executor/service integration tests. | A07. | Host CRUD DAG, private candidate, stale-state and failure atomicity, preservation. |
| A09 | Existing inspection/capture/error paths and security tests. | Interfaces from A03-A08. | Bounded reads, injection/path-denial, size/time limits, safe causal diagnostics. |
| A10 | Provider-free cross-product suites and attestation. | A01-A09. | AC-01..AC-24, regression matrix, no provider access. |
| A11 | Operator docs, schema examples, migration memory, pending Knowledge Delta promotion. | A10 and implementation review. | Code/docs/tests agree; old contracts marked historical rather than silently aliased. |
| A12 | Existing canonical live harness only. | A00 accepted, implementation accepted, separate live authority. | Fresh exact-head engineering smoke, independently reviewed; no authority for science in this ADR. |

**Implementation authorization:** not granted by this candidate. Independent
architecture acceptance plus one explicit Human authorization is required
before A01 or any production-source change. A12 remains a separate live gate.

## Open Decisions Requiring Review

The following questions must remain open until the architecture reviewer
accepts a specific answer. They must not be filled by implementation defaults.

| ID | Question | Candidate recommendation | Acceptance needed |
| --- | --- | --- | --- |
| OD-01 | Should planner emit a typed operation inventory? | Yes, as a constrained proposal verified against host-compiled request obligations; this amends only the current planner ban on operation intent, not host CRUD authority. | Confirm exact allowed planner semantics and provenance ownership. |
| OD-02 | How many operations per worker call? | One bounded batch per report/section scope by default, but numeric cap is unset. | Derive response/context ceilings from provider schema and bounded tests. |
| OD-03 | Should workers have read-only query tools? | Prefetch-first; on-demand only when a typed sufficiency check identifies missing facts. | Decide whether any tool is needed; define fixed count/bytes/time budgets and snapshot token. |
| OD-04 | Reuse current action DTOs or add sparse patch model? | Extend existing action family minimally; no durable second IR. | Choose exact discriminator/shape after compatibility/schema audit. |
| OD-05 | How are new section shells and child operations staged? | Host-generated staged identities and existing CRUD DAG. | Verify schema-valid shell defaults and rollback behavior in source/tests. |
| OD-06 | CREATE versus ENSURE and duplicate policy? | Literal intent; ambiguity/conflicts fail closed. | Define idempotence/no-op rules per supported operation. |
| OD-07 | Does ambiguous “GR and SP track” mean one or two tracks? | Do not infer. Use a documented domain rule only if authoritative, otherwise targeted clarification. | Resolve with domain evidence or preserve explicit ambiguity response. |
| OD-08 | Resistivity roles, units and visual emphasis? | Exact inspected mnemonic/unit; no arbitrary candidate choice or conversion. | Identify registry-backed role and style policy or leave unsupported/ambiguous. |
| OD-09 | Snapshot change during model work? | Optimistic version/hash check before lowering and publication. | Confirm existing document revision/hash mechanism and replan semantics. |
| OD-10 | How do report/section dependencies affect fan-out? | Parallel only for independent work on one immutable snapshot; dependent stages require explicit staged snapshot. | Define detection and deterministic scheduler ownership. |
| OD-11 | Correction count and preservation? | Retain one existing correction path and current ceiling. | Confirm no planner correction plus worker correction can exceed global per-turn limits. |
| OD-12 | Operation/schema/read budgets? | No arbitrary numeric defaults. | Set and test limits before implementation completion/qualification. |
| OD-13 | What does request-level atomic persistence guarantee? | Do not claim whole-request atomicity until private candidate and persistence path are audited. | Prove candidate swap/rollback and reload failure behavior. |

## Independent Review Instructions

Review this record together with the full remediation specification and the
listed code contracts at the exact reference checkpoint. Return one of:

- `ACCEPT` — architecture and unresolved-decision handling are coherent;
- `REWORK — NARROW` — list exact invariant or contract conflict and requested
  document-only correction;
- `REJECT` — identify the architectural reason this direction cannot fit the
  accepted baseline.

The review must explicitly evaluate:

1. Whether operation inventories amend the old planner boundary without
   transferring CRUD/dependency authority to the model.
2. Whether there remains one graph, one canonical `SemanticPlan` conversion,
   one provenance-attachment point, one worker per scope, one correction
   mechanism, and one deterministic lowering/reconciliation/execution path.
3. Whether a sparse multi-track patch can be represented without treating a
   changed-object set as a full-section replacement.
4. Whether read-only snapshot/context proposals reuse existing services and
   distinguish absent from uninspected/unavailable evidence.
5. Whether the proposed private-candidate/persistence claims match current
   source, or need qualification.
6. Whether OD-01..OD-13 are genuinely open and whether any recommendation
   prematurely chooses a domain semantic.
7. Whether A01-A12 dependencies, tests and acceptance gates are finite and
   measurable, and whether A12 remains separately authorized.
8. Whether the current failed binding smoke is represented as contract
   evidence, not as a scientific result or proof that the design will work.

No independent review should require or perform a provider/model call, smoke,
or scientific campaign. A00 must remain documentation-only. After ACCEPT,
Human architecture acceptance and implementation authorization are still
required before A01.

## Pending Knowledge Delta (Not Active Baseline)

If this architecture is accepted and later implemented, prepare a baseline
delta proposing that:

- planner semantic operation intent is permitted only as a typed, request-local
  proposal validated against host request obligations;
- host-owned target/source identity, obligation attachment, reconciliation,
  CRUD dependencies, mutation, persistence and rendering remain unchanged in
  ownership;
- worker patches are sparse, typed, operation-scoped, and cannot re-emit or
  mutate unrelated state;
- any snapshot/read-only inspection has explicit state, scope, provenance and
  finite resource bounds; and
- the existing single-engine, provider-schema parity, capability closure,
  bounded correction, causal failure and live-gate invariants remain binding.

This section is preparatory only. Do not edit or promote
`docs/agent-code-mode-current-baseline.md` until the ADR is independently
accepted and implementation evidence is available.

## Stop Condition

A00 ends at independent architecture review. It does not authorize A01,
production changes, a new provider-free experiment beyond ordinary document
validation, another binding smoke, Authority H, D5-FINAL-10, or C02 access.
