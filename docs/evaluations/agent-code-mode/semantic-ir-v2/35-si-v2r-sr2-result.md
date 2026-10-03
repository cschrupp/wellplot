# SI-V2R-SR2 Result

```yaml
decision: SI_V2R_SR2_REPORT_PRESENCE_RESOLVED
baseline: e97ae4d53ed82c724a014d7fc5b52598f9ca201d
raw_evidence_sha256: 9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08
raw_rows: 48/48
structurally_evaluable: 42/48
frozen_semantic_pass: 28/48
ownership_adjusted_semantic_pass: 34/48
frozen_stable_pass: 14/24
ownership_adjusted_stable_pass: 17/24
newly_recovered_attempt_passes: 6
newly_recovered_stable_cases: 3
model_report_overreach_rows: 10
cm58_reconciled_overreach_rows: 10/10
remaining_system_report_scope_failures: 0
report_content_failures: 0
remaining_adjusted_semantic_failures: 8
dominant_remaining_adjusted_residual: REQUIRED_CONTEXT_OWNER_ERROR
provider_inference_calls: 0
endpoint_calls: 0
worker_program_calls: 0
production_behavior_changed: false
adr_cm57: UNCHANGED
historical_lq0_decision: SI_V2R_PROVIDER_BOUNDARY_REJECTED
```

The ten report-presence overreaches remain visible as model diagnostics, but
all ten are reconciled by unchanged CM-58.2 and therefore no longer appear in
the ownership-adjusted system residual taxonomy. Report content remains
model-owned and was not lost in the regrade.

This is not `MODEL_QUALIFIED`, `PROVIDER_QUALIFIED`, or `PRODUCTION_READY`.
No ownership implementation or live inference is authorized by SR2.

## Next step

Authorize one bounded provider-free residual analysis/design slice focused on
the remaining context/reference/section semantic errors, starting with the
dominant `REQUIRED_CONTEXT_OWNER_ERROR` and preserving report presence as a
deterministic boundary.
