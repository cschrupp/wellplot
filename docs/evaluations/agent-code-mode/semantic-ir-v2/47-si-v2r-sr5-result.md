# SI-V2R-SR5 Result

```yaml
decision: SI_V2R_SR5_APPLICABILITY_MAP_COMPLETE
baseline: eb9736ddda9feb9e5e601760822da7e0e3933286
raw_evidence_sha256: 9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08
population: 48 rows / 24 cases / 2 attempts
structural_not_evaluable_attempts: 6
report_presence_contract_applicable_interventions: 10
reference_explicitly_forbidden_rows: 0
reference_unspecified_overreach_rows: 4
reference_representation_conflicts: 4
reference_rows_eligible_for_system_credit: 10
depth_column_scope_blocked_rows: 2
annotation_model_owned_residual_rows: 4
unresolved_requirement_model_owned_residual_rows: 2
applicability_map: COMPLETE
regrade_readiness: RE_GRADE_PARTIALLY_READY
historical_scores_recalculated: false
counterfactual_repairs: 0
scoring_changed: false
provider_inference_calls: 0
endpoint_calls: 0
worker_program_calls: 0
production_behavior_changed: false
adr_cm57: UNCHANGED
```

SR5 establishes coverage of the frozen SR4 contract over the historical
population. It does not establish new semantic correctness and does not alter
the frozen LQ0, SR2, or SR3 scores. `CONTRACT_APPLICABLE` means only that a
future regrade may consider the dimension; it is not a pass.

The map is `COMPLETE` because every row and dimension is assigned a defined
state, including `NOT_EVALUABLE` and both blocker classes. Readiness is only
`RE_GRADE_PARTIALLY_READY` because unresolved reference policy,
representation conflicts, and depth-column scope remain material blockers.

## Hard stop

No historical regrade, provider inference, prompt/schema change, CM58/V2R
change, synchronized-wrapper implementation, or production integration is
authorized by SR5. The only possible next activity is a separately authorized
provider-free regrade limited to eligible dimensions and preserving all
blocked/model-owned/not-evaluable states.
