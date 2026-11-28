# WellPlot V2 — Early S06 Architectural Consolidation

**Status:** Proposal for independent architectural review; S06 remains open.
**Scope:** Evidence synthesis and bounded future-experiment design only.
**No implementation, live inference, dependency change, or production activation is authorized.**

## Decision Requested

Select the minimum architecture direction supported by the completed isolated
role evidence, while retaining the negative S03 and specialist findings as
unresolved risks. Do not declare S06 complete. The existing Beads dependency
edges remain unchanged: integrated H2/S04 and S05 remain blocked pending an
explicitly reviewed reconciliation.

### Evidence inputs

| Evidence | Adjudicated result | Boundary |
| --- | --- | --- |
| Revised S03, `wellplot-v2-s03-revised-measured-20261125-001` | 4/6 scientifically correct; progression NOT MET. R03 added an unrequested RHOB relationship; R04 weakened mandatory same-track placement to permit overlay. | Combined planner/responsibility/context condition; not isolated causal evidence. |
| Isolated report/section specialists, `wellplot-v2-isolated-specialists-measured-20261126-001` | Typed 8/8; report 3/3, section 3/5; total 6/8; progression NOT MET. | No action was executed. W07/W08 are proposal-level observations. |
| Response agent, `wellplot-v2-response-agent-measured-20261127-001` | Typed 6/6, truthful 6/6, grounded 6/6, useful 6/6, fully complete 4/6; progression NOT MET. | Verified-record communication only; no production response route. |

The exact accepted identities and adjudications are recorded in the
[S03 closeout](../research/WELLPLOT_V2_S03_REVISED_CLOSEOUT.md),
[specialist closeout](../research/WELLPLOT_V2_SPECIALIST_CLOSEOUT.md), and
[response-agent closeout](../research/WELLPLOT_V2_RESPONSE_AGENT_CLOSEOUT.md).
No aggregate score is a controlled regression across these different
conditions, and none establishes generalization.

## Component Decision Matrix

| Component | Disposition | Evidence and bounded decision |
| --- | --- | --- |
| Planner | **ADAPT** | Keep the canonical `SemanticPlanner`, but keep its model-facing work centered on user outcomes and exact scientific constraints rather than implementation bookkeeping. S03 demonstrates both useful interpretation and material omission/addition risks. Do not replace the planner or declare that planner intent is recoverable from downstream operations. |
| Report specialist | **KEEP** | Its isolated development results were 3/3. Retain the existing report specialist and contract; this is component competence evidence only, not proof of integrated request coverage or publication safety. |
| Section specialist | **ADAPT** | Retain the existing specialist and action vocabulary. Its 3/5 result, W07 source ambiguity, and W08 lost pending geometry require stronger host admission and objective-lifecycle qualification before dependent work is authorized. Do not add action types or weaken validators to improve scores. |
| Dedicated response agent | **KEEP** | Retain as an isolated communication contract over verified outcomes. Its six answers were truthful, grounded, and useful, but only four met full completeness. No production route follows from this evidence. |
| Canonical authoring engine | **KEEP** | Preserve the one workflow, existing report/section actions, lowerers, reconciliation, private apply, `AuthoringService`, postcondition verification, and single-publication boundary. No shadow engine, alternate executor, or parallel conversational workflow. |
| Host admission and objective lifecycle | **ADAPT / QUALIFY** | Reuse canonical source inspection/enrichment, compiled obligations, task envelopes, execution results, shared postconditions, and private apply. Qualify independent source authority and end-to-end retention of original objectives, constraints, dependencies, and terminal dispositions. Current evidence does not prove those integrated properties for W07/W08. |
| Experimental naming and infrastructure | **DEFER** | Keep the existing D4/D5 path and historical labels for now. Simplify naming or infrastructure only when a demonstrated maintenance or usability problem warrants it; do not create a cleanup slice from observability debt alone. |

Evidence classifications: the single canonical execution and verification
path is an existing project invariant (`ESTABLISHED` within WellPlot). Reusing
existing inspections, obligations, private apply, and postconditions for
future host checks is `ADAPTED`. The strengths and failure modes above are
`EMPIRICALLY_SUPPORTED` only for the frozen exposed cases. Any new integrated
objective-lifecycle contract remains `NOVEL` until reviewed and qualified.

### Options and proposed selection

- **Keep every current boundary unchanged and proceed directly to integration:**
  rejected for now. S03 did not meet progression, and W07/W08 expose
  first-decision gaps that component evidence alone does not contain.
- **Replace the planner or add a second conversational engine:** rejected.
  The evidence does not isolate a planner-only cause, and this would violate
  the single-engine invariant.
- **Adapt the current planner/section responsibilities and qualify host-owned
  admission/completion while keeping the canonical execution path:** proposed.
  This addresses the observed gaps with the least architectural displacement;
  it does not authorize implementation or waive S03/H2/S05.

**Risks:** host checks can only independently verify facts and constraints
represented in authoritative inventories and canonical obligations; arbitrary
English coverage remains uncertain. Overly broad inference would create a
shadow parser, while overly narrow checks can miss omissions. More reasoning
may increase latency or exhaust output budget without improving correctness.
The proposed paired panel is small and exposed-development evidence only.

**Reversibility:** YES. This is a proposal; role dispositions and the
reasoning-mode diagnostic can be revised before implementation or live
authority. Preserve the current engine and safeguards while uncertainty is
resolved.

**Validation:** independent architectural review first; any later host change
must qualify source authority, exact objective/dependency custody, omissions,
safe ambiguity, refreshed-state behavior, shared postconditions, and
publication containment through existing canonical paths. Any reasoning-mode
comparison requires exact non-generative payload/runtime qualification, a
separately accepted operational smoke, frozen independent grading, and its own
live authority. Neither validation is authorized by this record.

## What the Evidence Does and Does Not Establish

### Measured behavior

- S03 R03 introduced an unrequested relationship; R04 did not preserve a strict
  same-track requirement. R06 correctly retained unavailable intent without
  substituting a channel or claiming feasibility/execution.
- W07 selected neither source explicitly in its typed action, yet its
  rationale assumed `early.las` despite two eligible SAL sources. A rationale
  is not source identity or source authority.
- W08 proposed the correct UPPER prerequisite and preserved LOWER, but its
  pending objective was null and it lost the exact blue between-curve shading
  geometry. The proposed prerequisite and fill were not executed.
- The response role reported the observed saved/private/blocked/pending states
  truthfully and usefully, with the two rubric completeness omissions above.

### Not established; do not claim containment

- W07 did not exercise canonical source enrichment or resolver admission.
  Existing `SOURCE_AMBIGUOUS` errors and source-binding checks are available,
  but the experiment does **not** establish that the production path currently
  blocks this exact W07 proposal. Future admission must consume authoritative
  eligible-source facts and reject or clarify a consequential unresolved
  choice; free-text rationale must never count as a selector.
- W08 did not traverse refreshed private state, dependent action selection, or
  final publication. It does **not** establish that an integrated workflow
  currently loses geometry at runtime. It demonstrates that the isolated
  first response did not preserve it. A later integrated qualification must
  bind the exact dependent objective to its original request and verify its
  final disposition.
- Existing compiled obligations and postconditions verify represented
  requirements; they do not prove arbitrary-English coverage or that every
  semantic constraint was extracted. S03 R03/R04 are evidence against
  assuming that typed validity or a successful private operation proves full
  request satisfaction.
- No isolated result establishes end-to-end conversational competence,
  transaction/publication safety for these cases, or a production response
  agent.

## Minimum Host-Owned Contracts to Qualify

These are proposed reuse/qualification boundaries, not authorization to
implement them in this documentation slice.

1. **Consequential source identity.** Build the eligible-source candidate set
   from the canonical inspected inventory. Require an exact source binding at
   the host boundary for consequential actions. A uniquely authorized source
   may be host-bound under existing policy; multiple eligible sources require
   clarification. Verify the selected source identity against the inspected
   candidate set before lowering. A model's prose, mnemonic match alone, or
   proposed task identity is not source authority. Keep channel interpretation
   in the existing authoring resolver.
2. **Original objective continuity.** Retain the immutable original request
   and its existing canonical requirement/provenance representation across
   worker tasks and private results. Any relationship/dependency must remain
   bound to its original endpoints, scope, exact constraint/geometry, and
   completion condition. Reuse existing host envelopes, task/result records,
   coverage and postcondition verification where they can carry this custody;
   do not introduce a parallel objective store. The existing C1/C2 provenance
   work is bounded and C2 remains non-executing, so it does not by itself
   qualify a multi-step lifecycle.
3. **Omission and weakened-constraint checks.** Independently check exact
   recognized values, source identities, exclusions, scope, numeric/unit
   constraints, ordering, and relationship constraints already represented by
   canonical obligations or inspected facts. For every recognized required
   outcome, require a matching accepted disposition and final verification.
   Unrepresented or unhandled required work remains unresolved/blocked; it
   must not silently count as whole-turn success. These checks are not a claim
   of deterministic arbitrary-English equivalence and must not become a
   mandatory regex parser for general natural language.
4. **Reuse one verification/mutation path.** Continue using source inspection
   and enrichment, existing capabilities and action models, reconciliation,
   `_apply_private_authoring()`, canonical `AuthoringService`, and the shared
   obligation/preservation postconditions. Validate any objective-specific
   evidence before the single existing publication boundary. Do not duplicate
   channel resolution, action lowering, execution, or verification.
5. **Minimum complete conversational slice.** Before calling the workflow
   integrated, qualify one existing entrypoint end-to-end: original request
   and dialogue; host-admitted objective/scope; specialist action against
   canonical state; refreshed verified private state before any dependent
   action; preservation of all original objectives and constraints; truthful
   clarification/unavailable outcomes; final shared verification; and at most
   one publication. No objective may be marked satisfied merely because it
   was acknowledged. Only verified state already satisfying it or verified
   execution can satisfy it. This is a proposed gate sequence, not current
   behavior or a waiver of S03/H2/S05.

The existing source-grounded boundaries include `compile_request_contract()`
and `_attach_compiled_requirements()` in `code_mode/planner.py`, source
candidate/error handling in `code_mode/enrichment.py`,
`verify_document_obligations()` and `verify_document_postconditions()` in
`code_mode/obligations.py`, the planner and worker graph in
`code_mode/workflow.py`, and `_apply_private_authoring()` in
`agent/_private_apply.py`. The planner and workflow currently fail closed for
dependency-bearing C2 work with `dependency_execution_not_authorized`; preserve
that gate. These code locations are reuse boundaries, not claims that all
proposed lifecycle checks already exist.

## Proposed Controlled Reasoning-Mode Diagnostic

**Decision:** consider a small paired diagnostic comparing Qwen's
thinking-disabled and thinking-enabled settings. This is a proposal for a
future separately authorized experiment, not an automatic progression gate,
not a prompt intervention, and not authorization to call the model.

### Question and scope

Question: on fresh scientific cases resembling the observed constraint and
source/objective failures, does enabling the model's documented reasoning
mode change first-response quality, failure type, token use, or latency under
otherwise identical conditions? The result would be local diagnostic evidence
only; six pairs cannot establish broad competence or justify production
activation.

Use six fresh development cases, three per role, drafted and independently
rubric-graded before any generation:

| Pair | Role | Targeted failure class |
| --- | --- | --- |
| P1 | Planner | Preserve separately requested outcomes without adding an attractive but unrequested cross-object relationship (R03 class). |
| P2 | Planner | Preserve mandatory same-track placement and exact dependent geometry rather than weakening it to overlay (R04 class). |
| P3 | Planner | Preserve a consequential explicit source/numeric/unit constraint and all requested objectives without substitution. |
| S1 | Section specialist | Multiple eligible sources: abstain/clarify rather than infer a source from rationale (W07 class). |
| S2 | Section specialist | Identify only the next supported prerequisite while retaining the exact dependent between-curve geometry for after verified co-location (W08 class). |
| S3 | Section specialist | Preserve scope, source identity, explicit values, and exclusions in a fresh bounded action-selection case. |

For each case, send the exact same request, dialogue/context, role manual,
advertised schema, runtime/model configuration, and output ceiling in both
conditions. Only `chat_template_kwargs.enable_thinking` differs. Do not reuse
S03, W07/W08, or response/specialist measured inputs; these are failure-class
templates, not replays. No grading answer or expected action is sent to the
model.

### Conditions and measurement

- Six paired items, one first response for each item in each condition: at
  most 12 logical generations and 12 physical attempts total.
- One request per cell; zero retries, corrections, or selective reruns.
- Keep temperature, model/build, prompt/manual, schema, context, and per-cell
  maximum output tokens identical; proposed cap is 4,096 generated tokens per
  cell, including reasoning tokens if the runtime counts them in the same
  output budget. Freeze the exact cap in the authority. Report, per case and
  condition, input tokens, the maximum output-token budget, total output
  tokens, visible answer tokens, any separately exposed reasoning-token
  counts, truncation/finish reason, and request latency. If the runtime does
  not expose reasoning-token usage separately, report it as unavailable rather
  than estimating it from text. Compare complete token and latency
  distributions descriptively; do not hide the extra reasoning cost inside a
  pooled average.
- Randomize or counterbalance which condition is sent first within each pair
  before the campaign. Keep calls serial and stateless; do not carry a prior
  answer into the paired request. Preserve exact request bodies and runtime
  identity.
- Freeze an independent rubric covering objective coverage, unauthorized
  additions/substitution, source authority, exact scope/geometry/numeric
  constraints, safe ambiguity handling, dependency retention, factual
  grounding, and typed validity. Grade each response independently and report
  paired changes per dimension. Do not define a new progression threshold or
  pool the outcomes with earlier panels.
- Infrastructure interruption, structured-output failure, and scientific
  failure remain separate dispositions. No automatic retry or replacement.

### Readiness and external evidence

Qwen's official usage documentation exposes `enable_thinking` as a chat
template control, including an explicit disabled setting. That establishes a
documented configuration variable, not compatibility with this deployed
Qwen/llama.cpp build or a quality benefit. Before any separate authority,
verify the exact enabled and disabled payload/template behavior, structured
output compatibility, exact input tokenization, context/output budget, and
reasoning-token accounting through non-generative supported runtime
operations. The enabled condition needs the applicable separately authorized
operational smoke before a scientific call.

Research on test-time compute reports gains for compute-optimized strategies
on challenging mathematical reasoning tasks, but does not establish that a
simple mode toggle improves this model's scientific planning or section
selection. The analogy supports testing a bounded variable, not predicting a
positive result. Evidence classes: configuration is `ESTABLISHED` by official
Qwen documentation; relevance and effect here are `NOVEL` and must be measured.

Sources:

- Qwen, [Quickstart: thinking and non-thinking modes](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html).
- Snell et al., [Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters](https://arxiv.org/abs/2408.03314), ICLR 2025. Its results concern compute-optimal reasoning strategies and math benchmarks; direct transfer to WellPlot is unestablished.

## Decision and Guardrails

The requested early disposition is: **ADAPT planner; KEEP report specialist;
ADAPT section specialist; KEEP isolated response-agent evidence; KEEP the
canonical authoring engine; ADAPT/QUALIFY host admission and objective
lifecycle; DEFER naming/infrastructure cleanup.** This is a decision proposal
for independent review, not an accepted architecture change.

No Beads dependency edge or task status changes are proposed. S03's negative
progression result remains active. Integrated H2/S04 and S05 stay blocked
until an explicitly reviewed decision reconciles their dependencies. C2
remains non-executing; its named-section resolution reservation remains a
prerequisite to any future dependency-aware execution authorization. No
runtime changes, prompt edits, live inference, holdout use, publication, or
merge to `main` are included.

**DRIFT_CHECK:** PASS. Active objective is evidence-supported early S06
consolidation. Exit is this durable, reviewable proposal and accepted
response-agent closeout. Scope is documentation and Beads recording only; the
next gate is architectural review. No provider/model call or benchmark use is
authorized. The work addresses the requested closeout and decision, not
hypothetical implementation infrastructure.
