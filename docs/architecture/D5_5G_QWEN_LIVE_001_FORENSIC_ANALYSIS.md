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
> calls returned JSON that failed the canonical `SemanticPlan` structured
> validation at the root, so the scientific semantic comparison was not
> observed. C0 independently failed in the harness before delegation.

This does **not** establish that Qwen cannot perform the WellPlot task. It does
not distinguish among an insufficient response contract, missing prompt/schema
context, provider structured-output behavior, or model behavior because the
sealed boundary retained only the bounded validation shape. Any such explanation
is a follow-up hypothesis, not a result of this campaign.

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
