# SI-V2R-SR1 Result

```yaml
decision: SI_V2R_SR1_DETERMINISTIC_REPORT_OWNERSHIP_SUPPORTED
baseline: 7a660d6f4efff7a6b3e54a09fa81a3e08e271de4
raw_evidence_sha256: 9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08
rows: 48/48
report_false_positive_rows: 10
stable_false_positive_cases: 5/5
deterministic_scope: 24/24
false_positive_rows_classified_section_only: 10/10
cm58_available_rows_reconciled: 42/42
report_only_content: 8/8
mixed_content: 8/8
provider_inference_calls: 0
endpoint_calls: 0
worker_program_calls: 0
production_behavior_changed: false
adr_cm57_changed: false
```

## Hypotheses

- `H1_SINGLE_LEXICAL_TRIGGER`: `NOT_SUPPORTED`
- `H2_PROMPT_AMBIGUITY`: `NOT_SUPPORTED`
- `H3_REQUEST_AMBIGUITY`: `NOT_SUPPORTED`
- `H4_COMPLEXITY_COORDINATION_PROMOTION`: `PARTIAL`
- `H5_OPTIONAL_REPORT_FIELD_PRIOR`: `NOT_EVALUABLE`
- `H6_MODEL_REPORT_ROUTING_RESIDUAL`: `PARTIAL`
- `H7_DETERMINISTIC_REPORT_PRESENCE_OWNERSHIP`: `SUPPORTED`

The dominant invented-report phenotype is
`REQUEST_SUMMARY_PROMOTION`, stable across all five false-positive cases.
Lexical and complexity results are descriptive counts, not causal estimates.

## Recommendation

Recommended owner of report presence: `DETERMINISTIC_BOUNDARY`.

The model should remain responsible for report goal, requirements, and
constraints when report scope is explicitly requested. This recommendation is
not implemented by SR1 and does not authorize live inference or production
changes.

## Next step

Authorize one bounded provider-free design slice for the report-presence versus
report-content ownership boundary. Then stop for independent review.
