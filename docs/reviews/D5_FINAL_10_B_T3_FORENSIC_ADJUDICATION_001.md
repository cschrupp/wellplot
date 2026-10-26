# D5-FINAL-10-B T3 Forensic Adjudication

## Scope

This is a read-only adjudication of `D4-L01:T2` from the consumed campaign
`d5-final-10-qwen-live-20261026-b`. No campaign artifact was modified, and no
provider, model, endpoint, replay, resume, or selective rerun was performed.

Investigated checkout:

```text
5e00654bd8d6f96bc38ce125972b7eb16f482686
```

The five supplied custody hashes were recomputed and matched:

```text
evidence  37a7dd80bc9c01384cc0193e393835be0343900f0364a755015cdf2a3327e100
journal   5b6a746c2b399d0e2464e687f47b23b2e4510b3e9d1a4c7f3b9b0426b8477710
model_io  325dd33c96fc59f02aab6d2a919da16d9ea4973961d70fd57b9f39fc7c5d998f
state     1e048c828126e0cef3eea7923e912e94f4940c76aee3da8d2b8d4b10559627f5
terminal  4b5c4262087238baca203fe28d59a1871b6e8de538bfa731c6f2a5544a0872f4
```

## Custody Reconstruction

The campaign evidence contains **two** logical calls for `D4-L01:T2`, both
planner calls. It does not contain the three valid semantic calls assumed by
the diagnostic request, nor any accepted report-worker or section-worker
response.

| logical call | role | request SHA-256 | response SHA-256 | result |
| --- | --- | --- | --- | --- |
| 8 | planner | `3e0c7545652ae004ace55e2c36a0fcfe3987e4785299e35eaf05b9230363868b` | `a6da2edc36a2cc62478b0af45b8621c314112d4f8d9a2cf7ebb0376bd1fc2525` | HTTP 200, structured validation rejected |
| 9 | planner | `d1f489e498ab597a0a2566d0648e247f4afd646a100ec694d0330ba0fec47924` | `a62c9c72312b79a81559dfd33658a3610693daf3064742212c2423366d3b50d2` | HTTP 200, structured validation rejected |

Both logical-call results record `failure_category=invalid_response`,
`response_reason=schema_validation`, and one bounded root validation issue.
The canonical backend path is: HTTP completion, JSON decoding, response-model
validation, then `StructuredResponseProviderError` with
`SCHEMA_VALIDATION`. The first response contains a natural-language summary
mentioning a linear `5–125` range, but its structured obligations use
placeholder spans/hashes and it does not provide an accepted semantic plan.
The second response contains only section-preservation obligations and also
does not provide a valid section task. Neither response is admissible as a
validated model semantic output.

This establishes the earliest observed divergence as
`PROVIDER_OR_STRUCTURED`, specifically
`PLANNER_RESPONSE_SCHEMA_VALIDATION_FAILURE`. It occurs before any semantic
worker, lowering, reconciliation, private application, obligation
verification, persistence, or rendering.

Therefore the following model-side facts are **not established** by custody:

- planner-selected target or accepted work unit;
- section-worker existing-curve handle;
- accepted output scale kind, minimum, or maximum;
- label/style preservation in an accepted semantic action;
- correction or repair output;
- a report-worker or section-worker semantic response.

## Request Obligations

The exact frozen request is:

```text
In Main Log, set the Gamma Ray curve to a linear 5–125 scale. Leave its label and styling unchanged.
```

The exact executable at the investigated checkpoint deterministically extracts
these scale obligations. All three are `explicit_field`, `owner_kind=binding`,
`owner_ref=request`, `scope=task`, and `state=SET`:

| field | value | UTF-8 span | span SHA-256 |
| --- | ---: | --- | --- |
| `scale_kind` | `linear` | `[37, 62)` | `20109acb0132690b11258dc7034c6660f820e8428a41f1f9ce35aaf4220c7077` |
| `scale_minimum` | `5.0` | `[37, 62)` | `20109acb0132690b11258dc7034c6660f820e8428a41f1f9ce35aaf4220c7077` |
| `scale_maximum` | `125.0` | `[37, 62)` | `20109acb0132690b11258dc7034c6660f820e8428a41f1f9ce35aaf4220c7077` |

Each obligation carries request SHA-256
`866ff67469139034c2062f1c668283c5532d0fc69fd711ed8e55e6c71d12d5f8`.
The request-owned values are internally consistent with the frozen expected
transition to `main.gr.GR.1`, but that target identity is not present in the
captured accepted semantic output.

## Lowering and Private Application

There is no custody-supported chain from a validated worker response through
`SectionSemanticAction`, `lower_section_action()`, reconciliation, grounded
operations, and private execution. Deterministic replay cannot reconstruct
that chain from the captured responses because both planner responses were
rejected before a valid plan existed.

The sealed `D4-L01:T2` row reports:

```text
apply_status       = compile_failed
intent_applied     = false
worker_status      = NOT_REACHED
worker_stage_evidence = []
host_stage_evidence   = all NOT_REACHED
persisted          = false
rendered           = false
starting artifact  = f92bdf2a0b5df8a87d4a02d2dd252e657fde872767181f44a1564edb9910af02
ending artifact    = f92bdf2a0b5df8a87d4a02d2dd252e657fde872767181f44a1564edb9910af02
```

The row diagnostics include `after_assertion_failed` for scale minimum and
maximum, `required_scientific_change_missing`, `persistence_not_proven`,
`render_not_proven`, and `verifier_failed`. They do not expose an accepted
private document state or grounded binding-operation inventory. The submitted
description refers to a `post_lowering_obligation_failed` boundary, but the
sealed row itself records `compile_failed` and no reached worker/host stage;
that difference cannot be resolved from the immutable custody.

Consequently, the requested comparison of expected versus actual private
scale, matching binding IDs, grounded binding IDs, and obligation match count
cannot be performed without inventing unrecorded state.

## LAS Interpretation

`LAS-05` and `LAS-09` are downstream evidence in this record:

- `LAS-05` cannot distinguish a wrong private scale from an unchanged artifact
  after rejection/rollback because no accepted private document was captured.
- `LAS-09` is downstream because persistence and rendering were not reached;
  it is not an independent persistence defect.

The existing campaign attribution
`HOST_SEMANTIC_APPLICATION / HOST_EXECUTION` is **MISATTRIBUTED**. The
sealed evidence establishes a structured-response failure before host
semantic application. It does not establish whether the underlying cause of
the invalid structured response was Qwen's conformance or a planner
schema/contract defect; that narrower ownership question remains open.

The current D5 classifier explains the misattribution. Its
`_classify_logical_call_failure()` recognizes structured failures with
categories `configuration` and `provider_rejected`, but not the actual
`invalid_response` category recorded here. The failure therefore falls
through to later `compile_failed` attribution as
`HOST_SEMANTIC_APPLICATION`, even though the provider/backend custody has
already recorded `response_reason=schema_validation`.

## Terminal

```yaml
forensic_terminal: PROVIDER_OR_STRUCTURED_RESPONSE_FAILURE
observed_failure: PLANNER_RESPONSE_SCHEMA_VALIDATION_FAILURE
existing_campaign_attribution: MISATTRIBUTED
model_semantic_failure: NOT_ESTABLISHED
host_semantic_application_reached: false
host_execution_reached: false
```

This result corrects the causal interpretation of the campaign's operational
`INCONCLUSIVE / HARNESS` terminal. It does not claim a model semantic failure:
the model-side semantic result remains unestablished. The bounded terminal is
known to be a provider/structured-response boundary failure, while ownership
between model structured conformance and a planner schema/contract defect
remains unresolved.

## Scientific Consequence

- `D4-L01:T2` does not constitute usable model semantic evidence for the
  requested scale transition.
- It does constitute evidence of a planner structured-response failure before
  host semantic application; the prior host attribution was incorrect.
- The remaining model-conformance versus planner-schema question can be
  investigated provider-free from the recorded request schema and response.
- No model call is required for this conclusion.
- `C02` remains model-unseen.
- The consumed campaign and namespace remain closed. No new campaign is
  authorized by this adjudication.

## Accounting

```text
base SHA:             5e00654bd8d6f96bc38ce125972b7eb16f482686
campaign:             d5-final-10-qwen-live-20261026-b
changed files:        docs/reviews/D5_FINAL_10_B_T3_FORENSIC_ADJUDICATION_001.md
provider calls:       0
model calls:          0
endpoint calls:       0
C02 exposure:         0
```

The next engineering step, if separately authorized, is provider-free
diagnosis of the exact planner schema mismatch and a bounded correction to
the D5 attribution classifier so `invalid_response` plus
`schema_validation` cannot fall through to `HOST_EXECUTION`. No new Qwen run
is justified by this record.
