# WellPlot NLP D2D — Ambiguity and Missing-Source Rejection Design

## Status

`DESIGN_ONLY / IMPLEMENTATION_NOT_AUTHORIZED`

Design authorization: `WELLPLOT-NLP-D2D-DESIGN-001`

Input baseline: `578982e93004d6ff33e326dbb01dbbfc393fdd64` (`WELLPLOT_NLP_D2C_ACCEPTED`)

Design branch: `delivery/nlp-d2d-ambiguity-design`

This document freezes the D2D design only. It authorizes no production edit, no test implementation, no provider/endpoint/model call, and no D2E/D3/D4 work.

## Delivery Requirement

D2D closes the negative-path LAS revision requirement:

- `LAS-01` — ground against the actual current document before deciding whether a request is safe;
- `LAS-07` — a rejected request produces zero semantic mutation;
- `LAS-08` — ambiguity or unavailable source/channel grounding fails closed with an actionable deterministic result.

D2D is deliberately a rejection slice. It does not create or mutate a plot object.

The canonical delivery rule remains:

> When a target is ambiguous, fail closed rather than choosing. When a requested source or channel is unavailable, return an actionable error rather than silently substituting another declared source or channel.

## Architectural Finding

The required fail-closed machinery already exists at the frozen D2C baseline.

### Existing-section ambiguity

`SemanticEnricher` resolves `SectionTask.existing_section_hint` against the inspected canonical document.

If more than one inspected section matches, it raises:

```text
EnrichmentErrorCode.SECTION_HINT_AMBIGUOUS
```

with the safe message:

```text
The existing-section hint matched multiple inspected sections.
```

Revision mode does not downgrade this error.

### Missing source

`SemanticEnricher._select_sources()` selects only explicit host source candidates.

If a semantic `source_hint` matches no explicit candidate, it raises:

```text
EnrichmentErrorCode.SOURCE_MISSING
```

with the safe message:

```text
A source hint did not match an explicit host candidate.
```

It does not search the filesystem for alternatives or substitute a different declared source.

### Public error projection

`CodeModeCompileFacade.compile()` already catches `SemanticEnrichmentError` and returns a failed compile result with a stable diagnostic:

```text
stage = enrichment
code  = enrichment.<error-code>
```

No worker is dispatched because enrichment happens before graph fan-out.

`DirectNotebookSession._apply_result()` returns immediately when compilation fails, before constructing an authoring plan or persisting a mutation.

### Unavailable channel in a valid source

Channel availability is enforced later than source selection.

The section worker receives only the inspected channels from the selected source. Its private `ProgramRuntime.dry_run()` reconciles the worker's intent against those exact `available_channels`.

If a requested binding channel is absent, canonical reconciliation records an issue equivalent to:

```text
channel_missing: No source channel matches 'NPHI'.
```

The private dry run returns an artifact-free failed `ProgramExecutionResult` using the existing bounded program diagnostic:

```text
stage = dry_run
code  = program.dry_run_error
```

The compile graph therefore exposes a failed section worker and never produces a merged intent. `DirectNotebookSession._apply_result()` again short-circuits before canonical application or persistence.

Therefore the expected D2D implementation is acceptance evidence over existing behavior, not a new error architecture.

## D2D Acceptance Cases

D2D must include exactly three primary public-path rejection cases.

---

# Case A — Ambiguous Existing Section

## Frozen Scientist Request

```text
In the Main Log section, change the Gamma Ray curve scale to 10–100.
```

The request intentionally names a section title that is ambiguous in the D2D fixture.

## Frozen Planner Output

A deterministic planner must return exactly one section task equivalent to:

```python
SectionTask(
    goal="Change the requested Gamma Ray scale in the existing Main Log section.",
    capability_ids=(
        "section.log_plot",
        "track.normal",
        "binding.curve",
    ),
    existing_section_hint="Main Log",
    requirements=(FROZEN_D2D_AMBIGUOUS_REQUEST,),
)
```

No source hint is required for this case because rejection must occur during existing-section resolution before source loading or worker dispatch.

## Fixture Requirement

Start from a valid copy of the accepted LAS-backed fixture family and create a deterministic test-only ambiguity fixture containing at least two distinct canonical sections:

```text
section id: main
title: Main Log

section id: repeat
title: Main Log
```

The IDs must remain distinct.

The fixture must remain a valid logfile before the revision call.

The ambiguity must be genuine canonical document state, not a fake enricher exception injected directly into the public-path test.

The test may construct the duplicate-title fixture deterministically from repository fixture data, but must not modify production examples or committed fixture assets unless separately authorized.

## Expected Rejection

The real public path must reach:

```text
DirectNotebookSession.revise(...)
→ deterministic planner
→ deterministic safety layers
→ SemanticEnricher
→ existing_section_hint = "Main Log"
→ two inspected exact title matches
→ SECTION_HINT_AMBIGUOUS
→ CodeModeCompileFacade failed result
→ DirectNotebookSession apply short-circuit
→ zero mutation
```

Required public evidence:

```text
result.report_facts["success"] == False
result.report_facts["changed"] == False
result.report_facts["apply_status"] == "compile_failed"
submitted_intent is None
```

The compilation diagnostics must contain exactly the relevant stable rejection class:

```text
stage = enrichment
code  = enrichment.section_hint_ambiguous
```

The user-facing failure projection must include an actionable ambiguity explanation. It need not expose internal IDs or raw paths and must not claim a target was selected.

## Worker Isolation

Because rejection occurs before fan-out:

```text
section worker calls = 0
report worker calls  = 0
worker_count          = 0
```

Any worker call is a D2D failure.

---

# Case B — Missing Explicit Source

## Frozen Scientist Request

```text
In the Main Log section, add a normal track titled "Neutron" and plot NPHI from missing.las on it.
```

The source name `missing.las` is intentionally absent from the explicit host candidate inventory.

## Frozen Planner Output

A deterministic planner must return exactly one existing-section task equivalent to:

```python
SectionTask(
    goal="Add the requested Neutron track and NPHI binding from the named source.",
    capability_ids=(
        "section.log_plot",
        "track.normal",
        "binding.curve",
    ),
    existing_section_hint="Main Log",
    source_hints=("missing.las",),
    requirements=(FROZEN_D2D_MISSING_SOURCE_REQUEST,),
)
```

The plan must preserve the scientist's explicit source identity. Host code must not delete, rewrite, broaden, or replace that source hint.

## Fixture Requirement

Use the repository-contained LAS-backed single-logfile fixture with its actual declared source.

Before invoking revision, prove:

- the logfile loads successfully;
- the `Main Log` section exists uniquely;
- at least one explicit host source candidate is derived from the logfile;
- none of the candidate IDs, filename labels, stem labels, or explicit labels equals/matches `missing.las` under the actual conservative source matcher;
- no file named `missing.las` is introduced for the test.

The test must exercise the real `_load_document_context()` / declared-source inventory path through `DirectNotebookSession.revise()`; do not inject an artificial `SOURCE_MISSING` exception.

## Expected Rejection

The public path must reach:

```text
DirectNotebookSession.revise(...)
→ deterministic planner
→ existing Main Log resolves uniquely
→ explicit host source candidates normalized
→ source_hints = ("missing.las",)
→ no candidate matches
→ SOURCE_MISSING
→ CodeModeCompileFacade failed result
→ DirectNotebookSession apply short-circuit
→ zero mutation
```

Required public evidence:

```text
result.report_facts["success"] == False
result.report_facts["changed"] == False
result.report_facts["apply_status"] == "compile_failed"
submitted_intent is None
```

Required diagnostic:

```text
stage = enrichment
code  = enrichment.source_missing
```

The user-facing failure projection must state that the requested source could not be resolved from the declared candidates.

It must not claim that a different source was used.

## Worker Isolation

Again:

```text
section worker calls = 0
report worker calls  = 0
worker_count          = 0
```

No section backend program should be generated.

---

# Case C — Requested Channel Unavailable in a Valid Source

## Frozen Scientist Request

```text
In the Main Log section, add a normal track titled "Neutron", 28 mm wide, and plot NPHI from fixture.las on it labeled "Neutron" with a linear scale from 0 to 45.
```

The source is intentionally valid and declared. The requested scalar channel `NPHI` is intentionally absent from that source's inspected channel inventory.

## Frozen Planner Output

A deterministic planner must return exactly one existing-section task equivalent to:

```python
SectionTask(
    goal="Add the requested Neutron track and NPHI binding from the named source.",
    capability_ids=(
        "section.log_plot",
        "track.normal",
        "binding.curve",
    ),
    existing_section_hint="Main Log",
    source_hints=("fixture.las",),
    requirements=(FROZEN_D2D_MISSING_CHANNEL_REQUEST,),
)
```

The plan must preserve both the explicit source identity and the requested channel semantics.

## Fixture Requirement

Use the same repository-contained LAS-backed single-logfile fixture used for grounded D2B-style structural revision.

Before invoking revision, prove:

- `Main Log` exists uniquely;
- the actual host-generated candidate ID for `fixture.las` is selected by the source
  matcher (expected `source-1` for this single-source fixture);
- the selected candidate labels include `fixture.las` and the basename of its
  canonical path is `fixture.las`;
- the inspected source contains scalar channels such as the fixture's real available channels;
- `NPHI` is absent from every inspected channel mnemonic/alias for the selected source;
- no alternate source containing `NPHI` is introduced.

The test must inspect the real deterministic source context. It must not fake a `channel_missing` reconciliation issue.

## Deterministic Worker Contract

Unlike Cases A/B, Case C is expected to reach exactly one section worker.

The deterministic section backend must inspect its actual bounded worker context and prove:

```text
target.kind == existing
```

The host-side source context must independently prove the identity binding:

```text
host candidate_id == <actual host candidate ID>
host candidate labels include fixture.las
basename(host canonical_path) == fixture.las
```

The worker-side bounded context must then prove the same host-selected identity
is the source whose inspected channels it received:

```text
worker source candidate_id == <actual host candidate ID>
NPHI not in section_context.sources[*].channels[*].mnemonic/aliases
```

The worker payload intentionally does not carry canonical host paths or source
labels. The acceptance proof is compositional: host candidate identity is bound
to `fixture.las`, and that same candidate ID is bound to the worker's inspected
channel inventory.

Only after proving the requested channel is genuinely unavailable may it emit a program that faithfully represents the scientist's request:

```python
report = wp.report()
section = wp.target_section(report)

track = wp.track(
    section,
    kind="normal",
    title="Neutron",
    width_mm=28,
)

wp.curve(
    track,
    channel="NPHI",
    label="Neutron",
    scale_minimum=0,
    scale_maximum=45,
    scale_kind="linear",
    reverse=False,
)
```

Do not substitute `GR`, `CALI`, or any other available channel.

Because `ProgramSectionCompiler` may perform its existing bounded repair attempt, any repair response must preserve the requested unavailable `NPHI` channel. A repair must not convert the request into a different scientifically meaningful curve merely to obtain a successful program.

## Expected Rejection

The real public path must reach:

```text
DirectNotebookSession.revise(...)
→ deterministic planner
→ Main Log resolves uniquely
→ fixture.las resolves uniquely
→ source metadata inspection
→ one section worker
→ worker emits requested NPHI binding
→ ProgramRuntime.dry_run()
→ canonical available-channel reconciliation
→ channel_missing
→ worker failure with no artifact
→ compile result has no merged intent
→ DirectNotebookSession apply short-circuit
→ zero persistent mutation
```

Required worker diagnostic evidence is equivalent to:

```text
stage = dry_run
code  = program.dry_run_error
message contains:
channel_missing: No source channel matches 'NPHI'.
```

Required public evidence:

```text
result.report_facts["success"] == False
result.report_facts["changed"] == False
result.report_facts["apply_status"] == "compile_failed"
submitted_intent is None
```

## Worker Isolation

Case C must prove:

```text
section worker calls = 1
report worker calls  = 0
aggregate worker_count = 1
failed_workers = 1
successful_workers = 0
```

The section worker must not return an accepted intent artifact.

## No-Substitution Evidence

The test must prove:

- the scientist requested `NPHI`;
- the planner retained the NPHI requirement;
- the worker attempted `NPHI`;
- the inspected source did not contain `NPHI`;
- no available channel was selected as a replacement;
- no track or binding was persisted.

This is the integrated unavailable-channel acceptance case. It is distinct from the D2B `NOT_A_CHANNEL` regression, which intentionally corrupted a worker program while the scientist request still named a valid channel.

---

# D0 LAS-08 Contract

Use the frozen `scripts/verify_las_revision.py` unchanged.

Each D2D case must be graded as a rejected request.

Acceptance shape:

```json
{
  "before_assertions": [
    {"path": "/sections/0/id", "operator": "equals", "value": "<expected id>"}
  ],
  "required_changes": {},
  "allowed_change_paths": [],
  "prohibited_change_paths": [
    "/sections",
    "/remarks",
    "/header"
  ],
  "expected_outcome": "rejected"
}
```

Use the actual case-specific before assertions required to prove the fixture state. The ambiguity case should additionally establish the two distinct section IDs/titles independently in the integration test.

Required D0 result:

```text
LAS-01 PASS
LAS-07 PASS
LAS-08 PASS
workflow_status PASS
```

Other change dimensions remain `NOT_CHECKABLE`.

## Rejected-Workflow Execution Evidence

D0's established rejected-request convention uses:

```python
execution_evidence={
    "accepted": False,
    "persisted": True,
    "rendered": True,
}
```

For D2D, these fields must be interpreted and evidenced carefully:

- `accepted=False`: the revision was rejected;
- `persisted=True`: the after-state logfile remains the valid persisted artifact and is byte-identical to the before-state; this does **not** mean a mutation write occurred;
- `rendered=True`: the unchanged logfile can still be rendered successfully after rejection.

The integration test must separately prove:

```text
result.report_facts["changed"] == False
result.report_facts["apply_status"] == "compile_failed"
before bytes == after bytes
before canonical document == after canonical document
```

Do not report a mutation persistence event.

## Zero-Mutation Evidence

For each rejection case prove all of:

1. Capture the original logfile bytes before `revise()`.
2. Capture the canonical document before `revise()`.
3. Call the real public `DirectNotebookSession.revise()`.
4. Reload the same logfile afterward.
5. Assert bytes are identical.
6. Assert canonical model dumps are identical.
7. Run the frozen D0 verifier against before/after paths.
8. Assert `LAS-07 PASS` and `LAS-08 PASS`.
9. Render the unchanged logfile to a real non-empty PDF after rejection.

No ignored change paths are permitted.

`allowed_change_paths` must remain empty.

---

# Actionable Error Contract

D2D does not require a new clarification UI.

The accepted public result is sufficient if it safely communicates the deterministic reason through existing diagnostics/user-report projection.

For ambiguity, evidence must include:

```text
enrichment.section_hint_ambiguous
```

and a user-facing reason equivalent to:

```text
The existing-section hint matched multiple inspected sections.
```

For missing source:

```text
enrichment.source_missing
```

and a user-facing reason equivalent to:

```text
A source hint did not match an explicit host candidate.
```

For unavailable channel, evidence must include the worker/private-dry-run diagnostic:

```text
stage = dry_run
code  = program.dry_run_error
message contains:
channel_missing: No source channel matches 'NPHI'.
```

Exact punctuation is not the acceptance object; the stable diagnostic code/stage and truthful actionable meaning are.

D2D must not expose absolute filesystem paths, provider internals, generated program text, or private model material in the user-facing error.

---

# No-Substitution Contract

Missing-source handling must prove the host does not:

- search undeclared directories;
- select the sole declared source merely because only one exists;
- drop the planner's explicit source hint;
- replace `missing.las` with a lexically unrelated candidate;
- create a track or binding without the requested source;
- invoke the worker and ask it to improvise.

For Case B, rejection must happen in deterministic enrichment before worker fan-out.

For Case C, the selected source is valid, so rejection must instead happen during the one section worker's private canonical dry run. The system must not use the repair opportunity to substitute another available channel.

---

# Ambiguity Contract

Ambiguous existing-target handling must prove the host does not:

- choose the first matching section;
- prefer section order;
- prefer `main` by ID;
- use source association to break a section-title tie;
- downgrade ambiguity to a new-section operation in revision mode;
- dispatch workers with one arbitrarily selected target.

The existing `SECTION_HINT_UNRESOLVED` reconstruction downgrade is not part of D2D and must not be generalized to ambiguous revision targets.

---

# Expected Production Scope

Repository inspection at the frozen D2C baseline finds no D2D production gap.

The existing path already provides:

- deterministic ambiguity detection;
- deterministic missing-source detection;
- facade normalization to safe diagnostics;
- failed results with no merged intent;
- public apply short-circuit before reconciliation/persistence;
- zero-worker evidence for pre-fan-out failures;
- private worker dry-run channel grounding against inspected `available_channels`;
- artifact-free worker failure for unavailable requested channels.

Therefore future D2D implementation authorization should initially permit only:

```text
tests/test_nlp_d2d_ambiguity_rejection.py
docs/nlp-d2d-ambiguity-rejection-result.md
```

No production files are expected to change.

If any integrated public-path case fails because existing production behavior does not satisfy this design, implementation must STOP and request a scope amendment rather than repairing production opportunistically.

## Production Files Explicitly Not Authorized by This Design Expectation

Do not modify without a later explicit amendment:

```text
src/wellplot/agent/code_mode/enrichment.py
src/wellplot/agent/code_mode/facade.py
src/wellplot/agent/code_mode/workflow.py
src/wellplot/agent/code_mode/planner.py
src/wellplot/agent/session.py
src/wellplot/agent/direct_notebook.py
src/wellplot/authoring_reconciler.py
src/wellplot/authoring_service.py
src/wellplot/authoring.py
src/wellplot/logfile_schema.py
scripts/verify_las_revision.py
```

The following existing tests are validation inputs, not initially authorized edits:

```text
tests/test_code_mode_enrichment.py
tests/test_code_mode_facade.py
tests/test_agent_session.py
tests/test_nlp_d0_acceptance.py
```

---

# Mandatory Regression Evidence

Future D2D implementation must run existing direct tests that establish the lower-level behavior, including the equivalent of:

- source selection is bounded to explicit candidates;
- multiple candidates without semantic resolution fail as ambiguous;
- source hints with no candidate fail as `SOURCE_MISSING`;
- ambiguous section hints fail as `SECTION_HINT_AMBIGUOUS`;
- revision unresolved hints do not downgrade to new-section work;
- facade enrichment failures produce no worker evidence;
- failed public session results expose no intent;
- section-worker private dry run rejects bindings whose requested channel is absent from the selected inspected channel set;
- failed worker outcomes do not expose an intent artifact.

The D2D public-path tests complement these unit/contract tests; they do not replace them.

---

# Adversarial Requirements

In addition to the three primary cases, future D2D tests should include bounded assertions that prevent false acceptance.

## A. Ambiguity fixture sanity

Before calling revision, prove both ambiguous sections truly exist and share the relevant title.

If the fixture accidentally contains only one match, the test must fail before invoking the public path.

## B. Missing-source fixture sanity

Before revision, prove `missing.las` is not present in the candidate inventory.

If a future fixture change introduces such a candidate, the test must fail rather than silently becoming a positive mutation case.

## C. Missing-channel fixture sanity

Before revision, prove `fixture.las` resolves and `NPHI` is absent from its inspected channel inventory.

If a future fixture change introduces `NPHI`, the test must fail before invoking the acceptance path rather than silently becoming a positive structural revision.

## D. Worker isolation and no fallback

For Cases A/B, use worker doubles that fail immediately if called; both must complete with zero worker calls.

For Case C, permit exactly one section worker and zero report workers. The worker must fail closed on `NPHI` and must not substitute an available channel during its initial or repair candidate.

## E. Mutation sentinel

A controlled verifier-only negative regression must show that if any unrelated canonical field is changed while `expected_outcome="rejected"`, D0 produces:

```text
LAS-07 FAIL
LAS-08 FAIL
workflow_status FAIL
```

This may reuse the frozen D0 harness directly rather than adding production behavior.

---

# Explicit Non-Goals

D2D does not authorize:

- clarification UI;
- interactive follow-up turns;
- automatic candidate ranking;
- fuzzy target selection;
- fuzzy source selection;
- filesystem discovery outside declared candidates;
- source upload workflows;
- conditional-instruction execution semantics;
- unavailable-channel **redesign** beyond the integrated Case C acceptance path;
- planner redesign;
- worker redesign;
- persistence changes;
- renderer changes;
- D2E successive-revision integration;
- D3 construction work;
- D4 live inference.

The completion-plan statement allowing explicit conditional instructions remains valid, but D2D selects the alternative accepted behavior: return a safe actionable rejection when the requested source is unavailable.

---

# STOP Conditions For Future Implementation

STOP and request architecture/scope review if D2D appears to require:

- changing section matching semantics;
- adding fuzzy section/source scoring;
- adding source discovery;
- modifying planner schemas;
- modifying the public result schema;
- changing reconciliation or persistence;
- weakening the D0 verifier;
- invoking a worker after an enrichment rejection in Cases A/B;
- provider/model calls;
- production changes outside a separately approved amendment.

---

# Future Validation Expectations

Future D2D implementation should run:

- focused D2D public-path tests;
- D0/D1/D2A/D2B/D2C/D2D delivery regression;
- `tests/test_code_mode_enrichment.py`;
- `tests/test_code_mode_facade.py`;
- `tests/test_agent_session.py`;
- `tests/test_code_mode_program_worker.py`;
- relevant authoring context/reconciliation channel-grounding tests;
- relevant direct-notebook tests;
- full repository suite;
- Ruff;
- formatting check;
- compilation/import validation;
- `git diff --check`.

Provider calls, endpoint calls, worker provider calls, and real model calls must remain zero.

Historical/environment failures must be reported separately from new D2D-attributable failures.

---

# Future Implementation Handoff

A future D2D implementation checkpoint must report:

```text
D2D IMPLEMENTATION COMPLETE

Authorization:
<future authorization>

Branch:
<implementation branch>

HEAD:
<exact SHA>

Parent / baseline:
<exact accepted design SHA>

Changed files:
<exact list>

Production changes:
0

CASE A — AMBIGUOUS SECTION

Request:
In the Main Log section, change the Gamma Ray curve scale to 10–100.

Ambiguous fixture:
section 1 id/title:
section 2 id/title:

Planner existing_section_hint:
Main Log

Public result:
success:
changed:
apply_status:
submitted_intent:

Diagnostic:
stage:
code:
message:

Worker counts:
section:
report:
aggregate worker_count:

Before/after byte identity:
PASS/FAIL

Before/after canonical identity:
PASS/FAIL

Render unchanged file:
PASS/FAIL

D0:
LAS-01:
LAS-07:
LAS-08:
workflow_status:

CASE B — MISSING SOURCE

Request:
In the Main Log section, add a normal track titled "Neutron" and plot NPHI from missing.las on it.

Declared source candidates:
<exact bounded identities/labels>

Requested source hint:
missing.las

Requested source absent from inventory:
PASS/FAIL

Public result:
success:
changed:
apply_status:
submitted_intent:

Diagnostic:
stage:
code:
message:

Alternative source substitution:
NONE

Worker counts:
section:
report:
aggregate worker_count:

Before/after byte identity:
PASS/FAIL

Before/after canonical identity:
PASS/FAIL

Render unchanged file:
PASS/FAIL

D0:
LAS-01:
LAS-07:
LAS-08:
workflow_status:

CASE C — MISSING CHANNEL IN VALID SOURCE

Request:
In the Main Log section, add a normal track titled "Neutron", 28 mm wide, and plot NPHI from fixture.las on it labeled "Neutron" with a linear scale from 0 to 45.

Selected candidate_id:
<actual host candidate ID, expected source-1 for this fixture>

Selected source filename:
fixture.las

Source-label match:
PASS/FAIL

Canonical-path basename:
fixture.las

Requested channel:
NPHI

Requested channel absent from inspected source:
PASS/FAIL

Worker context grounding evidence:
<exact source/channel evidence>

Public result:
success:
changed:
apply_status:
submitted_intent:

Worker diagnostic:
stage:
code:
message:

Alternative channel substitution:
NONE

Worker counts:
section:
report:
aggregate worker_count:
failed_workers:
successful_workers:

Before/after byte identity:
PASS/FAIL

Before/after canonical identity:
PASS/FAIL

Render unchanged file:
PASS/FAIL

D0:
LAS-01:
LAS-07:
LAS-08:
workflow_status:

Focused tests:
<result>

D0-D2D delivery regression:
<result>

Adjacent enrichment/facade/session tests:
<result>

Full suite:
<result and failure classification>

Ruff / format / compile / git diff --check:
<result>

Provider calls:
0

Endpoint calls:
0

Worker provider calls:
0

Real model calls:
0

D2E/D3/D4:
NOT AUTHORIZED
```

## Design Decision

`WELLPLOT-NLP-D2D-DESIGN-001`

Selected approach: prove three existing deterministic fail-closed paths through the public revision boundary:

1. ambiguous existing-section identity rejected during enrichment;
2. explicitly requested source absent from the declared host candidate inventory rejected during enrichment;
3. explicitly requested channel absent from a valid selected source rejected by the section worker's private canonical dry run.

Evidence class: `KNOWN-GOOD / INTEGRATED ACCEPTANCE` — lower-level deterministic behavior already exists and is unit-tested; D2D adds notebook-facing LAS-08 acceptance evidence and zero-mutation proof across target ambiguity, source absence, and channel absence.

Expected production changes: none.

Reversible: yes. This design itself changes no production behavior.

Next gate: independent review and explicit approval of this design. D2D implementation remains unauthorized until both occur.
