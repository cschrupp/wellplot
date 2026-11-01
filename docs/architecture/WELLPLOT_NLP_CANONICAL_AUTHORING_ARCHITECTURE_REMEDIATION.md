WellPlot — NLP-to-Canonical Authoring Architecture
Detailed Remediation Specification, Migration Plan, and Acceptance Matrix
Document ID: WELLPLOT-NLP-CANONICAL-AUTHORING-ARCH-001
Version: 0.1 — DESIGN CANDIDATE FOR REVIEW
Prepared: 2026-10-31
Repository: cschrupp/wellplot
Inspected development branch: engineering-d5-binding-path-repair
Inspected exact checkpoint: 6f0ef73d2a73b1a01d40767264e8dea0bbad3b45
Scope: Code Mode/NLP planning, semantic workers, read-only inspection, canonical-intent handoff, deterministic integration, qualification
Authority: Design and planning only. No repository modifications, model calls, smoke replay, scientific campaign, or production promotion are authorized by this document.
Primary design statement: WellPlot is a deterministic well-log authoring system whose source of truth is a validated document persisted to YAML. The NLP layer translates a scientist's instructions into bounded, typed changes to that existing document, using specialized semantic workers only as needed. The canonical host—not the LLM—owns object identities, resolution, authoritative dependencies, CRUD execution, validation, persistence, reload, and rendering.
________________________________________
0. Decision summary
0.1 Preserve, adapt, and forbid
Area	Decision for proposed architecture	Reason
Canonical YAML/logfile format and loader	KEEP	Existing source of truth and rendering input.
AuthoringService and its CRUD API	KEEP	Already supports typed create, read, update, remove, move, validation, atomic per-operation mutation.
AuthoringDocumentIntent	KEEP	Already supports partial desired state with explicit omission, clear, and remove semantics.
reconcile_authoring() and AuthoringExecutor	KEEP	Already compiles partial intent to typed, dependency-aware, phased CRUD operations.
Single CodeModeCompileFacade / shared LangGraph	KEEP, ADAPT IN PLACE	Required by accepted single-engine baseline.
Planner	KEEP, EXTEND ITS CONTRACT	Decompose by domain and target and propose bounded semantic operation inventory, conditions, and user ordering constraints.
Report and section workers	KEEP, NARROW THEIR ROLE	Translate assigned semantic operations into constrained typed patches; they do not choose an unrelated operation.
Source/document inspection	KEEP EXISTING SERVICES; EXPOSE BOUNDED READS	Workers need grounded current-state evidence; no worker-controlled writes.
Worker output	JSON typed semantic patch, not YAML and not executable CRUD script	Preserve stable provider-facing schema while host owns IDs and mutation mechanics.
reconstruct for adding multiple tracks to existing section	REMOVE THIS ROUTING AFTER MIGRATION	The current action label implies full reconstruction although the contract demands a sparse addition.
Second planner, alternate semantic engine, shadow executor, direct model-authored YAML	FORBID	Duplicates accepted canonical responsibilities and weakens safety.
Arbitrary LLM tool/CRUD loops	FORBID BY DEFAULT	Read-only bounded inspection only; execution happens in deterministic host.
0.2 Explicit distinction between the three meanings of “operation”
1.	Semantic operation: ADD_TRACK, UPDATE_CURVE_SCALE, SET_HEADER_FIELD, ADD_REMARK, ENSURE_TRACK, etc.; identifies the scientist's intended change. It may carry request-local references, conditions, and presentation constraints.
2.	Worker output: a typed JSON semantic patch representing only the authorized operations. It cannot introduce new operation families, targets, or scope. One worker call may return several operations in one bounded, independently verifiable batch.
3.	Canonical CRUD operation: the existing host's AuthoringOperation with action, object_kind, canonical IDs, phase, payload, and depends_on, produced by the existing reconciler and executed by the existing authoring executor.
Never conflate a report/section work unit, a semantic operation, a model call, and a transaction. Their cardinalities are not required to be equal.
0.3 Governing decisions requiring formal review
The current planner's accepted contract explicitly forbids producing operation order and mutation instructions. Extending it to produce a semantic operation inventory is therefore an intentional architecture-contract revision, not a trivial prompt edit. A reviewable ADR must amend/supersede only that restriction while preserving all settled invariants in docs/agent-code-mode-current-baseline.md. Until that decision is accepted, the material below is a design proposal, not a replacement active baseline.
________________________________________
1. Evidence-based current-state inventory
1.1 Verified production route at inspected checkpoint
flowchart TD
 U[Scientist request] --> P[SemanticPlanner]
 P --> S[Capability / report-boundary / section-leaf safety]
 S --> E[SemanticEnricher: source and document context]
 E --> W[Dispatch: report worker or one section worker per SectionTask]
 W --> V[Model-generated typed semantic action/response]
 V --> C[Host contract and obligation validation]
 C --> L[Deterministic lowering to AuthoringDocumentIntent]
 L --> M[Merge successful intent fragments]
 M --> R[reconcile_authoring]
 R --> X[AuthoringExecutor + AuthoringService on private document]
 X --> Q[Canonical + obligation + preservation validation]
 Q --> Y[Persist YAML; reload / render where applicable]
Code-grounded anchors (all inspected at the checkpoint above):
•	src/wellplot/agent/code_mode/planner.py: SemanticPlan, ReportTask, SectionTask; SectionTask cardinality is one per section scope, not one per track. Planner prompt currently forbids operation ordering/IDs and mutation steps.
•	src/wellplot/agent/code_mode/workflow.py: plan → safety → enrichment → Send fan-out → worker → deterministic merge; report and section fragments have separate ownership checks.
•	src/wellplot/agent/code_mode/worker_contracts.py: SectionWorkContract, source facts, track/binding requirements and deterministic action selection. At current checkpoint an existing section with exactly one requested track selects add_track; multiple tracks select reconstruct.
•	src/wellplot/agent/code_mode/typed_section_worker.py: worker submits section_work_contract, section_task, section_context, original request, and an action-specific example to a structured-output model; validates before lowering.
•	src/wellplot/agent/code_mode/canonical_workers.py: report worker already generates sparse report semantics, demonstrating the desired pattern.
•	src/wellplot/agent/code_mode/semantic_actions.py and semantic_section_compiler.py: typed section actions lower to host authoring intent. ReconstructSectionAction can lower against an existing section, though its semantics are easily misinterpreted as full-document replacement.
•	src/wellplot/model/intent.py: AuthoringDocumentIntent is explicitly provider-neutral partial desired state, with omission/set/clear/remove semantics.
•	src/wellplot/authoring_reconciler.py: typed operation phases REPORT, SECTIONS, TRACKS, BINDINGS, CONTENT, PRESENTATION, FINALIZE; typed CREATE/UPDATE/REMOVE/MOVE, dependencies, and readiness issues.
•	src/wellplot/authoring_executor.py, authoring_service.py: operation execution, preconditions, read-after-write checks, copy-validate-publish object mutations.
•	src/wellplot/agent/direct_notebook.py: private candidate document, reconciliation, execution, validation, obligation/preservation verification, then persistence.
•	src/wellplot/logfile.py: canonical YAML loading, template expansion, source resolution, validation.
•	examples/cbl_main.log.yaml: real persisted document has document.layout.log_sections[].tracks plus document.bindings.channels, among other fields. Do not require the model to emit this complete YAML.
1.2 D5 binding smoke 002: precise failure
•	Campaign: d5-binding-smoke-6f0ef73d-002; exact checkpoint above; accepted Qwen runtime, readiness pass; one planner call and one section-worker call.
•	Requested: append Bond Index (BI) and Gamma Ray (GR_STGC) to existing Main Log while preserving six existing tracks.
•	Deterministic work contract required exactly two track handles: bond_index, gamma_ray.
•	Worker produced a schema-valid eight-track response containing those two plus the six existing tracks (depth, cbl, vdl, gr, cali, rt), as established by the recorded handle mismatch evidence. No semantic lowering occurred.
•	Failure: TRACK_HANDLE_SET_MISMATCH; terminal SMOKE_CONTRACT_FAIL; no scientific population started, zero C02 exposure.
•	The returned full DTO bytes are separately referenced by the smoke custody ledger. The artifact was not among the supplied chat files. Therefore, the full binding/style payload has not been independently inspected here. Do not claim its detailed fields were correct.
•	Attribution: incorrect/ambiguous model-facing action semantics plus mismatch with deterministic cardinality; cannot label this solely as model incompetence. Do not loosen the two-track validator or re-run sealed smoke.
1.3 Existing authoritative constraints
Design work must bootstrap, in order, from:
1.	AGENTS.md;
2.	docs/project-decision-protocol.md;
3.	docs/agent-code-mode-current-baseline.md;
4.	relevant canonical source/tests/accepted ADRs;
5.	this candidate, only after checking it against the live baseline.
Preserve baseline K-01 single engine; K-02 model/host ownership; K-03 schema validity ≠ semantic correctness; K-04 deterministic safety ≠ semantic repair; K-05 immutable evidence; K-06 live smoke gate; K-07 canonical persistent runtime. Preserve R-01 through R-08 and their regressions, especially request-span obligation tracking, provider schema parity, source inspection states, bounded correction, causal negative grading, and one canonical repair protocol.
________________________________________
2. Target behaviors and non-goals
2.1 Positive requirements
T-01. A scientist may mix header/report/remarks and multiple log-section edits in one natural-language request.
T-02. The planner identifies domain scopes, targets, semantic operation intents, conditional clauses, and explicit presentation/order constraints.
T-03. A worker cannot autonomously expand its authorized operation set, even when shown the entire original request.
T-04. The host supplies a consistent, bounded snapshot of existing YAML document structure and inspected source channel inventory.
T-05. A worker may ask additional read-only, scope-limited questions when supplied context is insufficient; tools are host-mediated, not file/system shell access.
T-06. Only the host resolves stable canonical IDs, available source paths, object identity, match/duplicate policy, authoritative dependencies, and mutation.
T-07. Each operation has machine-verifiable expected effect, preconditions, typed payload constraints, and provenance back to the scientist's instruction.
T-08. Independent work can be prepared concurrently, but order-sensitive or state-dependent work uses explicit dependencies.
T-09. All changes are staged and verified as one request-level transaction; failures do not partially publish the well log.
T-10. Host writes schema-valid canonical YAML and demonstrates reload/inspect/render compatibility.
T-11. Model generation is bounded, auditable, and not automatically retried beyond accepted correction protocol.
T-12. Existing behavior outside the requested scope is preserved, including report fields, unrelated sections, tracks, bindings, styles, and scientific measurements.
2.2 Explicit non-goals
•	No replacement for the existing YAML authoring schema, AuthoringService, reconciler, or executor.
•	No new generic agent that calls create_track/update_binding directly.
•	No model-written full YAML document, canonical IDs, filesystem paths, program code, or command execution.
•	No separate “test-only” semantic engine, planner, or special smoke routing.
•	No model hallucination of LAS channels, file availability, tool descriptions, measured values, or physical units.
•	No automatic conflict resolution that changes user meaning; no inferred CREATE from an explicit UPDATE or vice versa.
•	No mandatory LLM call per track or mutation. Worker grouping is an efficiency choice, not execution authority.
•	No reliance on current D5 smoke success to establish scientific performance; this redesign requires new qualification.
________________________________________
3. Target end-to-end architecture and exact ownership
flowchart TD
 A[Scientist NL request] --> B[Planner: semantic scope + operation inventory]
 B --> C[Host: verify requirement coverage and capabilities]
 C --> D[Host: snapshot YAML and inspected sources]
 D --> E[Host: ground target handles and compile scoped work contracts]
 E --> R[Report semantic worker]
 E --> S[Section semantic worker per independent section scope]
 D -. bounded read-only snapshot queries .-> R
 D -. bounded read-only snapshot queries .-> S
 R --> V[Typed sparse report patch]
 S --> W[Typed sparse section patch]
 V --> F[Validate operation identity, scope, values, provenance]
 W --> F
 F --> L[One canonical semantic lowerer to AuthoringDocumentIntent]
 L --> G[Merge intents and verify complete semantic coverage]
 G --> H[Existing reconcile_authoring]
 H --> I[Existing AuthoringExecutor on private document]
 I --> J[Final obligations, preservation, schema checks]
 J --> K{All pass?}
 K -->|No| X[No publication; bounded diagnostic]
 K -->|Yes| Y[Persist canonical YAML; reload/render validation]
3.1 Responsibility matrix (authoritative proposed interfaces)
Layer	Inputs	Owns	Outputs	Forbidden
Planner/LLM	NL request, safe document summary, static capability registry	Domain separation; semantic operation intent; target clues; optionality; user order	Versioned semantic plan	Canonical IDs, source paths, CRUD calls, mutation
Obligation compiler/host	Original NL, plan, exact request spans	Independent requirement coverage, contradictions, evidence references	Verified obligation ledger	Silent invented facts or planner omissions
Snapshot + inspection/host	Canonical document, declared source assets	Current snapshot, source inspection state, approved handles	Read-only context + provenance	Letting provider read arbitrary files
Operation contract compiler/host	Verified plan, obligations, snapshot	Allowed op IDs/types/counts, target bindings, conditions, allowed fields	Immutable versioned worker contracts	Changing user intent implicitly
Report worker/LLM	Only report contract, report context	Semantic values and prose for authorized report operations	Report-only typed sparse patch	Section mutations, canonical IDs
Section worker/LLM	One section contract, inspected channel/object facts	Typed track/binding/scale/style semantics for authorized operations	Section-only typed sparse patch	Full YAML, unrequested state, cross-section writes
Semantic validator/host	Worker patch + frozen contract	Completeness, schema, allowed op identity, source/target references, correction boundaries	Accepted or rejected semantic patch	“Repairing” scientific intent by guessing
Lowerer/host	Accepted patches, snapshot, identity allocator	One canonical AuthoringDocumentIntent	Desired-state intent fragments	Side effects
Reconciler/host	Merged intent + canonical document	CRUD phases, dependency graph, moves, no-ops, preconditions	Existing AuthoringReconciliationPlan	LLM calls
Executor/host	Reconciliation plan	Private CRUD execution and verification	Candidate document	Partial public publication
Persistence/host	Fully accepted document	Canonical YAML serialization/reload/render	Updated logfile + evidence	Model-authored file text
3.2 Preserve two ordering domains
•	Semantic/presentation order: e.g., resistivity track visually immediately after depth; header remark appears on first page; multi-curve order deepest-to-shallowest if requested. This is a planner-proposed constraint derived from user language.
•	Execution/dependency order: create section before track; create track before binding; bind before certain presentation operations. This is computed and enforced by the host.
•	Independent report and section tasks may be evaluated in parallel on one immutable snapshot. They do not independently persist or mutate the canonical document. A state-dependent second stage must be explicitly scheduled against a staged new snapshot, not accidental stale context.
________________________________________
4. Contract A: planner output (candidate V2)
4.1 Plan shape
The existing SemanticPlan has one report_task and an ordered section_tasks collection. Preserve these groups, but propose additive fields (or a versioned successor) for typed semantic-operation inventory. Do not create one SectionTask for every requested track: retain one scope per independently addressable section.
Illustrative model-facing plan (not yet executable and not the current Python model):
{
  "version": "wellplot.semantic-plan.v2-candidate",
  "report_task": {
    "operations": [
      {"local_ref":"r1","verb":"SET_HEADER_FIELD","target_clue":"Company","value":"University of Utah"},
      {"local_ref":"r2","verb":"ADD_REMARK","target_clue":"first page","content_requirements":["open-hole quicklook", "user-supplied LAS", "source-inspected channels only", "iterative interpretation, not vendor-issued"]}
    ]
  },
  "section_tasks": [{
    "target_clue":"Main Log",
    "target_intent":"CREATE_SECTION_OR_REPORT_CONFLICT",
    "operations":[
      {"local_ref":"s1","verb":"CREATE_SECTION","target_clue":"Main Log"},
      {"local_ref":"s2","verb":"ADD_TRACK","semantic_ref":"gr_overview","channel_clues":["GR"],"constraints":{"scale":"linear","minimum":0,"maximum":150,"color_family":"green"}},
      {"local_ref":"s3","verb":"ADD_CONDITIONAL_BINDING","parent_ref":"gr_overview","channel_clues":["SP"],"when":"source-inspected available","constraints":{"minimum":-80,"maximum":20}},
      {"local_ref":"s4","verb":"ADD_TRACK","semantic_ref":"resistivity","channel_role_clues":["deep","medium","shallow"],"constraints":{"scale":"logarithmic","minimum":0.2,"maximum":2000,"unit":"ohm.m","deepest_emphasis":true}}
    ],
    "presentation_constraints":[{"relation":"after","item_ref":"s4","anchor_clue":"depth track"}]
  }]
}
IMPORTANT: This example is intentionally not canonical and exposes unresolved questions. It must not be implemented verbatim. In particular, CREATE_SECTION_OR_REPORT_CONFLICT is a diagnostic placeholder showing that a request to create a section needs a known starting document mode. The exact GR and SP track grouping is ambiguous; do not prematurely choose one versus two visual tracks. The example omits some header fields only to be readable; the actual compiled plan must cover all requested values.
4.2 Minimum required planner-operation fields
Define each operation with:
1.	Version + discriminated verb from a registered capability/operation family.
2.	Request-local local_ref unique within a request (host verifies uniqueness; not a canonical document ID).
3.	Scope (report or one section scope), no cross-scope mutation.
4.	Intended object type and target clue/role; section report targets must be distinguishable.
5.	Change semantics: CREATE, UPDATE, REMOVE, MOVE, ENSURE, SET, or supported domain action, with exact meaning and conflict policy.
6.	Typed explicit field requirements and optional qualitative constraints.
7.	Conditional clause, if any, with required evidence type: inspected source availability is different from unspecified or uninspected.
8.	User ordering/position constraint if explicitly requested.
9.	Original instruction provenance pointer or independently reconstructed request-span references (host-owned final authority).
10.	Any unresolved semantic ambiguity; do not invent unsupported operation types.
4.3 Planner validation
•	Independently compare plan to canonical request-obligation ledger; require full requested coverage for supported vocabulary.
•	Reject duplicate/conflicting local references, duplicate section scopes, invalid capability parentage, unsupported verbs, invalid report/section ownership, or contradictory condition semantics.
•	Do not infer document IDs from titles. Main Log is a natural-language target clue until grounded.
•	Prevent operation type drift: ADD_TRACK cannot become RECONSTRUCT_SECTION due to batch size.
•	For an existing section, CREATE_SECTION must be reconciled with explicit user wording and project mode; reject or ask for clarification if truly incompatible.
•	Preserve optionality of source-dependent curves and quantitative numeric values exactly.
•	Planner list order encodes user presentation preference only when supported by request provenance; list order alone does not authorize mutation order.
•	Preserve accepted provider/schema/Python parity, required revision discriminator, and capability closure regressions.
________________________________________
5. Contract B: bounded, read-only inspection
5.1 Principle
The worker must know the current state, but direct worker file access or CRUD is unnecessary. The host provides an immutable, versioned document/source snapshot and optional bounded query endpoints. Reuse existing AuthoringInspectionFacade, AuthoringService.list/get, SemanticEnricher, and LogfileSourceLoader as underlying capabilities; these are not new storage engines.
5.2 Proposed inspection methods (names are candidate interfaces)
Proposed read method	Required request	Returned facts	Guard
get_document_summary	snapshot token	report title, section handles, revision inventory, scoped counts	No full YAML or local paths
list_sections	snapshot token	opaque handles, titles, subtitles, kind	No writes
inspect_section	section handle	section title, kind, source identity handle, ordered track inventory	One authorized section only
list_tracks	section handle	track handles, order, title, kind, width, relevant style	Bounded count
inspect_track	track handle	bindings, scales, styles, position, optional cross-reference roles	Scope-limited
list_bindings	track handle	bound channel, binding kind, scale, style, display label	No raw samples
list_sources	snapshot token	approved source handles, format, inspected/not_inspected/unavailable, digest identity where available	Approved inputs only
inspect_source	source handle	inspection state, source format, available channel count, approved metadata	No arbitrary paths
list_channels	source handle	mnemonic, kind, units, shape, aliases, description where inspected	Paginated/filtered and bounded
resolve_channel_candidates	approved source handle + role clue	exact/alias candidate list and evidence; may yield ambiguity	Host performs actual identity resolution
get_capability_contract	registered capability ID	supported typed fields, valid enum/ranges, ownership	Static registry-derived
5.3 Inspection rules
•	Every result includes snapshot_id, source_inspection_state, relevant object handle(s), and a bounded provenance token; never leak full paths, API keys, unneeded file data, or raw large LAS/DLIS samples.
•	Existing caller-supplied source inventory is a first-class input; no global disk search for *.las.
•	not_inspected and unavailable are not equivalent to inspected and absent. Conditional omission is legal only after an inspected, authoritative inventory shows the channel absent (or an explicit user-approved fallback policy applies).
•	Exact channel name, alias, unit, measurement family, and curve-role inference must remain distinguishable; GR and GR_STGC, or RDEP and RT, are not automatically interchangeable.
•	Only expose source handles already approved for the request. Source resolution, byte identity, and allowed-root constraints are host responsibilities.
•	Default to host-prefetched contextual inventory. Offer tool querying only when an evidence sufficiency check finds missing facts. Do not require model re-query for facts already included.
•	Tools are read-only, bounded by per-worker request budget (specific caps chosen and tested in design slice), size limit, time limit, no nested arbitrary query language, no network/filesystem access, and no callback that can mutate the document.
•	Treat LAS/DLIS descriptions and YAML free text as untrusted data, not executable model instructions. Screen/escape tool response material and prevent tool-result prompt injection.
•	Independent workers share an immutable snapshot token. Before commit, host checks snapshot is still current; stale snapshot → revalidate/replan from fresh snapshot, never silently write over outside edits.
•	On consecutive dependent stages, host may create an explicit staged snapshot; prior workers remain bound to their earlier immutable snapshot.
5.4 No unbounded tool loop
Do not implement a general ReAct loop. Use a small, finite inspection→semantic-response process with a declared maximum of reads, correction attempts, and total bytes, and report INSPECTION_BUDGET_EXCEEDED or INSPECTION_INSUFFICIENT when necessary. Use one existing canonical provider adapter and the accepted correction protocol; additional tool functionality must not become an alternate agent executor.
________________________________________
6. Contract C: immutable host-generated work contract
6.1 Required contract contents
A WorkerOperationContract (illustrative name) is compiled from the verified semantic plan, request obligations, source/document snapshot and registered capability schemas. Include:
•	Version; immutable request hash; scope key; snapshot ID and source identity digests.
•	Enumerated allowed operation IDs (stable request-local host identifiers) and exact operation types.
•	Required count; permitted conditional count variation only when tied to specific verified source facts.
•	Target type and unique grounded opaque target handle (or exact new-object placeholder); forbidden target ambiguity.
•	Each operation's permitted fields and authoritative values; forbidden additional objects and modifications.
•	Required channel/role candidates with inspection evidence; exact numeric bounds, units, style constraints, and source ownership.
•	Existing state to preserve, expressed as host preservation obligations rather than content that the model should re-emit.
•	User ordering constraints; host-computed dependency preconditions; duplicate and idempotence policy.
•	Allowed patch shapes and schema hash; correction/observability policy and explicit failure taxonomy.
6.2 Worker response contract (illustrative)
{
  "contract_version": "wellplot.section-patch.v1-candidate",
  "scope_ref": "section-main-log",
  "operations": [
    {
      "operation_ref": "op-add-bond-index",
      "type": "ADD_TRACK",
      "track": {
        "semantic_ref": "bond_index",
        "title": "Bond Index",
        "kind": "normal",
        "width_mm": 34,
        "bindings": [
          {
            "semantic_ref": "bond_index.binding.1",
            "channel": "BI",
            "label": "Bond Index",
            "scale": {"kind":"linear","minimum":0,"maximum":1},
            "style": {"color":"#111111","line_width":0.8}
          }
        ]
      }
    },
    {
      "operation_ref": "op-add-gamma-ray",
      "type": "ADD_TRACK",
      "track": {
        "semantic_ref": "gamma_ray",
        "title": "Gamma Ray",
        "kind": "normal",
        "width_mm": 26,
        "bindings": [
          {
            "semantic_ref": "gamma_ray.binding.1",
            "channel": "GR_STGC",
            "label": "Gamma Ray",
            "scale": {"kind":"linear","minimum":0,"maximum":150},
            "style": {"color":"#16a34a","line_width":0.8}
          }
        ]
      }
    }
  ]
}
This is a proposed worker JSON response. It is not the canonical YAML, is not current code, and is not a CRUD execution file. The host maps it to existing authoring-intent models. Canonical track/binding IDs are assigned only by the host.
6.3 Validation invariants
•	Exact operation-ID multiset equality (including duplicate detection), allowing only explicitly evaluated conditional exceptions.
•	Exact semantic action type equality; no ADD→RECONSTRUCT coercion; no unauthorized REMOVE, UPDATE, MOVE.
•	Target scope equality; no extra section, report, or unrelated object properties.
•	Required field coverage, exact numeric/string requirements, permitted enums/types, required binding handle ownership, unique semantic refs.
•	Exact channel exists in inspected approved source inventory; scalar/array kind matches the requested binding.
•	New track identity cannot silently alias a current track unless an explicitly permitted ENSURE policy applies.
•	Existing-object update target resolves uniquely and still matches snapshot; otherwise reject.
•	Host owns preservation: worker need not regenerate unchanged tracks, header slots, or bindings.
•	Schema errors, contract errors, grounding errors, lowering errors, and execution errors remain separate terminal classes.
•	Schema/validator/example/test must agree about the operation count and whether tracks means changed tracks or all tracks.
6.4 Correction policy
One canonical correction mechanism only, respecting already accepted ValidationIssueSet → RepairContract → correction → _verify_repair_candidate() lineage. Any allowed correction must be scoped to exact invalid fields/operations, preserve all valid sibling operations, retain the original request and snapshot, and not widen scope. Host-grounding failures fail closed, not repaired by another model-generated identity. No silent schema coercion or response rewriting that hides a scientific mismatch.
________________________________________
7. Mapping semantic patches into the existing deterministic engine
7.1 Host-only conversion pipeline
Validated worker JSON patch
  -> one deterministic patch lowerer / adapter
  -> AuthoringDocumentIntent (partial desired state)
  -> merge_v2_intents (respecting distinct section/report ownership)
  -> reconcile_authoring(existing=canonical_snapshot)
  -> AuthoringReconciliationPlan (CREATE/UPDATE/REMOVE/MOVE, phases, dependencies)
  -> execute_authoring_plan(private AuthoringService)
  -> verify_document_obligations + verify_document_preservation
  -> canonical schema validation
  -> persist_authoring_document -> reload -> render verification
Keep conversion into AuthoringDocumentIntent inside the existing canonical lowering path. A new versioned semantic patch DTO may be necessary, but it must not become a competing authoring IR or a separate executor.
7.2 Atomicity and grouped calls
•	One worker call may emit a bounded sequence of semantic operations for a single section/report scope.
•	Each semantic operation is independently identified and independently validated.
•	Host produces an authoritative DAG of CRUD operations; planned list order is not execution authority.
•	Create section → create track → create binding → set scale/style and presentation is an example dependency chain. Use actual reconciler phases rather than a second hand-rolled scheduler.
•	All operations execute on a private copy. An individual AuthoringService._commit() validates each mutation; request-level atomic publication is a separate final gate after the entire operation plan succeeds. Never interpret per-operation atomicity as a guarantee of all-or-nothing publication without the private candidate path.
•	Do not persist intermediate worker outputs or partially successful document revisions.
7.3 Define these operation semantics unambiguously
Semantic verb	Required precondition	Intended outcome	Conflict behavior
CREATE_SECTION	Target section absent or explicit new-identity request	New section with host ID	Existing same-target section → conflict; no silent update
CREATE_TRACK / ADD_TRACK	Parent section exists in staged plan; duplicate policy satisfied	One new track	Existing matching track → require distinct-add authorization or reject
UPDATE_TRACK	Unique existing track	Change only specified fields	Missing/multiple target → reject
ENSURE_TRACK	Unique grounded target or clear absence	Create if absent, no-op/update only as defined by explicit ensure policy	Ambiguous duplicates → reject
CREATE_BINDING	Track exists; source channel inspected; binding absent as required	New channel binding	Existing identical binding → conflict/no-op only under explicit policy
UPDATE_BINDING	Unique existing binding	Change specified properties, preserve others	Missing target → reject
MOVE_TRACK	Track and anchor exist; ordering constraints consistent	Update track ordering	Absent/ambiguous anchor → reject
SET_HEADER_FIELD	Header slot exists and correct slot group	Update one field	Unknown/ambiguous slot → unresolved or reject
ADD_REMARK	Report/first-page semantics supported	One new remark with host ID	No duplicate from replays; scope guard
REMOVE_* / CLEAR_*	Explicit removal/clear intent and grounded target	Delete/clear exactly designated object	Never inferred from omission
Prefer the smallest set of semantic verbs mapping cleanly onto existing intent constructs. Do not add “domain macro” verbs such as ADD_RESISTIVITY_TRACK when ordinary track+binding+scale+style constraints suffice; “resistivity” is a semantic role, not a second engine operation.
7.4 Section construction and subsequent CRUD
For an actually new section: the host must create the section (and any schema-required shell fields) before child CRUD. For an existing section: emit a sparse change, never an unsolicited full replacement. Preserve the accepted AuthoringDocumentIntent omission semantics, including explicit clear/remove markers. Exact YAML serialization remains host-owned.
________________________________________
8. Scientific/source interpretation rules
8.1 Source inspection three-way (or more) logic
Evidence	SP conditional action	Required GR action
Source inspected, SP present	Include SP with explicit scale	Include GR only if inspected present
Source inspected, SP absent	Omit SP; record conditional fallback	Include GR if present
Source not_inspected	Do not pretend SP absent; inspect or block	Block required GR until confirmed
Source unavailable	Do not pretend SP absent	Block required GR
Multiple source candidates	Host resolves exact authorized source or blocks	Do not guess one
SP present with incompatible data kind	Binding/semantic conflict, not ordinary absence	Separate scientific diagnostic
8.2 Resistivity roles
•	“Deep, medium, shallow resistivity curves that are available” defines optional role-based selection among inspected source channels. Do not invent missing roles or aliases.
•	Preserve actual channel mnemonic, unit and sample kind. Never assert that RDEP, RMED, RSHAL are present without inspecting the selected source.
•	Role inference must use grounded metadata, aliases, units, and approved domain rules. Ambiguous candidates must remain unresolved; no arbitrary “first available” substitution.
•	Logarithmic scale 0.2–2000 ohm.m requires supported positive range, compatible source units or explicit unit policy; do not assume numerical conversion absent an approved unit conversion.
•	“Deepest visually strongest” requires a registered, testable style policy or bounded model-proposed mapping within supported style vocabulary. Unspecified emphasis defaults are not scientific truth.
8.3 Heading/report semantics
•	Company, well, field, county, state, location, section/township/range, footage, latitude and longitude are provided textual values, not inferred source facts. Verify exact destination slot coverage; never invent absent slots.
•	The listed log/service names may map to one or multiple header fields, depending on actual template. Preserve individual entries and their order if the destination contract requires it; do not invent a canonical field mapping.
•	Report title/subtitle are not generic header slots. Reuse current report boundary protections.
•	A “first-page remarks block” must be supported by the report page/remark model and placement logic; do not claim precise page layout without a render check.
•	“Open-hole quicklook built from a user-supplied LAS” is remarks text requested by the scientist, not evidence that CBL/VDL are or are not open-hole measurements; preserve requested phrasing and any contradictions as user-provided context.
8.4 Ambiguity in the FORGE prompt
The instruction “create the main log section with a GR and SP track” does not unambiguously say one shared GR/SP track or two separate tracks. The task compiler must either follow a documented domain default with verified provenance, or surface a targeted ambiguity; do not turn this into a hidden deterministic choice. The instruction “add one resistivity track after the depth track” requires a depth anchor that must exist or be explicitly added. It cannot be assumed simply because the scientist mentioned it.
________________________________________
9. Example end-to-end walkthroughs
9.1 Historical two-track binding smoke (positive example)
Request: Add Bond Index (BI) and Gamma Ray (GR_STGC) to existing Main Log; preserve six existing tracks.
flowchart TD
 A[Planner: one Main Log section task] --> B[Two ADD_TRACK semantic operations]
 B --> C[Host: confirm Main Log existing + source channels inspected]
 C --> D[One section-worker call: EXACT two track patches]
 D --> E{Valid op refs / fields / channel grounding?}
 E -->|No| X[Fail no lowering]
 E -->|Yes| F[Lower to sparse AuthoringDocumentIntent]
 F --> G[Reconcile to CREATE tracks + bindings]
 G --> H[Execute privately; verify six existing unchanged]
 H --> I[Publish eight-track Main Log]
Acceptance: one scoped worker result with exactly bond_index and gamma_ray; zero existing-track restatements; final Main Log has eight tracks and unchanged six original track/binding records, unchanged unrelated sections and report. A DTO with the six preserved existing handles must fail at semantic contract validation even if its final count is eight.
9.2 FORGE mixed report + section prompt
Original request categories:
•	Report header: service lines Cement Bond Log, Variable Density Log, Gamma Ray - CCL; company University of Utah; well FORGE 16B (78)-32; field Utah Forge; county Beaver; state Utah; section NWSW 32; township 26; range 9; footage 972' FSL & 523' FWL; latitude 38.501242; longitude -112.882661.
•	Report remarks: one concise first-page block including user-supplied LAS, open-hole quicklook, only source-confirmed curves, iterative/non-vendor-original status.
•	Main Log: GR overview 0–150 linear green; conditional SP −80–20; resistivity track immediately after depth; 0.2–2000 ohm.m log; available deep/medium/shallow curves, strongest deep presentation.
Required planner output: one report task with all report facts plus one Main Log section task with typed, conditional operations and presentation constraints. No headless report/section confusion.
Required host preflight: match header slots and document target mode; identify available inspected source and exact channel inventory; establish whether depth track exists; resolve GR/SP grouping ambiguity; inspect resistivity roles; record absent/unavailable separately.
Proposed worker grouping: one bounded report-worker call; one bounded Main Log section-worker call, provided all mandatory decisions are grounded. Independent calls may proceed concurrently from a consistent snapshot. If source inspection or a user clarification is needed, defer only dependent operations; do not publish partial results.
Required final: header and remarks in their correct slots, main-log tracks created only as resolved, correct scales/ordering, no fictional channels, YAML reload and rendered visual check. This example is not runnable gold until the target template, approved LAS inventory, source identities and ambiguous GR/SP grouping are explicitly frozen.
________________________________________
10. Security, integrity, diagnostics, and performance requirements
10.1 Immutable provenance
•	Bind original request text, UTF-8 digest, exact request-span ledger, planner schema/prompt versions and hashes, inventory snapshot ID, inspected source identities, worker input/output hashes, contract hashes, and decision outcomes.
•	Preserve original user wording for numeric ranges/units and source-dependent conditions.
•	Snapshot identity must bind both document version/hash and the declared source inventory, not just a section title.
•	Reconcile/execute only when input snapshot equals the expected current revision; on conflict, no publication.
10.2 Failure taxonomy (candidate extensions)
Diagnostic class	Example	Required behavior
PLANNER_COVERAGE_INCOMPLETE	Company field omitted	Fail before workers
PLANNER_OPERATION_UNSUPPORTED	Unknown verb	Explicit unresolved/fail
TARGET_AMBIGUOUS	Two Main Log sections	Fail; do not guess
SOURCE_NOT_INSPECTED	SP availability unknown	Inspect or block; not “absent”
SOURCE_UNAVAILABLE	Missing LAS	Fail required channel work
CHANNEL_AMBIGUOUS	Multiple deep candidates	Fail role selection or request clarification
CONDITIONAL_OMISSION_VALID	SP inspected absent	Record allowed omission, continue
WORKER_OPERATION_SET_MISMATCH	Two expected, eight returned	Fail before lowering
WORKER_SCOPE_VIOLATION	Section worker changes report title	Fail
WORKER_SEMANTIC_MISMATCH	SP scale 0–100 instead of −80–20	Fail / approved bounded correction
SCHEMA_VALIDATION_FAILURE	Wrong response type	Fail/schema corrective only under existing policy
SNAPSHOT_STALE	YAML modified since inspection	Fail before execution or recompile under fresh authority
RECONCILIATION_CONFLICT	Add existing track without duplicate permission	Fail with exact object scope
EXECUTION_PRECONDITION_FAILURE	Source binding target vanished	No final publication
PRESERVATION_FAILURE	Existing CBL track changed	No final publication
PERSISTENCE_RELOAD_FAILURE	YAML fails reload after write	No successful completion claim; restore/recover via accepted atomic persistence policy
Use established diagnostic names where possible; mapping above is an illustrative taxonomy, not an instruction to introduce every new literal code. Record stage, owner, failure class, and whether any authoritative state changed.
10.3 Security boundaries
•	Read-only inspection applies least privilege, request scope, path confinement, safe opaque handles, no secrets/logfile binary content by default.
•	Tool results, labels and descriptions are untrusted text. Do not obey instructions embedded in LAS metadata or document titles.
•	Model output is an untrusted proposal; strict Pydantic/schema validation and independent obligation verification are mandatory.
•	Worker correction must not expand allowed operation IDs or bypass source and scope restrictions.
•	No client or model gets AuthoringService mutation method handles.
•	Ensure original credential source and production config remain unchanged; no new environment variable/provider adapter to route this work.
10.4 Limits and observability
Define and freeze measurable limits before qualification for: maximum plan operations, per-section patch operations, worker context bytes, inspected channels, read-only tool calls, response tokens, correction rounds, worker timeout and private evidence size. Do not invent numeric production defaults without a compatibility review. Use bounded refusal with diagnostics, never silent truncation of essential requirements.
Capture (privately) a stage trace of planner coverage, snapshot, grounding, operation contract, worker schema and semantic validation, intent lowering, reconciliation, CRUD phases, preservation, persistence and reload/render. Continue existing D5 full-DTO optional capture protections (0700/0600, authorization-bound, secure retention and deletion). Do not add unconditional raw provider-body retention.
________________________________________
11. Migration strategy and minimum atomic implementation slices
Policy: Keep each slice independently reviewable with one purpose, its own development-memory record, exact code/test paths, a provider-free acceptance report, and any relevant active-baseline/roadmap/backlog delta. This document is design-only; executable changes require an accepted ADR and authorization at meaningful design and implementation gates, not separate Human approvals for every internal step. Exact frozen smoke/scientific authority remains separate.
Slice A00 — Architecture decision and invariant map (P0, design gate)
Task atoms:
1.	Read AGENTS.md, project decision protocol, current active baseline, accepted relevant ADRs, D5 single-engine inventory, D5 smoke 002 evidence and source.
2.	Record the original NLP-over-YAML product intent and the exact scope/ownership change being proposed.
3.	Inventory all existing paths that create, validate, serialize or apply report/section changes; classify KEEP, ADAPT, REPLACE, RETIRED, NOT_RELEVANT.
4.	Map each baseline K/R invariant to its new contract and provider-free test.
5.	Produce a decision record: planner operation inventory, bounded read-only inspection, worker patch vocabulary, unchanged canonical CRUD, single-engine promise.
6.	State every genuinely open semantic question (section create-vs-revise, GR/SP grouping, conditional absence, duplicate policy, style policy, staged-state dependency).
7.	Independently review the ADR and decide KEEP/ADAPT/REPLACE/REOPEN for restrictions it changes.
8.	Record accepted Knowledge Delta and update active baseline only after architecture acceptance.
Acceptance: one accepted architecture direction; no competing engine; unchanged live authority; exact affected baseline clauses identified. Do not implement before this gate.
Slice A01 — Golden behavior and test fixtures (P0, provider-free)
1.	Build synthetic existing six-track Main Log with an unrelated section and populated report fields.
2.	Build synthetic new-document and existing-section FORGE-shaped fixtures; controlled LAS inventories: GR+SP+deep/medium/shallow; GR/no-SP; uninspected; unavailable; ambiguous resistivity.
3.	Freeze expected semantic operation inventories separately from expected final YAML/model state.
4.	Include positive two-track sparse patch, eight-track invalid response, duplicate handle, invalid channel, changed existing-track negative.
5.	Include mixed report+section, missing header slot, exact requested numbers, first-page remark, tracking optional SP omission.
6.	Add fixture cases for existing target, absent target, duplicate targets, reordered tracks, duplicate GR existing track, same mnemonic different sources.
7.	Distinguish model-contract gold from host CRUD-operation gold, and gold from rendered visual evidence.
8.	Record fixture hashes, no provider calls, and required assets; never embed private LAS bytes.
Acceptance: golden expectations documented, self-consistent, and not hard-coded by implementation; no live calls.
Slice A02 — Planner V2 semantic-operation inventory (P0)
1.	Create versioned proposed planner schema under existing planner.py module or a tightly owned adjunct model; do not create new planner runtime.
2.	Add discriminated semantic verbs, request-local refs, scopes, conditional clauses, presentation-order constraints, unresolved semantics.
3.	Keep one report scope and one section task per distinct section; permit many operations within each.
4.	Explicitly distinguish CREATE, UPDATE, ENSURE, MOVE, REMOVE and SET semantics.
5.	Version planner prompt and structured provider schema; remove only accepted incompatible prohibition on semantic operation inventory.
6.	Preserve capability registry closure and required revision target fields; update provider-side requiredness checks.
7.	Adapt independent request-obligation coverage ledger to operations; exact numbers/units/scope must survive.
8.	Add planner tests: 2-track existing, FORGE mixed, one vs multiple sections, 20-track batch, missing operation, duplicate local ref, unsupported verb.
9.	Assert no canonical IDs, file paths, SDK commands or CRUD scripts in planner model output.
10.	Compare schema hash and Python/decoder parity; update baseline mapping.
Acceptance: planner proposes explicit operation types; does not collapse multi-add into reconstruct; no coverage regression.
Slice A03 — Snapshot and inspection contract (P0)
1.	Define immutable DocumentInspectionSnapshot or equivalent host-owned projection including canonical document revision, source identities and inspection states.
2.	Reuse existing AuthoringInspectionFacade, source loader, AuthoringService.list/get, SemanticEnricher; do not duplicate loaders.
3.	Add/extend safe projections for sections, tracks, bindings, ordering, scales/styles, header slots and source-channel metadata.
4.	Introduce opaque handles and host mapping to canonical identities; prevent model-supplied canonical paths/IDs.
5.	Define consistent snapshot semantics across parallel worker tasks.
6.	Add source inspected, not_inspected, unavailable, inspected-empty and multi-source negative tests.
7.	Implement optional bounded read-only worker queries only where prefetch is insufficient; no general shell, mutation calls, or unbounded loops.
8.	Add stale-snapshot and injected-LAS-description tests; prove no writes from inspection.
9.	Record budget/size limits and deterministic denial diagnostics.
Acceptance: workers can obtain all needed facts without modifying source/document; calls cannot escape authorized scope.
Slice A04 — Host operation-contract compiler (P0)
1.	Refactor build_section_work_contract() (or versioned compatible successor) to preserve semantic-operation types rather than selecting reconstruct by requested track count.
2.	Define operation IDs, exact permitted operation set, scope, target handles, conditional evidence, allowed fields, preservation rules, schema hash, ordering constraints.
3.	Add report-operation contract projection where appropriate without duplicating existing report worker validation.
4.	Explicitly distinguish new-section construction from existing-section sparse edits.
5.	Resolve target/source identities host-side, with exact-match and ambiguity diagnostics.
6.	Evaluate SP if available from inspected source facts; classify unknown/unavailable/absent distinctly.
7.	Enforce original request coverage, target ownership and no-op/duplicate rules.
8.	Define revalidation before lowering and before transaction commit.
9.	Add positive/negative provider-free contract tests including two vs eight tracks and exact value preservation.
Acceptance: multi-track addition produces ADD_TRACK × N (or equivalently typed additive patch), never reconstruct solely because N>1.
Slice A05 — Section worker: constrained sparse patch output (P0)
1.	Evolve CanonicalSectionWorker in place; no duplicate worker or side route.
2.	Make worker inputs one immutable operation contract + allowed source/target facts + supporting scoped instruction text.
3.	Replace ambiguous reconstruction-for-existing-add example with exact sparse patch semantics; retain legitimate new-section/replacement support.
4.	Emit only allowed operation refs, types, and fields; enforce exact multiset and no extra existing tracks.
5.	Support bounded multi-operation output from one provider call; preserve independent per-operation validation and diagnostics.
6.	Keep request-local semantic refs separate from canonical IDs.
7.	Preserve current accepted normalization/grounding, requirement application, and one correction protocol where applicable.
8.	Adapt capture and mismatch diagnostics to distinguish operation-set, track-set, binding-set, scope, field, and conditional failures.
9.	Add provider-free schema/Python parity tests and synthetic negative DTOs.
10.	Verify D5 single-engine reachability and no new implicit retries.
Acceptance: two requested tracks → exactly two semantic additions; an eight-track full reconstruction fails at contract boundary; correct patch lowers successfully.
Slice A06 — Report worker: scoped ordered sparse operations (P1)
1.	Preserve ReportSemanticResponse sparse semantics and existing title/header ownership boundaries.
2.	Map plan operation refs to report field/remark slots; no implicit cross-group field movement.
3.	Preserve exact header values, service line items, coordinates as supplied, and first-page remark requirements.
4.	Reject unsupported slot/duplicate/contradictory assignments; do not hallucinate template slots.
5.	Preserve bounded correction and unchanged sibling fields across correction.
6.	Keep separate report vs section fragment validation.
7.	Add FORGE heading/remarks synthetic regressions, including blank slot inventory, duplicates and page placement validation.
Acceptance: report operations change only report-owned fields; mixed request succeeds when all target slots exist and blocks otherwise.
Slice A07 — Single canonical patch-to-intent lowerer (P0)
1.	Specify mapping between accepted semantic operation variants and existing AuthoringDocumentIntent object families.
2.	Use current IdAllocator and canonical source resolution; prohibit LLM-supplied canonical IDs.
3.	Reuse semantic_actions.py, semantic_section_compiler.py as applicable; consolidate any duplicated mapping rather than building another lowering stack.
4.	Define new-section creation and child references as staged host identities; preserve correct bound source/track ownership.
5.	Implement exact ADD_TRACK multi-op lowering with independent bindings and style/scale semantics.
6.	Preserve partial intent omission/clear/remove semantics and report/section fragment boundaries.
7.	Add tests for serialization, each operation verb, merge conflicts, ID collisions, source binding, and ordering.
8.	Preserve existing no-second-engine attestations and retirement checks.
Acceptance: accepted semantic patches lower into the already accepted AuthoringDocumentIntent and existing reconciler without direct mutation.
Slice A08 — Dependency scheduling and transactional application (P0)
1.	Define semantic-order constraints separately from host CRUD phase/dependency ordering.
2.	Keep workflow.py report and section fan-out for independent tasks; group multiple ops per section into one worker call where bounded.
3.	Detect cross-scope dependencies and refuse unsafe parallelism; use explicit staged snapshot for genuinely dependent second stage.
4.	Continue merging only complete, successful worker outcomes.
5.	Confirm reconciler emits proper create/update/move operations with stable IDs and depends_on edges.
6.	Execute only on a private AuthoringService candidate; no intermediate persistence.
7.	Recheck stale snapshot/optimistic concurrency before publication.
8.	Confirm final complete requirement verification, preservation diff, canonical validation, YAML persistence, reload and render.
9.	Add injected failures at each CRUD phase and negative persistence/reload tests; verify unchanged public state.
Acceptance: no partially published mixed request, correct track order, existing state preserved, replay-safe only where specifically defined.
Slice A09 — Inspection security and observable failures (P1)
1.	Centralize safe inspection policy and quotas; avoid autonomous agent loops.
2.	Add prompt-injection fixtures in source/channel descriptions and document titles.
3.	Separate failure owner planner/inspection/worker schema/worker semantics/lowering/reconciliation/executor/persistence.
4.	Bind evidence hashes to request, operation contract, source snapshot, DTO and result.
5.	Preserve private full-DTO opt-in capture and deletion controls; no public upload of secret-bearing evidence.
6.	Integrate diagnostics with existing stage evidence; no new harness.
7.	Add cancellation/timeouts, size-limit, repeat-inspection and source-change tests.
Acceptance: bounded, reproducible, safe evidence; no permission expansion, no secret leakage, deterministic negative grading.
Slice A10 — Full provider-free integration and compatibility matrix (P0)
1.	Execute focused unit suites for planner, work contracts, worker patches, inspection, lowerer, report, section, revision, source resolution and CRUD.
2.	Execute two-track six-preserved end-to-end synthetic fixture.
3.	Execute FORGE mixed header/remarks/section fixtures with conditional SP present/absent/unknown and resistivity roles.
4.	Exercise single section, multi section, report only, new section, existing section, update/ensure/move/remove, dependent ops and invalid gold.
5.	Assert exact failure stage/owner, unchanged YAML bytes/state for failures, unchanged unrelated state for success.
6.	Confirm YAML round-trip and required render tests (provider-free).
7.	Re-run current D5 one-engine attestation and reachability; rebaseline production source manifest if needed.
8.	Produce parity matrix versus protected D4/D5 cases and independent implementation review package.
Acceptance: all mandatory suites pass with accounted deselections; one production path; no live calls; independent implementation acceptance.
Slice A11 — Documentation, migration, and deployment readiness (P1)
1.	Update AGENTS.md if governance rules need genuine changes; otherwise preserve it unchanged.
2.	Update docs/agent-code-mode-current-baseline.md only with accepted Knowledge Delta and new regression references.
3.	Write one development-memory page per slice: intention, files, frozen contract, evidence, limitations, lessons.
4.	Update architecture ADR, schema examples, operator doc, roadmap, task/backlog visibility, and stale references.
5.	Document a versioned schema migration strategy; define compatibility handling for callers using historical planner or action models.
6.	Confirm single production composition in notebook, MCP, and supported CLI paths.
7.	Enumerate retired/replaced code and avoid leaving shadow execution branches.
8.	Prepare rollback plan to prior accepted checkpoint without modifying historical evidence.
Acceptance: source, docs, tests and operator instructions agree; the accepted baseline is not stale.
Slice A12 — Exact-checkpoint live engineering qualification (separate authority)
1.	Only after accepted implementation: freeze schema/prompt/example hashes, production manifest, assets, runtime, model, endpoint and source context.
2.	Qualify canonical persistent checkout, environment permissions, local source assets, endpoint connectivity and credential source without provider generation.
3.	Use existing live harness; fresh isolated namespace, request/DTO/terminal custody, bounded attempt ceilings.
4.	Run a single separately authorized engineering smoke for the two-track sparse addition on exact accepted checkpoint.
5.	Verify both operation-set equality and entire lower→reconcile→private execute→preservation chain; distinguish infrastructure from model behavior.
6.	Seal evidence, independently review result; do not repeat consumed namespace.
7.	Only after accepted smoke may separate scientific qualification be proposed under its own population, authority and acceptance criteria.
Acceptance: exact-head live smoke has the claimed outcome, verifiable custody and no unintended scientific/C02 consumption. This document gives no authorization to run it.
________________________________________
12. Acceptance matrix and objective release gates
ID	Scenario	Required observation
AC-01	Existing Main Log + 2 additions	Exactly 2 authorized semantic additions; no existing-track re-emission; final 8 tracks
AC-02	Existing Main Log + invalid full 8-track DTO	WORKER_OPERATION_SET_MISMATCH or mapped existing failure, before lowering
AC-03	Header + remarks + Main Log request	One report + one section scope; all requested facts covered; no ownership bleed
AC-04	SP inspected absent	Only GR included, with explicit conditional omission evidence
AC-05	SP not inspected	No false absent claim or silent GR-only success
AC-06	Required GR absent	Correct fatal required-channel diagnostic and unchanged file
AC-07	Resistivity deep/medium/shallow present	Only available appropriate scalar curves bound, log 0.2–2000, deepest emphasized
AC-08	Resistivity candidates ambiguous	No arbitrary source selection or fake unit conversion
AC-09	Duplicate existing GR track	Conflict/explicit ENSURE policy; never silent destructive update
AC-10	Update nonexistent track	Fail without creating a different object
AC-11	Ordered resistivity immediately after Depth	Final canonical order correct after replay/reload
AC-12	Track or binding ID collision	Host IDs unique; no model canonical IDs
AC-13	Worker changes report from section scope	Rejected at ownership boundary
AC-14	Header slot absent	No hallucinated slot; explicit failure/unresolved
AC-15	Concurrent document modification	Stale snapshot blocks publication
AC-16	CRUD operation 2 fails	No persisted partial result; original document preserved
AC-17	Explicit remove vs omission	Only explicit removal changes existing object count
AC-18	20-track request within declared cap	One bounded section worker batch or justified deterministic partition, not 20 mandatory LLM loops
AC-19	Tool prompt injection / arbitrary path	No privilege escalation; safe bounded text only
AC-20	Provider schema vs Python model	Matching requiredness, discriminator, branch and count behavior
AC-21	Corrective response	Valid sibling operations and request coverage retained
AC-22	YAML roundtrip	Persisted file parses/reloads to equivalent canonical model and renders
AC-23	Notebook/MCP/CLI	Same production semantic worker and lowerer, no alternate engine
AC-24	Failure grading	Exact causal owner/stage; zero scientific inference from harness failure
AC-25	Governed live smoke	Accepted exact-head engineering smoke before any scientific campaign
Release gate: AC-01 through AC-24 are provider-free implementation criteria (subject to defined test fixtures); AC-25 is an independent live gate. Do not claim release-ready merely because one smoke passes. No need to invent a numerical model-quality target in this document; freeze that separately before scientific qualification.
________________________________________
13. Migration and backward-compatibility policy
1.	Baseline-first: architecture ADR and accepted Knowledge Delta before changes that contradict historical planner-operation restrictions.
2.	In-place evolution: version plan/worker schemas in existing canonical modules. Avoid parallel planner_v2 / section_worker_v2 runtimes or hidden fallback branches.
3.	Stable deterministic core: prefer zero behavior changes to AuthoringService, reconciler, YAML loader, and rendering unless tests identify an actual gap.
4.	Adapter compatibility: list every production entry point and stored provider schema consumer; implement an explicit migration plan and negative tests. Do not silently accept legacy reconstruct as an alias for additive operations.
5.	No broad rewrite: defer unrelated capabilities or UI changes until D5 semantic contract is corrected and testable.
6.	Rollback: preserve exact prior accepted executable SHA and artifacts; if new semantic contracts regress, revert routing as one reviewed change. Never rewrite sealed evidence or reuse a consumed namespace.
7.	Evidence discipline: historical D5 acceptance is evidence for old behavior, not proof of new schema/model capability.
________________________________________
14. Open decisions to resolve during A00, not by hidden implementation defaults
ID	Decision	Preferred starting position	Why open
OD-01	Planner emits semantic operation inventory?	Yes, versioned and independently validated	Changes historical accepted planner prohibition; needs ADR
OD-02	Worker batch size	One bounded batch per section/report scope by default	Schema/provider size limits need measurements
OD-03	Worker read-only tool interface	Prefetch-first, bounded on-demand host queries	Tool budget, provider/tool compatibility still need design
OD-04	Existing SectionSemanticDraft vs new sparse patch DTO	Reuse maximum stable typed models; introduce smallest versioned wrapper	Avoid redundant IR
OD-05	New-section CREATE_SECTION and child DAG	Host-owned staged identities	Need explicit schema-valid empty/shell section behavior
OD-06	CREATE vs ENSURE vs duplicate	Honor literal intent; ambiguity fails closed	Avoid surprising overwrites or duplicate tracks
OD-07	GR/SP one visual track vs two	Do not assume; domain default only if explicitly documented	Prompt is ambiguous
OD-08	Resistivity role and emphasis defaults	Registry-grounded domain policy where available; otherwise bounded resolution	Not universal across logs
OD-09	Snapshot change during worker calls	Optimistic version/hash guard and explicit recompile	Avoid stale modification
OD-10	Report/section dependencies	Parallel only if independent; staged snapshot otherwise	Mixed transactions can have cross-scope dependencies
OD-11	Correction budget	Preserve accepted single correction protocol	No hidden new retries
OD-12	Schema limits	Derive from provider constraints and bounded tests	Avoid arbitrary unsupported caps
OD-13	Persist/reload failure recovery	Guarantee no success or silent partial state	Exact durable-write semantics require audit
________________________________________
15. Suggested Codex implementation handoff (after design acceptance only)
Task: Implement the accepted WELLPLOT-NLP-CANONICAL-AUTHORING-ARCH-001 architecture through the existing canonical Code Mode graph, in bounded slices A01–A11, after A00 ADR acceptance. Preserve the current authoring YAML, AuthoringService, AuthoringDocumentIntent, reconcile_authoring(), AuthoringExecutor, provider composition and existing single-engine attestation. Do not introduce parallel compilers, planners, engines, direct LLM CRUD or agent loops. Maintain strict semantic operation inventories and read-only source/document inspection. For every slice, provide design delta, exact code changes, provider-free tests, baseline/regression impact, development memory, and remaining gaps. Stop at the agreed implementation-review gate. Do not run endpoint/model calls, reuse D5 sealed namespaces, or start scientific qualification without separate exact-checkpoint authorization.
Operational rule: Human acceptance is meaningful at architecture/design and completed implementation review boundaries. Routine within-slice steps can proceed under the approved design/implementation authority; live smoke and scientific campaigns retain their distinct accepted gates.
________________________________________
16. Source-of-truth reference list
All file paths refer to cschrupp/wellplot at 6f0ef73d2a73b1a01d40767264e8dea0bbad3b45, unless later explicitly revalidated.
•	AGENTS.md
•	docs/project-decision-protocol.md
•	docs/agent-code-mode-current-baseline.md
•	docs/architecture/ADR-CM57-planner-capability-contract.md
•	docs/architecture/D5_SINGLE_ENGINE_INVENTORY.md
•	docs/architecture/D5_5H_SEMANTIC_CONTRACT_REPAIR_DESIGN.md
•	docs/architecture/D5_5J_CANONICAL_REQUEST_OBLIGATION_PRESERVATION_RESULT.md
•	docs/architecture/D5_WORKER_ACTION_OBSERVABILITY.md
•	docs/backlog.md
•	src/wellplot/agent/code_mode/planner.py
•	src/wellplot/agent/code_mode/workflow.py
•	src/wellplot/agent/code_mode/worker_contracts.py
•	src/wellplot/agent/code_mode/typed_section_worker.py
•	src/wellplot/agent/code_mode/canonical_workers.py
•	src/wellplot/agent/code_mode/enrichment.py
•	src/wellplot/agent/code_mode/obligations.py
•	src/wellplot/agent/code_mode/semantic_actions.py
•	src/wellplot/agent/code_mode/semantic_section_compiler.py
•	src/wellplot/model/intent.py
•	src/wellplot/authoring_reconciler.py
•	src/wellplot/authoring_executor.py
•	src/wellplot/authoring_service.py
•	src/wellplot/agent/direct_notebook.py
•	src/wellplot/logfile.py
•	examples/cbl_main.log.yaml
Final boundary statement
This is a proposed architecture and migration specification grounded in inspected code. It does not assert that the currently frozen D5 pipeline already implements planner operation inventories, interactive read-only worker inspection, grouped section patches, or every FORGE behavior. Those are the work items to implement, prove, and accept. Existing deterministic CRUD/YAML functionality must be reused and protected, not rebuilt.
