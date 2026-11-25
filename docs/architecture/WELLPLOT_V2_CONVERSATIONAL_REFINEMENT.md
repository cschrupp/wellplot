# WellPlot V2 Conversational Refinement

Status: design checkpoint for independent review, not implementation or live authority.
Base: `cccda3533c4fd479260b4f5fb9afbae34fb5560b`.
Companion to the accepted [Planner–Worker Authority Revision](PLANNER_WORKER_AUTHORITY_REVISION.md);
its host admission, coverage, partial completion and publication constraints remain binding.

## Evidence and decision

H1a remains accepted at 9/10 on its exposed development panel. SOL closed the consumed
H1b condition: collection PASS, 8/8 first-pass typed valid, 6/8 scientifically complete,
original progression NOT MET. P04 omitted the independent Check Pass co-location;
P08 proposed display of XCAL and simultaneously declared it unavailable. H1b preserved
literal and semantic grounding, exact report values, scientific dependencies,
conversational references, source choice and preservation in the successful cases.
No regrading. P01–P08 remain exposed regressions, not fresh evidence.

Custody: `wellplot-v2-h1b-measured-20261124-001`, terminal SHA-256
`97ff3cb98d33f784c8c9d95ebdb669b442c7002649267f3b1b4efeb6f2aa6054`,
review ZIP SHA-256 `85d791f6c916dc9c627ad4b3d7997c8fa2037ba3df0fe53d7d67dda28d043f13`.
Preserve original artifacts; this record is not replacement evidence.
The original prompt-only H1b-R2 is suspended. P08 motivates moving detailed
feasibility out of planning; it does not prove that responsibility allocation caused
the failure. P04 still requires explicit objective coverage.

## Evidence applied

| Classification and primary source | Application and limit |
| --- | --- |
| ESTABLISHED: [Data Formulator 2](https://arxiv.org/abs/2408.16119) supports iterative authoring and reuse of earlier designs. | Adapt iteration to verified WellPlot snapshots; do not import branching chart state or generated mutation code. |
| ESTABLISHED: [DataTone](https://zcliu.cs.umd.edu/datatone/DataTone-UIST15.pdf) carries user disambiguations forward; [conversational NL4DV](https://arxiv.org/abs/2207.00189) retains dialogue context for visualization follow-ups. | Adapt pending decisions and reference grounding without importing a parser or assuming that yesterday's source identity is still current. |
| ESTABLISHED: [Rasa CALM](https://learning.rasa.com/rasa-pro/architecture-of-an-assistant/) separates dialogue understanding from business logic; its [conversation repair overview](https://learning.rasa.com/rasa-pro/introduction-to-calm/) addresses incomplete or changed input. | Keep user corrections in dialogue and host-owned pending state, not independent agent memory or a Rasa-style second flow engine. |
| ESTABLISHED: [Anthropic's orchestrator–workers pattern](https://www.anthropic.com/research/building-effective-agents) separates coordination and specialist work. | ADAPTED: existing graph routes bounded work; planner proposes ownership, not an autonomous execution hierarchy. |
| ESTABLISHED: [ReAct](https://arxiv.org/abs/2210.03629) uses observed environment feedback; [SWE-agent](https://arxiv.org/abs/2405.15793) shows the importance of the tool interface. | ADAPTED: expose verified readback and bounded recovery, not open-ended tool loops or free-form execution. |
| ESTABLISHED: [ChemCrow](https://arxiv.org/abs/2304.05376) and [Coscientist](https://pmc.ncbi.nlm.nih.gov/articles/10733136/) illustrate domain-tool grounding. | Keep inspection and typed APIs authoritative; tool access alone does not establish scientific correctness. No chemistry workflow is imported. |
| ESTABLISHED: [tau-bench](https://arxiv.org/abs/2406.12045) grades environment outcomes; [tau-squared-bench](https://proceedings.mlr.press/v306/barres26a.html) adds interaction with changing shared state. | Score verified outcome and truthful reporting independently; use frozen dialogue here, not a new simulator or scorer. |

EMPIRICALLY_SUPPORTED locally: application-aware instructions improved the exposed H1a
panel; H1b typed success was not sufficient for scientific completeness. ADAPTED:
full shared context and separating intent, feasibility and mutation. NOVEL locally:
an LLM response role over verified WellPlot outcome records; competence and context
cost are unqualified. No other system establishes this model's WellPlot performance.

## Roles and authority

| Owner | Responsibility | Boundary |
| --- | --- | --- |
| Planner | Account for each informational, authoring or mixed objective; resolve dialogue references and global scope; group by specialist; preserve literal selectors, exact quantities, exclusions and dependencies. Keep requested objectives even if they may be impossible. | May use visible facts to interpret intent, not select authoring actions, certify feasibility or grant authority. Flag unresolved meaning without converting absence into permission to substitute. |
| Report worker | Inspect report-level state and capabilities; identify already-satisfied work, feasible actions, prerequisites and blockers. | Propose permitted report actions only; host verifies the exact target and admissibility. |
| Section worker | Inspect sources and document hierarchy; investigate channel identity, ambiguity, addressability and feasibility; propose constrained track/binding actions or grounded alternatives. | No new source equivalence, implicit conversion, substitution or out-of-scope edit. Reuse verified evidence rather than repeat inspection. |
| Conversational response agent | Answer read-only scientific/application questions using verified facts; communicate saved, attempted, blocked and pending work; ask focused questions and present grounded alternatives. | Dedicated LLM role within the canonical workflow, not a hybrid template system or new router. No mutation tools, fabricated measurements, or promotion of proposed/private results to saved results. |
| Deterministic host | Admit investigation separately from mutation; validate request facts, scope, identity, capabilities and dependencies; run existing typed APIs, readback, preservation and single publication. | Own outcome and publication state. Filter action authority, not user intent. No model-produced state or response text overrides host evidence. |

Routine information-only turns should not dispatch mutation workers. If existing
verified facts suffice, provide them directly to the response role. Missing facts
permit only authorized read-only investigation. A report or section worker's proposed
prerequisite is not automatically authorized, especially for C2/dependent work.

## Shared context and manual

Use one read-only projection of existing canonical state per role invocation:

| Context | Contract |
| --- | --- |
| Transcript | Preserve the full ordered role-aware transcript in application storage; expose it initially without summarization, retrieval or separate memory agents. Prior user decisions are scoped to the pending objective; assistant statements are not authoritative facts. |
| Plot | Full canonical plot JSON, including report/header, remarks, sections, tracks, bindings, styles, scales, fills and annotations. Label persisted revision, verified private candidate and final published revision distinctly. Refresh after verified changes; never accept a model rewrite of the plot. |
| Inventory | Existing LAS/DLIS inspections only. Include verified source identity via safe host references, mnemonic, units, kind, addressability, frame, dimensions, depth coverage and completeness where known. Distinguish displayed, available but not displayed, affirmatively absent from a complete applicable inspection, not inspected, and inspection/source failure. Missing metadata is unknown. Source-authored descriptions are clearly delimited untrusted data, never instructions or catalog evidence. No sample arrays or credentials. |
| Workflow | Host-owned objective identity, assignment, dependencies, verified results, pending decisions, rejection and publication status. Reference evidence and revision; do not maintain competing per-agent outcome ledgers. |

Use the same assembly order for each manual: shared scientific application knowledge;
role responsibility and boundary; role procedure; relevant API/capabilities; independent
worked demonstrations; inventories; full canonical JSON; ordered transcript; verified
results/pending work; current request and assignment; typed role response contract.
Keep stable instruction prefixes where practical. Planner procedure enumerates objectives
and retains constraints; report procedure inspects report state before proposing actions;
section procedure checks source and state before choosing actions; response procedure
checks publication and blockers before forming claims. Only workers receive relevant
mutation API instructions. Example demonstrations must be independent of measured fixtures.

**Size qualification remains open.** No qualified complete-role prompt or matched
local tokenizer measurement exists for the proposed full context. Historical H1b smoke
reported 990 input tokens on a synthetic fixture, not a realistic capacity estimate.
Before proposing live authority, capture exact serialized payload sizes by block and role
for the reviewed open-hole LAS and CBL/VDL `CBL_Repeat.dlis`, each with full canonical JSON,
complete metadata, relevant API schemas and representative multi-turn transcript.
Report UTF-8 bytes and exact model-token counts if a compatible local tokenizer is
available, including chat wrappers, schemas and output reserve against the runtime limit;
otherwise label token counts unavailable and require a qualified budget before execution.
Do not silently truncate; if oversized, stop and separately qualify a bounded policy.
Report cache reuse descriptively, not as a performance guarantee.

## Canonical reuse and gaps

| Reuse | Gap to qualify later |
| --- | --- |
| `SemanticPlanner`, D4 accounting, D5 capture-only observations, provider and launcher | Current H1b dispositions mix intent and feasibility. No informational objective family qualified. Adapt the existing observation DTO/profile only if required; never turn it into executable wire. |
| `AgentSession`, Code Mode facade and `workflow.py` LangGraph, existing workers and capability registry | Current graph dispatches compile workers and merges intents; this is not yet verified refreshed sequential execution or a complete four-role conversation. Audit actual Notebook/MCP transcript continuity and restart persistence before adding storage. |
| Existing canonical authoring document/serialization and `AuthoringInspectionFacade` | Current model context uses projections, not uniformly full plot JSON. `workflow._planner_source_summary` includes units, but `planner._safe_source_summary` drops them and retains mnemonic/kind; audit addressability, frame, dimensions, completeness and coverage end to end. Preserve isolation and sensitive path redaction. |
| Shared `_apply_private_authoring`, AuthoringService, existing lowerers/reconciler/executor and shared postcondition verifier | Reuse existing verification and publication. Qualify partial continuation and dependency handling rather than infer execution from model output. C2 remains non-executing; the empty-subtitle named-section resolver defect must be corrected separately before affected execution. |
| Existing session/result and adapter envelopes | A dedicated response manual, non-mutating response contract and role wiring are new; no parallel workflow. Determine smallest envelope extensions after observation evidence. |

## Rejection and continuation

Host statuses must distinguish proposed, admitted for investigation, admitted for
mutation, verified already satisfied, verified privately completed, published,
pending clarification, unavailable, uninspected/inspection failed, unsupported,
dependency blocked, contained local failure, cancelled/superseded and transaction
failure. These are semantic distinctions for existing result contracts, not a new
state engine. Only verified already-satisfied or verified completed outcomes count
toward completion; persisted success must additionally match publication/readback.

Ask about consequential ambiguity, not routine reversible implementation choices.
Retry only an ordinary recoverable implementation problem within separate established
budgets and refreshed verified state. Do not retry an integrity, source continuity
or publication failure as a local task. Partial publication is allowed only for a
verified dependency-closed safe subset under the original request and preservation
policy. If all-or-nothing, cancelled, superseded, or integrity compromised, withhold
publication as applicable. A clarification answer resolves only its pending objective
against current revision and inventory; re-admit if facts changed, never replay
already verified work. The response agent reports actual host state, including when
changes were attempted but not saved.

## Five conceptual traces (not qualification)

1. **Informational:** “What unit is the displayed caliper in?” Planner retains the question; host reads the binding and inspected unit; response cites the verified unit. No mutation worker or publication.
2. **Mixed:** “Rename this report to Run Summary and tell me whether temperature is available.” Report worker proposes only the rename; host verifies it; response reports actual save status and inspection finding independently. If inspection failed, say unknown, not absent.
3. **Clarification:** Two inspected sources expose the requested literal channel; worker returns alternatives, host retains pending scope; response asks which source. “The repeat run” resolves that objective only after fresh identity/revision checks; verified earlier report work is not replayed.
4. **Dependent change:** “Put both porosity curves together and shade between them.” Planner preserves both outcomes and the dependency; only a separately authorized future execution gate could verify co-location privately before admitting shading. If the prerequisite fails, report both the failure and blocked shading; never manufacture an edge or claim publication.
5. **Partial/cancelled:** “Add a remark and plot XCAL from this file.” A complete inventory rules out XCAL; no executable display survives. Verified remark may publish once if independent and allowed; with “only if both can be done” or cancellation before publication, report no save. An integrity failure stops the transaction regardless.

## Experiment sequence and exits

**S03 next: revised planner feasibility pilot.** Can the planner account for every
objective, including informational and unavailable work, when detailed feasibility
is owned downstream and the planner sees richer verified context? H1b cannot answer
that: it tested a different responsibility contract. Test the combined contract as
one condition, not an ablation or evidence that any one prompt/context change caused
an effect. Use six proposed fresh synthetic development cases in this order:

| ID | Exact proposed request | Required fixture and grade |
| --- | --- | --- |
| R01 | What units is the deep resistivity curve displayed in? | Deep section with a bound RT curve; inventory and plot show ohm·m. Informational objective, identify current binding; no edit. |
| R02 | Retitle the report Morning Review and tell me whether the Pass B source includes SP. | Two inspected sources, only Pass B lacks SP in its complete inventory. Two independent objectives; exact title and scoped inquiry retained. |
| R03 | Make density green only in Pilot; in Repeat, put neutron and gamma ray on one track. | Both sections have matching density bindings; Repeat has separate neutron/gamma tracks. Account for both scopes and preserve “only”; no cross-edit. |
| R04 | Overlay porosity A and porosity B in East and shade between them after they are together. | Separate verified bindings in East, no directional instruction. Two outcomes with the correct edge, no invented normalization. |
| R05 | Plot the same curve from the second source instead, without changing the limits. | Transcript previously requests literal DT with 1200–1250 m and names ordered Base then Repeat alternatives; both inventories have DT. Resolve to Repeat, carry scope and limits, preserve other work. |
| R06 | Add the remark Review pending and plot physical XCAL from Run West; leave SP alone. | Run West complete metadata lacks XCAL and plot has SP. Preserve both objectives and SP restriction; route XCAL investigation, not a substitution or asserted executable action. |

These are design inputs, not a frozen execution package. Before launch bind exact
serialized complete contexts, transcripts, prompt/schema, rubric and case hashes.
Retain P01–P08 offline for regression reasoning, not extra measured calls. Mock HTTP
must show all six can reach the canonical non-executable boundary under existing
authority; any compiler rejection is a host outcome, not a failed model answer.
No blanket admission exception. If the canonical path cannot capture one safely,
stop for review rather than swap the case or add a runner.

Proposed ceiling: six logical/physical attempts, one response each, zero corrections
or SDK retries. Typed validity is separate from scientific completeness. Require at
least 5/6 complete usable interpretations, zero consequential wrong owner/scope,
missing required dependency, substitutions, destructive additions or unsafe handling
of ambiguity/preservation. Grade equivalent groupings by meaning, not order/text.
No progression on an incomplete panel. Freeze accepted runtime/output limits and
apply static, approved LAN readiness, separate smoke and independent authority gates.
Stop on infrastructure, integrity or custody failure; no replay/replacement.

**Response evidence before S06:** one separate frozen-record experiment, six turns
maximum, one attempt each, zero corrections/retries, no tools or mutation. Fixtures:
verified saved change; verified private but unsaved attempt; mixed partial completion;
pending two-source choice; inspected absence versus unknown; grounded informational
answer with no edits. Require 6/6 correct saved/unsaved/pending status, no invented
facts or claims of completion, and at least 5/6 complete useful replies. Capture raw
outputs; use independent grading, not another scorer. Admit after independent review
of the outcome-record contract; can use frozen synthetic verified records without H3
execution. This is not H4 and does not authorize integration.

**S04/H2** remains blocked on revised S03 planner progression. Extend action-selection
rubric to inspection, availability, existing state, ambiguity, safe no-op and blockers;
do not tell the worker which action to select. **S05/H3** follows H2: verified private
real-file completion, refreshed state, bounded recovery, dependencies and safe partial
completion; separately resolve named-section prerequisite before affected tests.
Freeze case count, action/correction/selection budgets and stop conditions separately
before each later gate rather than preauthorizing them here.

**S06** consumes reviewed planner, specialist, private completion and response evidence
(or explicit independent deferral after decisive negative evidence). Preserve S07–S09
vertical slices, S10–S13 conversational integration, and S14–S18 qualification and
product acceptance, including H4 extensibility. Current Beads hard edges stay in force:
S04 depends on S03.3, S05 on S04, and S06 on S03 and S05. Keep the response evidence
requirement within the existing S06 acceptance criteria; no separate epic or bypass.
The historical H1b condition is closed; its active Beads work remains open for the
revised progression decision. No implementation, live work, holdout consumption,
production routing or main merge is authorized by this document.
