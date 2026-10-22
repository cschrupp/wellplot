# D5-5I live-002 failure adjudication

Authority: `WELLPLOT-D5-5I-LIVE-FAILURE-ADJUDICATION-WORKPACKET-AUTH-001`.
Status: read-only adjudication and proposed corrective slice; ready for independent review.
Campaign: `d5-5i-qwen-live-002`, permanently closed; no replay.
Scientific executable: `fa3bfe59819d9b5e4cac9821b7770d7f4b4b3a0b`.

## 1. Decision summary

The accepted baseline was **not confirmed: 2 PASS / 7 FAIL**. Evidence integrity
passes. This is not evidence of seven independent model-capability failures,
nor evidence that persistence/rendering caused the campaign failure.

The strongest observed problems are loss of explicitly requested semantics at
worker boundaries, incorrect target/channel choices, and a correction that
changes protected plan content. There are also independently demonstrable
reporting defects. Two host-stage failure locations remain unestablished because
the sealed turn rows omit intermediate execution diagnostics. Do not fill these
gaps by treating downstream grader failures as causal evidence.

Some model mistakes occurred despite adequate explicit instructions. Other
failures expose the difference between carrying requirements as prose and
enforcing them as structured, host-owned constraints. This run cannot identify
model capacity as the sole cause, or prove that additional examples would fix it.

## 2. Integrity and analysis limits

[Machine-readable audit](D5_5I_LIVE_002_FAILURE_ADJUDICATION.json) preserves the
original nine turn rows, exact diagnostics, verifier IDs, changed YAML paths,
21 wire-call joins and hashes, schema-validation results, and file digests.
Its additional fields are an analysis overlay, not rewritten campaign evidence.

The audit recomputed accepted custody verification, exact serialized request and
response hashes, parsed-body agreement, authorization/campaign/turn/role joins,
before/after artifact hashes, and available render hashes. Every captured request
contains `chat_template_kwargs.enable_thinking=false`. All 21 physical responses
are HTTP 200, one physical attempt per logical call. The campaign used two
readiness observations; this analysis used zero endpoint/provider/model calls.

| Sealed artifact | SHA-256 |
| --- | --- |
| State | `43eea8fdcd715091ab02b2db1e66b40beee329fcc0d2f9805e1849a6ea4506e9` |
| Journal | `7ed0994a58feb0ef944f0d6bd8be807f19499afa14cff05fe67016e56f68c311` |
| Model I/O | `d877c087f3469b77e1f86295dd78bc713c530eb15693d01e6c44f5983f5495b7` |
| Evidence | `7acdb2e970b8be9eeabfa818bf861ad21f9d991d15b36ba50ad7c0158f9200b8` |
| Terminal | `fbd53f983e22ae672f7a1f96a18e84f352883a876d84a767f0a1f94add22565d` |
| Summary | `992997e4fd81b95c30561dd8adc02a70172bb9cc99d7284a171607654c4432ab` |

All campaign file hashes were unchanged across analysis. Analysis consisted of
JSON/YAML parsing, hash checks, validation against captured JSON Schemas and
existing Python response models, and source inspection. No planner, worker,
lowerer, reconciler, executor, renderer or campaign was invoked. Schema checking
is not response replay. No fixture, gold, prompt, schema or production edit was
made. Raw credentials/headers are not included in the analysis package.

Captured wire schema rejects calls 17 and 18. Existing Python models reject
calls 7, 17 and 18. All response contents decode as JSON. HTTP success therefore
does not imply structured validity. Provider `engine_outcome=success` denotes
response validation, not successful host application.

## 3. Nine-turn matrix

Call numbers refer to the companion JSON and its physical wire line references.
P = planner, R = report worker, S = section worker; correction counts are included.
NE means not established by sealed evidence; NA means not applicable. These
interpretations do not replace the original frozen grader outputs.

| Turn | Grade / calls | Planner and worker outcome | Structured / planner validity | First wrong observable | Primary causal class |
| --- | --- | --- | --- | --- | --- |
| D4-C01:C01 | FAIL / 1-4 (4) | P, R, S main, S repeat return typed responses; requested packet not realized | Wire and Python PASS; planner structural PASS | Section responses omit requested widths and use wrong pass titles; exact subsequent blocking stage NE | MIXED / REQUIRES_DECOMPOSITION |
| D4-L01:T1 | FAIL / 5-7 (3) | P correct; R invents title slot; correction returns empty report update | Wire PASS; Python FAIL on 7; planner PASS | Call 6 uses `report_title` as a general slot instead of top-level title | MODEL_SEMANTIC |
| D4-L01:T2 | PASS / 8-9 (2) | P and S correctly update GR scale | PASS / PASS | NONE | NA |
| D4-L01:T3 | FAIL / 10-11 (2) | P conveys complete request; S omits width; no track inserted | PASS / PASS | Call 11 omits requested 30 mm width | MIXED / REQUIRES_DECOMPOSITION |
| D4-L01:T4 | FAIL / 12-13 (2) | P capability error; P correction changes protected fields; no S call | Wire/Python PASS; canonical correction rejected | Missing section capability and wrong section hint, followed by out-of-scope correction | CORRECTION_PRESERVATION |
| D4-L02:T1 | FAIL / 14-16 (3) | P selects both sections; both S updates apply | PASS / PASS | Ambiguous singular target becomes two targets | MODEL_SEMANTIC |
| D4-L02:T2 | FAIL / 17-18 (2) | P and correction emit no executable work unit; no S call | Wire/Python FAIL both; planner FAIL | Contaminated starting state from T1; responses then violate work-unit schema | MIXED / REQUIRES_DECOMPOSITION |
| D4-L03:C01 | PASS / 19 (1) | P retains missing source request; no S call | PASS / PASS | NONE for accepted causal negative | NA |
| D4-L04:C01 | FAIL / 20-21 (2) | P retains RT; S substitutes ILD; document unchanged | PASS / PASS | Requested unavailable RT replaced with available ILD | MODEL_SEMANTIC |

| Turn | Semantics | Target grounding | Source/channel grounding | Capability | Correction preservation | Safe-negative correctness |
| --- | --- | --- | --- | --- | --- | --- |
| C01 | FAIL, packet absent | Wrong worker pass titles; host resolution NE | Correct source candidates; not proof all bindings applied | Full end-to-end NE | NA | NA |
| L01:T1 | FAIL | Correct report task, wrong title/slot ownership | NA | Report task selected | Failed correction; unrelated persisted loss absent | NA |
| L01:T2 | PASS | Correct curve | Correct GR binding | PASS for this update | NA | NA |
| L01:T3 | FAIL | Correct requested new-track identity | Correct ILD selection | Correct action/kind, incomplete requested payload | NA | NA |
| L01:T4 | FAIL | Initial track title used as section hint | Initial source hints lost during correction | Missing parent diagnostic; correction adds section capability | Guard rejects prohibited changes; guard not shown defective | NA |
| L02:T1 | FAIL | FAIL: two targets instead of clarification | Valid curves in wrong target set | Valid operations do not establish correct intent | NA: no correction call | FAIL: both sections changed |
| L02:T2 | Not independently interpretable | No valid plan | No worker | No valid work unit | Structural repair unsuccessful | NA |
| L03 | PASS negative | No erroneous persisted target | Missing source request preserved; sealed causal grade PASS | No executed worker | NA | PASS |
| L04 | FAIL | Requested target retained | FAIL: RT -> ILD substitution | Returned action valid, request semantics wrong | NA | FAIL despite unchanged file |

| Turn | Mutation | Persistence/reload/render | Frozen failing IDs / diagnostic anchors | Sealed scientific terminal |
| --- | --- | --- | --- | --- |
| C01 | Only scaffold normalization observed; requested packet absent | Required persistence/render not proven | CBL-01,02,04,05,06,08,09; `cbl_persistence_not_proven`, `cbl_render_not_proven`, `cbl_rendered_wrong_artifact`, `cbl_verifier_failed` | FAIL / RESIDUAL_SEMANTIC |
| L01:T1 | No change; title not delivered | Not reached/proven, downstream of title failure | LAS-02,09; title after-assertion and required-change failure | FAIL / RESIDUAL_SEMANTIC |
| L01:T2 | Correct scale change, 3 YAML paths | Sealed positive grading/persistence/render PASS | None | PASS |
| L01:T3 | No change; track absent | Not reached/proven | LAS-03,09; track title/kind/width/binding/scale assertions | FAIL / RESIDUAL_SEMANTIC |
| L01:T4 | No change, safety preserved; fill absent | Not reached/proven | LAS-06,09; fill kind/binding/color/alpha assertions | FAIL / RESIDUAL_SEMANTIC |
| L02:T1 | Wrong mutation in both sections, 5 paths | Persisted/rendered wrong semantics | `failure_mutated_artifact`, `failure_bytes_changed`, `failure_persisted_artifact`, `failure_canonical_state_changed`, `failure_applied_intent` | FAIL / RESIDUAL_SEMANTIC |
| L02:T2 | No new mutation; prior erroneous state remains | No new successful persistence/render | LAS-01,05,09; before-state and after-scale assertions | FAIL / RESIDUAL_SEMANTIC |
| L03 | No change, as required | No persistence/render is correct for this negative | None | PASS |
| L04 | No file change; submitted intent is not proven applied mutation | No persisted substituted curve | `failure_applied_intent`, `failure_flag_not_false: intent_applied` | FAIL / RESIDUAL_SEMANTIC |

The JSON retains **every exact diagnostic string**, not just these table anchors,
and the original dimension labels and first-divergence values for comparison.

## 4. Causal chains and limits

### CBL reconstruction: omissions, then an unlocalized host boundary

Calls 1-4 demonstrate substantial understanding: the planner carries requested
metadata, remarks, sources and tracks; section responses contain four ordered
tracks with proper kinds and source candidates. Nevertheless every requested
track width is omitted, and main/repeat worker titles are generic report titles.
The section context target is only `{"kind":"existing"}`; correct titles remain
in the task/authoritative request, so this is not total input absence.

Source inspection identifies a concrete fragility: the reconstruct dimension
normalizer expects `Track N (id): normal, 50mm`, while the captured planner uses
`Track 1 (Combo): Normal track, width 50mm`. That parser cannot recover these
widths from this representation. Other host semantic normalization exists, so
raw worker omissions or report-slot aliases cannot all be equated with persisted
defects. In particular, report normalization may repair raw report fields.

The final YAML contains scaffold normalization (40 changed paths), not the
requested packet. This fans out into seven CBL failures and missing render.
The record does not seal enough compile/reconciliation/apply diagnostics to
prove which host stage prevented the packet. This is **not evidence of a renderer
crash**, nor proof the width omission alone caused the entire CBL failure.

### Report title: ownership error followed by inconsistent repair contract

Call 6 receives explicit top-level title/subtitle instructions but emits
`general_fields=[{"slot_id":"report_title",...}]`. The correction request reports
`Unknown general report slot 'report_title'.` Its system instruction also says
to return values using exact host-approved slot IDs, which is an awkward repair
instruction for a top-level title. Call 7 emits `{"general_fields":[]}`.

That empty update passes the wire schema but fails Python's report nonempty
validator. Thus the initial mistake is observed model semantics; the repair
also exposes contract inconsistency and schema/Python disparity. No title change
occurs; persistence/render failures are consequences, not independent causes.

### Add track: missing required meaning despite valid response shape

Call 10 includes 30 mm width. Call 11 retains title, normal kind, ILD channel,
label and log scale 0.2..2000, but omits width. The add-track lowerer emits width
only when present; the reconstruct-only normalizer does not repair add-track.
The reconciler requires an effective width or defaults. The artifact is unchanged.

Missing width is proven; the exact host rejection and effective defaults are not
sealed. Do not assert `track_create_incomplete` was the actual terminal merely
because that source diagnostic exists. Eight missing final properties largely
describe **one absent track**, not eight separate model errors.

### Fill: protected correction rejected, not broken fill execution

Call 12 uses `Gamma Ray` as a section hint and lacks the section capability.
Call 13 receives `missing_section_capability` and a capability-only allowed-change
projection. It adds the section capability, but also changes the section hint,
drops source hints and adds constraints. Source inspection of the canonical
scope guard establishes why these captured changes are outside the permitted
repair. No section-worker call follows; the artifact is unchanged.

This supports a rejected correction-preservation attempt, not a defective
preservation guard or fill compiler. Missing fill fields are downstream. The
sealed `NOT_APPLICABLE` correction label misses a real correction invocation.

### Ambiguity fans out into the next turn

L02:T1 requests a singular Main Log target when inventory has Upper and Lower.
The planner selects both with no unresolved requirement. Workers correctly
perform the wrong two-target plan. Both sections persist at 20..110.

L02:T2 consequently begins in the wrong state. Its planner notices the requested
scale is already present and returns no work; both responses violate the captured
work-unit `anyOf` and Python validation. H's work-unit schema requirement is
present, not lost. HTTP 200 with schema-invalid content proves noncompliant output,
not why the server's structured-output enforcement failed. T2 cannot be used as
an uncontaminated independent test of clarified-target capability.

### Missing source passes; missing channel is silently substituted

L03 preserves the missing source request and passes the sealed causal-negative
grade without mutation. No additional failure-owner detail is invented.

L04's planner retains RT. Its worker substitutes available ILD, with a binding
named `bind-rt-01`, despite inspected inventory lacking RT. Availability checks
on returned ILD do not prove fidelity to requested RT. Width is also absent.
The document remains unchanged. The frozen evidence helper defines
`intent_applied` using presence of `submitted_intent`, so this flag alone does
**not** establish committed bad mutation. The semantic substitution is still
wrong; safety containment does not make it a correct negative.

## 5. Reporting defects, separate from scientific failures

At the frozen executable, `scripts/nlp_d5_live_semantic_qualification.py` contains
these source-verifiable limitations:

- Logical failure classification excludes `invalid_response` from the categories
  used to establish provider/structured failure. Dimension construction then
  defaults provider/planner validity to PASS, contradicting calls 7, 17 and 18.
- Mutation dimension treats any `changed=true` as FAIL, including successful
  positive L01:T2. Expected outcome must govern the interpretation.
- Persistence/render absence is marked FAIL even for correct safe negatives.
- String-matching `failure_bytes_changed` assigns CORRECTION_PRESERVATION even
  to L02:T1, which had no correction invocation.
- Correction evidence is not reliably joined to wire correction invocations.
- Bounded turn projection omits intermediate host diagnostics needed to locate
  CBL and add-track rejection. Aggregate first divergence is execution-order
  first, not a cross-turn causal minimum.

These are **GRADER_OR_FIXTURE-class evidence-reporting defects**, not a finding
that frozen gold should change or that seven failures should become passes.
The sealed terminal remains valid as produced; this document supplies a separate
interpretation. No failure is confidently assigned PERSISTENCE_RENDER as its
primary cause, and no exact HOST_EXECUTION root is proven for the unresolved cases.

## 6. Minimal supported clusters

1. **Requested semantics are not consistently bound to executable constraints.**
   Report title ownership, track dimensions and requested channel identity expose
   different instances. Some instructions were supplied correctly and ignored;
   some host interpretation remains prose-format dependent. These are related
   boundary weaknesses, not proof of a single shared implementation bug.
2. **Target cardinality/ambiguity escapes into execution.** L02:T1 causes actual
   wrong mutation and contaminates T2. This is one causal fanout, with a secondary
   schema-invalid no-work response, not two clean independent failures.
3. **Bounded correction does not reliably remain in scope.** L01:T4 is rejected
   safely. L01:T1 also shows an unsuccessful repair with a different ownership
   problem. Neither warrants removing preservation constraints.
4. **Evidence projection obscures the first boundary.** This affects interpretation
   across turns but does not itself explain the wrong model responses.

Seven failed grades therefore do not identify seven independent causes. Conversely,
the evidence is insufficient to collapse all failures into one universal defect.

## 7. Historical reconciliation, not rediscovery

Sources: [active baseline](../agent-code-mode-current-baseline.md),
[D5-5F reconciliation](D5_5F_HISTORICAL_SEMANTIC_CONTRACT_RECONCILIATION.md), and
[TW development memory](../evaluations/agent-code-mode/EXP-TW-consolidated-development-memory.md).
The repository labels this lineage CM/TW; no additional experiment called CW is
invented here to satisfy the informal historical label.

| Historical evidence | Controlled result / limitation | Current alignment or loss | Design implication and confidence |
| --- | --- | --- | --- |
| TW-02 / TW-02I | Typed task input, provenance and explicit host presentation policy; narrow successful deterministic compilation | Canonical typed lowering preserved; several explicit facts now rely on prose requirements and brittle consumption | Recover field-level ownership/provenance, not old engine. HISTORICALLY_DEMONSTRATED within that narrower task |
| TW-03 | Structural 20/20, semantic Gate A 4/20 | Many current responses structurally valid yet wrong | Syntax is not semantics. HISTORICALLY_DEMONSTRATED |
| TW-03S | Typed track/binding alternatives | Current normal/reference/array kinds retained | Do not repeat type-tag design experiments. HISTORICALLY_DEMONSTRATED |
| TW-05 / TW-06 | Union-related bisects did not establish a universal remedy | Current failures include valid schemas and correct kinds | Union simplification is INCONCLUSIVE, not an indicated repair |
| TW-07 / TW-08 | Required discriminators improved the controlled narrow bundle from R0 structural 1/20, Gate A 0/20 to R1 20/20 both | Required kinds retained; present defects concern other constraints | Reuse the lesson, not the score as a prediction for nine-turn D5. HISTORICALLY_DEMONSTRATED |
| CM-56R8 | Local raster contract 9/9; whole task 0/15 | Local successful scale operation coexists with campaign failure | Local examples do not establish whole-task correctness. HISTORICALLY_DEMONSTRATED |
| CM-57P10 | Prompt correction improved stable results 4/24 to 16/24, still below acceptance with protected/terminal failures | Current correction can leave scope | Old prompt is not an accepted remedy. HISTORICALLY_DEMONSTRATED limitation |
| CM-59A | Stable 21/24, wrong-plan escape 1 and planner failures 2 | L02 shows executable but wrong plan; L04 safe containment is not correct intent | Preserve wrong-plan rejection and causal-negative requirements. HISTORICALLY_DEMONSTRATED |

Current evidence supports explicit requested-width checks, title ownership,
channel identity preservation and target-cardinality checks
(`SUPPORTED_BY_CURRENT_D5_EVIDENCE`). The proposed integrated implementation below
is an `ADAPTED_DESIGN_HYPOTHESIS`, not already proven by an old score.

Reuse candidates: typed provenance, explicit host policy, required discriminators,
bounded target inventories, causal negatives, existing correction-scope guards.
Superseded: retired TW/CM runtimes and alternate engines. Benchmark-specific:
old score/fixture wording. Inconclusive: generic schema simplification or more
examples as sufficient remedies. Rejected: broad old prompt promotion, relaxed
negative grading, silent channel substitution, or removing scope protection.

The distinction is consistent with established schema semantics: properties are
not required merely because declared, and defaults are annotations rather than
automatic value insertion ([JSON Schema objects](https://json-schema.org/understanding-json-schema/reference/object),
[annotations](https://json-schema.org/understanding-json-schema/reference/annotations)).
Constrained decoding addresses formal validity, not correct user-target identity;
[PICARD](https://aclanthology.org/2021.emnlp-main.779/) is relevant evidence for that
boundary, not proof about the deployed Qwen server's schema implementation.

## 8. Proposed next bounded implementation slice (not implemented)

**Canonical request-to-action obligation preservation**, within the existing
planner/workers/lowering/reconciliation path. No new planner, worker, adapter,
semantic runtime or evaluator. Review this package before implementation.

Prioritize by causal leverage:

1. Bind already-explicit requested properties and their ownership to existing
   canonical tasks/actions, and validate them before application: report title
   versus slot, requested track width, requested channel versus merely available
   channel, singular target versus multiple candidates. Preserve provenance and
   fail closed on ambiguity; do not recover intent with fixture-shaped regexes.
2. Remove reliance on one planner sentence format for host dimensions. Use the
   existing canonical representation and explicit host policy. Do not fabricate
   omitted user facts or introduce a second semantic contract.
3. Make existing bounded corrections ownership-consistent while retaining scope
   enforcement. Align report nonempty wire/Python validation. Reject omissions
   and substitutions with precise canonical diagnostics, not hidden repair.
4. Include boundary evidence as acceptance instrumentation: exact host diagnostic,
   submitted versus applied intent, expected-outcome-aware dimensions and actual
   wire correction joins. This is necessary to validate this slice, not permission
   to rewrite sealed outcomes or weaken graders.

Provider-free acceptance should use unrelated names, paraphrased requirements,
reordered tracks, omitted required dimensions, unavailable requested channels,
ambiguous singular targets, no-work responses and protected correction changes.
Prove the same canonical path, scope guards and causal negatives survive. Include
positive scale/title cases, not only rejection tests. Preserve frozen H regressions,
cases/gold, historical campaigns and attestation discipline. No live rerun is part
of this proposal; no estimated improved pass rate is asserted.

The unresolved CBL/add-track host locations must remain explicit acceptance gaps
until authorized deterministic tests expose their diagnostics. This analysis did
not execute those tests or silently select a speculative host repair.

**Do not fix:** endpoint/runtime configuration, thinking control, model selection,
SDK retries, render engine, source assets, frozen gold, required-kind schema,
H work-unit requirement, single-engine composition or the working preservation
guard. Do not start an examples/prompt/model comparison campaign on this evidence.

## 9. Closeout

Evidence integrity PASS; all nine turns adjudicated; sealed outcome unchanged.
Analysis calls: endpoint 0, provider 0, model 0. Production changes 0; execution
or replay 0; historical mutation 0. Baseline confirmation remains FAILED.
Stop for independent scientific/adjudication review. Implementation and another
live campaign are not authorized by this package.
