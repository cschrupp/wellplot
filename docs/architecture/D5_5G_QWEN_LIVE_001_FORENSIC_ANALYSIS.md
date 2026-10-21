# D5-5G Qwen Live-001 Forensic Analysis

## Scope and custody

```yaml
authority: WELLPLOT-D5-5G-LIVE-INCONCLUSIVE-FORENSIC-CLOSEOUT-AUTH-001
parent_checkpoint: 1714a944181077fe1b63ac634b5d3f00459981e4
implementation_checkpoint: 1714a944181077fe1b63ac634b5d3f00459981e4
campaign: d5-5g-qwen-live-001
sealed_artifact_root: workspace/evaluations/d5-5g/qwen-live-001
sealed_campaign_mutated: NO
provider/model_calls_during_analysis: 0
```

This report reads the sealed state, journal, model-I/O, evidence, terminal, and
summary artifacts. It does not replay or modify them. The machine-readable
companion contains only sanitized evidence: no credentials, headers, or
reasoning content.

## Terminal result

```yaml
status: TERMINAL
decision: INCONCLUSIVE
attribution: D5G_SEMANTIC_REVALIDATION
readiness: LIVE_READY
completed_turns: 5
logical_generation_calls: 4
physical_generation_attempts: 4
endpoint_calls: 2
identity_endpoint_calls: 2
provider_calls: 4
model_calls: 4
```

The companion JSON records SHA-256 values for all six sealed artifacts and the
terminal's digest links. The campaign remains historical evidence.

## A/B evidence

A0, A1, B0, and B1 each reached the provider, received HTTP 200, and produced
an `invalid_response` result with `response_reason=schema_validation`. Each
retained validation shape is one `value_error` at `$root`; `json_decode=PASS`,
`schema_validation=FAIL`, and canonical semantic validation was not reached.
The four cases therefore have the same earliest supported boundary:
`PROVIDER_OR_STRUCTURED`.

The assistant content was valid JSON text but incomplete for the canonical
`SemanticPlan` contract. The companion JSON preserves the returned assistant
content and parsed object for boundary inspection, while intentionally
excluding reasoning content. No case yielded a valid plan, so no semantic
grading or A/B scientific comparison is admissible.

The exact observed response shape for all four cases contains `summary` and
`unresolved_requirements`, but neither `report_task` nor `section_tasks`.
That shape is valid JSON and is admitted by the provider-facing schema as
serialized in the sealed request, but it cannot satisfy the canonical runtime
invariant: `SemanticPlan.validate_work_units()` requires at least one report or
section work unit. Therefore the immediate rejection mechanism is established:

```text
HTTP 200
-> valid JSON
-> no report_task and no section_tasks
-> SemanticPlan.validate_work_units()
-> ValueError at $root
-> schema_validation
-> canonical semantic validation not reached
```

This identifies why WellPlot rejected the response, but not why Qwen selected
that permitted no-work-unit shape.

| Case | Request SHA-256 | Response SHA-256 | HTTP | Boundary | Outcome |
| --- | --- | --- | ---: | --- | --- |
| D5-5G-A0 | c6eb5fb7267a8f96cf1131306756f389cd0a6fe02555dedc6e105449f5edd96b | 0d391d8a33bceccd76d6f9c34e3f382eff8d0b68e59ffaca6194fecb9f36733c | 200 | schema validation at `$root` | INCONCLUSIVE |
| D5-5G-A1 | fcf95f93ead4da8253953262936db5222d394d26aea11fe392fc1b1d4834b2e4 | b384451bdfe1b8839947999ea60e5046a7411956b9d50c710c7d183022f37a79 | 200 | schema validation at `$root` | INCONCLUSIVE |
| D5-5G-B0 | c6eb5fb7267a8f96cf1131306756f389cd0a6fe02555dedc6e105449f5edd96b | 5e6624859642a936ac4d51ae4eba37f14e0029d81ededa2162ab2657bea4b87e | 200 | schema validation at `$root` | INCONCLUSIVE |
| D5-5G-B1 | 1c7379069d3a69cf0edc76001db869ae9497222556e29e376263ca37a11469d5 | 30890ce526a39ef39d3996e4dfb9ee0ca5c569f396788301261914bd557c480d | 200 | schema validation at `$root` | INCONCLUSIVE |

The A request hashes differ, as do the B request hashes. That confirms distinct
wire requests, not a successful experiment: both controlled comparisons stop
at the same pre-semantic boundary.

## C0 evidence

C0 has no request or response record. The committed correction path created a
planner request with `temperature=None`, while the accepted CountingBackend
planner control requires `temperature=0.0`. Control validation therefore failed
before logical-call reservation and physical delegation. C0 is a `HARNESS`
first divergence with zero model calls, not evidence about correction quality.

The same sealed experiment also exposed a context-fidelity defect. The
provider-free D5-5G fixture supplied `current_document_summary.sections` and
`source_summary.candidates`, while the canonical production workflow supplies
`current_document_summary.existing_section_hints` and
`source_summary.sources[].labels` (with channel records). The production
planner prompt names the canonical keys, so the fixture did not exercise the
same planner-context contract. The correction request's safe-summary helpers
would likewise omit those non-canonical fixture fields. This is a deterministic
methodology defect, not a model observation.

## Comparison with D5-4

The campaign reproduces the broad D5-4 pattern of a live provider path failing
before deterministic WellPlot grading, but it is not a direct causal identity:
D5-5G has its own five-case population and its retained evidence identifies the
same class of early provider/structured boundary, not the underlying server or
prompt cause. The evidence supports preserving the first-divergence boundary
and avoiding semantic conclusions; it does not establish that the D5-4 failure
mechanism is identical.

## Causal conclusion

The strongest supported conclusion is:

> The accepted runtime reached Qwen successfully, but all four attempted model
> calls returned JSON with no work unit. The provider-facing schema admitted
> that shape, while the canonical `SemanticPlan` runtime invariant rejected it
> at the root. C0 independently failed in the harness before delegation.

The A/B immediate rejection mechanism is therefore **ESTABLISHED**. The
provider-schema/runtime invariant mismatch and the D5-5G synthetic-context
mismatch are also established. The reason Qwen chose the no-work-unit object
is **NOT ESTABLISHED**. Consequently the A requiredness effect, B capability
contract effect, and C correction-preservation effect were not revalidated;
Qwen semantic capability was not adjudicated.

This does **not** establish that Qwen cannot perform the WellPlot task. It does
not establish why Qwen selected the admitted no-work-unit shape. The remaining
causal alternatives include provider-schema guidance, model behavior, and
prompt/context effects, but they are follow-up hypotheses rather than results
of this campaign.

## D5-5H design handoff

The next design study must restore representation fidelity before another
model comparison. It must:

1. Generate D5 planner inputs from the same canonical summary builders used by
   the production workflow, including `existing_section_hints` and
   `sources[].labels`.
2. Make the provider-facing contract reject a no-work-unit response before
   canonical semantic validation, or document and validate a narrow equivalent
   if the provider's supported schema subset cannot encode the invariant.
3. Reconnect the design to TW-07/TW-08's requiredness findings and the
   established principle that type invariants must not exist only in prompt
   prose.
4. Preserve the single canonical `SemanticPlan` and execution engine; no
   second planner, validator, repair engine, compiler, or shadow path is
   permitted.
5. Define a finite provider-free G-successor matrix that changes neither the
   scientific variables nor the five-case population.

This is a design boundary only. D5-5H implementation and live execution are
not authorized by this record.

## Bounded repair

The authorized repair is limited to deterministic harness correctness:

- default live credential discovery uses the existing D4 loader;
- C0 uses `temperature=0.0`, matching the accepted planner control contract;
- provider-free tests prove default loader resolution, one C0 correction call,
and the five-case shared execution path.

No sealed artifact is changed, no provider/model call is made during repair, and
no prompt, schema, grader, scientific population, or production source is
changed.

## Sealed artifact digests

The companion JSON is the authoritative sanitized digest map. No replay or
selective rerun is performed.
