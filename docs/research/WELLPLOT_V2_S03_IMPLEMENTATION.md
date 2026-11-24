# S03 H1 provider-free implementation handoff

Beads: `well_log_os-bdn.4`, in progress. Planning parent:
`002815f7ebbfa50b2390d559f55854f17ca4c153`.
This checkpoint is not live authority, empirical evidence or product acceptance.

The [frozen panel](WELLPLOT_V2_H1_PANEL.json) carries only requests, expected
compiler dispositions, and explicitly synthetic inspection fixtures. The
scientific grading expectations remain in the [planning record](WELLPLOT_V2_S01_S02_H1.md)
and never enter model messages. Panel artifact SHA-256:
`967b3f670e4d5763b8aaa37cdbf9805ef76a8e7f831ea5106567895126391402`.

Actual system prompt:

> Describe the requested scientific outcomes using only the request and supplied inspection. Preserve physical versus semantic channel clues, sources, scope, quantities, units and restrictions. Report unavailable or ambiguous work without substitution; ask for consequential clarification. Do not produce implementation steps, operation IDs or prerequisites.

The user message is `USER REQUEST:\n{exact request}\n\nINSPECTED CONTEXT:\n`
followed by the sorted-key JSON representation of that case's context.
The advertised schema is `_H1ObservationResponse.model_json_schema()` in
`planner.py`, digest (D5 canonical JSON):
`a3ffbc58e61eb6cd1ca05f6801e47da1ec978cc646dbf79bc422c71f3fd3ada4`.
It admits only an object with required `outcomes` (minimum one item). Each
item requires nonempty `statement` and `disposition` in
`requested | already_satisfied | unavailable | needs_clarification`, with
optional `qualifiers` (string array, default empty). Both objects forbid
extra fields. No outcome can be converted into an executable plan.

The existing planner compiles the original request first and retains its
actual result. The internal H1 argument must match a frozen case's complete
digest, exact request and compiler disposition; dependency-bearing and C2
requests remain forbidden. H04/H05/H07 are the only pinned coverage failures
that can reach H1 capture. The same structured call and D4 accounting are
used, with no normal correction block reached. A valid response stops even
without the observer; an invalid response propagates without correction.
Notebook/MCP do not receive an experiment control.

The D5 selector admits only the complete ordered H1 panel under an H1
descriptor, in planner-only mode. It retains the actual prompt/schema,
raw bodies, compiler trace, typed outcome, request counts, timing and
tokens in existing custody. Synthetic contexts have no real source path,
format, source hash or numerical data. The measured limits are 10 logical
and 10 physical attempts, zero corrections or SDK retries, temperature 0,
thinking disabled, cap 4096, 900 s provider timeout and the existing 10800 s
watchdog with 10 s grace.

## Remaining operational gate

Before live use, freeze the reviewed implementation, descriptor, ordered
case IDs, panel and schema hashes, config/SDK identity, exact worktree and
private evidence namespace. Run non-generative model/build/template/defaults
readiness over approved LAN execution. Obtain and independently accept a
separately authorized operational smoke proving this exact response model,
transport, accounting, custody and orderly stop, without consuming the
ten measured H1 observations. The existing A10 smoke does not certify the
H1 DTO; the H1 campaign selector intentionally rejects subsets. An
H1-specific smoke descriptor uses the existing canonical planner smoke
entrypoint, not the measured panel or a weakened selector. Then obtain
separate live campaign authority.

The operational fixture `H1-SMOKE` asks: “Could you display the natural gamma
radiation measurement?” Its synthetic, complete inventory contains one
addressable scalar GR curve (gAPI), with no real file or numerical data. The
compiler returns `NO_SUPPORTED_SEMANTICS`, not a coverage failure. The smoke
mode binds the request, synthetic fixture, system prompt, existing H1 schema,
harness, executable checkpoint, reviewed worktree and runtime identity.
Use `scripts/run_d5_live_campaign.sh planner-smoke h1-development AUTH_JSON`
only with this separate smoke authority: one generation and one physical
attempt, no correction or SDK retry, same thinking-off and output controls.

No live call, scientific result, holdout execution, mutation, activation
or merge was authorized in this implementation slice.

## Accepted H1a measured closeout

SOL and Human Authority accept H1a at
`ed87f7c2d84ea57733cb51200fa1ef7a638e8e2f`, campaign
`wellplot-v2-h1a-measured-20261124-001`. Paired ZIP SHA-256
`29b47b5528ea61e8d3f05ec74057c248144f0b6519d957ed78e0502e712e242c`;
authority `a309ae597f851ec12e389d757f327e1aeaf1e043183d6c5ddcb83ba1964084e1`;
terminal `31d4e63eb4887adf587f40d1eb21fa951319ed20dca054efc956453e11f5fc0b`.

Both conditions collected ten typed-valid first responses, ten logical and
physical attempts, no corrections, retries or authoring. Only system-message
content differed in the actual paired payloads. Scientific progression:
**PASS, 9/10 versus H1-R1 1/10**, for this exposed panel only. H02 falsely
asserted GR and resistivity shared one track. H01/H04 called Main Pass a track
but preserved the uniquely grounded target and pass under the frozen scoring.
False unavailability fell from nine to zero. No consequential substitution,
explicit scope violation or invented destructive outcome was identified.

| Verified totals | H1-R1 | H1a |
| --- | ---: | ---: |
| Input / cached / uncached tokens | 3,624 / 590 / 3,034 | 9,694 / 6,660 / 3,034 |
| Output tokens | 1,387 | 561 |
| Server prompt / generation seconds | 21.362 / 72.341 | 21.506 / 23.813 |

Equal uncached input here motivates testing stable instruction prefixes and
scoped dynamic context. It does not establish general caching equivalence,
causal latency improvement, or fresh scientific generalization. Both
conditions are consumed and immutable. Next: [H1b design](WELLPLOT_V2_H1B_DESIGN.md).

## Provider-free qualification

Python 3.12, existing virtualenv, `PYTHONPATH=src`:

```bash
.venv/bin/python -m pytest -q tests/test_code_mode_planner.py \
  tests/test_code_mode_workflow.py tests/test_d5_single_engine_convergence.py \
  tests/test_d5_5_model_io_custody.py tests/test_nlp_d5_live_semantic_qualification.py \
  -k 'not (final_population or c02)'
.venv/bin/python -m pytest -q tests/test_nlp_d5_live_semantic_qualification.py \
  -k 'first_pass_campaign or h1_planner or first_pass_authority'
```

297 scoped and 6 focused tests passed, both exit 0. The second run included
the final advertised-schema equality and compiler-trace assertions. Mock
HTTP transport observed all ten ordered cases with one logical and physical
attempt each, nine valid fixture responses and one deliberately invalid fixture,
zero corrections and no wire conversion. A separate mock timeout stopped the
campaign. The tests also covered exhaustive H08 inventory, equally eligible
H09 sources, production rejection, C2 blocking, tampering and unconditional
termination without a trace callback. Mock validity counts are not model results.
Local tests ran outside the sandbox after a one-line asyncio executor reproducer
isolated sandbox teardown hangs. No inference endpoint was contacted. Scoped
Ruff/format, compilation, shell syntax, diff, manifest and reachability checks
passed. This was not a repository-wide run.

## H1-R1 disposition and instruction recovery

H1-R1 completed once at `4a80e81ba682e94d7e83177d911029597949e9cd`:
10/10 typed, 10 logical and physical attempts, 0 corrections/retries.
Preliminary scientific grade: **1/10 (H08); progression failed**.
All ten outputs used `unavailable`. H01/H02/H03 conflated absence of samples
or presentation with absence of data; H04/H05/H06/H07 confused desired
state with already observed state or demanded implementation details;
H09/H10 misread literal mnemonic wording. H09's actual ambiguity was
source selection. H08 shows that genuine absence should still be reported.
Neither these observations nor the prior smoke resolve causal attribution.
See `workspace/evaluations/wellplot-v2-h1-measured-20261124-001/`;
sealed SOL review ZIP SHA-256:
`cc6ebd5e9339c2be66565a38776e5060fa92877adb01c78baaafd137b415a392`.

| Existing manual section / evidence | Reuse for role instruction | Check against current implementation |
| --- | --- | --- |
| [Concepts: Dataset and Composition](../site/concepts.md), [Domain Contract Matrix: Object Families, Dependency Graph and Compatibility Matrix](../site/reference/domain-contract-matrix.md) | Planner: inspected sources are independent of report/section/track/binding state. Sections scope passes; tracks group presentations. | Registry projects report, section, track, binding, fill and annotation capabilities. Do not require registry IDs for interpretation. |
| [Report Pages: Heading, Remarks, Tail and Detail Tables](../site/workflows/report-pages.md) and matrix Header Contract | Report worker: distinguish report title/subtitle, header slots and first-page content. Change only requested values; preserve unrelated slots. | Existing report worker contract and inspected slot identities govern; display labels alone are not slot identifiers. |
| [Matrix: Scale, Grid, and Raster Semantics](../site/reference/domain-contract-matrix.md) and [CBL reconstruction: sections and channel binding](../site/guides/example-1-cbl-reconstruction.md) | Section worker: distinguish scalar curves from depth-indexed rasters, existing binding from source channel, named pass from track. Preserve explicit scale, units and fill geometry. | `binding.curve` uses scalar channels; `binding.raster` is DLIS/array-track scoped; `fill.curve` is normal-track scoped. Capability registration alone does not prove a route is executable. |
| [LAS step-by-step workflow](../site/guides/example-7-agent-las-step-by-step.md), tracked LAS and CBL notebooks, and A09 custody evidence | Future planner examples: group works by report and logging pass. Future worker trajectories: incremental scoped changes, inspect refreshed state and verify before claiming completion. | Historical notebook helpers and public Python builders are not the active worker interface. `AuthoringService.create/update` use typed requests; `worker_contracts.py` currently selects `required_action` before generation. |
| [MCP API reference](../site/reference/mcp-api.md) and [MCP authoring model](../mcp-authoring-model.md) | Use as background documentation, not as a list of tools available to a model. | H1 has no tools. H2 must obtain its vocabulary from current worker DTO/lowering contracts, not advertise documented MCP `bind_curve`, `add_curve_fill`, or other public adapter operations as worker actions. C2 and the named resolver reservation remain unchanged. |

These are the three role-specific instruction outlines, not duplicate manuals.
Only the planner interpretation slice is developed fully here. Report/section
API examples and feedback trajectories wait for their experiments. In-context
demonstrations are an **adapted** technique ([Brown et al.](https://arxiv.org/abs/2005.14165));
limited, relevant context also avoids relying on long-context position
robustness ([Liu et al.](https://arxiv.org/abs/2307.03172)). Neither paper
establishes that this package will improve WellPlot or this model.

## H1a instructional package

Proposed exact system message: contents of the next code block, with internal
LFs, no surrounding fence and no trailing LF. Preserve the existing user
message: `USER REQUEST:\n{exact request}\n\nINSPECTED CONTEXT:\n`, then
the same sorted-key fixture JSON. No other messages or capability payload.

```text
You interpret scientific authoring requests for WellPlot. Describe what the scientist wants, not how to implement it. Your answer is not a plot, an API call, an execution decision, or a claim that the document was changed.

A source inventory describes available channels. A report contains sections, such as different logging passes; a section contains tracks; a track contains bindings that display source channels. A channel can be available even when no track displays it. Inspected metadata, including a synthetic fixture, is authoritative for this interpretation task. You do not need numerical samples, a renderer, existing tracks, or an algorithm to state a requested outcome.

Read the request as desired state, not as a question about whether the current document already contains that state. Report title and subtitle are separate report properties. Line color, numeric scale and fill geometry are presentation settings; absence of a current setting does not make a requested setting unavailable. A grouping request means the measurements should appear together, even if not currently bound. Preserve all requested outcomes, target scopes, exact values and units, ordering or grouping relationships, and explicit preservation constraints. Do not invent defaults, conversions, substitute channels or destructive changes.

An explicit physical mnemonic means the literal channel identifier, not a transformation or a special physical variant. Keep semantic terms semantic; mention a grounded channel only when the inspected context supports it. If several sources equally fit a literal selector and no route is specified, ask which source; do not claim the mnemonic itself is ambiguous.

Use requested for intended outcomes, including additions or revisions. Use already_satisfied only when inspected document state already meets the whole outcome. Use unavailable for an affirmatively absent required measurement in the relevant exhaustive inventory, not for unplotted or unspecified presentation. Use needs_clarification if a consequential choice remains unresolved. Retain any independent outcome that can still be stated. Return the outcomes schema only. No action verbs as API instructions, generated IDs, capability IDs or prerequisite selection.

Independent examples:

Request: Display the acoustic transit-time measurement.
Inspection: The selected source has addressable scalar DT (acoustic transit time, us/ft); the section has no tracks.
Response: {"outcomes":[{"disposition":"requested","statement":"Display acoustic transit time from the selected source."}]}

Request: In Calibration Pass, make the SP curve dashed and leave the other passes alone.
Inspection: Calibration Pass has an SP binding; its current line style is not supplied.
Response: {"outcomes":[{"disposition":"requested","statement":"Use a dashed line for the SP curve in Calibration Pass.","qualifiers":["Preserve all other passes."]}]}

Request: Display the literal CALX channel from North Well.
Inspection: North Well has an exhaustive inventory containing CALI and SP but not CALX.
Response: {"outcomes":[{"disposition":"unavailable","statement":"CALX is absent from North Well's complete channel inventory."}]}

Request: Display the literal DT channel.
Inspection: North Well and South Well each have addressable DT; neither source is preferred.
Response: {"outcomes":[{"disposition":"needs_clarification","statement":"Which source should supply literal DT: North Well or South Well?"}]}
```

Examples are independent synthetic cases (DT, SP and CALX, different scopes
and properties); no measured answer or historical failed response is in the
prompt. This is one combined instruction-and-demonstration intervention;
it cannot separate those elements or establish generalization on unseen
requests. Do not pad the prompt to the proposed planner range of 4,000–9,000
tokens: planner, report-worker and section-worker budget ranges are future
planning estimates, not H1a requirements.

Exact prompt SHA-256:
`ebc9aa1d1a01967e6088a6ec5b403192fa274fc9f19bba026ddf734f4035c013`.
Local measurement: 3,481 UTF-8 bytes, 470 whitespace-delimited words, four
examples validated against the existing H1 DTO. H1-R1 reported 352–391 input
tokens per case. Planning estimate for H1a: roughly 1,000–1,500 input tokens
per case including the unchanged user/context and schema/template overhead
as accounted by the runtime. This is not a tokenizer measurement; retain
actual runtime usage in the next evidence. No request was sent for costing.

### Frozen controls and implementation boundary

- Reuse H01–H10, in order, and the exact [panel](WELLPLOT_V2_H1_PANEL.json) and
  [grading expectations](WELLPLOT_V2_S01_S02_H1.md). Preserve panel SHA-256
  `967b3f670e4d5763b8aaa37cdbf9805ef76a8e7f831ea5106567895126391402` and
  DTO SHA-256 `a3ffbc58e61eb6cd1ca05f6801e47da1ec978cc646dbf79bc422c71f3fd3ada4`.
  Same configured Qwen, runtime identity, temperature 0, thinking disabled,
  cap 4096, 900 s timeout, and existing 10800 s watchdog; one response per
  case, ten logical/physical attempts, no corrections or retries.
- Only the internal H1 system-message selection in `SemanticPlanner.plan`
  and its exact prompt identity binding in existing D5 authority/preflight
  need adaptation. The current planner hardcodes H1-R1 instructions and
  measured authority does not separately bind the system-message digest.
  Pin the approved H1a prompt at its successor checkpoint; do not introduce a
  general prompt override or runtime documentation loader. Same fixture
  checks, compiler custody (including only H04/H05/H07), observer, accounting,
  launcher and termination; preserve ordinary planner, smoke and C2 behavior.
  No code changes under S03.1.
- Provider-free next gate: mock canonical HTTP for all ten exact payloads;
  prove only system-message bytes changed, checksum the prompt, verify
  raw custody, limits, typed rejection and zero downstream execution.
  Measure exact token usage with the qualified runtime when authorized;
  require static preflight, approved LAN readiness, separate accepted
  operational smoke as required, and fresh explicit measured authority.
- Grade against the original table. Report typed validity separately;
  incomplete panel or infrastructure interruption is not a scientific pass.
  At least 9/10 correct usable interpretations with zero consequential
  substitution, scope violation or destructive invention is required before
  proposing fresh H1b. On failure review mechanisms; no automatic retuning.
