# Planner, Worker, and Host Authority Revision

**Design only.** Reviewed against `8097dcd3d6fcc211b967664a2216881206d8020b`.
This companion revises the responsibility split and migration gates in the
[realignment design](PLANNER_WORKER_RESPONSIBILITY_REALIGNMENT_DESIGN.md);
it does not activate them or supersede the accepted code checkpoint.

## Decision

The planner interprets **what** the user wants. The worker determines **how**
to achieve it from inspected state. Host policy independently decides whether
the proposed action is safe and in scope. Existing deterministic lowering,
reconciliation and execution translate the admitted action to typed API calls.
The shared verifier determines whether the final candidate satisfies the
accepted outcomes and preserves everything else. None of those stages
substitutes for another.

**Evidence class: ADAPTED.** The established [tool-feedback pattern](https://www.anthropic.com/research/building-effective-agents)
supports bounded actions based on observed results, and [LangGraph's sequential
supersteps](https://docs.langchain.com/oss/python/langgraph/graph-api) support
one ordered graph. Neither supplies WellPlot's scientific authority or
publication guarantees. Retaining a regex admission gate for every natural
language wording would preserve the observed extraction bottleneck; giving
workers direct mutation tools would bypass accepted safeguards. Neither is
selected. The staged proposal is reversible without persisted-schema changes.

## Current Path And Proposed Ownership

Confirmed path: [Notebook `_apply_result`](../../src/wellplot/agent/direct_notebook.py#L220)
and [MCP `_apply_session_result`](../../src/wellplot/mcp/agentic.py#L125)
consume a compilation result from [`AgentSession`](../../src/wellplot/agent/session.py#L359).
The shared [composition root](../../src/wellplot/agent/composition.py#L91)
builds the planner, enricher, and workers. The following is a responsibility
inventory, not a claim that the proposed workflow is already implemented.

| Boundary and source | Confirmed today | Proposed change and protected guarantees |
|---|---|---|
| [`SemanticPlanner.plan`](../../src/wellplot/agent/code_mode/planner.py#L905), [`compile_request_contract`](../../src/wellplot/agent/code_mode/obligations.py#L1917) | The planner compiles request facts before generation; compilation failures can block generation. A plan-attachment helper also calls the compiler. The planner wire includes operation and compact forms. | In place, move to ordered outcome proposals. Eventually retire mandatory regex coverage as an interpretation gate only after its authority consumers are replaced. Preserve typed abstention and host rejection. |
| [`extract_supported_anchors`](../../src/wellplot/agent/code_mode/obligations.py#L886), [`extract_supported_obligations`](../../src/wellplot/agent/code_mode/obligations.py#L1062), [`_attach_compiled_requirements`](../../src/wellplot/agent/code_mode/planner.py#L1203) | Recognized phrases become byte-bound facts; anchors check coverage of recognized patterns only. Attachment assigns those facts to host-bound scope. | Keep exact request provenance and useful independent checks for explicit facts and restrictions. Unrecognized phrases are not proof of absent intent. Replace legacy authorization dependencies only under parity gates; never mint request evidence from a model paraphrase. |
| [Enrichment](../../src/wellplot/agent/code_mode/enrichment.py) and [section/report contracts](../../src/wellplot/agent/code_mode/worker_contracts.py#L1376) | Scope, source, and opaque handles are grounded in inspected context; the section operation contract binds planner proposals to request facts. | Retain deterministic source and scope authority. Simplify operation contracts into per-step admission against an accepted outcome and verified snapshot, rather than relying on a planner inventory. |
| [Section worker](../../src/wellplot/agent/code_mode/typed_section_worker.py#L406), [report worker](../../src/wellplot/agent/code_mode/canonical_workers.py#L160), [graph](../../src/wellplot/agent/code_mode/workflow.py#L102) | Section worker serializes a host-selected typed action and may repair it; report worker lowers report intent. Fan-out compiles against a common snapshot, then merges. | Existing workers choose the next admissible action in one ordered graph. Retain typed action checks, freshness, bounded repair and no arbitrary tools. Replace rather than supplement fan-out at cutover. |
| [`lower_section_action`](../../src/wellplot/agent/code_mode/semantic_actions.py#L173), [`compile_section_semantics`](../../src/wellplot/agent/code_mode/semantic_section_compiler.py#L55), [`AuthoringDocumentIntent`](../../src/wellplot/model/intent.py#L461) | Translate semantic drafts/actions into sparse canonical desired state and allocate host identities; report lowering does the analogous work. | This is already part of the API compiler. Reuse it; preserve omission versus clear, exact binding types and approved defaults. No new compiler or arbitrary document JSON. |
| [`reconcile_authoring`](../../src/wellplot/authoring_reconciler.py#L1306), [`execute_authoring_plan`](../../src/wellplot/authoring_executor.py#L879), [`AuthoringService`](../../src/wellplot/authoring_service.py#L763) | Reconciliation derives scoped operations and dependencies; executor builds typed service requests, orders effects and reads them back; service validates canonical mutations. | Same implementation and API models. These stages already know schema, parameter, relationship and dependency rules. They do not reinterpret prose, decide user authority or rewrite YAML. |
| [Private apply](../../src/wellplot/agent/_private_apply.py#L44), [postconditions](../../src/wellplot/agent/code_mode/obligations.py#L3233), [persistence](../../src/wellplot/mcp/service.py#L1692) | Shared helper exposes only a verified candidate or a failure. Both adapters retain snapshot rechecks, publication and recovery classification. Compile-only callers get intent, not a mutation. | Keep one verifier and publication path. Extend shared evidence for ordered private effects; no private step saves. Preserve adapter parity, conflict detection and recovery semantics without claiming crash-safe rollback. |

## Planner, Worker, And Execution Envelope

The planner proposes typed user outcomes and explicit relationships, such as
“plot exact GR” then “split fill on the curve from the first outcome at 0.”
It preserves restrictions, explicit values, units, exclusions and ordering.
It does not prescribe a parent track, CRUD, API parameters, canonical IDs,
action schemas or a reconciliation plan. A provisional interpretation is
not a mutation grant. Keep the original request immutable and inspectable.
Check proposal shape, supported outcome family, contradictions and independently
recognizable restrictions; surface unresolved consequential interpretations.
An exact quote proves provenance, not that the model interpreted it correctly.

### Host outcome admission

Before dispatch, the host records one disposition for each proposed outcome
and each known request item not represented by a proposal. An admission is
bound to the immutable request digest, the typed outcome and its user-evidence
references, explicit constraints and exclusions, and required relationships
to other outcomes. It records applicable capability, authorized scope,
permitted effects, trusted document/source evidence, and the verification
condition. Dependent selectors can remain pending until the predecessor is
verified; they grant no action authority until grounded on the current
snapshot. New state does not expand the admitted scope.

| Disposition | Meaning |
|---|---|
| **Proposed** | Typed planner interpretation, not executable. Schema validity and a matching quote alone cannot admit it. |
| **Accepted executable** | Supported outcome, consistent with known request facts and restrictions, with bounded effects and a verifiable result. Only this disposition can enter the worker envelope. Every concrete action still needs state-grounded host admission. |
| **Rejected** | Contradictory, out of scope, unsupported, or not safely verifiable. Record the reason; no execution authority. |
| **Needs consequential clarification** | Plausible interpretations differ materially in scope, scientific meaning, geometry, identity or irreversible effect, and trusted evidence cannot resolve them. Ask a specific question and do not execute the ambiguous work. |

Independent checks cover recognized literals, values, units and exclusions;
supported capability and geometry; actual inspected object/source identity;
effect limits; and the existence of a verifier for the requested result.
Whether unfamiliar prose means the proposed outcome, or contains a nuance
not covered by those checks, remains interpretation uncertainty. For a
well-grounded, low-risk interpretation, the host can admit a bounded effect
without a regex match or user confirmation. For destructive, scientific or
otherwise consequential ambiguity, require resolution before admission.
Ordinary admitted actions and necessary prerequisites do not require
per-action confirmation.

### Request coverage before execution

Coverage asks whether the proposed outcomes represent the user's request.
Satisfaction asks whether verified state meets those outcomes. Keep them
separate. During admission, reconcile the proposal list with independently
recognized explicit facts, constraints, exclusions, and order. Preserve
unmatched recognized work as unresolved; do not discard it when the planner
omits it. Require a request-grounded reason for each proposed effect; do not
accept surplus outcomes because they are supported API operations.

For phrases outside known extraction patterns, retain the model's proposed
interpretation and its request reference, and record uncertainty rather than
claim independent coverage. Absence of an extractor match is neither a
rejection nor proof that all work was captured. Allow a bounded repair of an
identified omission or contradiction using the original request and existing
correction budget. If a material coverage discrepancy remains, block the
turn or ask a consequential clarification; do not save a verified subset as
successful completion. No second general-purpose parser or deterministic
proof of arbitrary English equivalence is assumed.

The worker observes the verified private document and relevant source
inventory, chooses among lawful possibilities, and submits a typed action.
Host checks precede lowering and are rechecked against the reconciled effects
before execution. Bind scope and selectors against the current snapshot;
allocate IDs through existing host mechanisms. Do not reuse stale handles.

| Class | Authorization | Example |
|---|---|---|
| Direct outcome | Admit if it implements the accepted outcome in the selected scope with exact supported source/geometry and no effects beyond allowed objects and fields. | Add the requested physical GR binding to a compatible track. |
| Necessary prerequisite | Admit automatically if current state proves no lawful reusable parent, the outcome requires it, and collateral effects are limited to the smallest supported structure and approved omitted-field defaults. | One normal track plus the requested GR binding via existing compound `AddTrackAction`. Not permission to add depth work or a new section. |
| Out of scope, ambiguous, unsupported or consequential | Reject or ask a precise clarification using verified choices. No hidden substitution, destructive cleanup, new source, unapproved scientific mapping, or unsupported geometry. | Two plausible source identities, or deleting a track unrelated to GR. |

No confirmation is required for ordinary necessary and reversible actions.
“Reversible” here means dropping an unpublished private draft, not undoing
arbitrary published changes. Precedence is explicit values or clears, then
preserve existing values on reuse, then approved presentation defaults or
omission. Scientific equivalence and catalog activation remain host-trusted,
not defaults. Distinguish absent data from uninspected/unavailable data.

After each action, verify readback and narrow preservation, refresh the
private snapshot and reconsider what remains. Count successful action
occurrences separately from selection calls and repairs. Qualify the prior
proposed four-step/task and sixteen-step/turn ceilings, at most one optional
selection per step and one correction per task, within existing deadlines.
An invalid recoverable proposal can be corrected on a clean private copy
using authoritative diagnostics; unknown effects, stale dependencies, failed
trust, ambiguity, exhaustion or no progress stop without publication. Report
draft verification separately from saved changes. The host, not the worker,
decides whether the outcome is complete.

## Complete Turn Verification

Use host-owned ordered occurrences that retain the original request digest,
task/step position, intact reconciliation plan/IDs, scoped admission, before
and after snapshot identities, readback and source/catalog evidence. Per-step
verification must reject unauthorized transient changes even if a later step
reverses them. Join the original document to the first snapshot, each result
to its successor, and the final snapshot to the proposed publication.
Reject lost, repeated, reordered or stale occurrences and contradictory edits
unless explicit supersession was established from the request.

Extend the existing shared postconditions, not a second verifier. Require
each accepted typed outcome or restriction to have a deterministic check;
unhandled requirements block apply in the migrated path. Record completion
as **satisfied by verified execution**, **satisfied by verified existing
state** (no-op), or **blocked, unresolved or unsupported**. Only the first
two count toward success. Before final publication, require every admitted
outcome to be satisfied and no known material coverage gap, rejection or
clarification to remain. Honest reporting of unsupported work is not
completion, and verified draft work is not a published success.
Check exact report values and identities (including
remark and tail), exact scoped binding and source identity, fill geometry,
baseline and target relationship, and earlier necessary effects against the
final candidate. Validate each step's preservation and the final cumulative
effect against the original snapshot. Recheck exact host-expected/observed
semantic evidence against final bindings and trusted release. A refreshed
snapshot must not silently rebind old evidence. Publish once through the
existing adapters after final verification and external drift rechecks.

**Open defects, not solved by this design:** The old compiler misses
subtitle; it can compile remark and tail requirements that the shared final
verifier fails to enforce; separate private plans can both contain
`update:report:report`. The existing
[`_order_plan_operations`](../../src/wellplot/authoring_executor.py#L332)
correctly rejects duplicates *within one plan*. Do not flatten plans,
rename IDs or treat an otherwise valid final document as evidence of
whole-turn intent satisfaction.

## Nine Conceptual Traces

These describe the proposed behavior, not results on the current runtime.

| Request or event | Planner output | Worker and host decision | Compiler and canonical API | Verification and publication |
|---|---|---|---|---|
| Plot GR; compatible track exists | Plot literal GR. | Inspect and choose exact inspected GR in a lawful existing scope; reuse equivalent binding or admit one compatible placement. | No-op or lower `AddBindingAction`; reconcile and create one curve binding. | Exact identity and unchanged siblings; publish once if changed, otherwise no write. |
| Plot GR; no compatible track | Same outcome, no track instruction. | Prove one source and lawful existing section, no eligible track; admit only one normal track and requested binding. | Compound `AddTrackAction`; canonical track creation then dependent binding creation. | Verify both effects, no orphan, extra track, depth work or sibling changes. Publish only after whole-turn pass. |
| Create GR then explicit split fill at 0 | Plot GR then split fill on that new curve at 0. | Admit GR first; refresh and bind the second outcome to its exact verified binding, not an older GR or stale handle. | Lower the applicable add action, then `AddFillAction`; create scoped fill with `baseline_split` and value 0. | Verify original binding/source and dependent geometry together. No publication if either fails. |
| Rename report and set subtitle | Two independent exact text outcomes. | Admit each scoped report-field edit against its preceding snapshot. | Two sparse report intents, two canonical report updates; keep both local IDs. | Assert both final fields and each private effect. One publication only; current subtitle/aggregation gaps gate it. |
| Worker attempts unrelated track deletion | Original goal remains GR; no delete outcome. | Reject out-of-envelope removal even if the API would allow deletion. | No lowering or mutation for that action. | No publication on failure; only an authorized alternative may continue within bounds. |
| Two plausible GR sources | Plot GR, source unspecified. | Inspect both; ask which source, not which color. | No binding API call before resolution. | No publication; a new user turn supplies the selector against fresh state. |
| Invalid API parameter | Preserve the original outcome. | Validate proposal; give bounded exact diagnostic and permit one correction if safe. | Reject invalid typed parameters before mutation; lower only a corrected, admitted action. | Read back corrected result, or stop without publication if repair fails. |
| Later action invalidates earlier outcome | Preserve both outcomes, absent explicit supersession. | Reject a known conflict before execution; if discovered at readback/final check, discard the draft. | No unauthorized mutation; any already applied effects were private. | Final check fails if either outcome was undone. No publication. |
| Unsupported fixed-baseline fill | Preserve the requested fixed-baseline geometry, not split fill. | Report unsupported or ask whether a different explicitly approved geometry is acceptable. | No substitution to `baseline_split`; no fill API call. | No publication for the unresolved turn. |

### Adversarial admission and coverage design tests

Inject these proposals at the existing provider boundary in the future
provider-free gate. Assert admission/coverage results separately from final
verification; no blocked case may publish.

| Request and proposed outcome | Expected result |
|---|---|
| User asks for title and subtitle; planner proposes only title. | A qualified explicit-field check identifies the missing subtitle. Correct or block; a verified title alone is not whole-turn success. The current subtitle extraction gap must be closed before this case is qualified. |
| User requests GR only; planner adds deletion of resistivity. | Reject the deletion as surplus, destructive work. Do not dispatch it or publish a partial turn around the unresolved mismatch. |
| User requests fixed-baseline fill; planner proposes `baseline_split`. | Reject the geometry substitution. Report unsupported or clarify; schema validity and a matching baseline number do not make the geometries equivalent. |
| User specifies an exact source or numeric constraint; planner omits it. | Detect a missing recognized selector, value or unit; require repair or block. A coincidentally matching default or source is not proof of coverage. |
| User says “Could you get the GR trace onto this plot?” without a matching legacy regex. | Admit a bounded literal GR outcome when the inspected scope and source are unambiguous and no material uncertainty remains. Verify the effect (or an exact no-op); do not reject solely for unfamiliar wording. |

## Migration And Review Gates

1. **Freeze current contracts.** Keep Slice 1 and the accepted corrective
   checkpoint as reference evidence. Inventory compiler, obligation and
   compile-only callers. Qualify title/subtitle, remark and tail verification,
   fail-closed unhandled outcomes, and unchanged legacy public behavior.
   Stop if a proposed check makes missing work look successful.
2. **Qualify the shared boundary provider-free.** Prove locally scoped plan IDs,
   original-request and source custody, ordered consecutive snapshots,
   transient unauthorized change rejection, independent report edits, and
   semantic expected/observed closure. Test GR prerequisite and exact dependent
   split-fill separately. No second graph, production test switch or planner
   cutover. If step authority or final custody cannot be expressed, stop for
   review. Roll back only the unaccepted evidence/contract slice.
3. **Qualify a bounded outcome interface and envelope.** Test synthetic outcome
   proposals at the existing dependency boundary against exact source,
   explicit restrictions, no-collateral prerequisite and rejection cases.
   Require the admission and coverage adversarial matrix above, including
   omission, substitution, surplus work and a valid unfamiliar paraphrase.
   Prove known unresolved work cannot be counted as success or published.
   Compare accepted D4/D5/A09/A10 behavior, worker budgets and Notebook/MCP
   parity. Do not remove current compiler authority checks until replacement
   checks demonstrably cover their consuming paths. No runtime fallback.
4. **Separately authorize a coupled cutover.** Replace, in place, the planner
   inventory and fan-out with the outcome interface and one sequential graph.
   Keep public signatures, compile-only semantics, persisted schema and
   canonical publication path. Qualify attestation/reachability and full
   deterministic regressions. Revert the coupled cutover on protected
   regression; defer bootstrap and relocation to separate gates. Live
   qualification is outside this design authority.

**Open decisions:** the minimum complete typed outcome vocabulary; which
independent request checks are retained once extraction is nonblocking;
how exact source and expected semantic evidence span successive snapshots;
and whether the proposed budgets cover protected workloads. Unsupported
geometry, incomplete report verification, ambiguous interpretation, or
unverifiable cumulative evidence are stop conditions, not reasons to bypass
the verifier.

**DRIFT_CHECK: PASS.** This document is the only deliverable change. No
runtime, test, schema, prompt, catalog, routing or sealed evidence change.
No execution, publication, commit or push. Stop for independent review.
