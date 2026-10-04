# SI-V2R SR7-P0 Result

```yaml
decision: SI_V2R_SR7_P0_REWORK_REQUIRED
baseline: 9c0dfd2fa0a060195199f21655ccdffd2cc68c9c
case_count: 24
dimension_count: 14
case_dimension_rows: 336
base_logical_calls: 96
provider_calls: 0
endpoint_calls: 0
worker_program_calls: 0
production_changes: 0
live_inference: NOT_STARTED
```

The machine-readable fixtures are the authoritative P0 contract. Their
configuration, runtime-attestation, dimension, mask, comparison, schedule,
evidence, and synthetic-fixture hashes are recorded in
`prelive_result.json`.

This checkpoint is an implementation checkpoint only, not an independently
accepted freeze. The previous raw-equality grader was representation-sensitive;
the current correction replaces it with explicit semantic-equivalence
predicates and adversarial invariance coverage. Future rows also bind the
semantic-dimension-contract hash and scorer-source hash. No live A/B comparison
is authorized by P0. A later P1 must use the repaired hashes without modifying
the scoring mask, retry policy, drift rules, schedule, or evidence schema after
outputs are observed.
