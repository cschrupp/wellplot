# SI-V2R Live Evaluation Contract

## Contract Identity

```yaml
experiment: SI-V2R-LQ0
schema: SemanticIRV2R
compiler_result: CompiledSemanticPlanV2R
accepted_baseline: d896a7e9a634bffe15c6f39ed156dc52c17b2bed
historical_si_v2_2_stable_semantic: 8/24
request_corpus_sha256: b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b
gold_fixture_sha256: eb4803c1b0265f72e2b7f3f97176afe585698473f108d60768e792e4ecfca0a5
semantic_ir_v2r_schema_sha256: d84cdef165ba6d060addd3ed73b018a1f10a3e70ef4a674b5d1a06352c0d58d8
prompt_sha256: 5ebdd3da9bc3cdf78442a97ba0a2ef9fc1c0d5e8b1ca641f18a30fe1b0cb50e3
structural_retry_prompt_sha256: 27c6a43c7f611a79401914b6732dbcec946493bba51058c1eb1d1245f47990f0
qualification_harness_sha256: 6224d77256b045711ad3b1989367fc036dc97afe853c8a1c4343da1b2719d931
```

## V2R Semantic Projection

The hard projection retains report-work presence, ordered sections, ordered
feature kinds, fill target positions, extension keys, and section-owned
reference meaning. Arbitrary `semantic_id` spelling is removed. A
`companion_depth_lane` is not equivalent to an additional curve, and
`reference_track` retains the target feature position.

Report-work goal, requirements, constraints, section context, feature context,
and unresolved requirements are recorded separately as normalized diagnostics.

## Compilation and Safety

Every structurally valid V2R result is compiled through
`compile_semantic_ir_v2r(...)`. The result must be a
`CompiledSemanticPlanV2R`; its section-aligned reference metadata must equal
the generated V2R reference projection. CM58 receives only the compiled legacy
`SemanticPlan` projection, while the V2R metadata remains beside the safety
result.

The future final system result requires capability-type equivalence with the
frozen CM-59A gold, zero CM58 safety regressions, zero wrong final escapes, and
zero reference metadata conflicts. Capability ordering is retained as a
diagnostic and is not itself a safety rejection.

## Thresholds and Decisions

Integrity and endpoint failures take precedence, followed by structural,
compiler/reference-preservation, semantic, and safety gates.

```text
SI_V2R_MODEL_QUALIFIED
SI_V2R_PROVIDER_BOUNDARY_REJECTED
SI_V2R_COMPILER_REJECTED
SI_V2R_MODEL_SEMANTIC_REJECTED
SI_V2R_SAFETY_REJECTED
SI_V2R_LIVE_INCONCLUSIVE_INFRASTRUCTURE
```

Qualification requires zero terminal structural failures, zero unstable cases,
at least 22/24 stable semantic passes, at least 3/4 stable passes in every
family, 2/2 for Fig, Linden, Kestrel, and Xenon, 4/4 for the
`REFERENCE_REQUIRED` family, successful compilation and reference preservation
for every semantic pass, and no CM58 safety failure.

## Provider Contract

The provider sees only the frozen V2R system prompt and a request payload with
the natural-language request, `mode: reconstruct`, and an empty current
document summary. The gold fixture, case ID, family, expected capability IDs,
grader output, and historical evidence never enter provider input.

The sole retry is a format-only structural retry. It cannot contain semantic
feedback or expected output values.

## Evidence and Provenance

Each row binds the reviewed checkpoint, request/prompt/schema/gold/compiler/
registry hashes, execution controls, PRE fingerprint hash, provider trace,
structural status, V2R projections, compiled reference projection, CM58 layer
evidence, and final system classification. Secrets and provider headers are
never serialized.

The future sequence is exactly:

```text
guards -> PRE -> provider construction -> 48 sequential executions -> POST
-> stop network activity -> provider-free finalization
```

Partial evidence is preserved and is inconclusive. It is never resumed,
appended, or automatically replaced.
