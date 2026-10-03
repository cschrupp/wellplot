# SR2 Residual Analysis

## Model versus system residuals

The model diagnostic taxonomy retains `REPORT_FALSE_POSITIVE: 10`. The
ownership-adjusted system taxonomy removes that mechanism after successful
CM-58.2 reconciliation. Remaining adjusted system residual counts are:

| Mechanism | Rows |
| --- | ---: |
| `REQUIRED_CONTEXT_OWNER_ERROR` | 6 |
| `REFERENCE_FALSE_POSITIVE` | 4 |
| `ANNOTATION_ERROR` | 4 |
| `FEATURE_KIND_ERROR` | 4 |
| `FEATURE_MULTIPLICITY_ERROR` | 4 |
| `SECTION_ORDER_ERROR` | 4 |
| `UNRESOLVED_REQUIREMENT_ERROR` | 2 |

The dominant remaining residual by row count is
`REQUIRED_CONTEXT_OWNER_ERROR`. This is a bounded regrade observation, not a
new ownership decision.

## Family metrics

| Family | Adjusted passes / evaluable | Stable passes | Stable failures | Unavailable |
| --- | ---: | ---: | ---: | ---: |
| `REPORT_ONLY` | 8/8 | 4 | 0 | 0 |
| `SINGLE_SECTION` | 4/8 | 2 | 2 | 0 |
| `REFERENCE_REQUIRED` | 6/6 | 3 | 0 | 1 |
| `MULTITRACK_SINGLE_SECTION` | 6/6 | 3 | 0 | 1 |
| `MULTI_SECTION_ALLOCATION` | 4/6 | 2 | 1 | 1 |
| `MIXED_REPORT_SECTION` | 6/8 | 3 | 1 | 0 |

Named anchors retain their historical interpretation: Fig, Kestrel, and Xenon
are stable passes after adjustment; Linden remains structurally unavailable.

## Interpretation boundary

SR2 establishes only that report-presence overreach is resolved for this frozen
population under the accepted deterministic ownership contract. It does not
claim that Qwen would have emitted better output, does not qualify the model,
and does not authorize production integration.
