# WellPlot NLP D2C — Grounded Existing-Curve Fill Design

## Status

`DESIGN_ONLY / IMPLEMENTATION_NOT_AUTHORIZED`

Design authorization: `WELLPLOT-NLP-D2C-DESIGN-001`

Input baseline: `b0fe50e59fa74644edc2ddfa51d507ef620dfe99` (`WELLPLOT_NLP_D2B_ACCEPTED`)

Design branch: `delivery/nlp-d2c-fill-design`

This document freezes the D2C design only. It authorizes no production edit, no test implementation, no provider or endpoint call, no model inference, and no D2D/D2E/D3/D4 work.

## Delivery Requirement

D2C advances the remaining positive LAS revision capability:

- `LAS-01` — ground against the existing document;
- `LAS-06` — add one fill relation;
- `LAS-07` — preserve unrelated semantic state;
- `LAS-09` — persist, reload, validate, and render successfully.

D2C is deliberately limited to one relation owned by one existing normal track and one already-grounded existing curve binding.

D2C does not attempt:

- new track creation;
- new curve creation;
- between-curve fill creation;
- fill update/removal;
- ambiguity UX;
- unavailable-source workflow;
- complete LAS sequence acceptance.

## Architectural Finding

Fill support already exists below the Code Mode worker boundary.

Current canonical/runtime support includes:

- canonical `CurveFillSpec`;
- fill kinds `between_curves`, `between_instances`, `to_lower_limit`, `to_upper_limit`, and `baseline_split`;
- `IntentBuilder.add_fill()`;
- runtime `wp.fill(track, binding, [other_binding], ...)`;
- `fill.curve` in the canonical capability registry;
- track-local fill ownership validation;
- reconciliation/execution of track-local fills;
- Matplotlib rendering for lower/upper-limit, between-curve, and baseline fills.

The current production section worker already exposes:

- `wp.target_section(report)`;
- `wp.target_track(section, track_id=...)`;
- `wp.target_curve(track, binding_id=...)`;
- exact grounded existing-curve inventory.

But its executable SDK reference does **not** currently advertise `wp.fill(...)`, and its existing-section instruction mentions sparse section updates, existing-curve updates, and adding new child tracks, but not creating fills from grounded existing bindings.

Therefore the expected D2C production change is a bounded worker-vocabulary extension, not a new mutation architecture.

## Frozen Scientist Request

Exact natural-language request:

```text
In the Main Log section, on the GR track, fill from the Gamma Ray curve to its lower scale limit using light gray (#d9d9d9) at 25% opacity.
```

The request is intentionally explicit about:

- existing section;
- existing track;
- existing scientific curve;
- fill direction;
- exact color;
- exact opacity.

No source-channel creation or scientific target guessing is required.

## Frozen Starting Fixture

Use the repository-contained LAS-backed fixture family:

`create_mcp_fixture_paths(...).single_logfile`

The starting canonical document must be verified before revision.

Expected relevant state:

```text
section:
  id: main
  title: Main Log

track:
  id: gr
  kind: normal
  title: GR

existing curve:
  binding_id: main.gr.GR.3
  channel: GR
```

The exact existing binding identity must be recovered from the canonical document and/or the grounded worker inventory, not invented by host code.

The GR track must begin with no fill objects for this test.

The implementation test must prove those fixture facts before invoking the public NLP revision path.

## Why This Fill Form Is Selected

D2C intentionally chooses `to_lower_limit` rather than a between-curve fill.

The frozen fixture has one scalar binding per normal track. A between-curve fill would require first adding or moving another binding onto the GR track, which would mix `LAS-04` delivery behavior into the D2C acceptance object.

A one-binding lower-limit fill isolates the new capability:

```text
grounded existing track
        +
grounded existing curve binding
        ↓
new track-local relation
```

This keeps D2C about relational ownership rather than structural creation.

## Frozen Expected Semantic Transition

Before:

```text
/sections/0/tracks/3/id = "gr"
/sections/0/tracks/3/fills length = 0
/sections/0/tracks/3/bindings contains binding_id "main.gr.GR.3"
```

After, exactly one fill must exist on the existing GR track.

Required semantic properties:

```text
/sections/0/tracks/3/fills/0/kind       = "to_lower_limit"
/sections/0/tracks/3/fills/0/binding_id = "main.gr.GR.3"
/sections/0/tracks/3/fills/0/color      = "#d9d9d9"
/sections/0/tracks/3/fills/0/alpha      = 0.25
```

The fill ID is allocator-owned and must not be frozen as the scientific answer. It must be non-empty, canonical, stable after persistence/reload, and owned by the GR track.

No existing track, binding, scale, style, source route, report field, header, remark, page/depth/output field, fill, annotation, or presentation value may change.

Compatibility serialization may mechanically mirror the new fill. Any such mirror path must be identified from actual deterministic evidence and allowed only at its narrowest stable path.

## Required Public Path

The D2C acceptance test must enter through:

```python
DirectNotebookSession.revise(
    feedback=(
        "In the Main Log section, on the GR track, fill from the Gamma Ray "
        "curve to its lower scale limit using light gray (#d9d9d9) at 25% opacity."
    ),
    logfile_path=<fixture>,
)
```

Required integrated route:

```text
existing persisted WellPlot document
        +
natural-language fill request
        ↓
DirectNotebookSession.revise()
        ↓
revision planner with current-document context
        ↓
one SectionTask targeting Main Log
        ↓
deterministic enrichment
        ↓
grounded existing-curve inventory
        ↓
ProgramSectionCompiler
        ↓
target existing section
        ↓
target grounded GR track
        ↓
target grounded GR curve binding
        ↓
wp.fill(... kind="to_lower_limit" ...)
        ↓
canonical reconciliation
        ↓
canonical execution / validation
        ↓
persist
        ↓
reload
        ↓
real render
        ↓
frozen D0 LAS verifier
```

The report worker must not be dispatched.

## Deterministic Planner Contract

D2C implementation must use zero real provider/model calls.

A deterministic planner may return one existing-section task with the frozen request in its requirements.

Recommended capabilities:

```text
section.log_plot
track.normal
binding.curve
fill.curve
```

Recommended target:

```text
existing_section_hint = "Main Log"
```

The test must prove the real public path invoked the planner in `mode="revise"` with current-document summary.

## Required Worker Vocabulary Extension

The current section worker's underlying restricted runtime already implements `wp.fill`.

A future D2C implementation is expected to make the smallest production change necessary to expose that existing operation safely.

Expected change location:

```text
src/wellplot/agent/code_mode/program_worker.py
```

The future implementation should add the executable SDK contract equivalent to:

```text
wp.fill(track, binding[, other_binding]):
    kind, id_hint, label, color, alpha
```

The worker contract must make clear:

- fills are track-local relations;
- existing bindings must first be selected from the grounded inventory;
- a fill must not reference an invented binding identity;
- all fill operands must belong to the exact same selected track;
- D2C authorizes creation only, not fill selection/update/removal;
- no report-wide mutation accompanies a section fill request.

The existing-section worker instruction should be minimally expanded from its current vocabulary to permit adding a requested fill using grounded existing child identities.

Do not add a second fill compiler or direct document mutation path.

## Frozen Deterministic Worker Program

A deterministic backend may emit the restricted program equivalent to:

```python
report = wp.report()
section = wp.target_section(report)

track = wp.target_track(
    section,
    track_id="gr",
)

curve = wp.target_curve(
    track,
    binding_id="main.gr.GR.3",
)

wp.fill(
    track,
    curve,
    kind="to_lower_limit",
    id_hint="gr_lower_fill",
    color="#d9d9d9",
    alpha=0.25,
)
```

Before emitting that program, the deterministic backend must inspect its actual worker context and prove that the grounded existing-curve inventory contains the exact relation:

```text
track_id   = gr
binding_id = main.gr.GR.3
channel    = GR
```

The backend must not use its own hard-coded binding ID as evidence of grounding.

The exact expected answer may exist in deterministic test/backend evidence and acceptance specifications, but must not be hard-coded into production logic or prompts.

## Relational Ownership Contract

This is D2C's new safety property:

> A fill may reference only binding handles owned by the exact selected parent track.

The system must reject:

- an invented binding ID;
- a valid binding ID from another track;
- a binding selected without grounded inventory authorization;
- a fill attached to a different track than its binding;
- an unsupported fill kind/operand combination.

The current canonical model already validates that normal-track fills reference binding IDs present on that same track. The existing runtime handle builder also validates leaf-parent ownership.

D2C must reuse these invariants rather than reimplement them in host code.

## D0 Acceptance Contract

The frozen D0 verifier remains authoritative.

Required D2C result:

```text
LAS-01  PASS
LAS-06  PASS
LAS-07  PASS
LAS-09  PASS
```

Unexercised LAS requirements may remain `NOT_CHECKABLE`.

Acceptance should establish before-state grounding using exact fixture identities.

`LAS-06` must assert a real before-to-after fill transition.

At minimum, after assertions must prove:

```text
/sections/0/tracks/3/fills/0/kind       == "to_lower_limit"
/sections/0/tracks/3/fills/0/binding_id == "main.gr.GR.3"
/sections/0/tracks/3/fills/0/color      == "#d9d9d9"
/sections/0/tracks/3/fills/0/alpha      == 0.25
```

The D2C integration test must independently assert:

```text
before fill count = 0
after fill count  = 1
```

The intended semantic allowed-change boundary is initially:

```text
/sections/0/tracks/3/fills/0
```

plus only exact mechanical compatibility mirrors observed in the persisted canonical diff.

No broad `/extensions` allowance is permitted.

## Preservation Contract

Before/after canonical comparison must prove that:

- section identity and metadata are unchanged;
- all track identities/order/types/widths remain unchanged;
- the complete pre-existing GR binding remains unchanged;
- all other bindings remain unchanged;
- scales and styles remain unchanged;
- no track is added, removed, or moved;
- no binding is added, removed, or modified;
- no report/header/remark/page/depth/output state changes;
- no annotation changes;
- no other fill changes.

The only new semantic object is one fill under the existing GR track.

## Persistence and Render Contract

After an accepted D2C revision:

1. public path persists without manual repair;
2. canonical reload succeeds;
3. the GR track has exactly one fill;
4. the fill targets the original GR binding ID;
5. canonical validation succeeds;
6. real render/export succeeds;
7. output exists and is non-empty;
8. D0 may credit `LAS-09` only from observed persistence/render evidence.

Renderer modification is not authorized by the design expectation. The existing renderer already implements lower-limit curve fills.

## Mandatory Adversarial Coverage

### A. Invented binding identity

Controlled worker program:

```python
track = wp.target_track(section, track_id="gr")
curve = wp.target_curve(track, binding_id="main.gr.GR.404")
```

Required outcome:

- worker/private compile fails closed;
- no fill is persisted;
- canonical document remains unchanged;
- logfile remains byte-identical if failure precedes persistence.

This is a D2C relation-grounding regression, not D2D `LAS-08` acceptance.

### B. Cross-track binding ownership

Controlled worker program selects:

```text
track = gr
binding = main.cali.CALI.4
```

and attempts to use that CALI binding in a fill owned by `gr`.

Required outcome:

- rejected before persistence;
- no partial fill;
- no canonical mutation.

This proves relation ownership is parent-local rather than document-global.

### C. Collateral existing-binding mutation

Controlled acceptance evidence contains the requested valid fill plus an unrelated modification to the existing GR binding scale or style.

Required D0 result:

```text
LAS-06 PASS
LAS-07 FAIL
workflow_status FAIL
```

The collateral mutation belongs only in deterministic test evidence.

### D. Worker ownership isolation

Successful case must prove:

```text
section worker calls = 1
report worker calls  = 0
```

Submitted intent must contain exactly the selected existing section/track, the preserved referenced existing curve identity as required by the sparse intent representation, and exactly one new fill. It must not contain report-wide mutation or a new track/binding.

## Expected Future Implementation Scope

Unlike D2A and D2B, D2C has one known worker-vocabulary gap.

A future implementation authorization should initially allow:

```text
src/wellplot/agent/code_mode/program_worker.py
tests/test_nlp_d2c_fill_revision.py
docs/nlp-d2c-fill-revision-result.md
```

No other production file is expected.

Existing tests for `ProgramSectionCompiler` may be modified only if the eventual authorization explicitly includes their exact paths.

If implementation appears to require any additional production subsystem, STOP for architecture review rather than broadening scope.

## Production Files Not Expected To Change

The design currently finds no justification to modify:

```text
src/wellplot/authoring_program/intent_builder.py
src/wellplot/model/**
src/wellplot/authoring_context.py
src/wellplot/authoring_reconciler.py
src/wellplot/authoring_executor.py
src/wellplot/authoring_service.py
src/wellplot/renderers/**
src/wellplot/agent/code_mode/enrichment.py
src/wellplot/agent/direct_notebook.py
```

If one of these becomes necessary, future implementation must STOP and request an explicit scope amendment.

## Explicit Non-Goals

D2C does not authorize:

- between-curve fill acceptance;
- between-instance fill acceptance;
- baseline-split fill acceptance;
- upper-limit fill acceptance;
- fill update;
- fill removal;
- fill selection as an end-user action;
- new tracks;
- new bindings;
- curve updates;
- report/header work;
- ambiguity UX;
- missing-source UX;
- renderer redesign;
- planner redesign;
- V2R or typed-worker promotion;
- live provider/model evaluation;
- D2D/D2E/D3/D4 work.

The lower-level canonical support for these other fill kinds remains unchanged; they are simply outside this delivery slice.

## STOP Conditions For Future Implementation

Stop if D2C appears to require:

- a new fill mutation engine;
- direct document mutation outside canonical intent/reconciliation;
- canonical schema changes;
- weakening grounded track/binding selection;
- host-side fuzzy curve selection;
- global binding lookup that bypasses track ownership;
- renderer changes;
- persistence redesign;
- source-inspection redesign;
- a new planner architecture;
- a new worker/agent;
- D0 verifier weakening;
- live provider/model calls;
- broad work on ambiguity or other fill kinds.

## Future Validation Expectations

Future D2C implementation should run:

- focused D2C tests;
- D1/D2A/D2B/D2C delivery regression;
- relevant `ProgramSectionCompiler` tests;
- `IntentBuilder` fill and target-curve tests;
- reconciler/executor fill tests;
- renderer fill tests;
- public notebook adapter tests;
- full repository suite;
- Ruff;
- formatting check;
- compilation/import validation;
- `git diff --check`.

Provider calls, endpoint calls, and real model calls must remain zero.

Historical/environment failures must be reported separately from any new D2C-attributable failure.

## Future Implementation Handoff

A future D2C implementation checkpoint must report:

```text
D2C IMPLEMENTATION COMPLETE

Authorization:
<future authorization>

Branch:
<implementation branch>

HEAD:
<exact SHA>

Parent / baseline:
<exact authorized SHA>

Changed files:
<exact list>

Natural-language request:
In the Main Log section, on the GR track, fill from the Gamma Ray curve to its lower scale limit using light gray (#d9d9d9) at 25% opacity.

Public API path:
<exact call>

Existing section:
main / Main Log

Existing track:
gr

Grounded existing curve:
binding_id:
channel:

Grounding evidence:
<exact worker-context evidence>

Before fills:
0

After fills:
1

New fill:
fill_id:
kind:
binding_id:
color:
alpha:

Frozen D0:
LAS-01:
LAS-06:
LAS-07:
LAS-09:

Canonical semantic diff:
<exact paths>

Compatibility mirrors:
<exact paths>

Existing GR binding unchanged:
PASS/FAIL

All unrelated state preserved:
PASS/FAIL

Persistence/reload:
<evidence>

Render:
<evidence>

Invented-binding regression:
<result>

Cross-track-ownership regression:
<result>

Collateral-mutation regression:
LAS-06:
LAS-07:
workflow_status:

Worker ownership:
section worker calls:
report worker calls:

Focused tests:
<result>

Adjacent tests:
<result>

Full suite:
<result and failure classification>

Ruff / format / compile / git diff --check:
<result>

Provider calls:
0

Endpoint calls:
0

Real model calls:
0

D2D/D2E/D3/D4:
NOT AUTHORIZED
```

## Design Decision

`WELLPLOT-NLP-D2C-DESIGN-001`

Selected approach: prove one `to_lower_limit` fill owned by the existing `gr` track and referencing the exact grounded existing GR binding.

Evidence class: `ADAPTED` — the accepted D1 existing-object selection spine is extended to a relation using already-existing canonical fill/runtime/reconciler/renderer primitives.

Expected new production behavior is limited to exposing the already-implemented `wp.fill` operation in the section worker's bounded SDK/revision vocabulary.

Reversible: yes. This design itself changes no production behavior.

Next gate: independent review and explicit user approval of this design. D2C implementation remains unauthorized until then.
