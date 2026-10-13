# D5-3 Provider-Free Parity / Regression Acceptance Design

## Status

```yaml
slice: WELLPLOT-D5-3
authorization: WELLPLOT-D5-3-DESIGN-AUTH-001
design_status: DESIGN_ONLY / READY FOR INDEPENDENT DESIGN REVIEW
starting_checkpoint: 560ec48d2b2809ed2feb55467da15195f527ec44
production_implementation: NOT AUTHORIZED
provider_calls: 0
endpoint_calls: 0
model_calls: 0
```

This document defines the next bounded acceptance slice after D5 single-engine
convergence. It does not accept D5-3, change production behavior, or authorize
live qualification.

## 1. Objective And Boundary

D5-3 answers one question:

> Does the converged canonical engine preserve the accepted scientist-visible
> WellPlot construction, revision, safety, persistence, and rendering behavior?

The acceptance object is the resulting canonical document and rendered artifact,
plus deterministic behavioral evidence. The historical implementation that
produced earlier evidence is not itself the acceptance object.

The frozen production route remains:

```text
public adapter
  -> shared composition root
  -> SemanticPlanner
  -> deterministic enrichment / source inspection
  -> canonical report or section worker
  -> deterministic semantic lowering
  -> AuthoringDocumentIntent
  -> reconcile_authoring()
  -> AuthoringExecutor
  -> AuthoringService
  -> persistence / reload / render
```

D5-3 may add provider-free acceptance tests and test-local evidence fixtures.
It may not change this route, introduce a worker family, restore a retired
engine, or alter the D5-2 production manifest.

## 2. Frozen D5-2 Baseline

D5-2 is frozen at:

```text
560ec48d2b2809ed2feb55467da15195f527ec44
```

The D5 production attestation is active and must pass before D5-3 acceptance:

```text
scripts/d5_single_engine_attestation.py --check
scripts/check_d5_single_engine_reachability.py --repo-root .
```

The attestation derives its component set from the six accepted canonical
entrypoints. The current reachable count is 91, but that number is not a D5-3
constant. The computed closure and hashes remain authoritative.

The following are already frozen evidence, not new D5-3 experiments:

- D1 through D2E public revision behavior and persistence evidence.
- D3 CBL construction and the CBL-01 through CBL-09 verifier.
- D4's exact nine-turn provider-free rehearsal.
- D4R1 typed worker convergence and D4R2 CBL/scaffold correction.
- D5-2 single-engine convergence, reachability, and production attestation.

## 3. Parity Definition

Parity means preservation of the accepted behavioral contract, not preservation
of deleted class names, test counts, prompt wording, or internal call graphs.

For an accepted construction, parity requires:

```text
request + declared sources + starting scaffold
  -> intended canonical state
  -> validated persisted state
  -> reload-equivalent state
  -> successful real render where required
```

For an accepted revision, parity requires:

```text
requested semantic state: CHANGED AS REQUIRED
unrelated semantic state: UNCHANGED
failure state: bounded and mutation-free
```

The comparison is canonical and semantic. JSON/YAML formatting, compatibility
mirror ordering, and other representation-only differences are ignored unless
the particular contract explicitly requires byte identity. Rejected revisions
explicitly require byte identity of the persisted artifact in addition to
canonical identity.

The D5-3 result must distinguish:

- model-facing fixture response validity;
- canonical semantic correctness;
- reconciliation and safety correctness;
- persistence/reload equivalence;
- render success;
- adapter parity.

Provider-free fixture success is not model capability evidence.

## 4. Accepted Historical Behavior Inventory

The frozen CBL and LAS contracts are the reference set. They are retained as
behavioral requirements even where the historical implementation was deleted.

### CBL construction

CBL construction is the exact D4-C01 request and uses the accepted real local
DLIS pair:

```text
workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis
workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis
```

The accepted D3 evidence freezes the pair's custody, sizes, and SHA-256 values.
The provider-free test must use the existing local-data custody rule and must
not synthesize a replacement source. The test-local starting scaffold is the
accepted cased-hole scaffold used by D3/D4. The deterministic worker responses
come from `tests/_d4_canonical_fixtures.py` or an equivalent test-only fixture,
never from production context.

CBL parity requires the existing verifier to return PASS for all nine:

```text
CBL-01 report heading / service presentation
CBL-02 remarks and report content
CBL-03 section identity and order
CBL-04 track identity, kind, order, and width
CBL-05 binding identity, channel, and multiplicity
CBL-06 reference/depth semantics
CBL-07 raster/image configuration
CBL-08 scales, labels, styles, widths, and presentation
CBL-09 canonical validation, persistence, reload, and real render evidence
```

### LAS revision

The LAS seed is the frozen canonical seed in
`tests/fixtures/nlp_d4_live_gold.json`, with the accepted source contract and
source custody from the D4 design. The exact nine D4 request strings and request
hashes remain immutable.

The accepted state sequence is:

```text
D4-L01:T1  report title mutation
D4-L01:T2  existing GR scale mutation
D4-L01:T3  new track plus grounded ILD binding
D4-L01:T4  grounded GR fill creation
D4-L02:T1  ambiguous target rejection
D4-L02:T2  clarified target acceptance
D4-L03:C01 unavailable source rejection
D4-L04:C01 unavailable channel rejection
```

Together with D4-C01, these are the finite nine-turn behavioral population.
They cover LAS-01 through LAS-09 as mapped below. D5-3 does not silently add a
new request or replace a source because an implementation is inconvenient.

## 5. Historical-To-Canonical Coverage Matrix

The matrix is the primary D5-3 design control. `Current evidence` describes
what is already available; `D5-3 action` describes what the implementation
must either reuse or add to make the parity decision terminal.

| Requirement | Accepted historical evidence | Canonical production owner | Current canonical test/evidence | Gap | D5-3 action |
| --- | --- | --- | --- | --- | --- |
| CBL-01 | D3/D4 CBL verifier | canonical report worker, report intent, service | D4 nine-turn CBL PASS | none identified | COVERED: reuse exact CBL case |
| CBL-02 | D3/D4 remarks and slots | canonical report worker and report mapping | D4 CBL PASS | no separate parity artifact | COVERED: retain verifier evidence |
| CBL-03 | D3/D4 section-order verifier | canonical section worker and reconciler | D4 CBL PASS | none identified | COVERED: retain verifier evidence |
| CBL-04 | D3/D4 track verifier | canonical section worker and authoring models | D4 CBL PASS | none identified | COVERED: retain verifier evidence |
| CBL-05 | D3/D4 binding/multiplicity verifier | canonical section worker, identity allocator, reconciler | D4 CBL PASS | none identified | COVERED: retain verifier evidence |
| CBL-06 | D3/D4 depth/reference verifier | canonical models and authoring service | D4 CBL PASS | explicit parity summary required | NEEDS_CANONICAL_REGRESSION: assert reference topology |
| CBL-07 | D3/D4 VDL raster verifier | canonical raster model and renderer | D4 CBL PASS | none identified | COVERED: retain verifier evidence |
| CBL-08 | D3/D4 presentation verifier | canonical scale/style models and renderer | D4 CBL PASS | style comparison must be canonical | NEEDS_CANONICAL_REGRESSION: normalized projection |
| CBL-09 | D3/D4 persistence/render evidence | AuthoringService, logfile mapping, renderer | D4 CBL PASS | none identified | COVERED: reuse real persistence/render |
| LAS-01 | D1-D4 grounding assertions | SemanticEnricher, context resolver, canonical workers | D2E/D4 accepted grounding evidence | adapter overlay not yet explicit | NEEDS_INTEGRATED_ACCEPTANCE: assert public-path context |
| LAS-02 | D2A/D2E title revision | report worker and report intent | canonical report regression and D2E | none identified | COVERED: reuse title case |
| LAS-03 | D2B/D2E track creation | section worker and canonical intent | canonical section regression and D2E | none identified | COVERED: reuse track case |
| LAS-04 | D2B/D2E source-grounded binding | enrichment, source context, reconciler | canonical worker regression and D4 | no adapter parity case | NEEDS_INTEGRATED_ACCEPTANCE: assert source custody |
| LAS-05 | D1/D2E scale revision | canonical section worker and reconciler | canonical worker regression and D2E | none identified | COVERED: reuse scale case |
| LAS-06 | D2C/D2E fill creation | canonical section worker, fill model, reconciler | canonical worker regression and D2E | none identified | COVERED: reuse fill case |
| LAS-07 | D0-D4 preservation verifier | canonical document, reconciler, executor | D2E cumulative preservation | normalized comparison needs explicit contract | NEEDS_CANONICAL_REGRESSION: normalized preservation comparator |
| LAS-08 | D2D/D2E safe rejection | enrichment and canonical worker diagnostics | D4-L02/L03/L04 evidence | invalid relation overlay not yet formalized | NEEDS_INTEGRATED_ACCEPTANCE: bounded rejection matrix |
| LAS-09 | D1-D4 persistence/render evidence | AuthoringService and renderer | D2E and D4 accepted evidence | adapter parity render subset | NEEDS_INTEGRATED_ACCEPTANCE: representative render set |
| One composition root | D5-2 convergence contract | `agent.composition` | D5 reachability and convergence tests | none identified | COVERED: require attestation/audit PASS |
| Bounded diagnostics | D4/D4R1 taxonomy | worker/facade diagnostic projections | D5 canonical worker tests | full parity matrix not assembled | NEEDS_CANONICAL_REGRESSION: assert stable codes |
| Public adapter convergence | D1-D4 notebook path plus MCP contracts | Direct Notebook and MCP composition root | D5 composition tests | same semantic cases not compared | NEEDS_INTEGRATED_ACCEPTANCE: three-case adapter overlay |
| Production integrity | D5-2 attestation | package-aware D5 manifest/checker | D5 attestation PASS | none identified | COVERED: require current PASS |

Rows marked `SUPERSEDED / NOT CURRENT PRODUCT CONTRACT` are not present in the
18 behavior rows because none of those accepted CBL/LAS requirements is being
superseded. Historical implementation details are handled separately below.

## 6. Test-Retirement Audit

D5-2 removed executable alternate engines, not the behavioral contracts they
were once used to test. The implementation slice must review the following
families and preserve only current product invariants:

| Historical family | Current invariant | Current canonical owner/evidence | D5-3 disposition |
| --- | --- | --- | --- |
| header-slot identity/value behavior | requested report/header values map to owned slots | canonical report worker, CBL-01/02, D3 verifier | COVERED; retain slot-custody assertions |
| grid/style validation | requested grid/style/presentation values remain valid and owned | canonical models, renderer, CBL-07/08 | NEEDS_CANONICAL_REGRESSION; normalized presentation projection |
| section applicability | only declared capabilities and valid section targets are accepted | planner, enrichment, section worker, reconciler | NEEDS_CANONICAL_REGRESSION; include invalid capability/target fixture |
| reconciliation and preservation | requested paths change and unrelated canonical state remains unchanged | `reconcile_authoring`, D0 verifier, LAS-07 | COVERED with explicit normalized comparator |
| source/channel grounding | inspected source/channel evidence, not model guesses, authorizes bindings | enrichment, canonical workers, LAS-01/04/08 | COVERED with adapter overlay |
| fill semantics | fill remains bound to an existing canonical binding | fill model, reconciler, LAS-06 | COVERED; retain wrong-track rejection |
| execution rollback/failure | failed action leaves persisted artifact unchanged | executor/service and D2D/D2E rejection evidence | NEEDS_INTEGRATED_ACCEPTANCE; assert zero mutation after each rejection |
| MCP/notebook adapter behavior | supported adapters use one composition root and preserve semantics | composition root, D5 audit, MCP/direct adapters | NEEDS_INTEGRATED_ACCEPTANCE; three-case overlay |
| legacy `AuthoringSession` behavior | no alternate engine remains a current product contract | source retirement and D5 reachability audit | SUPERSEDED / NOT CURRENT PRODUCT CONTRACT |
| program/graph/typed-delivery engine internals | internal implementation behavior of retired engines | D5 physical retirement and Git history | SUPERSEDED / NOT CURRENT PRODUCT CONTRACT |
| retired provider adapters | old provider routing behavior | D5 source retirement | SUPERSEDED / NOT CURRENT PRODUCT CONTRACT |

The audit must not restore deleted tests merely to preserve historical test
counts. A deleted test is restored only when its scientist-visible invariant is
listed as current and lacks canonical coverage.

## 7. Finite D5-3 Acceptance Population

The population is fixed at 13 execution slices: nine canonical Direct Notebook
cases, one accepted invalid-relation safety case, and three MCP parity overlays.
There is no open-ended case-addition rule.

### Direct Notebook cases

| Case ID | Starting state/input | Deterministic response | Expected result | Preservation/render requirement |
| --- | --- | --- | --- | --- |
| D5-CBL-01 | D3 cased-hole scaffold plus the accepted Main/Repeat DLIS pair | `_cbl_report_response` plus `_cbl_section_response` | CBL-01..09 PASS, `DIRECT_CORRECT` | generated artifact persists, reloads, and real-renders |
| D5-LAS-01-T1 | D4 canonical LAS seed, title `Original Well Log Report` | sparse report title response | title changes only | canonical diff plus mirrors; persist/reload |
| D5-LAS-01-T2 | prior accepted state with original GR scale | existing-curve scale action | GR becomes linear 5..125 | all non-scale state unchanged; persist/reload |
| D5-LAS-01-T3 | prior accepted state with six-track LAS seed | add-track plus grounded ILD binding | one Resistivity QC track is appended | existing tracks/bindings unchanged; persist/reload |
| D5-LAS-01-T4 | prior accepted state with GR binding | grounded lower-limit fill action | one GR fill is created | fill parent identity preserved; persist/reload/render |
| D5-LAS-02-T1 | two matching Main Log candidates | scale response is not dispatched because target is ambiguous | bounded ambiguity failure | zero mutation and no persistence |
| D5-LAS-02-T2 | clarified Main Log - Upper target | existing-curve scale action | clarified target changes | other section and state preserved; persist/reload |
| D5-LAS-03-C01 | valid seed, hint `missing_neutron.las` | no worker response; enrichment rejects source | `enrichment.source_missing` | zero workers, zero mutation, byte-identical artifact |
| D5-LAS-04-C01 | valid seed, valid source without `RT` | attempted unavailable-channel response | `typed.channel_missing` or canonical `channel_missing` per frozen route | no substitution, zero mutation, byte-identical artifact |
| D5-REL-01 | D2E S0 with `main.gr.GR.3` and another track's real binding | fill targeting a binding owned by another track | bounded ownership failure | no canonical mutation or persistence |

The D4 exact request strings and hashes are loaded from
`tests/fixtures/nlp_d4_live_cases.json`; they are not duplicated in runtime
code. Gold and expected outcomes are loaded from
`tests/fixtures/nlp_d4_live_gold.json` and the accepted CBL verifier contract.

### MCP parity overlay

These are not a second nine-turn campaign. They are three representative
replays through the MCP agentic public adapter using the same canonical fixture
backend and semantic expectations:

| Overlay ID | Replayed case | Adapter assertion |
| --- | --- | --- |
| D5-MCP-01 | D5-LAS-01-T1 title mutation | MCP builds the same canonical dependency roles and produces the same normalized title diff |
| D5-MCP-02 | D5-LAS-01-T2 GR scale mutation | MCP preserves grounding, canonical binding identity, normalized preservation, persistence/reload, and the required real render |
| D5-MCP-03 | D5-LAS-04-C01 unavailable channel | MCP returns the same bounded failure class and leaves the artifact unchanged |

The overlay compares normalized canonical outcomes, not internal object
identity, worker call order, or prompt serialization. It does not authorize
provider calls through MCP.

### Resource and runtime bounds

The D5-3 implementation must declare finite local bounds before execution:

- one provider-free run of the 10 Direct Notebook cases;
- one provider-free run of the three MCP overlays;
- exactly the required real renders: D5-CBL-01, D5-LAS-01-T4, and D5-MCP-02;
- no generation calls beyond deterministic fixture backend calls;
- no live network requests;
- fail the slice on timeout, missing external source custody, or unclassified
  diagnostic rather than extending the population.

The existing accepted real DLIS custody and source hashes remain mandatory. A
missing ignored local data asset is a precondition failure, not permission to
substitute synthetic data.

## 8. Fixture And Gold Provenance Rules

Fixtures may provide structured worker responses only at the provider boundary.
They may not bypass:

```text
worker validation -> canonical lowering -> reconciliation
-> execution -> persistence -> reload -> render -> verifier
```

The implementation must record for every response:

- fixture identifier and source file hash;
- response-model validation result;
- canonical intent/result projection;
- expected semantic diff and preservation projection;
- failure code, stage, and mutation status where rejected.

Expected values belong to test/evaluation data. They must not be added to
prompts, production context, planner logic, or source inspection.

The CBL gold remains the existing verifier and frozen result contract. The LAS
gold remains the existing request/gold fixture pair and D0 verifier semantics.
Any change to source assets, request hashes, gold, verifier ownership, or
accepted outcome taxonomy is outside this design and must stop for review.

## 9. Semantic Correctness Assertions

Each successful case must assert both the requested semantics and the owner of
those semantics:

- report values are report-owned;
- section/track/binding/fill values are section-owned;
- source and channel identity comes from inspected deterministic context;
- canonical IDs are host-owned and stable after persistence/reload;
- reference/depth structure is preserved, not inferred from prose;
- no response-local identifier is treated as a canonical document identity.

The assertion layer must compare canonical Pydantic/model projections after
removing only explicitly allowed compatibility mirrors. It must not compare
arbitrary worker wording or serialized formatting as semantic content.

## 10. Mutation-Preservation Assertions

For each accepted LAS revision, the implementation must compute:

```text
before = normalized canonical document
after  = normalized canonical document
```

and assert:

1. all required before assertions hold;
2. all required after assertions hold;
3. at least one required semantic transition occurred;
4. every path outside the declared allowed change projection is equal;
5. compatibility mirrors are consistent with the canonical source path;
6. reload preserves the same normalized after projection.

The allowed path sets remain those frozen in the D0 specifications. A test
must not broaden them to accommodate collateral changes.

For CBL construction, preservation is expressed by the CBL verifier's required
fields and by a canonical projection of the scaffold-independent requested
artifact. CBL construction is expected to change the incomplete scaffold; it
must not be judged by starting/ending artifact byte identity.

## 11. Fail-Closed Behavior

Every rejection must produce:

```text
bounded actionable diagnostic
-> no unintended semantic mutation
-> no persisted partial result
-> no silent source/channel substitution
```

The required failure matrix is:

- ambiguous target: enrichment rejects before worker dispatch;
- unavailable source: source matching rejects before worker dispatch;
- unavailable channel: canonical worker/dry-run rejects after exact source
  inspection, with no intent or persistence;
- invalid relation: ownership validation rejects an invented or cross-track
  binding/fill relation before mutation.

Failure evidence must include only sanitized diagnostics and stage/category
fields. It must not include prompt text, credentials, raw provider responses,
or generated payloads.

## 12. Persistence And Reload Equivalence

Every successful representative construction/revision must prove:

```text
private canonical document
-> persisted logfile
-> strict logfile validation
-> reload
-> normalized canonical document
```

The normalized reloaded result must retain requested semantics, host-owned
identities, source bindings, compatibility projections, and unrelated state.

Every rejected case must prove both canonical equality and byte identity of the
persisted artifact before and after the attempted request.

## 13. Real Rendering

Final parity evidence must use the actual configured renderer and produce a
non-empty output artifact. No renderer mock or bypass may stand in for the
final render assertion.

The required real-render acceptance subset is exactly:

1. `D5-CBL-01`: the generated CBL artifact must persist, reload, real-render,
   and pass CBL-01 through CBL-09.
2. `D5-LAS-01-T4`: the cumulative Direct Notebook state after title, scale,
   track/binding, and fill revisions must pass canonical correctness,
   preservation, persistence, reload, and real render.
3. `D5-MCP-02`: the MCP GR-scale overlay must pass adapter semantic parity,
   canonical grounding and binding identity, normalized preservation,
   persistence, reload, and real render.

All other successful cases retain their canonical semantic, preservation, and
case-specific persistence/reload requirements, but do not independently
require a real render. Diagnostic renders may occur during implementation;
they are not part of the frozen minimum acceptance population. The D5-2
Matplotlib resource correction remains part of the frozen production path.

## 14. Public-Adapter Parity Strategy

Direct Notebook and MCP must use the frozen composition root and canonical
worker roles. The parity overlay must assert:

- the same planner/worker role classes or canonical dependency roles;
- the same source/channel grounding inputs for equivalent cases;
- equivalent normalized canonical intent and final document results;
- equivalent bounded failure category and zero-mutation behavior;
- persistence and render through the same service/renderer boundary.

The overlay must not require duplicate CBL execution through MCP. One real CBL
construction establishes the expensive construction/render boundary; the three
small overlays establish adapter semantic convergence.

## 15. Current Coverage And Implementation Gaps

Current coverage is strong but not yet a single terminal D5-3 artifact:

```yaml
CBL-01..CBL-09: COVERED by accepted D3/D4 verifier evidence
LAS-01..LAS-09: COVERED across D1-D4 and D2E accepted evidence
D5 single-engine closure: COVERED by D5-2 attestation/reachability evidence
normalized preservation contract: NEEDS_CANONICAL_REGRESSION
invalid relation in integrated matrix: NEEDS_INTEGRATED_ACCEPTANCE
Direct Notebook/MCP parity overlay: NEEDS_INTEGRATED_ACCEPTANCE
retired-test invariant audit: NEEDS_CANONICAL_REGRESSION
```

The finite D5-3 implementation backlog is:

1. Add one provider-free parity test module for the 10 Direct Notebook cases.
2. Add the normalized semantic diff/preservation projection used by those
   tests, reusing D0 allowed-path semantics.
3. Add three MCP adapter overlays without duplicating the whole population.
4. Add the invalid relation and rollback/no-persistence assertion.
5. Add the historical test-retirement coverage assertions for section
   applicability, normalized style/grid state, and bounded diagnostics.
6. Emit one deterministic D5-3 result artifact with case-level and
   requirement-level outcomes.

No production file is in this backlog.

## 16. Exact Anticipated Implementation Footprint

The design anticipates only test/evidence changes:

```text
tests/test_d5_provider_free_parity_acceptance.py
tests/fixtures/d5_3_provider_free_parity_cases.json
tests/fixtures/d5_3_provider_free_parity_gold.json
docs/architecture/D5_PROVIDER_FREE_PARITY_ACCEPTANCE_RESULT.md
```

Existing D0-D5 scripts and production sources should be reused unchanged.
Fixture placement may differ if existing deterministic fixtures are sufficient,
but any difference must remain test/evidence-only. No source under
`src/wellplot/` is anticipated or authorized.

## 17. Deterministic Pass/Fail Criteria

The implementation must end in one terminal result:

```yaml
PASS:
  all mandatory finite cases pass
  CBL-01..CBL-09 covered and passing
  LAS-01..LAS-09 covered and passing
  preservation assertions pass
  all rejection cases are bounded and mutation-free
  persistence/reload equivalence passes
  required real renders are non-empty
  Direct Notebook/MCP overlay passes
  D5 attestation and reachability audit pass
  no accepted current invariant is lost

REWORK_REQUIRED:
  an accepted behavior fails or lacks the specified canonical coverage

ARCHITECTURAL_ESCALATION:
  provider-free evidence proves an accepted requirement cannot be represented
  by the frozen D5 architecture without changing an architectural boundary
```

Test defects, missing fixtures, unclassified diagnostics, or environment
failures must not be labeled architectural escalation. They terminate the
bounded slice with the specific failure category and require review.

## 18. Explicitly Deferred Live Qualification Boundary

D5-3 does not authorize:

- provider/model calls or endpoint identity calls;
- Qwen or any other model qualification;
- prompt, decoder, provider, or model tuning;
- model comparison;
- new semantic IR, planner, worker, or compiler architecture;
- renderer redesign or UI work;
- restoration of retired engines;
- production promotion;
- D5 post-parity live qualification.

Only after independent acceptance of the finite provider-free D5-3 result may
a separate bounded live-qualification design be proposed.

## Decision Record

```text
DECISION:
Use one finite provider-free behavioral parity population plus a small MCP
adapter overlay to validate the frozen D5 canonical engine.

PROJECT SCOPE:
WellPlot scientists must obtain correct, safe, persistent, renderable well-log
plots through the supported natural-language workflow.

EXTERNAL EVIDENCE:
This slice adapts the repository's accepted D0-D4 requirement-level verifier,
canonical Pydantic models, persistence boundary, and real-render checks. It
does not introduce a new architecture or claim model capability from fixtures.

ESTABLISHED PRACTICE:
Regression acceptance should measure stable externally visible behavior while
allowing internal implementation replacement when the contract is preserved.

WELLPLOT DIFFERENCE:
Scientific source custody, canonical identity ownership, and real rendering
are WellPlot-specific obligations and therefore remain explicit in the matrix.

OPTIONS CONSIDERED:
A. Recreate all deleted historical tests.
B. Reuse accepted behavior and add finite canonical/adaptor parity coverage.
C. Start another live model campaign.

SELECTED APPROACH:
B. Historical tests are mapped to current responsibilities; only missing
scientist-visible invariants enter the finite D5-3 backlog.

EVIDENCE CLASS:
ADAPTED

RISKS:
The D5-3 comparator could accidentally encode representation equality, the
MCP overlay could test construction without semantic equivalence, or ignored
external data could be silently substituted.

REVERSIBLE:
YES. This is a provider-free test/evidence slice with no production changes.

VALIDATION:
Finite case matrix, canonical normalized projections, D0 verifier, strict
persistence/reload, real renders, adapter overlay, D5 attestation, and
reachability audit.

STOP / REVISIT CONDITION:
Stop if any accepted requirement lacks an owner, if a rejection mutates state,
if adapter parity requires a second engine, or if an accepted behavior cannot
be represented by the frozen D5 architecture.
```

## Required Handoff

```yaml
D5-3 PROVIDER-FREE PARITY / REGRESSION ACCEPTANCE DESIGN:
COMPLETE / READY FOR INDEPENDENT DESIGN REVIEW

Authority:
WELLPLOT-D5-3-DESIGN-AUTH-001

Branch:
design/d5-3-provider-free-parity-acceptance

Starting SHA:
560ec48d2b2809ed2feb55467da15195f527ec44

Candidate SHA:
<created after independent design review or publication authorization>

Parent SHA:
560ec48d2b2809ed2feb55467da15195f527ec44

Design artifact:
docs/architecture/D5_PROVIDER_FREE_PARITY_ACCEPTANCE_DESIGN.md

Changed-file footprint:
design document only

CBL requirements mapped:
9/9

LAS requirements mapped:
9/9

Current canonical coverage:
accepted CBL/LAS behavior covered across D0-D4; normalized preservation,
adapter overlay, invalid-relation integration, and retirement audit require
the finite D5-3 implementation slice

Proposed finite acceptance population:
13 execution slices: 10 Direct Notebook cases plus 3 MCP overlays

Provider/model calls:
0

Production code changed:
NO

Tests changed:
NO

Working tree:
CLEAN after documentation commit

D5-3 implementation:
NOT AUTHORIZED

Live qualification:
NOT AUTHORIZED

Status:
STOP FOR INDEPENDENT DESIGN REVIEW
```
