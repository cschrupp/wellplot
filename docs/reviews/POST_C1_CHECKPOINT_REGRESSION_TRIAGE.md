# Post-C1 Checkpoint Regression Triage

## Disposition

Baseline under review: `fe5b750d05e07585c902e61d1f39bc0b0f6e292c`

Parent comparison: `640010ae48a1be075b45719843d969aec177b32b`
Branch: `design/planner-worker-responsibility-realignment`

**Result:** no C1 R2 regression was established. The bounded 215-test selection
passes. A repository-wide run is not green and did not complete. The 102
failure node IDs observed before it stopped were replayed at both HEAD and the
accepted parent; all 102 fail at both checkpoints. Their classification is
therefore `PRE-EXISTING`, with environmental or stale-fixture causes noted
below where established. No C2, acceptance promotion, merge, or publication is
authorized by this diagnostic.

## Environment and Test Evidence

- Canonical checkout: `/home/user/projects/well_log_os`.
- Python: `.venv/bin/python`, Python 3.12.7; pytest 9.0.2.
- Import setup: `PYTHONPATH=src`.
- No provider/model calls were part of these tests.
- `PYTHONPATH=src .venv/bin/python -m pytest --collect-only -q` collected
  2,373 tests.
- Full-suite invocation: `PYTHONPATH=src .venv/bin/python -m pytest -q`.
  The rerun emitted 1,981 test outcomes through about 83.5% of the collected
  suite, including 102 failures and 2 skips, then its execution session ended
  without pytest's terminal summary or exit status. The log is diagnostic
  output, not a completed full-suite result.
- Bounded failure-set reproduction at HEAD:
  `PYTHONPATH=src xargs -a /tmp/wellplot-post-c1-failed-nodeids.txt .venv/bin/python -m pytest -q --tb=short`.
  Result: 102 failed in 97.93s (xargs exit 123 because pytest exited 1).
- The same 102 node IDs at the parent were run from a read-only
  `git archive` export in `/tmp/wellplot-parent-640010ae-audit`, using the
  canonical interpreter. Result: 102 failed in 92.53s (xargs exit 123).
- The first ten failures were also independently reported with tracebacks by
  `PYTHONPATH=src .venv/bin/python -m pytest -q --tb=short --maxfail=10`:
  10 failed, 413 passed, 1 skipped in 169.95s. All ten reproduced at the
  parent with the same failure messages.
- The scoped post-C1 selection was rerun:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_d5_5j_obligations.py tests/test_code_mode_planner.py tests/test_code_mode_workflow.py tests/test_d5_single_engine_convergence.py`
  Result: 215 passed in 13.51s. This is the reproducible latest scoped result.
- The previously reported 657-test result is not independently reproducible
  from repository records: no exact command, selector list, or qualification
  output for that count was found. It must not be represented as a current
  repository-wide pass. Its scope cannot be compared reliably with the current
  2,373-test collection.

The complete list below is the exact bounded set extracted from the full-run
progress output and rerun at both checkpoints. Every listed test is
`PRE-EXISTING` by parent reproduction. Where a failure relies on absent local
evidence/configuration or a fixture path, its proximate classification is also
`ENVIRONMENTAL / FIXTURE`; none is classified `INTRODUCED_BY_C1_R2`.

## Failure Classification

| Test group | Count | Evidence / proximate cause |
| --- | ---: | --- |
| `test_agent_reachability.py` | 2 | Both checkpoints reject required migration module `wellplot.agent.core`, which is not discovered in the inventory. Pre-existing inventory/source mismatch. |
| `test_agent_tool_contract.py` | 1 | Both measure `combined_schema_chars=45297`, exceeding the frozen 40000 ceiling. Pre-existing contract-budget mismatch. |
| `test_capability_plugin_extensibility.py` | 1 | Both reference absent `src/wellplot/agent/graph/workflow.py`. Pre-existing fixture/path mismatch. |
| `test_cm56r7_semantic_failure_decomposition.py` | 2 | Both require absent `/tmp/cm56r6-authoritative-qwen-rerun.jsonl`. Environmental missing evidence. |
| `test_cm57p10_final_promotion.py` | 2 | Both detect frozen provider-base drift; the shared-row test also supplies `SemanticPlan` where current planner code expects a wire plan with `abstention`. Pre-existing frozen-contract/test-fixture mismatch. |
| `test_cm57p2_planner_shadow.py` | 9 | Both checkpoints fail historical prompt/source/corpus identity checks or feed old plan fixtures to the current planner contract. Pre-existing retired-harness drift. |
| `test_cm57p3_work_unit_bisect.py` | 9 | All reproduce at parent; historical arm/prompt identity assumptions no longer match the active planner. Pre-existing retired-harness drift. |
| `test_cm57p4_prompt_interaction_bisect.py` | 10 | All reproduce at parent; frozen prompt/composition hashes and historical source assumptions drifted. Pre-existing retired-harness drift. |
| `test_cm57p5_fresh_holdout.py` | 1 | Historical production-path equivalence fixture fails at both checkpoints. Pre-existing frozen-harness drift. |
| `test_cm57p6_report_invariant_bisect.py` | 6 | Historical schema, prompt and pre-live identities fail at both checkpoints. Pre-existing retired-harness drift. |
| `test_cm57p7_fresh_promotion.py` | 5 | Historical arm and promotion identity checks fail at both checkpoints. Pre-existing retired-harness drift. |
| `test_cm57p8_prompt_factor_localization.py` | 5 | Historical prompt/frozen-contract checks fail at both checkpoints. Pre-existing retired-harness drift. |
| `test_cm57p9a_inference_reproducibility.py` | 1 | Frozen historical controls fail at both checkpoints. Pre-existing harness drift. |
| `test_cm59a_e2_system_reevaluation.py` | 25 | Frozen source/prompt/schema/response-diagnostic checks fail at both checkpoints; fixture is tied to an earlier production snapshot. Pre-existing historical-contract drift. |
| `test_cm59a_r2a_l1_xenon_diagnostic.py` | 8 | Historical prelive/call-budget/finalization/collision contracts fail at both checkpoints. Pre-existing harness drift. |
| `test_cm59a_r2c_a_schema_validation_shape_diagnostic.py` | 2 | Historical helper and prelive identities fail at both checkpoints. Pre-existing harness drift. |
| `test_cm59a_system_reevaluation.py` | 6 | Historical system-reevaluation fixtures fail at both checkpoints. Pre-existing harness drift. |
| `test_code_mode_capability_safety.py` | 1 | Graph routing/safety expectation fails identically at parent and HEAD. Pre-existing contract drift. |
| `test_code_mode_report_boundary_safety.py` | 3 | Graph boundary expectations fail identically at parent and HEAD. Pre-existing contract drift. |
| `test_code_mode_section_leaf_safety.py` | 1 | Graph safety ordering expectation fails identically at parent and HEAD. Pre-existing contract drift. |
| `test_d5_5i_runtime_pin_establishment.py` | 1 | Exact test rerun at both checkpoints fails with `configured server origin mismatch`. Environment/config fixture mismatch, pre-existing. |
| `test_graph_architecture_invariants.py` | 1 | Historical graph topology expectation fails at both checkpoints. Pre-existing contract drift. |

The group counts total 102. The full-suite run did not complete the remaining
392 collected nodes, so those nodes have no result in this triage.

### Captured Traceback Signatures

The first ten current-HEAD failures and their parent replays produced these
same terminal frames/messages:

1. `test_agent_reachability.py:135`, `main(...)` returned 1; stderr:
   `Required migration module 'wellplot.agent.core' was not discovered.`
2. `test_agent_reachability.py:197` -> `_validate_classifications` at
   `check_agent_reachability.py:470`: `InventoryError: Required migration
   module 'wellplot.agent.core' was not discovered.`
3. `test_agent_tool_contract.py:49`: assertion `45297 <= 40000` failed.
4. `test_capability_plugin_extensibility.py:110` -> `Path.read_text`:
   `FileNotFoundError` for
   `src/wellplot/agent/graph/workflow.py`.
5-6. `test_cm56r7_semantic_failure_decomposition.py:151,162` ->
   `verify_evidence_integrity`: `EvidenceIntegrityError: R6 evidence is
   missing: /tmp/cm56r6-authoritative-qwen-rerun.jsonl`.
7. `test_cm57p10_final_promotion.py:190` -> `verify_frozen_contract` at
   `scripts/cm57p10_final_promotion.py:681`: `RuntimeError: CM-57P10 frozen
   artifact drifted: .../src/wellplot/agent/providers/base.py`.
8. `test_cm57p10_final_promotion.py:247` -> `planner.plan` ->
   `_canonical_plan_from_wire`: `AttributeError: 'SemanticPlan' object has no
   attribute 'abstention'`.
9. `test_cm57p2_planner_shadow.py:117` -> `verify_frozen_contract`:
   `RuntimeError: CM-57P1 planner prompt drifted.`
10. `test_cm57p2_planner_shadow.py:133` expected
    `CM-57P1 planner source drifted`, but received
    `CM-57P1 planner prompt drifted.`

The separate D5-5I test
`test_static_preflight_binds_tooling_and_target_checkpoints` failed
independently at both checkpoints: `_static_preflight` raised
`MetadataStaticPreflightError: configured server origin mismatch`.

### Exact Failed Node IDs

```text
tests/test_agent_reachability.py::test_inventory_output_is_deterministic_and_rewrites_identically
tests/test_agent_reachability.py::test_required_migration_modules_are_classified_in_current_inventory
tests/test_agent_tool_contract.py::test_profile_budget_is_bounded_and_smaller_than_diagnostic_contract
tests/test_capability_plugin_extensibility.py::test_protected_runtime_modules_do_not_depend_on_the_fixture
tests/test_cm56r7_semantic_failure_decomposition.py::test_real_evidence_analysis_has_frozen_integrity_and_eligibility
tests/test_cm56r7_semantic_failure_decomposition.py::test_pairwise_recovery_and_regression_buckets_are_present
tests/test_cm57p10_final_promotion.py::test_pre_live_report_is_provider_free_and_exactly_sized
tests/test_cm57p10_final_promotion.py::test_shared_row_preserves_p_then_rc_order_without_workers
tests/test_cm57p2_planner_shadow.py::test_prelive_report_is_provider_free_and_guarded
tests/test_cm57p2_planner_shadow.py::test_historical_planner_drift_still_fails_closed
tests/test_cm57p2_planner_shadow.py::test_frozen_corpus_and_source_summary_are_path_free
tests/test_cm57p2_planner_shadow.py::test_valid_production_planner_result_is_classified_without_downstream_work
tests/test_cm57p2_planner_shadow.py::test_semantic_correction_is_recorded_and_final_plan_is_classified
tests/test_cm57p2_planner_shadow.py::test_invalid_structured_response_retry_is_distinct_from_correction
tests/test_cm57p2_planner_shadow.py::test_terminal_semantic_failure_is_bounded
tests/test_cm57p2_planner_shadow.py::test_wrong_selection_and_duplicates_remain_visible_without_repair
tests/test_cm57p2_planner_shadow.py::test_initial_duplicate_is_recorded_without_normalization
tests/test_cm57p3_work_unit_bisect.py::test_prompt_arm_changes_only_system_prompt[P]
tests/test_cm57p3_work_unit_bisect.py::test_prompt_arm_changes_only_system_prompt[W]
tests/test_cm57p3_work_unit_bisect.py::test_prompt_arm_changes_only_system_prompt[R]
tests/test_cm57p3_work_unit_bisect.py::test_prompt_arm_changes_only_system_prompt[WR]
tests/test_cm57p3_work_unit_bisect.py::test_p_arm_is_production_equivalent
tests/test_cm57p3_work_unit_bisect.py::test_correction_path_uses_same_factor_prompt
tests/test_cm57p3_work_unit_bisect.py::test_direct_and_p_wrapped_correction_requests_are_equivalent
tests/test_cm57p3_work_unit_bisect.py::test_prelive_report_makes_no_provider_calls
tests/test_cm57p3_work_unit_bisect.py::test_historical_planner_drift_still_fails_closed
tests/test_cm57p4_prompt_interaction_bisect.py::test_prompt_composition_preserves_controls_and_hashes
tests/test_cm57p4_prompt_interaction_bisect.py::test_prompt_wrapper_changes_only_system_prompt[R]
tests/test_cm57p4_prompt_interaction_bisect.py::test_prompt_wrapper_changes_only_system_prompt[WR]
tests/test_cm57p4_prompt_interaction_bisect.py::test_prompt_wrapper_changes_only_system_prompt[RW]
tests/test_cm57p4_prompt_interaction_bisect.py::test_prompt_wrapper_changes_only_system_prompt[RC]
tests/test_cm57p4_prompt_interaction_bisect.py::test_correction_path_uses_the_same_arm_prompt
tests/test_cm57p4_prompt_interaction_bisect.py::test_instruction_hash_drift_aborts_before_provider_construction
tests/test_cm57p4_prompt_interaction_bisect.py::test_composed_prompt_hash_drift_aborts_before_provider_construction
tests/test_cm57p4_prompt_interaction_bisect.py::test_prelive_report_is_provider_free_and_frozen
tests/test_cm57p4_prompt_interaction_bisect.py::test_historical_planner_drift_still_fails_closed
tests/test_cm57p5_fresh_holdout.py::test_production_path_equivalence_self_test_is_provider_free
tests/test_cm57p6_report_invariant_bisect.py::test_production_and_experimental_schema_hashes_are_frozen_and_isolated
tests/test_cm57p6_report_invariant_bisect.py::test_rcv_matches_production_requests_when_invariant_is_inactive
tests/test_cm57p6_report_invariant_bisect.py::test_rcs_uses_experimental_schema_and_converts_without_mutation
tests/test_cm57p6_report_invariant_bisect.py::test_rcs_invalid_response_uses_only_production_retry
tests/test_cm57p6_report_invariant_bisect.py::test_prelive_report_runs_provider_free_and_is_json_serializable
tests/test_cm57p6_report_invariant_bisect.py::test_historical_planner_drift_still_fails_closed
tests/test_cm57p7_fresh_promotion.py::test_arm_identity_and_schema_contract_are_frozen
tests/test_cm57p7_fresh_promotion.py::test_all_arm_paths_run_without_provider_calls
tests/test_cm57p7_fresh_promotion.py::test_prelive_report_is_provider_free
tests/test_cm57p7_fresh_promotion.py::test_no_live_summary_or_provider_object_is_created_by_default
tests/test_cm57p7_fresh_promotion.py::test_prelive_does_not_construct_provider
tests/test_cm57p8_prompt_factor_localization.py::test_manifest_and_frozen_contract_hashes_pass
tests/test_cm57p8_prompt_factor_localization.py::test_factor_prompts_change_only_the_frozen_system_suffix
tests/test_cm57p8_prompt_factor_localization.py::test_p8_does_not_use_nonempty_report_or_invariant_schema
tests/test_cm57p8_prompt_factor_localization.py::test_prelive_report_constructs_no_provider
tests/test_cm57p8_prompt_factor_localization.py::test_p8_revision_preflight_qualifies_two_fresh_planner_processes
tests/test_cm57p9a_inference_reproducibility.py::test_frozen_controls_and_future_population_are_provider_free
tests/test_cm59a_e2_system_reevaluation.py::test_prelive_report_is_provider_and_endpoint_free
tests/test_cm59a_e2_system_reevaluation.py::test_frozen_contract_accepts_current_v2_stack
tests/test_cm59a_e2_system_reevaluation.py::test_execution_uses_current_planner_and_three_safety_layers
tests/test_cm59a_e2_system_reevaluation.py::test_fig_report_boundary_repair_is_included_in_e2_stack
tests/test_cm59a_e2_system_reevaluation.py::test_complete_population_is_accepted_with_target_passes
tests/test_cm59a_e2_system_reevaluation.py::test_target_safe_rejection_rejects_even_within_general_allowance
tests/test_cm59a_e2_system_reevaluation.py::test_pre_live_budget_and_target_projection_are_exact
tests/test_cm59a_e2_system_reevaluation.py::test_schema_correction_is_recorded_without_response_leakage
tests/test_cm59a_e2_system_reevaluation.py::test_semantic_correction_call_kind_is_accepted
tests/test_cm59a_e2_system_reevaluation.py::test_each_target_safe_rejection_is_a_hard_failure[FIG]
tests/test_cm59a_e2_system_reevaluation.py::test_each_target_safe_rejection_is_a_hard_failure[LINDEN]
tests/test_cm59a_e2_system_reevaluation.py::test_each_target_safe_rejection_is_a_hard_failure[XENON]
tests/test_cm59a_e2_system_reevaluation.py::test_each_target_wrong_escape_is_a_hard_failure[FIG]
tests/test_cm59a_e2_system_reevaluation.py::test_each_target_wrong_escape_is_a_hard_failure[LINDEN]
tests/test_cm59a_e2_system_reevaluation.py::test_each_target_wrong_escape_is_a_hard_failure[XENON]
tests/test_cm59a_e2_system_reevaluation.py::test_two_non_target_safe_rejections_preserve_22_of_24_acceptance
tests/test_cm59a_e2_system_reevaluation.py::test_family_floor_rejects_two_of_four
tests/test_cm59a_e2_system_reevaluation.py::test_residual_floor_requires_both_cases[LICHEN_CLASS]
tests/test_cm59a_e2_system_reevaluation.py::test_residual_floor_requires_both_cases[MARINER_CLASS]
tests/test_cm59a_e2_system_reevaluation.py::test_unstable_case_rejects_population
tests/test_cm59a_e2_system_reevaluation.py::test_xenon_schema_recovery_metrics_and_terminal_guard
tests/test_cm59a_e2_system_reevaluation.py::test_r1_target_report_shapes_are_provider_free[FIG]
tests/test_cm59a_e2_system_reevaluation.py::test_r1_target_report_shapes_are_provider_free[LINDEN]
tests/test_cm59a_e2_system_reevaluation.py::test_finalize_is_network_free_and_records_exact_file_hashes
tests/test_cm59a_e2_system_reevaluation.py::test_response_diagnostics_artifact_is_protected
tests/test_cm59a_r2a_l1_xenon_diagnostic.py::test_prelive_report_is_provider_and_endpoint_free
tests/test_cm59a_r2a_l1_xenon_diagnostic.py::test_production_planner_call_budget_is_bounded[responses0-1-PLANNER_SUCCESS]
tests/test_cm59a_r2a_l1_xenon_diagnostic.py::test_production_planner_call_budget_is_bounded[responses1-2-PLANNER_SUCCESS]
tests/test_cm59a_r2a_l1_xenon_diagnostic.py::test_finalization_is_provider_and_endpoint_free
tests/test_cm59a_r2a_l1_xenon_diagnostic.py::test_live_collision_guard_runs_before_endpoint_or_provider[evidence_path]
tests/test_cm59a_r2a_l1_xenon_diagnostic.py::test_live_collision_guard_runs_before_endpoint_or_provider[endpoint_fingerprint_pre]
tests/test_cm59a_r2a_l1_xenon_diagnostic.py::test_live_collision_guard_runs_before_endpoint_or_provider[endpoint_fingerprint_post]
tests/test_cm59a_r2a_l1_xenon_diagnostic.py::test_live_collision_guard_runs_before_endpoint_or_provider[summary_path]
tests/test_cm59a_r2c_a_schema_validation_shape_diagnostic.py::test_historical_helper_drift_is_rejected_before_live_activity
tests/test_cm59a_r2c_a_schema_validation_shape_diagnostic.py::test_pre_live_report_is_provider_free
tests/test_cm59a_system_reevaluation.py::test_prelive_report_is_provider_and_endpoint_free
tests/test_cm59a_system_reevaluation.py::test_run_execution_uses_production_planner_and_three_safety_layers
tests/test_cm59a_system_reevaluation.py::test_cm581_terminal_clears_transient_final_plan
tests/test_cm59a_system_reevaluation.py::test_cm582_terminal_clears_transient_final_plan
tests/test_cm59a_system_reevaluation.py::test_cm583_terminal_clears_transient_final_plan
tests/test_cm59a_system_reevaluation.py::test_safety_terminal_row_is_integrity_valid_and_stable_safe_reject
tests/test_code_mode_capability_safety.py::test_graph_safety_runs_before_enrichment_and_workers
tests/test_code_mode_report_boundary_safety.py::test_graph_section_only_cleanup_skips_report_worker
tests/test_code_mode_report_boundary_safety.py::test_graph_mixed_repair_keeps_both_work_units
tests/test_code_mode_report_boundary_safety.py::test_composed_safety_layers_preserve_order_and_emit_both_warnings
tests/test_code_mode_section_leaf_safety.py::test_three_safety_layers_run_in_order_before_enrichment
tests/test_d5_5i_runtime_pin_establishment.py::test_static_preflight_binds_tooling_and_target_checkpoints
tests/test_graph_architecture_invariants.py::test_graph_topology_contains_no_domain_specific_capability_names
```

## C1 Impact and Recommended Action

The C1 R2 implementation files are limited to `obligations.py`, its focused
tests, and the single-engine manifest; the review record is documentation
only. The affected historical/frozen test modules do not touch these changed
contracts. The four-module 215-test selection, including the complete C1
obligations tests and single-engine convergence tests, passes at HEAD. The
evidence therefore does not justify reverting or changing C1 R2.

Keep the 657-test result as an unverified historical report until its exact
selector and output are recovered. Treat the broad historical harness failures
as independent maintenance debt; do not repair them in C1 or use them to
promote C2. No corrective implementation is recommended here.

## Git Integrity Assessment

Read-only diagnostics found this loose ref path:

```text
refs/codex/turn-diffs/checkpoints/4bef3a77292848a33d613f457e1c3bfc0aea1010892fadb75045b11a879ac81f/8b45250568f205cde08e3c63fd98727df06305fa5bda31b06a4e227aa9f17fb4/1791670083964/a2194ccf-945c-4796-8576-edc636e96b97
```

The file is zero bytes. `git fsck --full --no-reflogs --no-progress` exits 2
and reports `invalid sha1 pointer 0000000000000000000000000000000000000000`
for that ref. `.git/gc.log` records:

```text
fatal: bad object refs/codex/turn-diffs/checkpoints/4bef3a77292848a33d613f457e1c3bfc0aea1010892fadb75045b11a879ac81f/8b45250568f205cde08e3c63fd98727df06305fa5bda31b06a4e227aa9f17fb4/1791670083964/a2194ccf-945c-4796-8576-edc636e96b97
fatal: failed to run repack
```

The same `git fsck` reports 214 dangling trees, 6 dangling commits, and 2
dangling blobs. This prevents successful repack/GC and can block commands that
enumerate all refs (a read-only `git log --all -S...` failed on the bad ref).
Dangling objects may accumulate because pruning/repack is not completing. The
active branch, commit lookup, status, and normal push remain operational; the
remote branch resolves to `fe5b750d05e07585c902e61d1f39bc0b0f6e292c`.

No ref, object, `gc.log`, worktree, or user file was deleted or repaired. Git
repair requires separate authorization.
