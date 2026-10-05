# WellPlot NLP D2A — Report Revision Design

## Status

`DESIGN_ONLY / IMPLEMENTATION_NOT_AUTHORIZED`

Design authorization: `WELLPLOT-NLP-D2A-DESIGN-001`

Input baseline: `1ad7e21e4003b194769bf9cc0a842ed708f32d02` (`WELLPLOT_NLP_D1_ACCEPTED`)

Design branch: `delivery/nlp-d2a-report-revision-design`

This document freezes the next bounded delivery vertical after D1. It authorizes no production implementation, no provider or endpoint call, no model inference, and no D2B/D2C/D2D/D2E work.

## Delivery Requirement

D2A advances `LAS-02` while reusing the D1 revision spine and rechecking the already accepted preservation/execution obligations:

- `LAS-01` — ground against the existing document;
- `LAS-02` — mutate one requested report-level value;
- `LAS-07` — preserve all unrelated semantic state;
- `LAS-09` — persist, reload, validate, and render successfully.

D2A does not attempt stable header-slot mutation yet. Its purpose is to prove the report-worker branch of existing-document revision with the smallest scientist-visible report mutation: the canonical report title.

## Architectural Basis

The existing production path already contains a bounded report worker:

- `ReportProgramCompiler` accepts one `ReportTask` plus bounded report context;
- its executable SDK includes `wp.report(title=..., subtitle=...)`;
- report programs are forbidden from creating or revising sections or plot-child objects;
- report programs dry-run against the current canonical `AuthoringDocumentSpec`;
- canonical reconciliation/application remains downstream of worker generation;
- D1 already proved the public `DirectNotebookSession.revise()` apply/persist/reload/render spine.

Therefore D2A must reuse the existing report branch. It must not create a second report mutation path or route a report-title request through the section worker.

## Frozen Scientist Request

Exact natural-language request:

```text
Change the report title to "Gamma Ray Quality Control Review".
```

The quoted title is part of the requested literal value.

## Frozen Starting Fixture

Use a deterministic test logfile derived from the same repository-contained LAS-backed fixture family used by D1 (`create_mcp_fixture_paths(...).single_logfile`).

Before invoking the public NLP revision path, the deterministic test fixture must establish the canonical report title explicitly as:

```text
Original Well Log Report
```

This explicit setup avoids dependence on template interpolation or source-derived title defaults.

The fixture must otherwise preserve the normal D1-compatible document structure, source declaration, tracks, bindings, remarks, page/depth/output state, and renderability.

The test must persist the deterministic starting fixture through existing canonical/compatibility serialization machinery; it must not alter production source code merely to create the fixture.

## Frozen Expected Semantic Transition

Canonical before state:

```text
/title = "Original Well Log Report"
```

Canonical after state:

```text
/title = "Gamma Ray Quality Control Review"
```

The intended semantic delta is exactly the canonical report-title value.

No section, track, binding, source, scale, fill, annotation, remark, page, depth, output, header-slot value, or unrelated presentation field may change.

If canonical compatibility metadata necessarily mirrors the report title during normal persistence, the implementation must identify the exact deterministic mirror path in its handoff. Such a mirror may be proposed as an additional D0 `allowed_change_path`, but it may not be silently accepted. Any non-mechanical collateral semantic change is a D2A failure.

## Public Path Requirement

The acceptance test must enter through the real notebook-facing revision API:

```text
DirectNotebookSession.revise(
    feedback='Change the report title to "Gamma Ray Quality Control Review".',
    logfile_path=<fixture>,
)
```

The expected integrated route is:

```text
existing persisted WellPlot document
        +
natural-language report-title request
        ↓
DirectNotebookSession.revise()
        ↓
revision-mode planner with current-document context
        ↓
report task only
        ↓
existing ReportProgramCompiler
        ↓
restricted report program
        ↓
canonical authoring intent
        ↓
existing reconciliation/application boundary
        ↓
canonical validation
        ↓
persist
        ↓
reload
        ↓
real render
        ↓
frozen D0 LAS verifier
```

The section worker must not be dispatched for this D2A request.

## Deterministic Test Backends

D2A implementation/validation must make zero real provider/model calls.

A deterministic fake planner may return exactly one report task describing the requested report-title mutation and no section tasks.

A deterministic fake report backend may return the minimal restricted program equivalent to:

```python
report = wp.report(title="Gamma Ray Quality Control Review")
```

The expected title must exist only in deterministic test/backend evidence and D0 acceptance specifications. Production prompts/runtime code must not hard-code the D2A answer.

The test must assert that the report worker prompt contains the semantic report request and that no section-worker backend is invoked.

## D0 Acceptance Specification

The frozen D0 verifier remains the independent acceptance authority.

At minimum the D2A specification must contain:

```text
before_assertion:
  /title == "Original Well Log Report"

required_changes:
  LAS-02:
    before:
      /title == "Original Well Log Report"
    after:
      /title == "Gamma Ray Quality Control Review"

allowed_change_paths:
  /title
  <only deterministic compatibility mirror paths independently justified by implementation evidence>

prohibited_change_paths:
  /sections
  /remarks
  /header
  /page
  /depth
  /output

expected_outcome:
  accepted
```

Required final D0 results:

```text
LAS-01  PASS
LAS-02  PASS
LAS-07  PASS
LAS-09  PASS
```

Unexercised LAS dimensions may remain `NOT_CHECKABLE`.

## Preservation Contract

D2A must prove preservation semantically, not merely by checking the requested field.

Before/after canonical comparison must establish that:

- section count/order/identity is unchanged;
- track count/order/identity is unchanged;
- binding identities/channels/scales/styles are unchanged;
- report remarks are unchanged;
- header content is unchanged;
- page/depth/output configuration is unchanged;
- source routing is unchanged;
- no fill/annotation content appears or disappears.

D0 `LAS-07` is authoritative for the canonical preservation verdict.

## Persistence and Render Contract

After the accepted revision:

1. the public API must persist the result without manual repair;
2. reloading through the canonical authoring loader must produce `/title = "Gamma Ray Quality Control Review"`;
3. canonical validation must succeed;
4. a real render/export must succeed;
5. the output file must exist and be non-empty;
6. D0 execution evidence must credit `LAS-09` only from observed persistence/render success.

A dry-run-only success is insufficient.

## Adversarial Requirements

D2A implementation tests must include at least:

### Already-satisfied request

Starting title:

```text
Gamma Ray Quality Control Review
```

Same natural-language request.

Required behavior:

- no semantic mutation;
- no false `LAS-02 PASS` for a required transition;
- persistence must not fabricate a change merely to satisfy the request.

### Report/section ownership isolation

For the accepted D2A request:

- report worker is invoked;
- section worker is not invoked;
- generated report intent contains no sections, curve/raster bindings, fills, annotations, or removals.

### Collateral mutation rejection

A controlled test mutation that changes the report title plus one unrelated canonical field must cause `LAS-07 FAIL` and workflow failure.

The collateral mutation may be injected only in test evidence; do not add production repair logic for it.

## Preferred Implementation Scope

The design expectation is that D2A may require **no production change at all** because the report worker already supports sparse report-title mutations and D1 proved the notebook apply/persistence/render path.

A future implementation authorization should initially allow only:

```text
tests/test_nlp_d2a_report_revision.py
docs/nlp-d2a-report-revision-result.md
```

plus fixture-local test construction if required.

No production file is pre-authorized by this design.

If the end-to-end test exposes a concrete integration defect in the existing report path, implementation must STOP and return:

```text
D2A BLOCKED
<exact boundary>
<exact missing context/contract>
<smallest proposed production file set>
```

A production-scope amendment may then be reviewed independently, as was done in D1.

## Explicit Non-Goals

D2A does not authorize:

- stable general-header field editing;
- service-title editing;
- detail-table editing;
- remarks creation or replacement;
- page/depth/output changes;
- track creation;
- curve/binding creation;
- fill creation;
- ambiguity UX;
- unavailable-source handling beyond existing safety behavior;
- planner redesign;
- typed-worker or V2R promotion;
- renderer redesign;
- source-inspection redesign;
- live-provider experimentation;
- D2B, D2C, D2D, D2E, D3, or D4 work.

## STOP Conditions For Future Implementation

Stop and return for architecture review if D2A appears to require:

- a new report mutation engine;
- routing report mutations through section programs;
- weakening report/section ownership safety;
- changes to canonical authoring schemas;
- renderer behavior changes;
- persistence-format redesign;
- host-side guessing of scientific meaning;
- provider/model calls;
- more than the smallest bounded integration correction needed to reuse the existing report branch.

## Future Implementation Handoff Contract

A future D2A implementation checkpoint must report:

```text
D2A IMPLEMENTATION COMPLETE

Authorization:
<future implementation authorization ID>

Branch:
<implementation branch>

HEAD:
<exact SHA>

Parent / starting baseline:
<authorized D2A baseline>

Changed files:
<exact list>

Natural-language request:
Change the report title to "Gamma Ray Quality Control Review".

Public API path exercised:
<exact call>

Before title:
Original Well Log Report

After title:
Gamma Ray Quality Control Review

Frozen D0 result:
LAS-01:
LAS-02:
LAS-07:
LAS-09:

Canonical semantic diff:
<exact paths>

Persistence evidence:
<details>

Render evidence:
<details>

Focused tests:
<result>

Adjacent tests:
<result>

Full suite:
<result and classification of new failures>

Provider calls:
0
Endpoint calls:
0
Real model calls:
0

D2B/D2C/D2D/D2E/D3/D4:
NOT AUTHORIZED
```

## Design Decision

`WELLPLOT-NLP-D2A-DESIGN-001`

Selected approach: prove one sparse canonical report-title revision through the existing public notebook/report-worker path before extending revision support to structural section content.

Evidence class: `ADAPTED` — existing report worker and D1 notebook revision machinery are reused under a new integrated delivery acceptance requirement.

Reversible: yes. This design authorizes no implementation and no production modification.

Next gate: independent review of this design, followed only then by an explicit D2A implementation authorization.
