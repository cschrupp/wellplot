# SR2 Ownership-Adjusted Regrade

## Population integrity

The exact 48-row population authenticated successfully:

| Measure | Result |
| --- | ---: |
| Rows | 48 |
| Cases | 24 |
| Attempts per case | 2 |
| SHA-256 | `9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08` |

The frozen LQ0 facts remain unchanged: `28/48` semantic passes, `14/24`
stable semantic passes, six terminal structural failures, and decision
`SI_V2R_PROVIDER_BOUNDARY_REJECTED`.

## Regrade metrics

| Measure | Frozen | Ownership-adjusted |
| --- | ---: | ---: |
| Semantic attempt passes | 28/48 | 34/48 |
| Stable case passes | 14/24 | 17/24 |
| Structurally evaluable attempts | 42 | 42 |
| Newly recovered attempt passes | - | 6 |
| Newly recovered stable cases | - | 3 |
| Remaining adjusted failures | - | 8 |

The transition table is:

| Transition | Rows |
| --- | ---: |
| `FROZEN_PASS -> ADJUSTED_PASS` | 28 |
| `FROZEN_FAIL -> ADJUSTED_PASS` | 6 |
| `FROZEN_FAIL -> ADJUSTED_FAIL` | 8 |
| `NOT_EVALUABLE -> NOT_EVALUABLE` | 6 |

No frozen pass regressed. The six unavailable rows remain unavailable.

## Report-presence accounting

- Model report-routing overreach: `10` rows.
- CM-58.2-reconciled overreach: `10/10`.
- Rows whose only frozen failure was report presence: `6`.
- Rows with report overreach plus another semantic error: `4`.
- Remaining system report-scope failures: `0`.
- Report-content failures: `0`.
- Report removals: `10`.
- Report additions: `0`.
- Boundary rejections: `6`.

Garnet remains `FAIL -> FAIL` because required context ownership is still
wrong; report presence itself is reconciled. Ruby is `FAIL -> PASS`, Tamarind
is `FAIL -> PASS`, Verde is `FAIL -> FAIL` because of reference false positives,
and Willow is `FAIL -> PASS`.

For genuine report-bearing rows, report-owned content remains independently
graded and no content failure was introduced.
