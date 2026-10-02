# SI-V2R Provider-Free Result

## STATUS

```yaml
decision: SI_V2R_ACCEPTED_FOR_LIVE_QUALIFICATION
baseline_sha: 6249557de70f6f3b740e9ea17a96d600c6acf3f0
correction_checkpoint: 7dc5833cb800300cc9c3b45930745c84337f0b79
branch: research/semantic-ir-v2-reconciliation
provider_calls: 0
endpoint_calls: 0
worker_program_calls: 0
historical_si_v2_result_changed: false
```

This decision records provider-free acceptance of the V2R lowering boundary
for a future qualification design. It does not authorize live inference,
production integration, ADR-CM57 changes, CM58 changes, or routing changes.

## FROZEN SI-V2.2

```yaml
decision: SI_V2_MODEL_SEMANTIC_REJECTED
stable_semantic_passes: 8/24
initial_structural_successes: 44/48
terminal_structural_failures: 0
compiler_invariant_failures: 0
semantic_pass_compile_failures: 0
cm58_safety_regressions: 0
exact_order_final_system_passes: 28/48
```

The historical result document and raw JSONL were not modified.

## FAILURE TAXONOMY

```yaml
exact_v2_passes: 16
reference_representation_mismatch: 8
reference_overreach: 2
report_false_positives: 10
report_false_negatives: 2
report_note_section_duplication: 10
allocation_errors: 0
feature_errors: 0
order_only_final_mismatches: 6
other: 0
ambiguous: 0
```

The taxonomy has no case-specific branches and is reproducible from the
authenticated raw evidence SHA
`1b95ebe42ed5227dd134e122c739ca6c6ec90aa72520fc745ffbb622c5527fd7`.

## REPOSITORY RECONCILIATION

Existing typed-worker semantics already distinguish normal, reference, and
array tracks and retain worker-owned channels, scales, sample-axis values,
source candidates, and titles. Existing report-worker ownership covers report
title/subtitle, headers, service/detail fields, remarks, page, depth, output,
and tail. V2R therefore remains planner-level.

The selected planner responsibility is:

```text
coarse report work
+ ordered section allocation
+ curve/raster/fill/annotation semantic features
+ section-owned reference/depth intent
+ source and revision hints
+ requirements and constraints
```

It excludes worker details and report construction.

## IMPLEMENTATION RESULT

```yaml
fresh_cm59a_gold_cases: 24/24
additional_domain_fixtures: PASS
plugin_extensibility: PASS
ambiguous_parent_fail_closed: PASS
immutable_deterministic_lowering: PASS
capability_type_equivalence: PASS
authenticated_48_row_taxonomy: PASS
reference_semantic_preservation: PASS
production_imports_of_v2r: 0
production_route_changed: 0
```

The V2R compiler lowers every fresh gold intent through the existing
`SemanticPlan` validator and `validate_semantic_plan`. It does not normalize,
repair, or infer missing semantic content. Independent review accepted the
`CompiledSemanticPlanV2R` boundary: the validated legacy `SemanticPlan` is
returned together with one section-aligned reference-intent slot per lowered
section, so `companion_depth_lane` and `reference_track(target=...)` remain
distinct for downstream consumers.

## SAME-ENVIRONMENT VERIFICATION

Pre-change baseline:

```text
focused: 398 passed, 6 known CM-59A Xenon failures
full: 2306 passed, 23 known baseline failures, 3 skipped, 11 subtests passed
```

Final focused and full-suite results:

```text
V2R focused/provider-free tests: 13 passed
adjacent focused regression set: 411 passed, 6 known CM-59A Xenon failures
full suite: 2319 passed, 23 known baseline failures, 3 skipped,
            11 subtests passed
```

The post-correction full-suite failure node IDs are identical to the recovered
baseline failure IDs. There are zero new attributable failures. The adjacent
regression set retains only the six known CM-59A Xenon failures. Ruff check,
Ruff format check, Python compilation, JSON validation, and `git diff --check`
all pass after the correction.

## QUALIFICATION STATUS

The 24/24 capability-type representability result and the corrected
reference-preservation boundary are accepted for future SI-V2R live model
qualification. The correction changes no production `SemanticPlan`, routing,
or frozen SI-V2 evidence.

## NEXT STEP

The next substantive slice is the separately authorized SI-V2R live model
qualification. Until that authorization:

```yaml
production_adoption: NOT_AUTHORIZED
live_inference: NOT_AUTHORIZED
ADR-CM57: UNCHANGED
CM58: UNCHANGED
```
