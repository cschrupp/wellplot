# WellPlot V2: S01 evidence and S02 H1 freeze

Planning baseline: `fa10bd0b867b530ca820eb51b4856a3e53e4a88e`.
Beads: `well_log_os-bdn.2` (audit), `well_log_os-bdn.3` (preparation),
`well_log_os-bdn.4` (next gate). This is a proposed experimental freeze,
not implementation or live authority.

## S01: what is already known

- [A10 non-rediscovery preflight](A10_SEM_NON_REDISCOVERY_PREFLIGHT.md) and
  [first-pass R1](A10_FIRST_PASS_R1.md) separate first-pass measurement from
  corrected output. [R3–R5 synthesis](../architecture/PLANNER_WORKER_RESPONSIBILITY_REALIGNMENT_DESIGN.md)
  records R3 and R4 at 0/10 typed-valid and R5 F04 as a limited diagnostic.
  Form choice, correct-looking fragments, advertised schema compliance and
  local typed validity are not interchangeable. Do not assign ungraded
  historical output a scientific correctness score.
- [Smoke 003](../evaluations/agent-code-mode/A10-SEM-NL-PLANNER-SMOKE-003-qualification.md)
  demonstrates operational correction, not first-pass model capability.
  Provider timeouts and interrupted custody are infrastructure observations.
- The [active baseline](../agent-code-mode-current-baseline.md) records A09's
  deterministic CBL/VDL authoring, verification, reload and render evidence.
  [C2](../reviews/GATE_2B_C2_IMPLEMENTATION_CANDIDATE.md) adds compiler/custody
  coverage but intentionally rejects before inference; named resolver debt
  remains an execution prerequisite. Neither result measures model understanding.
- `SemanticPlanner.plan`, `_PlannerWirePlan` and `_planning_catalog` in
  `src/wellplot/agent/code_mode/planner.py` couple model output to task forms,
  capabilities and host compilation. Reuse registry facts, not model-generated
  capability closure. Worker `required_action` in `worker_contracts.py` is
  host-selected, so its existing DTO observations cannot establish H2 (action
  choice). H3 (completion from feedback) needs private sequential evidence;
  H4 (extensibility) must later exercise the existing registry, typed lowering,
  AuthoringService and renderer contracts, not invent an extension framework.

**Decision:** no new current-contract arm for this first feasibility decision.
History establishes the practical limitation and justifies testing a smaller
surface; it is not a paired control for this panel, and cannot establish a
causal improvement. A paired study would require a distinct question and
authority. S01 closes an evidence gap, not H2–H4 (PR-01–PR-13).

## S02: one proposed condition

**H1:** Can the configured model, given sufficient inspected context, express
the intended scientific outcomes and restrictions without generating
implementation bookkeeping? Observe ten first responses and nothing downstream.
This tests PR-02/04/06/08 directly; PR-03/13 are future implications, not graded
claims. Passing on synthetic development metadata does not establish real-file
execution, generalization or product readiness.

### Frozen development panel (ordered)

These are intentionally exposed development categories, not holdouts. The
exact texts and metadata below are proposed frozen inputs for review, not a
claim of unseen wording. Use synthetic, fully enumerated inspection fixtures
in the existing host summary shapes. They assert no facts about real LAS/DLIS.
Common context **C**: inspected source `Survey A`, complete inventory of
addressable scalar channels `GR` (gAPI; Gamma Ray), `RT` (ohm.m; Resistivity),
`RHOB` (g/cm3; Density), `NPHI` (v/v; Neutron Porosity). These are fixture
descriptions, not a semantic catalog expansion. Current report `Survey`, subtitle
`Initial`; section `Main Pass` contains separately labeled `GR` and
`Resistivity` tracks, each with a same-named curve (resistivity uses RT).
Both route to Survey A. No other sources, bindings or sections unless listed.
Use exact labels, no paths or samples.

| ID | Exact request | Context | Scientific expectation and acceptable alternatives |
| --- | --- | --- | --- |
| H01 | Could you show the gamma-ray measurement? | C | Display semantic Gamma Ray. Equivalent wording or a grounded GR pointer accompanying the semantic clue; not replacement of the clue by a guessed mnemonic. |
| H02 | Show physical GR alongside the resistivity measurement. | C | Exact physical GR and semantic resistivity as distinct outcomes. Either order; no requirement that they share a track. |
| H03 | Put the density and neutron porosity curves in the same track. | C | Both semantic measurements with an explicit shared track. One grouped outcome or two with the same grouping; no track IDs or scale choices required. |
| H04 | Split the fill of the existing physical GR curve at a baseline of 0 gAPI. | C | Existing GR, split fill and exact zero in gAPI. Equivalent split geometry wording is valid; fixed-baseline fill or a new curve is not. |
| H05 | Use a logarithmic scale from 0.2 to 2000 ohm.m on the resistivity curve. | C | Existing resistivity, logarithmic scale and both bounds and unit. Numeric equivalents and equivalent ohm-metre spelling accepted; no value conversion. |
| H06 | Make the GR line red in Main Pass only. | C plus Repeat Pass with its own GR curve routed to Survey A. | Change GR line color in Main Pass and preserve Repeat Pass. Red or exact red hex accepted; do not recolor fill. |
| H07 | Set the report title to Well Review and the subtitle to Main Survey. | C | Both exact strings in distinct fields; one or two outcomes accepted. |
| H08 | Plot the physical mnemonic ZZZ_UNKNOWN from Survey A. | C, its inventory explicitly exhaustive. | Flag requested channel unavailable for Survey A and do not plot a substitute. Either blocked or an explicit request for a different source/channel while retaining the unavailable selector. |
| H09 | Plot physical GR. | C with no existing tracks or selected/default source in the context projection; Survey B has an equally eligible, distinct addressable scalar GR (gAPI); both sources explicitly inspected and equally eligible. | Ask which source or explicitly mark the source selection unresolved, preserving both candidates and the exact mnemonic. No unilateral choice or combination. |
| H10 | Show physical GR without changing the existing Resistivity track. | C | Display GR (including noting already displayed if explicitly grounded) and preserve that track. No removal, reordering or restyling of Resistivity. |

For H09 represent an unbound target with the existing bounded summary shape;
if the current shape cannot distinguish complete inventory, absence of
preference, and ties, include only that explicit fixture information in the
experimental message. Test the actual serialized contexts before spending calls.

### Minimum experimental surface (separate authorization required)

One concise instruction: describe the requested scientific outcomes using
only the request and supplied inspection; preserve physical versus semantic
clues, scope, quantities and constraints; report unavailable or ambiguous
work without substituting. No operations, capability IDs, local refs, action
ordering, generated IDs or prerequisite selection. One small typed response
envelope: an ordered list of outcome statements with a typed disposition
(`requested`, `already_satisfied`, `unavailable`, `needs_clarification`);
each statement records the outcome or question and explicit scientific
qualifiers in text. Allow multiple statements to preserve independent work.
Require nonempty statements and forbid extra keys. This is an evidence DTO,
not an executable IR. Human review grades synonyms and parameters; JSON
success alone never establishes correctness.

| Existing location | Smallest proposed change and necessity |
| --- | --- |
| `planner.py`: request construction and generation inside `SemanticPlanner.plan` | At a successive experimental checkpoint, reuse the existing generation call and provider with the bounded prompt/DTO for the authorized planner-only observation. Stop on the first validated response via existing observation stop; no canonical plan conversion or C2 guard bypass. Preserve normal production behavior; if this cannot be isolated without a second maintained path, stop before implementation. |
| `scripts/nlp_d5_live_semantic_qualification.py`: `D5Authorization.__post_init__`, `_select_first_pass_turns`, population loader, `provider_free_preflight`, `execute_live_campaign`, runner case selection and CLI | Bind exactly one reviewed H1 development population, its ordered IDs and request/context digests to the existing authorization and selection at each boundary. Current first-pass authority requires A10 and its existing IDs; do not rename these requests as A10 or change its historical population. |
| Same script: `_build_planner_smoke_inputs`, `_ObservedLiveAdapter.execute_planner_case` and the existing wire capture | Extend the bounded context construction to validate/project these synthetic fixtures, including two inspected sources and missing-channel evidence. Existing path hardcodes one source and Main Log. Bind and capture the actual experimental response schema in existing custody. Do not add a second adapter or runner. |

Reuse `create_live_adapter`, canonical provider/config, `D5CampaignRunner`,
custody, limits and standard `scripts/run_d5_live_campaign.sh`. If that shell
launcher enumerates populations, add only the new closed population value at
the same admission boundary. No changes proposed to worker, resolver, grammar,
reconciler, persistence or renderer. Qualify pre-generation admission across
all ten requests with zero network calls before any live authority: the current
compiler does reject before the model sees some of these requests.

Read-only probe at the planning baseline: import `compile_request_contract`
and `is_c2_request` under `PYTHONPATH=src .venv/bin/python` and apply both to
the ten exact Request cells above (no summaries or provider constructed).
H04, H05 and H07 returned `COVERAGE_FAILURE`; H06 and H09 returned
`EXTRACTION_COMPLETE`; the other five returned `NO_SUPPORTED_SEMANTICS`.
All ten returned false for C2 family membership. An unchanged admission
boundary therefore cannot measure the full panel.

**Explicit authorization decision required:** in the existing planner-only
capture, record the canonical compiler's disposition for every case but
allow these three ordinary coverage failures to reach the same backend call
solely for a non-executable H1 observation. Bind this exception to the frozen
authority and exact requests, preserve the C2/dependency gate and keep normal
production compilation fail-closed. Capture must terminate on either valid
or invalid response before correction, attachment or conversion; an
unexpected return is a harness failure, never a plan. This is a proposed
measurement interlock, not justification to weaken the compiler. If this
containment cannot be proved with the existing planner and D5 capture, stop
instead of replacing cases or creating another workflow.

### Boundaries, grading and readiness

One condition, ordered H01–H10, maximum **10 logical and 10 physical
generation attempts**, zero native corrections and SDK retries. Propose
temperature 0, thinking disabled, 4096 output tokens, existing 900 s request
timeout and 10800 s campaign watchdog with 10 s termination grace. Configured
model is llama.cpp `qwen3.6-35b-a3b`; actual model/build/template/defaults and
runtime identity are unverified. Reserve a fresh private H1 namespace when
authority is frozen, not an A10 or holdout namespace.

Grade all ten independently against this table. Record semantic completeness,
scientific values and constraints, consequential clarification, and unsafe
additions separately from advertised schema and typed validity. Raw parseable
but invalid output may support forensic interpretation, not an accepted
contract response. Deterministic admission rejection is a host observation;
transport/custody interruption is infrastructure inconclusive, not a model
failure. Preserve every observation, stop on interruption, no automatic rerun.
No progression claim on an incomplete panel. Progression requires at least
9/10 complete, scientifically correct interpretations in usable responses and
no consequential substitution, scope violation or invented destructive outcome
in any case. A failure informs KEEP/SIMPLIFY/REJECT, not an automatic redesign.

Require separately reviewed implementation, exact executable and contextual
fixture preflight, approved LAN execution in the canonical checkout, rolling
non-generative readiness, separately authorized and accepted operational smoke,
then a frozen live authority with exact digests and budgets. Preserve complete
model I/O, diagnostics, timing, tokens, admission events and sealed custody.
No experimental response may reach worker dispatch or mutation.

Beads 1.3.4 exposes native `bd dolt push` / `bd dolt pull`; `bd dolt remote
list` shows a Git-backed Dolt origin. Only local persistence was checked.
Verify remote suitability and obtain separate sync authority before use.
Git planning push is not verification of off-machine issue recovery.
