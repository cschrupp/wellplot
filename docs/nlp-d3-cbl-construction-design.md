# WellPlot NLP D3 — One-Shot CBL/VDL Construction Design

## Status

`DESIGN_ONLY / IMPLEMENTATION_NOT_AUTHORIZED`

Design authorization: `WELLPLOT-NLP-D3-DESIGN-001`

Design rework authorization: `WELLPLOT-NLP-D3-DESIGN-REWORK-001`

Rework parent: `92026e1cfa89f6ec5e5761cff37126252108b2c9`

Input baseline: `694f0121c11e21d1baa7a01dcae52045cfa4dd28` (`WELLPLOT_NLP_D2E_ACCEPTED`)

Design branch: `delivery/nlp-d3-cbl-construction-design`

This document freezes the D3 design only. It authorizes no implementation, provider or endpoint call, model inference, D4 work, release promotion, or production routing change.

---

# 1. Delivery Requirement

D3 closes the deterministic `CBL-CONSTRUCT` workflow defined by the NLP completion plan.

The acceptance object is one substantial scientist request through the public notebook-facing construction API that produces one persisted, validated, renderable CBL/VDL packet without manual repair of intermediate planner state.

D3 must close the full deterministic CBL checklist:

- `CBL-01` — report/header presentation;
- `CBL-02` — remarks/content;
- `CBL-03` — main/repeat section identity and order;
- `CBL-04` — ordered track construction;
- `CBL-05` — source/channel bindings and multiplicity;
- `CBL-06` — depth/reference-track semantics measured by the frozen verifier;
- `CBL-07` — VDL raster settings;
- `CBL-08` — explicit labels/scales/styles/widths;
- `CBL-09` — canonical persistence and successful real render.

D3 is not a planner benchmark. A correct plan or worker artifact is insufficient unless the final persisted document passes `scripts/verify_cbl_packet.py` and renders successfully.

---

# 2. Relationship to Historical CBL Evidence

The repository already contains useful but non-delivery evidence:

- `tests/fixtures/agentic_cbl/frozen_prompt.txt`;
- `tests/fixtures/agentic_cbl/compile_contract.json`;
- `tests/test_cbl_compile_only_graph.py`;
- the production CBL example and packet blueprint;
- CM-56 source/context research.

Those artifacts prove that the intended packet is well specified and that older/research compilation paths can represent large portions of it.

They do **not** establish D3.

D3 must use the current public `DirectNotebookSession.run(...)` / Code Mode v2 path accepted by the current delivery program.

Do not promote the legacy reconstruction graph, typed worker, or V2R research path merely because historical CBL evidence exists.

---

# 3. Public Boundary

The D3 integration test must enter through exactly one construction call:

```python
result = await DirectNotebookSession.run(
    goal=D3_REQUEST,
    output_logfile=<test-local output>,
    source_logfile_path=<test-local cased-hole source scaffold>,
)
```

Required public semantics:

```text
request_kind = author
mode         = reconstruct
```

No follow-up `revise()` call may be used to make the final packet pass.

No direct authoring service repair may be applied after `run()`.

No manual YAML repair may occur after `run()`.

The final output from that one call is the D3 acceptance artifact.

---

# 4. Frozen Scientist Request

D3 uses the established substantial CBL prompt already carried by:

```text
tests/fixtures/agentic_cbl/frozen_prompt.txt
```

with one deterministic staging normalization only.

The historical source lines:

```text
- main: workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis
- repeat: workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis
```

must be normalized for the test-local staged project to:

```text
- main: CBL_Main.dlis
- repeat: CBL_Repeat.dlis
```

All other prompt text remains byte-for-byte identical.

The normalized request therefore retains all existing scientific and presentation requirements:

- three service titles;
- all requested well/header values;
- three requested remarks;
- main and repeat packet sections;
- four tracks in exact order on each section;
- exact widths and kinds;
- the four combo curves;
- the three depth/reference-track curves;
- two distinct CBL bindings on one track;
- VDL raster;
- explicit scales;
- explicit labels;
- explicit colors;
- explicit line widths and requested dashed/dotted styles;
- VDL x scale;
- VDL colormap;
- colorbar;
- sample axis;
- hidden VDL vertical main/secondary grid lines;
- unsupported vendor-only packet pieces explicitly excluded.

Implementation must compute and record the SHA-256 of the normalized request used in the test.

Expected values belong only in this deterministic acceptance fixture/test contract. They must not be added to production prompts or runtime code.

---

# 5. Construction Scaffold Ownership

D3 is a construction workflow over a stable cased-hole packet scaffold, not construction from an untyped empty document.

That is deliberate and consistent with the scientist instruction:

```text
Keep the cased-hole scaffold intact.
Keep the section ids main_pass and repeat_pass.
```

The canonical model requires every `AuthoringSectionSpec` to contain at least one track. Therefore a section shell with `tracks: []` is not a valid D3 seed and is explicitly rejected by this design.

The minimum valid scaffold owns only mechanically stable packet structure that is not the scientist's requested scientific binding content.

## Scaffold may provide

- cased-hole header slot structure;
- page/depth/output defaults;
- tail scaffold;
- exactly two ordered source-bearing section shells:
  - `main_pass`
  - `repeat_pass`;
- section titles:
  - `Main Pass`
  - `Repeat Pass`;
- each section's declared staged DLIS source;
- exactly one structural anchor track per section:
  - id `combo`
  - kind `normal`
  - title `Combo`
  - width `50 mm`
  - zero bindings
  - zero fills.

The `combo` anchor exists only because the canonical section contract requires at least one track and because `combo` is the requested first final track. It must contain no scientific curve content before the public request.

## Scaffold must NOT provide

- requested header values;
- requested service-title values;
- requested remarks;
- any combo curve binding;
- the requested `depth` track;
- the requested `cbl` track;
- the requested `vdl` track;
- any curve binding;
- any raster binding;
- any requested CBL duplication;
- any requested VDL presentation settings.

Thus D3 does **not** claim that the request creates eight tracks from zero. It proves that one scientist request transforms two minimal valid source-bearing section scaffolds containing only structural `combo` anchors into the complete two-section CBL/VDL packet.

The scientist request remains responsible for all 20 scientific bindings and for creating the remaining six tracks.

---

# 6. Test-Local Scaffold Construction

Build the test-local scaffold from the stable report structure in:

```text
tests/fixtures/agentic_cbl/base.template.yaml
```

Do not modify that historical fixture merely to seed D3.

Create one self-contained test-local source logfile with the template's report/page/depth/tail/header-slot structure and exactly two canonical sections.

Conceptually:

```yaml
sections:
  - id: main_pass
    title: Main Pass
    data_source: CBL_Main.dlis
    tracks:
      - id: combo
        kind: normal
        title: Combo
        width_mm: 50
        bindings: []

  - id: repeat_pass
    title: Repeat Pass
    data_source: CBL_Repeat.dlis
    tracks:
      - id: combo
        kind: normal
        title: Combo
        width_mm: 50
        bindings: []
```

The exact serialized legacy/logfile envelope may follow current normal authoring/logfile conventions.

Before `run()`:

```text
section count = 2

main_pass tracks   = [combo]
repeat_pass tracks = [combo]

each combo:
  kind       = normal
  title      = Combo
  width_mm   = 50
  bindings   = []
  fills      = []

total bindings = 0
```

There must be no starting remarks satisfying the frozen prompt.

The scaffold's stable page/output/tail settings remain part of the cased-hole scaffold and should be preserved by the one-shot request, not rewritten merely to earn verifier credit.

---

# 7. Reproducible Real-DLIS Fixture Requirement

D3 must use real renderable DLIS bytes, but the acceptance inputs must also be reproducible from a clean repository checkout.

Independent review established that:

```text
workspace/ is gitignored
workspace/data/CBL_Main.dlis is not committed
workspace/data/CBL_Repeat.dlis is not committed
```

Therefore machine-local `workspace/data` files are **not** an acceptable frozen D3 test dependency.

## Required future fixture location

Before D3 implementation can claim deterministic acceptance, the two real files must become versioned D3 test fixtures at:

```text
tests/fixtures/agentic_cbl/data/CBL_Main.dlis
tests/fixtures/agentic_cbl/data/CBL_Repeat.dlis
```

The implementation must also add:

```text
tests/fixtures/agentic_cbl/data/manifest.json
```

containing, for each file:

- exact filename;
- byte size;
- SHA-256;
- provenance/source description;
- redistribution basis or permission status;
- expected source format `dlis`;
- required D3 channel mnemonics.

If the files are too large for ordinary Git policy, Git LFS is the preferred versioned transport and the required `.gitattributes` change becomes part of the D3 implementation scope.

## Provenance / redistribution gate

The existing repository notes describe these as public or repository-provided demonstration data but also instruct users to confirm provenance and redistribution rights.

D3 must not silently convert that ambiguity into a committed binary fixture.

Before committing the fixture bytes, the implementation operator must establish and record a redistribution basis sufficient for the repository's test use.

If redistribution cannot be established:

```text
STOP
```

and request a data-fixture governance decision. Do not substitute machine-local acceptance.

## Fixture integrity

The D3 integration test must:

1. load the manifest;
2. SHA-256 both versioned files;
3. require exact manifest matches;
4. copy them into the test-local project as:
   - `CBL_Main.dlis`
   - `CBL_Repeat.dlis`;
5. require real source inspection and real rendering from those copied bytes.

The scaffold declares only the staged test-local filenames.

Do not:

- use `workspace/data` as the acceptance source;
- replace the files with text placeholders;
- fake the source loader;
- mock the renderer;
- skip the D3 acceptance test when fixtures are absent;
- silently fetch unpinned mutable URLs;
- accept a hash mismatch.

After D3 implementation is complete, a clean clone with its versioned fixture transport must be sufficient to execute D3 without workstation-specific files.

---

# 8. Preflight: Scaffold Must Not Already Satisfy D3

Before the public `run()` call, inspect the scaffold and prove it is scientifically incomplete.

At minimum:

```text
main_pass tracks   = [combo]
repeat_pass tracks = [combo]

main combo bindings   = 0
repeat combo bindings = 0

depth track absent
cbl track absent
vdl track absent

total bindings = 0
requested remarks absent
requested service-title values not already complete
```

Run the frozen CBL verifier against the starting scaffold as diagnostic evidence.

It must **not** report full CBL acceptance.

At minimum the starting scaffold must fail/not satisfy the scientific construction dimensions corresponding to:

```text
CBL-02
CBL-04
CBL-05
CBL-07
CBL-08
```

and should fail other content dimensions that depend on the requested values.

This prevents D3 from passing by seeding the final scientific answer while still respecting the canonical requirement that every section begin with at least one track.

---

# 9. Frozen Deterministic Plan and Semantic Ownership

D3 deterministic acceptance uses zero provider/model calls.

A test-local planner must record its invocation and return one plan containing:

- one report task;
- one main-pass section task;
- one repeat-pass section task.

Planner call requirements:

```text
call count = 1
mode       = reconstruct
request    = exact normalized D3 request
```

The planner's current-document summary must show the source scaffold's section IDs:

```text
main_pass
repeat_pass
```

The planner source summary must expose two source labels corresponding to the staged filenames.

The D3 planner fixture must prove **semantic decomposition**, not merely return three work units. Scientific values must be present in the task that owns them because workers receive isolated task payloads.

## Report task

```text
capability_ids = ("report.standard",)
```

The report task requirements must contain only report-wide scientist semantics:

- the three service titles;
- all requested general header values;
- the requested run/logging detail values;
- the three requested remarks and their required phrases;
- the instruction to keep the supported packet boundary and not invent unsupported vendor-only content.

The report task must not carry combo/depth/CBL/VDL track construction requirements.

The deterministic report backend must assert its actual `ReportTask.requirements` contains the frozen report semantic set before emitting a program.

## Main section task

```text
existing_section_hint = "Main Pass"
source_hints          = ("CBL_Main.dlis",)

capabilities:
  section.log_plot
  track.normal
  track.reference
  track.array
  binding.curve
  binding.raster
```

Its `requirements` must independently preserve the complete local scientific contract:

- preserve/use the existing `combo` anchor as the first 50 mm normal track;
- add `depth` as a 10 mm reference track;
- add `cbl` as a 44 mm normal track;
- add `vdl` as a 48 mm array track with x-scale 200-1200;
- combo curves:
  - ECGR_STGC, full label, scale 0-150, green, width 0.8;
  - TT, full label, scale 200-400 reverse, blue, width 0.75;
  - TENS, full label, scale 5000-0, dark, dashed, width 0.65;
  - MTEM, full label, scale 100-500, dark, width 0.9;
- depth/reference curves:
  - STIT, full label, 0-50, dark, width 0.65;
  - TDSP, label `Cable Drag`, 0-50, brown, dotted, width 0.65;
  - VSEC, label `Tool_Tot. Drag`, 0-50, blue, dashed, width 0.65;
- two distinct CBL bindings to channel `CBL`, both with the full CBL label:
  - 0-100 dark width 0.75;
  - 0-10 blue dashed width 0.65;
- VDL raster:
  - channel VDL;
  - full requested label;
  - profile vdl;
  - colormap gray_r;
  - hidden vertical main and secondary grid lines;
  - colorbar enabled, label Amplitude, position header;
  - sample axis enabled, unit us, 200-1200, 7 ticks, origin 40, step 10.

## Repeat section task

```text
existing_section_hint = "Repeat Pass"
source_hints          = ("CBL_Repeat.dlis",)

capabilities:
  section.log_plot
  track.normal
  track.reference
  track.array
  binding.curve
  binding.raster
```

The repeat task must carry the same complete local scientific requirements independently. It may not rely on the main task, report task, sibling worker, external call order, or a test-global CBL answer object.

## Required planner-to-worker chain of custody

The deterministic section backend must parse the actual serialized `section_task` in its `ProgramGenerationRequest` and assert that the local frozen semantic values above are present before returning any controlled program.

The backend may use test constants to **verify** the received semantic payload. It must not use those constants as a substitute for missing planner semantics.

Therefore this is forbidden:

```text
task says only "build CBL section"
+
test backend knows the golden packet
+
backend emits full packet anyway
```

The accepted chain must be:

```text
scientist request
-> planner-owned task-local semantics
-> isolated worker task payload
-> host-grounded source/track context
-> restricted program
-> canonical intent
```

The two tasks must remain distinct and ordered main then repeat.

No section task may select both sources.

---

# 10. Source-Grounding Contract

The current public adapter builds source candidates only from sources declared by the seeded scaffold.

D3 must prove:

```text
main task   -> exactly the staged CBL_Main.dlis candidate
repeat task -> exactly the staged CBL_Repeat.dlis candidate
```

Each selected source must expose, through real deterministic source inspection, at least:

```text
ECGR_STGC scalar
TT        scalar
TENS      scalar
MTEM      scalar
STIT      scalar
TDSP      scalar
VSEC      scalar
CBL       scalar
VDL       array
```

The worker backend must inspect its actual bounded `section_context.sources[*].channels` before emitting its program.

Do not accept channel presence merely because the mnemonic appears in the scientist prompt.

No source/channel substitution is permitted.

---

# 11. Worker Ownership

Expected graph ownership for the successful one-shot compile:

```text
report workers  = 1
section workers = 2
worker_count    = 3

successful_workers = 3
failed_workers     = 0
```

Expected worker order in public compilation evidence:

```text
plan_order 0 -> report
plan_order 1 -> main section
plan_order 2 -> repeat section
```

No repair is expected.

Any repair must be reported and independently reviewed; it may not alter scientific values or source/channel identities.

The report worker must emit no sections.

Each section worker must emit exactly one sparse fragment targeting its host-selected section and must emit no report-wide state.

---

# 12. Report Worker Contract

Current Code Mode v2 report vocabulary is sufficient for the D3 report requirements.

No report-worker production change is expected.

The deterministic report backend must inspect the actual bounded report context and prove the required host-approved header/detail/service slots exist before emitting its program.

## General header values

Set the scientist-requested values through exact host-approved keys:

```text
company             = University of Utah
well                = FORGE 16B (78)-32
field               = Utah Forge
county              = Beaver
country             = Utah
section             = NWSW 32
township            = 26
range               = 9
footage             = 972' FSL & 523' FWL
latitude            = 38.501242
longitude           = -112.882661
logging_date        = 08-May-2023
measured_from       = Kelly Bushing
log_measured_from   = Kelly Bushing
elevation_kb        = 5445.50 ft
elevation_gl        = 5415.00 ft
elevation_df        = 5445.00 ft
top_log_interval    = 25.00 ft
bottom_log_interval = 4845.00 ft
fluid_type          = Fresh Water
```

Use the scaffold's actual approved `country` key for the scientist's State value because the frozen verifier treats state/country as the shared semantic slot.

## Service titles

Use the actual host-provided service-title slot IDs, in scaffold order, to set:

```text
Cement Bond Log
Variable Density Log
Gamma Ray - CCL
```

Do not hard-code a slot identifier unless the worker context proves that exact ID exists.

## Detail values

Use exact host-approved detail keys:

```text
run_number         = ONE
driller_depth      = 4980.00 ft
logged_depth       = TD Not Tag
fluid_density      = 8.4 lbm/gal
bottom_temperature = 177.2 degF
logged_by          = D. May / D. Jones
witnessed_by       = Leroy Swearingen
```

## Remarks

Create exactly the requested three remark blocks with stable test-owned IDs:

```text
Supported Reconstruction Scope
Data Sources
Public Data and IP Notice
```

Each must retain the scientist-requested phrase(s) checked by the frozen verifier.

## Scaffold settings

Do not mutate page/output/tail merely because the verifier checks them if the scaffold already carries the requested stable packet defaults.

Preserving those defaults is part of the "keep the cased-hole scaffold intact" contract.

---

# 13. Section Construction Contract

Each section worker targets one existing section shell:

```python
report = wp.report()
section = wp.target_section(report)
```

The existing `combo` anchor is host-owned structure and must be selected through grounded existing-track evidence:

```python
combo = wp.target_track(section, track_id="combo")
```

The worker then adds the four requested combo curve bindings to that existing track.

It creates exactly three new tracks after the anchor, in this order:

```text
depth
cbl
vdl
```

Final track contract on both sections:

| Track | Origin | Kind | Width |
| --- | --- | --- | ---: |
| combo | existing structural anchor | normal | 50 mm |
| depth | D3 request | reference | 10 mm |
| cbl | D3 request | normal | 44 mm |
| vdl | D3 request | array | 48 mm |

The final canonical order must be:

```text
combo
depth
cbl
vdl
```

No fifth track.

No reordered track.

No duplicate `combo` track.

No track may be created in the sibling section.

D3 must explicitly prove that the existing anchor remained the same canonical track identity and acquired exactly the four requested combo bindings.

---

# 14. Combo Track Contract

Create exactly four scalar bindings, in order.

## ECGR_STGC

```text
channel    = ECGR_STGC
label      = Gamma Ray (ECGR_STGC) QTGC-B
scale      = linear 0 to 150
reverse    = false
color      = #16a34a
line_width = 0.8
```

## TT

```text
channel    = TT
label      = Transit Time for CBL (TT) QSLT-B
scale      = linear 200 to 400
reverse    = true
color      = #2142ff
line_width = 0.75
```

## TENS

```text
channel    = TENS
label      = Cable Tension (TENS)
scale      = linear 5000 to 0
reverse    = false
color      = #111111
line_style = dashed
line_width = 0.65
```

## MTEM

```text
channel    = MTEM
label      = Mud Temperature (MTEM) LEH-MT
scale      = linear 100 to 500
reverse    = false
color      = #111111
line_width = 0.9
```

---

# 15. Depth / Reference Track Contract

The `depth` track must be `kind="reference"`.

That track-kind requirement is the current frozen CBL-06 acceptance semantic.

Create exactly three scalar bindings, in order:

## STIT

```text
channel    = STIT
label      = Stuck Tool Indicator, Total (STIT)
scale      = linear 0 to 50
color      = #111111
line_width = 0.65
```

## TDSP

```text
channel    = TDSP
label      = Cable Drag
scale      = linear 0 to 50
color      = #92400e
line_style = dotted
line_width = 0.65
```

## VSEC

```text
channel    = VSEC
label      = Tool_Tot. Drag
scale      = linear 0 to 50
color      = #1d4ed8
line_style = dashed
line_width = 0.65
```

D3 does not add a new reference-overlay/lane semantic beyond what the current frozen verifier requests and checks.

Do not broaden D3 into a new reference-overlay feature slice.

---

# 16. Dual CBL Contract

The `cbl` track must contain exactly two distinct curve bindings to the same real source channel `CBL`.

Both labels:

```text
CBL Amplitude (CBL) QSLT-B
```

First binding:

```text
scale      = linear 0 to 100
color      = #111111
line_width = 0.75
```

Second binding:

```text
scale      = linear 0 to 10
color      = #2563eb
line_style = dashed
line_width = 0.65
```

Use separate allocator-owned binding identities.

The scientist did not request exact binding IDs.

Acceptance requires:

```text
binding_id_1 != binding_id_2
```

on both sections.

---

# 17. VDL Raster Contract

The `vdl` track must be:

```text
kind     = array
width_mm = 48
x scale  = linear 200 to 1200
```

Its vertical grid settings must explicitly persist:

```text
vertical_main_visible      = false
vertical_secondary_visible = false
```

Create exactly one raster binding:

```text
channel  = VDL
label    = VDL VariableDensity (VDL) QSLT-B
profile  = vdl
colormap = gray_r
```

Colorbar:

```text
enabled  = true
label    = Amplitude
position = header
```

Sample axis:

```text
enabled       = true
unit          = us
minimum       = 200
maximum       = 1200
tick_count    = 7
source_origin = 40
source_step   = 10
```

These values must be explicit canonical output, not renderer-only defaults.

---

# 18. Known Code Mode Representability Gaps

At frozen D2E baseline, canonical models already represent all requested D3 scientific output, but two bounded worker-surface gaps remain.

## A. VDL executable SDK bridge

`IntentBuilder.add_raster()` already accepts typed colorbar/sample-axis objects, and canonical tracks already carry grid intent.

The missing layer is the executable authoring-program vocabulary.

Current `wp.raster(...)` does not expose the requested colorbar/sample-axis fields.

Current `wp.track(...)` can express x-scale but not the requested VDL vertical-grid visibility.

## B. Empty-anchor existing-track grounding

D3 now uses a minimum valid existing `combo` anchor with zero bindings.

The private builder already seeds existing track IDs from the canonical document and can enforce `wp.target_track(...)` ownership.

However the worker prompt currently exposes grounded existing **curves**, not an empty existing-track inventory. A worker therefore cannot legitimately discover/select the anchor from its bounded prompt.

D3 requires a local `program_worker.py` context bridge that derives the selected section's existing track inventory directly from the canonical `document` and host-selected `section_context.section_id`.

The projection must be bounded to:

```text
track_id
title
kind
width_mm
binding_ids
```

For the D3 seed each worker must observe exactly one existing track:

```text
track_id    = combo
title       = Combo
kind        = normal
width_mm    = 50
binding_ids = []
```

This projection must be added to the worker prompt/SDK reference and repair context as host-grounded evidence.

Do not modify `enrichment.py` merely to transport this document-owned track fact; `ProgramSectionCompiler.compile(...)` already owns both the canonical document and host-resolved section target.

These are known design findings, not implementation authorization.

---

# 19. Frozen Worker-Surface Extension Design

Future D3 implementation should extend only the narrow worker/authoring-program surfaces needed by already-supported canonical models.

## wp.track additions

Add flat optional keyword arguments:

```text
grid_vertical_main_visible
grid_vertical_secondary_visible
```

When either is supplied, construct a sparse canonical grid intent containing only those explicit fields.

When omitted, existing behavior must remain unchanged.

## wp.raster additions

Add flat optional keyword arguments:

```text
colorbar_enabled
colorbar_label
colorbar_position

sample_axis_enabled
sample_axis_unit
sample_axis_minimum
sample_axis_maximum
sample_axis_tick_count
sample_axis_source_origin
sample_axis_source_step
```

The runtime must construct validated:

```text
AuthoringRasterColorbarSpec
AuthoringRasterSampleAxisSpec
```

only when the corresponding group is explicitly supplied.

Paired sample-axis constraints must continue to be enforced by the canonical typed models.

Do not expose arbitrary dicts.

Do not expose generic object construction.

Do not let programs set fields outside this frozen vocabulary.

## Existing-track worker projection

Inside `program_worker.py`, derive the host-selected section's existing tracks from the canonical document and serialize only:

```text
track_id
title
kind
width_mm
binding_ids
```

into:

- the initial worker prompt's bounded section context;
- the executable SDK reference;
- bounded repair context.

The SDK reference must explicitly identify those IDs as the only grounded values valid for `wp.target_track(section, track_id=...)`.

No generic track search, fuzzy title matching, or document serialization is authorized.

For D3, the deterministic backend must prove that `combo` appears in this actual host-grounded inventory before emitting `wp.target_track(section, track_id="combo")`.

---

# 20. Expected Production and Fixture Change Boundary

Expected D3 production files:

```text
src/wellplot/authoring_program/intent_builder.py
src/wellplot/agent/code_mode/program_worker.py
```

Purpose:

- map the frozen flat grid/raster SDK keywords into already-supported typed canonical intent;
- advertise those exact keywords in the section worker executable SDK reference;
- expose the bounded host-grounded existing-track inventory from the selected section.

No other production file is expected to change.

Expected D3 fixture/provenance files:

```text
tests/fixtures/agentic_cbl/data/CBL_Main.dlis
tests/fixtures/agentic_cbl/data/CBL_Repeat.dlis
tests/fixtures/agentic_cbl/data/manifest.json
```

If Git LFS is required:

```text
.gitattributes
```

is additionally expected solely to version the D3 binary fixtures reproducibly.

The fixture bytes/provenance gate must be satisfied before the integrated D3 test can claim acceptance.

In particular, D3 does not expect changes to:

```text
src/wellplot/model/authoring.py
src/wellplot/model/intent.py
src/wellplot/authoring_reconciler.py
src/wellplot/authoring_executor.py
src/wellplot/authoring_service.py
src/wellplot/logfile_schema.py
src/wellplot/agent/code_mode/planner.py
src/wellplot/agent/code_mode/enrichment.py
src/wellplot/agent/code_mode/report_worker.py
src/wellplot/agent/direct_notebook.py
scripts/verify_cbl_packet.py
renderer code
```

If any of those become necessary, future implementation must STOP for scope review.

---

# 21. Required Worker/SDK Regression Evidence

A future implementation must add deterministic lower-level tests proving:

## Track grid bridge

A restricted authoring program using:

```python
wp.track(
    section,
    ...,
    grid_vertical_main_visible=False,
    grid_vertical_secondary_visible=False,
)
```

produces a track intent whose grid carries exactly those requested values.

## Raster colorbar bridge

A restricted `wp.raster(...)` call with:

```text
colorbar_enabled=true
colorbar_label=Amplitude
colorbar_position=header
```

produces the corresponding canonical colorbar object.

## Raster sample-axis bridge

A restricted `wp.raster(...)` call with:

```text
sample_axis_enabled=true
sample_axis_unit=us
sample_axis_minimum=200
sample_axis_maximum=1200
sample_axis_tick_count=7
sample_axis_source_origin=40
sample_axis_source_step=10
```

produces the exact canonical sample-axis object.

## Existing-track projection

A program-worker test must provide an existing selected section containing an empty `combo` track and prove the worker request exposes:

```text
combo
Combo
normal
50
[]
```

through the bounded existing-track inventory and executable SDK reference.

It must also prove a track from a sibling section is not exposed as selectable context for the current worker.

## Existing-anchor execution

A restricted section program must be able to:

```python
report = wp.report()
section = wp.target_section(report)
combo = wp.target_track(section, track_id="combo")
wp.curve(combo, channel="ECGR_STGC", ...)
```

and dry-run successfully when `combo` is the exact grounded existing track.

An ungrounded track ID must remain rejected.

## Backward compatibility

Existing programs that omit the new grid/raster arguments must retain their existing intent semantics.

Existing workers without an empty structural anchor must retain their existing behavior.

No implicit D3 values may be inserted for unrelated programs.

---

# 22. Deterministic Section Backend

The future D3 deterministic section backend must parse the actual structured worker payload.

Before returning a program, it must assert:

- the local `section_task.requirements` carries the complete frozen scientific semantics for that section;
- target kind is `existing`;
- exactly one source is scoped to the task;
- the source contains all required real inspected channels;
- the selected capability inventory includes the needed track/binding categories;
- the bounded existing-track inventory contains exactly the expected local `combo` anchor;
- the executable SDK reference advertises:
  - `wp.target_track` for the grounded combo identity;
  - the frozen D3 grid additions;
  - the frozen D3 raster colorbar/sample-axis additions.

Only after those checks may it emit the controlled program.

The backend must route main vs repeat from the actual task semantics / source hint, not merely an external call counter.

The two section programs may share a code-generation helper because their local scientific specifications are equivalent, but each backend invocation must independently prove its own task payload and own selected source.

The backend must not fill missing planner semantics from a global golden answer object.

---

# 23. Final Document Contract

After the one public construction call, the final canonical document must contain exactly two sections in order:

```text
main_pass
repeat_pass
```

Each must contain exactly:

```text
combo
depth
cbl
vdl
```

in that order.

Each source must preserve:

```text
main_pass   -> CBL_Main.dlis / dlis
repeat_pass -> CBL_Repeat.dlis / dlis
```

The final document must contain no third section and no extra track/binding.

---

# 24. Frozen CBL Verifier

Use:

```text
scripts/verify_cbl_packet.py
```

unchanged.

Call:

```python
verdict = verify_cbl_packet(
    output_logfile,
    execution_evidence={
        "persisted": True,
        "rendered": True,
    },
)
```

Required:

```text
ok = true
acceptance_status = PASS
errors = []
```

Requirement statuses:

```text
CBL-01 PASS
CBL-02 PASS
CBL-03 PASS
CBL-04 PASS
CBL-05 PASS
CBL-06 PASS
CBL-07 PASS
CBL-08 PASS
CBL-09 PASS
```

The verifier is the final scientist-visible deterministic oracle.

Do not modify it simply to fit implementation output.

---

# 25. Public Result Contract

The one `run()` call must report:

```text
request_kind = author

report_facts.success      = true
report_facts.changed      = true
report_facts.apply_status = persisted

submitted_intent != None
```

Compilation evidence must show:

```text
worker_count       = 3
successful_workers = 3
failed_workers     = 0

report workers  = 1
section workers = 2
```

No failed worker artifact may be ignored.

Expected total repair count:

```text
0
```

If repair occurs, record it explicitly and require independent review.

---

# 26. Merged-Intent Evidence

Before treating final persistence as sufficient, inspect the public submitted intent and worker evidence.

Require:

- report fragment contains only report-wide fields;
- section fragments target exactly:
  - `main_pass`
  - `repeat_pass`;
- section fragments contain no report-wide fields;
- each section contains exactly four track fragments;
- each section contains expected curve/raster multiplicity;
- the two CBL instances are distinct;
- no source/channel outside the selected scoped source appears.

This is diagnostic ownership evidence.

The persisted verifier remains the acceptance oracle.

---

# 27. Real Render Contract

After successful `run()`, explicitly render the generated output logfile through:

```python
DirectNotebookSession.render_logfile_to_file(...)
```

to a distinct PDF path.

Require:

```text
file exists
file size > 0
```

Do not mock render.

Do not count an old pre-existing PDF.

The direct notebook's internal previews may provide additional evidence, but they do not replace the explicit final render.

---

# 28. Adversarial Acceptance Requirements

Future D3 implementation must include bounded checks preventing false acceptance.

## A. Starting artifact is incomplete

The source scaffold must contain only the structural `combo` anchor per section.

Before `run()`:

```text
combo bindings = 0
depth absent
cbl absent
vdl absent
requested remarks absent
```

## B. Task-local semantic chain

The report backend must fail the test if report semantics are missing from the actual report task.

Each section backend must fail before program emission if any frozen local scientific semantic is missing from the actual `section_task.requirements`.

A hard-coded golden section program may not compensate for an under-specified planner task.

## C. Grounded existing anchor

Each section worker must prove that the local `combo` track came from the host-grounded existing-track inventory.

The worker may not invent/select `combo` solely because the request text contains that word.

## D. Exact worker count

Exactly three successful workers.

No hidden fourth construction worker.

## E. Source isolation

Main and repeat workers must not see/use the sibling source as their selected source.

## F. Binding multiplicity

On each section:

```text
combo = 4 bindings
depth = 3 bindings
cbl   = 2 bindings
vdl   = 1 binding
```

Total per section:

```text
10 bindings
```

## G. Repeated channel identity

Two CBL bindings:

```text
same channel
different binding IDs
different requested scales/styles
```

## H. No generic-label collapse

Full scientist labels must persist exactly.

Do not accept generic aliases such as `GR` or `CBL` when the request supplies the full label.

## I. VDL exactness

The test must independently assert the requested:

- x-scale;
- hidden vertical grids;
- colormap;
- profile;
- colorbar;
- sample axis.

This protects against accidental verifier drift.

## J. Versioned source integrity

The integration test must verify the manifest SHA-256 and byte size for both real DLIS fixtures before staging them.

A missing fixture or hash mismatch is a failure, not a skip.

## K. No post-run repair

Capture final logfile bytes after `run()`.

The explicit render and verifier must consume exactly those bytes.

---

# 29. D3 Does Not Require Live Inference

All D3 deterministic implementation and acceptance must use test-local deterministic planner/report/section backends.

Required external-call counts:

```text
provider calls        = 0
endpoint calls        = 0
real model calls      = 0
worker provider calls = 0
```

D4 is the later bounded live-acceptance stage.

Do not turn D3 into a model-selection experiment.

---

# 30. Expected Future Implementation Scope

Subject to independent design closure review, expected implementation scope is:

```text
src/wellplot/authoring_program/intent_builder.py
src/wellplot/agent/code_mode/program_worker.py

tests/test_authoring_program_intent_builder.py
tests/test_authoring_program_interpreter.py
tests/test_code_mode_program_worker.py

tests/test_nlp_d3_cbl_construction.py
docs/nlp-d3-cbl-construction-result.md

tests/fixtures/agentic_cbl/data/CBL_Main.dlis
tests/fixtures/agentic_cbl/data/CBL_Repeat.dlis
tests/fixtures/agentic_cbl/data/manifest.json
```

If Git LFS is required for those binary fixtures, also:

```text
.gitattributes
```

Before any future implementation authorization is treated as executable, the operator must confirm that the two real DLIS inputs are available and that their redistribution basis is documented sufficiently to create the versioned fixtures.

If that prerequisite cannot be met, implementation must STOP at the data-fixture gate rather than producing a local-only D3 result.

An implementation authorization may narrow or amend this set after review.

No implementation is authorized by this design document.

---

# 31. Validation Expectations

Future D3 implementation must run:

## Focused

```text
tests/test_nlp_d3_cbl_construction.py
tests/test_cbl_packet_verifier.py
tests/test_authoring_program_intent_builder.py
tests/test_authoring_program_interpreter.py
tests/test_code_mode_program_worker.py
tests/test_code_mode_report_worker.py
```

## Delivery regression

```text
D0
D1
D2A
D2B
D2C
D2D
D2E
D3
```

## Adjacent

At minimum:

- direct notebook;
- Code Mode planner/facade/workflow/session;
- enrichment/source grounding;
- report worker;
- section worker;
- authoring reconciliation/execution;
- logfile persistence;
- DLIS loading;
- renderer.

Then run the full repository suite.

Also require:

```text
Ruff
formatting check
Python compilation/import validation
git diff --check
```

Classify failures as:

```text
new D3-attributable
reproduced known baseline
unclassified
```

---

# 32. STOP Conditions For Future Implementation

STOP and request architecture/scope review if D3 requires:

- modifying the frozen CBL verifier;
- planner schema changes;
- enrichment/source-selection changes;
- report-worker architecture changes;
- canonical model/schema changes;
- reconciliation changes;
- executor changes;
- persistence changes;
- renderer changes;
- source-loader mocking to avoid real DLIS;
- fake render evidence;
- a second public revision call;
- manual post-run YAML repair;
- another agent hierarchy;
- promotion of the legacy reconstruction graph;
- promotion of typed-section research solely to make D3 pass;
- live provider/model calls;
- D4 work.

Also STOP if:

- real CBL DLIS fixture provenance/redistribution cannot be established;
- the versioned fixture bytes cannot be provided from a clean checkout;
- either manifest hash does not match its fixture;
- real source inspection does not expose a requested channel;
- the report scaffold lacks a required semantic header/detail slot;
- the minimum valid scaffold cannot retain one empty `combo` anchor per section;
- the bounded existing-track projection cannot ground that anchor without wider context architecture changes;
- the bounded SDK bridge cannot express the VDL requirements without wider architecture changes;
- a section task does not carry the complete local scientific semantics and the backend would need to reconstruct them from external constants;
- final packet contains extra tracks, bindings, or sections;
- the one-shot public call cannot produce all nine CBL requirements.

---

# 33. Future Result Document

A future implementation must create:

```text
docs/nlp-d3-cbl-construction-result.md
```

and record observed evidence only.

Required header:

```text
Authorization:
<future D3 implementation authorization>

Design baseline:
<accepted D3 design SHA>

Branch:
<implementation branch>

Decision:
WELLPLOT_NLP_D3_IMPLEMENTATION_COMPLETE_REVIEW_PENDING
```

Do not claim independent acceptance.

Record:

## Request

- normalized request SHA-256;
- source-line normalization;
- exact public API call.

## Fixture provenance

For both versioned DLIS fixtures:

- repository fixture path;
- byte size;
- SHA-256;
- provenance description;
- redistribution basis;
- clean-checkout availability.

## Scaffold

- section IDs/order;
- exact starting `combo` anchor identity/kind/width on each section;
- zero starting bindings;
- absent depth/cbl/vdl tracks;
- source basenames;
- preflight verifier failure/incompleteness.

## Planner semantic decomposition

- one report task with exact report-local semantic requirement evidence;
- one main task with complete main-local scientific requirements;
- one repeat task with complete repeat-local scientific requirements;
- source hints per task;
- proof that section workers do not depend on report/sibling semantics.

## Source grounding

For main and repeat:

- selected scoped source identity;
- inspected channel set;
- source format.

## Existing-track grounding

For main and repeat:

- worker-visible bounded track inventory;
- exact `combo` anchor evidence;
- absence of sibling track leakage.

## Report worker

- approved header/detail/service slots;
- report-task semantic assertions;
- program generation count;
- repair count;
- report mutation categories.

## Main worker

- task-local semantic assertion;
- selected source;
- channel inventory;
- grounded combo anchor;
- track/binding program;
- repair count.

## Repeat worker

Same evidence.

## Public result

```text
success
changed
apply_status
worker counts
submitted intent ownership
```

## Final packet

- section order;
- track order;
- preserved combo anchor identities;
- binding multiplicity;
- duplicate CBL IDs;
- source basenames;
- VDL settings.

## CBL verifier

```text
CBL-01 through CBL-09
acceptance_status
errors
document_sha256
```

## Render

- explicit final PDF;
- non-empty status.

## Validation

- focused counts;
- D0-D3 counts;
- adjacent counts;
- full-suite counts and classifications;
- static checks;
- external-call counts.

---

# 34. Design Decision

`WELLPLOT-NLP-D3-DESIGN-001`

Reworked under:

```text
WELLPLOT-NLP-D3-DESIGN-REWORK-001
```

Selected approach:

One deterministic public `DirectNotebookSession.run()` reconstruction from a deliberately incomplete but canonically valid cased-hole source scaffold, using the established substantial CBL request and two reproducibly versioned real DLIS fixtures.

Each source-bearing section begins with only one empty structural `combo` anchor. The scientist request supplies all scientific bindings and creates the remaining `depth`, `cbl`, and `vdl` tracks.

The planner fixture must decompose the scientist request into task-local semantic requirements. Report, main, and repeat workers may act only on semantics actually present in their isolated task payloads.

Known implementation gaps are bounded to:

1. executable SDK exposure for already-supported VDL grid, colorbar, and sample-axis semantics;
2. a host-grounded existing-track projection inside `program_worker.py` so an empty existing `combo` anchor can be selected safely.

Expected architecture impact:

```text
small / local
```

Expected renderer/reconciler/schema/enrichment impact:

```text
none
```

Data prerequisite:

The two real CBL DLIS inputs must become reproducibly versioned D3 fixtures with SHA-256/provenance/redistribution metadata. If that prerequisite cannot be satisfied, D3 implementation must stop.

Evidence class:

```text
INTEGRATED DETERMINISTIC CONSTRUCTION ACCEPTANCE
```

Reversible: yes.

Next gate:

Independent closure review of this reworked D3 design and explicit design acceptance.

D3 implementation remains unauthorized until that gate passes.

D4 remains unauthorized.

---



`WELLPLOT-NLP-D3-DESIGN-001`

Selected approach:

One deterministic public `DirectNotebookSession.run()` reconstruction from a deliberately incomplete cased-hole source-declaration scaffold, using the established substantial CBL request and two real staged DLIS sources.

The scaffold owns only stable packet mechanics and source declarations.

The scientist request owns report content and all scientific plot construction.

Known implementation gap:

A bounded executable-SDK bridge is required for already-supported canonical VDL grid, colorbar, and sample-axis semantics.

Expected architecture impact:

```text
small / local
```

Expected renderer/reconciler/schema impact:

```text
none
```

Evidence class:

```text
INTEGRATED DETERMINISTIC CONSTRUCTION ACCEPTANCE
```

Reversible: yes.

Next gate:

Independent review of this D3 design and explicit design acceptance.

D3 implementation remains unauthorized until that gate passes.

D4 remains unauthorized.
