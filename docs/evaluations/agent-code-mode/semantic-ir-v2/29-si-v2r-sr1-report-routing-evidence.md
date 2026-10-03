# SR1 Evidence

## Authenticated population

The exact external JSONL population authenticated successfully:

| Measure | Result |
| --- | ---: |
| Rows | 48 |
| Cases | 24 |
| Attempts per case | 2 |
| SHA-256 | `9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08` |

The five stable false-positive cases are Garnet, Ruby, Tamarind, Verde, and
Willow. Their two attempts each contain generated `report_work` despite
section-only gold scope, for 10 rows total. The sanitized report projection is
`tests/fixtures/semantic_ir_v2r_sr1/report_routing_rows.json`.

## Deterministic report-boundary comparison

The existing CM-58.2 classifier agrees with the frozen gold scope for every
case:

| Gold scope | Correct | Total |
| --- | ---: | ---: |
| `REPORT_ONLY` | 4 | 4 |
| `SECTION_ONLY` | 16 | 16 |
| `MIXED` | 4 | 4 |
| Total | 24 | 24 |

All 10 false-positive rows classify as `SECTION_ONLY`. All 16 genuine
report-bearing rows classify as `REPORT_ONLY` or `MIXED`.

The unchanged CM-58.2 implementation was recomputed from the generated V2R
model for all 42 structurally available rows. Stored intent, actions, and
changed status matched in `42/42` rows; six structural rows were unavailable
and were not converted into passes.

## Generated report phenotype

The dominant primary phenotype is `REQUEST_SUMMARY_PROMOTION` (`10/10` rows):
the generated report work restates the requested visualization at a higher
level rather than expressing document work. Secondary labels are derived from
the generated report content and section content using generic criteria:

- `CONSTRAINT_PROMOTION`: `10/10`
- `SECTION_CONTENT_DUPLICATION`: `8/10`
- `TOP_LEVEL_COORDINATION_PROMOTION`: `8/10`
- `CONTEXT_PROMOTION`: `2/10`

All five cases are phenotype-stable across their two attempts. The matched
control table, lexical counts, complexity counts, and report-content counts are
machine-readable in `mechanism_summary.json` and `result.json`.

## Prompt and content controls

The frozen LQ0 prompt already states that report work is only for requested
report/document/packet/brief work, that visualization vocabulary does not by
itself imply report work, and that report work must not be invented. SR1 did
not edit or reinterpret that prompt.

For genuine report-bearing rows, report-owned content was preserved in `8/8`
`REPORT_ONLY` rows and `8/8` `MIXED` rows. This separates report-presence
errors from report-content competence.

These results are corpus observations only. They are not a claim about all
natural-language requests or about model behavior outside this frozen
population.
