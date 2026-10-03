# SR5 Applicability Contract

## Applicability vocabulary

Every relevant dimension receives exactly one primary state:

- `CONTRACT_APPLICABLE`
- `MODEL_OWNED`
- `BLOCKED_BY_REPRESENTATION_CONFLICT`
- `BLOCKED_BY_UNRESOLVED_CONTRACT`
- `FAIL_CLOSED`
- `NOT_APPLICABLE`
- `NOT_EVALUABLE`

These states classify coverage and ownership. They do not adjudicate semantic
correctness and cannot produce a new overall pass, adjusted pass, or score.

## Report ownership

SR4 and SR2 make report presence a deterministic boundary. For structurally
evaluable rows, report-presence policy is `CONTRACT_APPLICABLE` while original
model routing evidence remains visible separately. Report content is
`MODEL_OWNED` whenever report scope is requested; it is not synthesized by
SR5.

## Reference ownership

The reference-intent distinction is explicit in the machine-readable summary:

| Request intent | Applicability | Additional ownership rule |
| --- | --- | --- |
| `EXPLICITLY_FORBIDDEN` | `CONTRACT_APPLICABLE` only when representations are consistent | bounded removal may be eligible for later system credit |
| `EXPLICITLY_REQUESTED` | `CONTRACT_APPLICABLE` for presence preservation | kind and target remain `MODEL_OWNED` |
| `UNSPECIFIED` with a model reference | `BLOCKED_BY_UNRESOLVED_CONTRACT` | current CM58.1 removal is not SR4 credit |
| `CONFLICTING` | `FAIL_CLOSED` | no deterministic resolution |

The raw population contains no `EXPLICITLY_FORBIDDEN` rows. That absence is
recorded rather than converted into an unspecified or eligible state. The
contract still records the distinction so a future population cannot silently
conflate the two intents.

Reference kind and target remain `MODEL_OWNED`. A capability-plan/sidecar
disagreement is `BLOCKED_BY_REPRESENTATION_CONFLICT`, even when an underlying
admissibility rule would otherwise apply.

## Other dimensions

- Annotation semantics are `MODEL_OWNED`; SR5 does not promote prose into an
  annotation feature.
- Unresolved requirements are `MODEL_OWNED`; SR5 does not deterministically
  complete or remove them.
- The WellPlot depth-column scope remains unresolved under SR4, so Garnet's
  possible owner movement is `BLOCKED_BY_UNRESOLVED_CONTRACT`.
- Structurally unavailable rows are `NOT_EVALUABLE` unless frozen evidence
  already contains a valid canonical semantic object. SR5 does not reconstruct
  one.

## Credit boundary

`system_credit_eligibility_by_dimension` is only a prerequisite flag for a
separately authorized regrade. It is not a semantic result. The applicability
map preserves frozen structural status, frozen model status, SR2 status, SR3
root diagnostics, and historical CM58 actions alongside the new SR4 states.
