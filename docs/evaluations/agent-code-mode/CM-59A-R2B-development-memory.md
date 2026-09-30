# CM-59A-R2B - Schema-Validation-Aware Bounded Retry

## Status

- Baseline: `f0ffdb4d0344407e20e44f821a355dafb7e4c259`
- Evidence basis: CM-59A-R2A-L1
- L1 raw evidence SHA-256: `ccc60d1f30dc823f4caabf0ef8b2b95b9f081562ef984e20018a6fb949648d1d`
- Observed reason: `schema_validation`, `4 / 4` responses
- Endpoint identity: stable

## Scope

R2B changes only the existing second invalid-response retry when the first
failure is a provider-neutral `StructuredResponseProviderError` with category
`invalid_response` and reason `schema_validation`. That retry uses the same
bounded planning context and provider controls, plus the fixed marker
`Schema correction context:`. All other invalid-response reasons retain the
existing identical retry. Non-invalid provider failures remain one-call
terminals.

The response schema, system prompt, semantic validation, semantic correction
path, and two-call maximum remain unchanged. The previous response,
validation details, safe message, raw JSON, and exception representation are
not retained or copied into the schema-correction request. No JSON repair,
schema relaxation, deterministic plan synthesis, Xenon-specific behavior, or
additional retry is introduced.

## Verification Boundary

Implementation makes zero provider, endpoint, worker, or program calls. The
historical live harnesses, historical hashes, and historical evidence remain
unchanged. The implementation checkpoint is pending independent review;
live Xenon retest, CM-59A-E2, and CM-57D remain unauthorized or blocked.

## R2B-R1 Historical Test Isolation

The first full-suite verification after R2B exposed the expected historical
provenance boundary: the current planner source hash is
`1e2858b4663996ccacaf1c42979fc62fe988ba7501d6ec63e00911e6cdc86740`, while
the closed P2-P10 harnesses retain the frozen planner source hash
`0189b290ef4f76bdd776fe2612c454809ff77725379def7d8c5a98d9ae165413`.
The initial R2B result was 2194 passed, 26 failed, and 3 skipped. Thirteen
additional historical failures were blocked at their planner-hash guard before
their intended assertions:

- `tests/test_cm57p10_final_promotion.py::test_pre_live_report_is_provider_free_and_exactly_sized`
- `tests/test_cm57p2_planner_shadow.py::test_prelive_report_is_provider_free_and_guarded`
- `tests/test_cm57p3_work_unit_bisect.py::test_prelive_report_makes_no_provider_calls`
- `tests/test_cm57p4_prompt_interaction_bisect.py::test_instruction_hash_drift_aborts_before_provider_construction`
- `tests/test_cm57p4_prompt_interaction_bisect.py::test_composed_prompt_hash_drift_aborts_before_provider_construction`
- `tests/test_cm57p4_prompt_interaction_bisect.py::test_prelive_report_is_provider_free_and_frozen`
- `tests/test_cm57p5_fresh_holdout.py::test_live_gate_rejects_prompt_source_or_control_drift_before_provider[prompt-Production planner prompt drifted]`
- `tests/test_cm57p6_report_invariant_bisect.py::test_prelive_report_runs_provider_free_and_is_json_serializable`
- `tests/test_cm57p7_fresh_promotion.py::test_prelive_report_is_provider_free`
- `tests/test_cm57p7_fresh_promotion.py::test_prelive_does_not_construct_provider`
- `tests/test_cm57p8_prompt_factor_localization.py::test_manifest_and_frozen_contract_hashes_pass`
- `tests/test_cm57p8_prompt_factor_localization.py::test_prelive_report_constructs_no_provider`
- `tests/test_cm57p9a_inference_reproducibility.py::test_frozen_controls_and_future_population_are_provider_free`

R2B-R1 isolates only the historical planner-byte seam in the corresponding
test modules. Each wrapper returns its harness's frozen planner hash for the
planner path and delegates every other artifact hash to the real implementation.
Each distinct harness also retains a real bogus-planner-hash regression test,
so historical compatibility does not weaken fail-closed drift detection.
Historical scripts, manifests, prompts, schemas, corpora, summaries, raw
evidence, and expected hashes are unchanged. The isolation is test-only and
does not make provider or endpoint calls.

After isolation, the nine historical test modules report 222 passing tests;
the only remaining failure is the known pre-existing P7 stale-summary assertion
(`test_no_live_summary_or_provider_object_is_created_by_default`). The planner
focused and required adjacent suites remain separate gates, and the complete
suite must still be checked against the accepted baseline of 13 known failures
and 3 skips before R2B-R1 is closed.

## R2B-R1 Verification Result

The R2B-R1 historical compatibility set completed with 222 passing tests and
one known pre-existing P7 stale-summary failure. The R2B planner-focused suite
passed 58 tests, and the required adjacent suite passed 123 tests.

The complete repository suite completed with 2216 passed, 13 accepted
pre-existing failures, and 3 skipped. The 13 failures are the established
baseline categories: two agent API tests, the tool-budget threshold, two CM-56R7
missing-evidence tests, the stale CM-57P7 no-live-summary assertion, five graph
report-worker tests, and two graph section-submission tests. No new
R2B-attributable failure was observed.

The frozen planner prompt hash remains
`5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18`, and the
SemanticPlan response-schema hash remains
`3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3`.
Ruff, formatting, Python compilation, and `git diff --check` pass. No provider,
endpoint, worker, or program calls were made.
