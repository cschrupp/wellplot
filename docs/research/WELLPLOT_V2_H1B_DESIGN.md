# H1b: scientific planning and delegation

Design freeze proposed for SOL review, not runtime or live authority.
Beads `well_log_os-bdn.4.3`; parent S03 remains in progress.
H1a's accepted exposed-panel progression is recorded in the
[S03 evidence record](WELLPLOT_V2_S03_IMPLEMENTATION.md).

## Exact system message

Use the contents of the text block with LF, without its fence or trailing LF.
Its demonstrations are synthetic and independent of P01–P08.

```text
You are the scientific planner for WellPlot, a conversational application for creating and refining well-log presentations. Return scientific work for specialists to consider, not edits, API calls, execution steps, implementation prerequisites or claims that a new change has already happened.

The report owns report-wide title, subtitle and report-page content. A section is a logical panel, often one logging pass. A section contains tracks; a track groups displayed measurements. A binding displays a source channel in a track. A named pass is a section, not a track. A track title does not prove which channels it displays: use bindings. Channels in an inspected source can be available without any binding. Two curves in the same section are not necessarily in the same track.

Give report-wide objectives to the report specialist. Give channel display, scale, style, fills and other section-local objectives to the section specialist, scoped to the named or unambiguously identified section. Group tasks with the same worker and scope; grouping by section is distinct from grouping curves in a track. Split independently assessable objectives, but retain inseparable scientific relationships together. A scientific dependency means one outcome requires another to be satisfied first. Link the dependent to the earlier task using a task-local reference. Do not manufacture dependencies between independent edits or create tasks merely for internal construction like choosing IDs, creating a binding object or validating YAML.

Preserve exact physical mnemonics, semantic measurement clues, source identities, numeric values, units, geometry, ordering and restrictions. Use inspected state as evidence, not as a limit on new requested presentation. Use already_satisfied only if verified state matches the whole objective. Use unavailable for an affirmatively absent measurement in the relevant complete inventory. Use needs_clarification when a consequential choice is unresolved. Do not pick a source by guesswork or replace a channel. Retain independent safe work alongside blocked work.

Resolve phrases like "it" or "that curve" only from grounded prior turns and verified current state. A previous assistant proposal does not prove a change happened. Treat an answer to a pending clarification as resolving that choice for the original task; preserve still-applicable values, target and constraints. Do not treat unrelated conversation as new instructions.

Return only the structured tasks. Each task has a unique local ref, worker, scope, disposition and outcome. Use null scope for report work or unresolved scope, and state the needed clarification instead of guessing. Qualifiers carry explicit restrictions. depends_on lists only necessary other task refs, never object identifiers. Keep the set acyclic.

Example 1. Request: Set the report title to Calibration Summary and make the existing SP line dashed in Calibration Panel without changing its scale. Inspection: Calibration Panel is a section; its Signals track contains SP.
Response: {"tasks":[{"ref":"A","worker":"report","scope":null,"disposition":"requested","outcome":"Set report title to Calibration Summary."},{"ref":"B","worker":"section","scope":"Calibration Panel","disposition":"requested","outcome":"Make the existing SP line dashed.","qualifiers":["Preserve SP scale."]}]}

Example 2. Request: Show physical DT and DTS together in Vp/Vs Panel, then shade the region between them. Inspection: Vp/Vs Panel contains DT in the Sonic track; complete source inventory contains both DT and DTS.
Response: {"tasks":[{"ref":"A","worker":"section","scope":"Vp/Vs Panel","disposition":"requested","outcome":"Display literal DT and DTS together on one track."},{"ref":"B","worker":"section","scope":"Vp/Vs Panel","disposition":"requested","outcome":"Shade between the DT and DTS curves.","depends_on":["A"]}]}

Example 3. Verified prior result: Calibration Panel now displays CALI from Source West on Geometry. Request: Keep that curve and show physical PE too. Inspection: Complete Source West inventory contains CALI but not PE, and CALI is still displayed.
Response: {"tasks":[{"ref":"A","worker":"section","scope":"Calibration Panel","disposition":"already_satisfied","outcome":"Retain the verified CALI curve unchanged."},{"ref":"B","worker":"section","scope":"Calibration Panel","disposition":"unavailable","outcome":"Physical PE is absent from the inspected Source West inventory."}]}
```

### Sources and context

[Concepts](../site/concepts.md) and the [Domain Contract Matrix](../site/reference/domain-contract-matrix.md)
provide object ownership and compatible groupings; [Report Pages](../site/workflows/report-pages.md)
separates headings, remarks and tail. The [CBL workflow](../site/guides/example-1-cbl-reconstruction.md)
illustrates separate logging passes and binding; the [LAS workflow](../site/guides/example-7-agent-las-step-by-step.md)
illustrates grounded incremental revision. H1a identifies the hierarchy
mistakes explicitly. Current `CapabilityRegistry.planning_catalog()`,
`canonical_workers.py` and `worker_contracts.py` distinguish report, section,
tracks and bindings; registry membership is not execution permission.
No worker DTOs, API listings or MCP operations enter this interpretation input.
Use the previously reviewed scoped-context and few-shot research cited in
the [H1a record](WELLPLOT_V2_S03_IMPLEMENTATION.md#h1-r1-disposition-and-instruction-recovery).
[SHOP2](https://arxiv.org/abs/1106.4869) is precedent for separating compound
tasks from their decomposition and ordering. H1b adapts only that distinction:
its scientific dependencies are observations, not primitive operators or an
execution engine.

User message: exact UTF-8 bytes `USER REQUEST:\n{request}\n\nINSPECTED CONTEXT:\n`
then compact JSON (sorted keys, separators comma/colon, UTF-8 without ASCII
escaping) of the case context below. No grader expectations enter the prompt.
Use only the relevant inspected snapshot and dialogue, not full history.

Manual SHA-256: `6cb230f71729199521b52dd2d602553aad58f8c9827a3ec4209b17cdda9499bd`.
Local counts: 4,465 UTF-8 bytes, 571 whitespace-delimited words. Compact
context sizes are 109–590 bytes. Allow roughly 1,200–1,700 input tokens per
case including template/schema overhead, an engineering estimate, not a
tokenizer measurement. The deployed tokenizer was not invoked; capture
exact accounted input and cache tokens during separately authorized work.

## Frozen proposed fresh panel

These are new synthetic development scenarios authored for this design,
not selected from or checked against reserved holdouts. The JSON objects
are the complete context fixtures (no inferred defaults or extra state).
Section names and track names are distinct.

| ID | Exact request | Expected scientific plan and accepted alternatives |
| --- | --- | --- |
| P01 | Could you put the borehole diameter measurement on the log for Run Cedar? | Section Run Cedar: display semantic borehole diameter, optionally ground it in CALI from Cedar LAS. One requested task; no invented existing track or implementation prerequisite. |
| P02 | Rename this report to Pressure Review and replace the subtitle with Stage Three. | Report: exact title and subtitle, both requested. Two tasks or one grouped report task; no dependency, no header-slot or section edit. |
| P03 | Add the report remark Fluid contact under review, and use a linear scale from 1.8 to 2.8 g/cm3 for the density curve in Upper Review. | Two independent tasks: report remark with exact text; section Upper Review linear density scale with exact bounds and units. Either order, no fabricated dependency. |
| P04 | Make the sonic line blue in Baseline Pass only; in Check Pass, put sonic and caliper in the same track. | Two section groups. Baseline Pass: blue sonic line, preserve other settings. Check Pass: new co-location of sonic and caliper, currently on separate tracks. No recolor in Check Pass or regroup in Baseline Pass. |
| P05 | In Reservoir Panel, bring the two porosity measurements together on one track so I can see shaded crossover between them. | Section Reservoir Panel: display density porosity and neutron porosity together, then crossover fill referencing the display task. The fill direction is unspecified; carry the geometry request without guessing a directional threshold or inventing calibration. Report clarification only if consequential execution choice is explicitly identified; preserve both scientific objectives and the relation. |
| P06 | Make that curve dotted, and leave its scale alone. | Resolve the verified last edit to NPHI in Verification Pass; request dotted line there, preserve its scale. Do not restyle similarly named curves in other sections. |
| P07 | The second one, please. | Resolve the pending choice by ordered alternatives to Repeat Survey; request literal SGR in Correlation Panel, preserving earlier request and depth interval exactly. Do not re-ask or select Base Survey. |
| P08 | Add a report remark Repeat acquisition reviewed, keep the existing SP presentation as it is, and display physical XCAL from Revisitation LAS in Run Fir. | Report remark requested; section Run Fir: preserve verified SP presentation, and mark XCAL unavailable from the specified exhaustive inventory. Retain available independent work; no fallback or omission. |

```json
{"report":{"sections":[{"name":"Run Cedar","tracks":[]}]},"sources":[{"name":"Cedar LAS","section":"Run Cedar","inspected":true,"complete":true,"channels":[{"mnemonic":"CALI","measurement":"borehole diameter","kind":"scalar","addressable":true,"unit":"in"}]}]}
```
```json
{"report":{"title":"Working Copy","subtitle":"Stage Two","header_slots":[{"label":"Field","value":"Ridge"}]}}
```
```json
{"report":{"remarks":[],"sections":[{"name":"Upper Review","tracks":[{"name":"Lithology","bindings":[{"channel":"RHOB","measurement":"density","unit":"g/cm3","source":"Upper LAS"}]}]}]}}
```
```json
{"report":{"sections":[{"name":"Baseline Pass","tracks":[{"name":"Acoustic","bindings":[{"channel":"DT","measurement":"sonic","source":"Base LAS"}]}]},{"name":"Check Pass","tracks":[{"name":"Acoustic","bindings":[{"channel":"DT","measurement":"sonic","source":"Check LAS"}]},{"name":"Geometry","bindings":[{"channel":"CALI","measurement":"caliper","source":"Check LAS"}]}]}]}}
```
```json
{"report":{"sections":[{"name":"Reservoir Panel","tracks":[{"name":"Porosity","bindings":[{"channel":"DPHI","measurement":"density porosity","unit":"v/v","source":"Reservoir LAS"}]}]}]},"sources":[{"name":"Reservoir LAS","section":"Reservoir Panel","inspected":true,"complete":true,"channels":[{"mnemonic":"DPHI","measurement":"density porosity","kind":"scalar","addressable":true,"unit":"v/v"},{"mnemonic":"NPHI","measurement":"neutron porosity","kind":"scalar","addressable":true,"unit":"v/v"}]}]}
```
```json
{"dialogue":[{"role":"user","text":"Show neutron porosity in Verification Pass."},{"role":"assistant","text":"Neutron porosity has been added there."}],"verified_last_change":{"section":"Verification Pass","track":"Porosity","binding":"NPHI","source":"Verify LAS"},"report":{"sections":[{"name":"Verification Pass","tracks":[{"name":"Porosity","bindings":[{"channel":"NPHI","source":"Verify LAS","line":"solid","scale":{"kind":"linear","min":0,"max":0.45,"unit":"v/v"}}]}]},{"name":"Reference Pass","tracks":[{"name":"Porosity","bindings":[{"channel":"NPHI","source":"Reference LAS"}]}]}]}}
```
```json
{"dialogue":[{"role":"user","text":"Display physical SGR in Correlation Panel between 810 and 850 m."},{"role":"assistant","text":"Which inspected source should supply SGR: Base Survey first, or Repeat Survey second?"}],"report":{"sections":[{"name":"Correlation Panel","tracks":[]}]},"sources":[{"name":"Base Survey","inspected":true,"complete":true,"channels":[{"mnemonic":"SGR","kind":"scalar","addressable":true,"unit":"gAPI"}]},{"name":"Repeat Survey","inspected":true,"complete":true,"channels":[{"mnemonic":"SGR","kind":"scalar","addressable":true,"unit":"gAPI"}]}]}
```
```json
{"report":{"remarks":[],"sections":[{"name":"Run Fir","tracks":[{"name":"Electrical","bindings":[{"channel":"SP","source":"Revisitation LAS","unit":"mV"}]}]}]},"sources":[{"name":"Revisitation LAS","section":"Run Fir","inspected":true,"complete":true,"channels":[{"mnemonic":"SP","kind":"scalar","addressable":true,"unit":"mV"},{"mnemonic":"CALI","kind":"scalar","addressable":true,"unit":"in"}]}]}
```

## Proposed observation contract and limits

One object, required nonempty `tasks` array (1–8). Each object forbids extra
keys and requires nonempty `ref` (A–H), `worker` (report/section), `scope`
(nonempty string or null), `disposition` (reuse the four H1 dispositions),
and nonempty `outcome` text. Optional `qualifiers` (string array) and
`depends_on` (array of local refs) default to empty. Local validation:
unique refs, report scope null, section scope null only for unresolved work,
and dependency references exist, are distinct and acyclic. Reordering an
equivalent graph is accepted; presentation order is not execution authority.
No host IDs, callable payloads, capability closures or schema for API
operations. The example payloads are proposals, not executable plans.

H1's existing reduced DTO has no typed worker, scope or dependencies.
The canonical `_PlannerWirePlan` instead carries per-worker task forms and
operation capabilities in a production-oriented schema. Do not stretch
either to grant execution authority or encode edges in free text. The minimal
future change is an H1b-only observational DTO and frozen message branch at
the same `SemanticPlanner.plan` generation boundary; existing D4 response
role accounting recognizes it as planner, and the existing D5
`D5Authorization`, selection, preflight, observer and custody bind eight exact
requests/contexts and this prompt/schema. Reuse launcher, provider and raw
capture. Like H1a, stop unconditionally on first response, even with no
observer callback; never convert, attach, dispatch or mutate.

The current H1 lane cannot accept any P-case as written: case digests,
population and known compiler dispositions are frozen to H1. A read-only
probe at `ed87f7c2d84ea57733cb51200fa1ef7a638e8e2f` using the real
`compile_request_contract` and `is_c2_request` found:

| Cases | Current compiler status |
| --- | --- |
| P01, P05, P06, P07 | `EXTRACTION_COMPLETE` |
| P02, P03, P04, P08 | `NO_SUPPORTED_SEMANTICS` |

All eight had no diagnostics, no dependencies and false C2 membership.
No coverage-failure exception is proposed. Recheck these dispositions in
provider-free qualification; drift stops the experiment. The capture
context, not deterministic compilation, supplies prior dialogue. **Never**
bypass recognized C2 or dependency-bearing compiler output: the scientific
edge in P05 is an experimental response, not a trusted request dependency.
If a case conflicts with that containment, stop for review, not live probing
or silent replacement. No authorization for runtime changes exists here.

Use one first response per case, max eight logical and eight physical,
zero corrections or SDK retries; propose the same configured Qwen runtime,
temperature zero, thinking disabled, 4096 output cap, 900 s timeout and
10800 s watchdog. Freeze exact endpoint/build/config/template, panel,
prompt/schema and evidence authority before launch. Require provider-free
mock qualification, approved non-generative LAN readiness, separate
accepted operational smoke as applicable and separate measured authority.
Grade typed validity, scientific interpretation and decomposition/delegation
separately. At least 7/8 complete correct plans, and mandatory correctness
for consequential ownership, scope, dependencies, source ambiguity and
preservation. Consequential substitution, unsafe scope expansion or invented
destruction blocks progression. Unusable/incomplete observations do not
establish progression. H2/H3 remain blocked; decisive negatives may take the
reviewed early S06 route.
