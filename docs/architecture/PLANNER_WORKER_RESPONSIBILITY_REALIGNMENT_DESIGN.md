# Planner and Worker Responsibility Realignment

**Status:** Design candidate for independent review. No implementation or live
authority. **Base:** `c6a183f918003261bae4e7f4858acc7cf90a419b`.

**Decision (ADAPTED):** Change what crosses the planner boundary, not who
owns authoring. The planner proposes ordered outcomes; existing workers are
responsible for accomplishing each outcome against current state. The
deterministic host still owns authority, identifiers, resolution, lowering,
mutation, verification and publication. Use one existing graph and publish
once per successful turn. Do not change the R4 prompts, R5 schema, campaign
machinery or active baseline in this design slice.

## A. Current responsibilities and evidence

| Owner | Verified on the base checkpoint |
|---|---|
| Composition | [`create_canonical_dependencies`](../../src/wellplot/agent/composition.py#L91) builds the shared planner, enricher and canonical report/section workers; do not add another composition root. |
| Planner and host request binding | [`SemanticPlanner.plan`](../../src/wellplot/agent/code_mode/planner.py), [`_attach_compiled_requirements`](../../src/wellplot/agent/code_mode/planner.py#L1203), and [`compile_request_contract`](../../src/wellplot/agent/code_mode/obligations.py#L1831) already separate model proposals from independently grounded request facts. The wire still has compact and operation forms. In particular, a compact proposal is converted into a canonical operation inventory, not sent straight to mutation. |
| Observe and ground | [`SemanticEnricher`, `_resolved_section_id`, `validate_enriched_snapshot`](../../src/wellplot/agent/code_mode/enrichment.py) ground section/source context and protect snapshot and source revisions. [`AuthoringInspectionFacade`](../../src/wellplot/agent/inspection.py#L103) projects sections, tracks, bindings, headers and known channels. `worker_contracts.py` owns eligible tracks, binding slots, opaque handles and the expected semantic-publication contract. A missing inspection is not proof of absence. |
| Workers | [`CanonicalSectionWorker.compile`](../../src/wellplot/agent/code_mode/typed_section_worker.py#L406) consumes bounded context and validates a typed action, with scoped repair. [`CanonicalReportWorker.compile`](../../src/wellplot/agent/code_mode/canonical_workers.py#L160) produces report intent with bounded alias correction. These are compile workers today, not file-mutating agents. Keep their typed contracts and existing lowerers. |
| Scheduling | [`build_compile_graph`](../../src/wellplot/agent/code_mode/workflow.py#L102) runs plan and safety gates, enrichment and semantic-publication preparation; `dispatch_workers` sends all workers the same base document with isolated context. `merge_node` checks cardinality, failures and identity boundaries, then sorts successful fragments. Sorting at merge is not sequential execution; task two cannot see task one's edits. |
| Execution/publication | Notebook [`_apply_result`](../../src/wellplot/agent/direct_notebook.py#L235) and MCP [`_apply_session_result`](../../src/wellplot/mcp/agentic.py#L150) each orchestrate private apply using the same `reconcile_authoring`, executor, canonical service and [`verify_document_postconditions`](../../src/wellplot/agent/code_mode/obligations.py#L2906), followed by [`persist_authoring_document`](../../src/wellplot/mcp/service.py#L1692). The executor checks operation dependencies and reads back each applied operation but can return a partially changed private service after a failure. |
| Defaults and reporting | [`semantic_actions.py`](../../src/wellplot/agent/code_mode/semantic_actions.py#L338) already uses generic track width. [`generic_authoring_defaults`](../../src/wellplot/authoring_defaults.py#L628) produces defaults and provenance; its broader family selection is tested but not wired into the shared production graph at this checkpoint. [`AgentRunTrace`](../../src/wellplot/agent/execution_trace.py#L142), facade worker outcomes and public session diagnostics already provide evidence; there is no shared task-level chat progress contract. |

**Why change.** R1 and R2's paired evidence shows that first-pass validity is
possible but still leaves contract complexity, invented bookkeeping and intent
errors; the narrow SET-schema R2 change did not recover F04. R3 proved compact
intent can reach the real read-only reconciliation boundary with synthetic
responses, not live host execution; live R3 used operations in all ten cases
and 0/10 passed typed validation. R4 moved nine of ten responses to compact
form but still yielded 0/10 typed. R5 F04 supplied the missing section keys and
passed the advertised schema, then failed the unchanged local validator on
operation bookkeeping inside compact intent. These observations support a
smaller boundary; they neither prove decoder enforcement nor prove that a
worker loop will improve live quality. Preserve the consolidated R1/R2/R3
export and sealed R4/R5 observations; no experiment replay or regrading.

**Precedent and limits.** LangGraph documents [separate sequential
supersteps and Send fan-out](https://docs.langchain.com/oss/python/langgraph/graph-api);
the installed and locked version is 1.2.11. Anthropic's [tool-feedback
pattern](https://www.anthropic.com/research/building-effective-agents) supports
observing actual results and bounding recovery. Neither pattern requires
giving workers unrestricted tools. [SQLite's atomic commit
documentation](https://www.sqlite.org/atomiccommit.html) illustrates why
private staging and replacement do not, by themselves, establish crash
recovery comparable to a database. These are precedents, not claims of
WellPlot parity with their guarantees.

## B. Planner task semantics

Amend the existing `SemanticPlanner` in place in a later slice. The response
is a bounded ordered list of outcomes with a short goal and user-expressed
selectors/settings only, or a typed non-executing abstention with unresolved
requirements. Keep literal physical mnemonics distinct from semantic
measurement clues. Omit unspecified settings, carry explicit clears, and
preserve units, bounds, exclusions, conditional requirements and user-stated
ordering. Do not output operations, capability IDs, generated references,
dependency IDs, source IDs, inferred current object names, or proposed defaults.
Supply the original request and only the bounded context demonstrably needed
to interpret it; detailed mutable inventory belongs to worker observation.

Illustrative semantics below, not a proposed JSON schema or prompt:

| User request | Ordered planner outcomes |
|---|---|
| Create a GR curve. | Ensure a curve for literal physical `GR`. No chosen section, track, color or scale. `GR` remains physical, not a semantic alias. |
| In Survey, add Gamma Ray, then change its scale to linear 0-100 gAPI. Do not use CGR. | 1. Add semantic `Gamma Ray` in the user-named Survey section, excluding `CGR`. 2. Set the same requested curve's scale to linear 0-100 gAPI. The host validates the textual dependency, channel/scale applicability and final obligation; a task number is not authority. |
| Add a CBL track scaled linear 0-1 mV, then clear the report subtitle. | 1. Add physical `CBL` on a new track with explicit bounds and unit; no depth work. 2. Clear the report subtitle. No inferred report work or presentation order beyond the request. |
| Move the GR curve to the first track. | Move the identified physical `GR` binding to the actual first track in the resolved section. If that track cannot accept it, do not silently choose the first *compatible* track. |

Task list position is not an authorization to infer a dependency or to
silently change presentation order. The host binds tasks to the original
request and its independently compiled obligations using existing request-byte
and scope mechanisms. It rejects omitted or unauthorized work, conflicting
assignments, and ungrounded scope. In particular, anonymous HOST_CONTEXT
assignments still ignore model section hints. If the existing compiler cannot
bind a task or later-task reference safely, fail closed; do not manufacture
host authority from a paraphrase or introduce another compiler. Explicit
supersession within a turn needs deterministic grounding; until proved, stop
on conflicting obligations rather than letting the last task win.

## C. Worker observe, act, verify

1. **Observe** the current private candidate and only the applicable source
   snapshots through existing enrichment and inspection. Expose task-local
   approved options and opaque handles through existing work contracts. Avoid
   loading numeric samples merely to choose a track or resolve a mnemonic.
2. **Decide** among authorized actions: satisfy an existing equivalent
   binding as a no-op, patch only explicitly requested fields on a unique
   existing binding, or create an authorized prerequisite and binding.
   Reconcile exact physical identity within the source and binding scope; the
   same mnemonic on another source is not the same binding. An explicit
   request for another instance is distinct from an ensure/no-op.
3. **Default** only omitted presentation fields on the relevant new object.
   Priority: explicit settings or clear; preserve existing values on reuse;
   approved applicable presentation defaults; generic deterministic fallback
   or omission. Record default provenance and keep patch omission distinct
   from clear. An eligible normal track can be chosen by a reviewed
   deterministic policy when alternatives are presentationally equivalent;
   initial policy should be conservative: reuse a unique eligible compatible
   track or create an authorized normal track with host identity/width. Do not
   invent a source or section when no lawful scope exists. Do not ask for a
   color, width, or scale merely because the user omitted it.
4. **Act** by selecting from the existing typed worker actions and lowerers.
   The worker receives authoritative host results, not filesystem write
   tools, a generic Python executor, or public MCP authoring endpoints that
   can persist per call. The [stable MCP tool contract](../../src/wellplot/mcp/assets/defaults/stable_tool_contract.yaml)
   documents the existing track and curve edit capabilities; use it to avoid
   rediscovery, not as a worker write interface. Reuse typed in-memory service
   contracts; inspect, lower, reconcile, apply and verify through the host. Worker-selected
   prerequisites must be recorded as allowed changes, verified as necessary
   for the request, and never broaden scientific scope.
5. **Verify and recover.** Require success from canonical private execution,
   operation readback, validation and task postconditions. For an explicitly
   recognized recoverable proposal error, allow at most one corrected
   attempt within the existing worker correction budget, not an extra retry
   layer. Use authoritative errors and fresh task context, restore/discard the
   tentative task copy first, and leave the target, source and obligations
   frozen. No repeat after unknown effects, stale external state, trust or
   semantic rejection, ambiguity, unexpected failure, or cancellation.
   Budget exhaustion stops the turn; no automatic whole-turn retry or resume.
6. **Clarify** a material source, channel or target ambiguity with a precise
   question and only safe, inspected options. Distinguish no inspected
   evidence, unsupported capability, missing channel and multiple eligible
   channels. A new user answer starts a new turn against freshly inspected
   persisted state; the failed draft is not conversational authority.

**Trust is separate from defaults.** Use only the host-selected trusted
deployment and its approved catalog applicability, including the CAT-03
fixture path/content and physical channel checks. Related mnemonics and
compatible units do not imply equivalence. The asset-backed defaults helper
is not a scientific catalog or new authority; audit its allowed presentation
fields and provenance before wiring it more broadly. The dirty, untracked
`examples/families/` are not reviewed runtime inputs. No global CBL scale,
calibration, unit conversion or sentinel handling is implied.

## D. One ordered graph and one private draft

Replace fan-out in the existing graph at cutover. Do not merely serialize old
`Send` payloads: they already contain stale enriched context. Use one cursor
and a bounded queue in existing graph state. Bind one task, refresh context
against the latest verified draft, rebuild affected contracts, invoke the
existing typed worker, then advance only after the host verifies the effect.
Report and section tasks share the cursor; report-first must not override
explicit user ordering. Initially use serial execution for independent tasks
too; no DAG inference, dual scheduler or parallel optimization.

```text
one plan + authoritative request / source gates
  -> select next grounded task -> inspect current private candidate
  -> existing worker -> existing lowerer -> reconcile -> private apply -> verify
  -> advance with verified candidate, or stop without publication
  -> verify final candidate against original turn -> canonical publication once
```

Split two kinds of custody: immutable original turn authority (original
document, byte obligations, external file/dependency revisions and release),
and per-task private snapshot (draft revision, source-bound handles and task
evidence). Rebuild document-derived projections and handles after each
verified task; reuse inspected source metadata only if existing freshness and
content checks allow, never rebase external authority onto a changed file.
Do not retain handles across snapshots. Retain one canonical graph entry per
turn; no graph re-entry per task, no durable graph checkpoint or graph
interrupt-based resume in the first implementation.

## E. Progress and final reports

Reuse the existing trace/callback and result projection; add a bounded
task-indexed status projection only where existing fields cannot distinguish
private verification from publication. Derive safe natural-language text
from typed outcomes, not raw tool exception text or another model call.
Notebook can display events as they arrive; MCP should expose progress when
the transport supports it and return the same ordered result otherwise. No
second progress service. Distinguish: `planned` (intent), `inspecting`,
`retrying` (bounded), `verified_in_draft`, `blocked`/ `needs_clarification`,
`not_attempted`, `not_published`, `no_change`, and `published`. Only the
adapter can emit `published` after canonical persistence and reload checks.

Example private progress: "Found one GR curve and verified the revised scale
in the draft." Example final on success: "Saved the GR curve using the
default track width." Example when task two blocks: "The GR change was
verified in the draft but not saved. Which of the two resistivity curves
should I use? No changes were published." When post-replacement recovery
fails, report that the file state must be checked; do not say it is unchanged.
Render/preview is a separate outcome, not inferred from successful authoring.

## F. Transaction and publication contract

- **One turn, one private candidate.** Start from the authorized canonical
  document. The existing service performs one copy-and-validate mutation at a
  time; the executor does not undo an already applied prefix. Make each task's
  tentative in-memory service discardable and advance only verified copies.
  A later-task failure discards the whole private turn. Do not publish a
  partial success by default or implement interactive undo.
- **Final verification is mandatory.** Preserve one shared
  `verify_document_postconditions` authority. Final input is the original
  document, final candidate, independently bound whole-turn obligations,
  grounded cumulative change authority and host-derived expected semantic
  set. Do not blindly concatenate operation lists or trust intermediate
  success as final evidence: later effects may undo earlier work, collide in
  identity or change a binding's scope. Prove cumulative preservation and
  obligation composition mechanically before enabling dependent tasks. Refresh
  semantic evidence only through trusted resolver/reconciler checks; never
  edit it to fit the candidate. If exact final expected/observed evidence
  cannot be validated using the shared authority, stop the slice.
- **Snapshot and publication.** Recheck original external revision tokens,
  content SHA constraints, release trust and existing dependency revisions at
  established gates, including immediately before publication. Optimistic
  revision checks are not file locks, a cryptographic content identity, or a
  general compare-and-swap. `_persist_validated_logfile_mapping` stages a
  same-directory file, flushes it, validates it, checks revisions, replaces
  the destination, reloads/validates, and attempts to restore original bytes
  if post-replace verification fails. Preserve recovery-failed distinction.
  No claim of ACID, crash-safe rollback, cross-file atomicity, concurrent
  writer isolation, or durable resumability.
- **Replay.** Exact same-source ensure/update can be a host-confirmed no-op
  when resulting state already matches; preserve deliberate repeat creates.
  There is no general exactly-once tool execution. On unknown publication
  outcome, reload and classify the actual file state before further work.
  Repeated moves/setters may only be no-ops if verified at the new revision.

## G. In-place changes and capability gap

| Existing files / functions | Proposed change and boundary |
|---|---|
| `planner.py: SemanticPlanner.plan, _attach_compiled_requirements`; `obligations.py: compile_request_contract` | Replace the provider-facing task inventory at cutover. Reuse canonical request facts and derive scoped contracts before dispatch; retain typed abstention and rejection distinctions. Extend compiler coverage only with reviewed causal fixtures. No translation to a second semantic engine. |
| `workflow.py: build_compile_graph, dispatch_workers, compile_worker_node, merge_node`; `state.py`; `facade.py` | Rework dispatch and final projection in place. Keep existing safety and semantic-publication preparation attached to refreshed task context and retain identity-boundary checks. Add only cursor, original/current snapshot and typed task outcome projection. No second graph or batch-vs-sequential runtime switch. |
| `enrichment.py`, `agent/inspection.py`, `worker_contracts.py`; `typed_section_worker.py: CanonicalSectionWorker.compile` and `canonical_workers.py: CanonicalReportWorker.compile` | Reuse inspection and contract builders, action verification and repair at the task boundary. Broaden worker choices only within host-grounded options. A host-managed feedback step is enough initially; no arbitrary worker tool harness. |
| `semantic_actions.py`, `semantic_section_compiler.py`, `authoring_defaults.py` | Reuse intent lowering and generic width; wire only approved omitted-field presentation defaults at one canonical merge/creation point if tests demonstrate the gap. Do not change numerical loaders, source-resolution or renderer logic. |
| `direct_notebook.py: _apply_result`; `mcp/agentic.py: _apply_session_result`; `session.py: _project_result` | Extract existing reconcile/private apply/verify orchestration into one shared internal boundary callable by the existing graph. This extraction replaces duplicated private apply ownership; it is not a service or new executor. Pass a host-produced verified candidate/authority result through existing facade/session contracts; adapters must not reapply it or accept arbitrary candidate documents. Publication stays behind final shared verification and the existing persistence service. Preserve compile-only consumers' no-publication contract; inventory all consumers before changing result types. |
| `authoring_reconciler.py`, `authoring_executor.py`, `authoring_service.py`, `model/intent.py`, `obligations.py` | No routine mechanics rewrite. Only if a scoped capability or cumulative authority cannot be expressed, return for review before expanding these contracts. Attestation hash/reachability updates follow approved production changes only. |

**Move GR to the first track is not track reorder.** The canonical
[`MoveRequest`](../../src/wellplot/authoring_service.py#L504) accepts section,
track or remark; `AuthoringService.move` does not reparent a binding. Do not
reuse the public MCP mutation endpoints or silently perform delete/recreate:
binding identity, source assignment, position, fill references and other
dependents can be lost. First inspect whether current intent and canonical
operations can demonstrate a same-section transfer preserving all of those
invariants. If not, the narrow proposal is one typed canonical binding
relocation capability end-to-end, in a separate approved slice, with strict
destination-kind/identity/ownership checks, explicit treatment of dependent
references and readback verification. Until that proof or approval, report
unsupported/incompatible and publish nothing; do not reinterpret the request.

## H. Preservation matrix

Historical acceptance is regression evidence, not scope to run those campaigns.
These are proposed provider-free gates; none were rerun for this design.

| Preserve | Baseline and required regression |
|---|---|
| Single canonical roles and reachability | D5 [single-engine inventory](D5_SINGLE_ENGINE_INVENTORY.md); run single-engine manifest and reachability gates, verify no duplicate scheduler/provider/lowerer or persistence path, preserve entry-point signatures or explicitly review contract changes. |
| Report, revision, CBL/raster, fill and declared order | D5 [provider-free parity result](D5_PROVIDER_FREE_PARITY_ACCEPTANCE_RESULT.md); protect title, GR-scale, ILD binding, GR fill, unrelated-state preservation, cross-track negative and all existing raster/sample-axis/annotation/ordering semantics using workflow, section-contract, canonical-authoring and executor regressions. Replace fan-out assertions with observed dependency order, not weaker result-count assertions. |
| Exact source/channel, ambiguity and requested values | A09 accepted attempt 007 and A10 [R3 provider-free qualification](../evaluations/agent-code-mode/A10-SEM-R3-qualification.md); retain `test_a09_source_inspection.py`, `test_authoring_context.py`, `test_a10_r3_scalar_intents.py`, `test_host_02_scalar_binding.py` and `test_section_work_contract.py`. Cover scalar/raster, duplicate identities in different sources, unavailable/uninspected sources, explicit scale/units, multi-section/multi-source and anonymous scope ambiguity. |
| Trusted catalog and strict publication | A09 CAT-02I/CAT-03 and parity/REPORT-01 in the [active baseline](../agent-code-mode-current-baseline.md); retain `test_semantic_catalog.py`, `test_direct_notebook_transaction.py`, `test_mcp_agentic_transaction.py`: exact GR/gAPI fixture scope, path/content drift, expected/evidence completeness, verifier-before-persistence, malformed contracts and unchanged bytes on rejection. |
| Defaults, omitted/clear, retries and status | Retain `test_authoring_defaults.py`, `test_authoring_intent.py`, `test_code_mode_planner.py`, `test_code_mode_semantic_section_compiler.py`, `test_agent_execution_trace.py`; test explicit-over-default and sparse preservation, only grounded repairs, cancellation, sanitized diagnostics and no false success. |
| Render, custody and stage distinctions | A09 attempt 007 proved real CBL and VDL rendering after YAML reload; preserve existing integration/regression coverage without rerunning the sealed attempt. Preserve R1-R5 artifacts and separation of advertised vs typed vs host outcomes; decoder enforcement remains unverified. |

## I. Provider-free acceptance

Inject synthetic planner and worker replies only at existing provider
boundaries. Inspect real private canonical effects and, for adapter scenarios,
temporary YAML bytes/reload and ordered trace events. No mocked successes for
reconciliation, verification or publication.

| Scenario | Required observation |
|---|---|
| Create GR, presentation unspecified | Unique inspected exact GR is bound; existing compatible placement or approved defaults selected and reported. No request for cosmetic details. |
| No suitable track | One authorized normal-track prerequisite and one curve; no unrelated depth work. With no lawful scope/source, no mutation. |
| Reuse/update existing GR | Equivalent ensure is a no-op and does not rewrite YAML; explicit patch updates the exact binding only; explicit duplicate request is not silently coalesced. |
| Later turn moves GR to first track | Reload the saved revision, resolve exact binding and actual first target; preserve identity, source, style and unrelated contents. Incompatible target or unresolved dependent references fail closed. Positive case is gated on the relocation proof in G. |
| Explicit settings vs defaults | User scale, units and color override defaults; explicit clear remains clear; updates to unrelated defaults are rejected. |
| Multiple ordered tasks | Task two observes task one's verified object under a new snapshot. Cover mixed report/section order, external source change between tasks, and a later operation that breaks an earlier obligation. |
| Recoverable failure | One recognized repair from a clean task checkpoint; authoritative error and success trace; no budget extension or repeated task effect. Unknown failure, exhaustion and cancellation stop with no publication. |
| Scientific ambiguity | Two compatible-looking sources/measurements and no selector produce a precise clarification with safe options; no guess, substitution or execution. |
| Partial task failure | Show an earlier task verified privately, later task blocked, subsequent task not attempted, original YAML unchanged; no claim of successful publication. |
| Notebook/MCP parity | Both use one graph, compare canonical final document/bytes and task status, verifier before persistence, same no-publication on trust/staleness/preservation failure, and honest publication-recovery failure. |

## J. Implementation sequence, gates and rollback

1. **Mechanical extraction first.** With the graph and wire unchanged, share
   the existing private apply orchestration under the two adapters. Gate on
   byte/stage parity, revision/source/trust and verifier-order regressions,
   no new public apply path and attestation. Rollback: revert this isolated
   extraction; no persisted schema change.
2. **Provider-free sequential boundary proof.** In the same graph use a
   bounded ordered cursor; test with host-grounded synthetic tasks at the
   graph's existing planner dependency boundary. Show stale handles rejected,
   task two observes a verified effect, and final whole-turn obligations and
   semantic evidence are complete. Inventory compile-only callers before
   moving apply ownership. This proof and the wire cutover are one activation
   gate; no alternate production entry point or settings toggle for the proof.
   If custody composition fails, revert the scheduler/ownership change
   together, retaining only an independently accepted extraction.
3. **Planner cutover and worker behavior.** Replace the old model-facing
   inventory in place, not alongside a fallback. Qualify defaults,
   clarification, bounded repair, and progress projection incrementally in
   the same path. Run H/I and provider-free prompt/schema/typed/host contract
   checks. Rollback: revert the coupled planner/contract changes to the last
   accepted checkpoint; no live prompt trial or corpus consumption.
4. **Relocation if needed, then adoption review.** Land the positive later-turn
   test only after capability proof or separate narrow approval. Recheck full
   preservation, attestation/reachability and no automatic publication from
   trace status. Record a Knowledge Delta only after acceptance. Any live
   qualification needs separate authority and the existing safety gate.

**Alternatives rejected:** Prompt/schema tuning alone leaves fixed
snapshot fan-out and forces implementation bookkeeping back into the
planner. A free-form worker with public file-mutating tools creates a
competing authorization/publication path. Per-task publication offers earlier
visibility but changes rollback behavior and user-visible failure semantics.

**Review decisions and stop conditions:** Confirm the single-publish
turn policy and accepted automatic presentation choices; decide how explicit
in-turn supersession is represented by current obligations; prove final
source/binding evidence survives dependent tasks; determine whether canonical
relocation requires a new operation. Stop rather than adding a second
authority, duplicating a lowerer, weakening preservation, claiming unsupported
atomicity or scheduling work against a stale snapshot. Reverse the proposed
change if provider-free gates cannot hold; R1-R5 offer no reason to waive them.

**DRIFT_CHECK: PASS.** Design only. No changes to production, tests, prompts,
benchmark, baseline, catalogs, notebooks or family assets. No inference,
source inspection runtime, document mutation or campaign execution.
