# SI-V2.2 Live Model Qualification Result

## Population

```yaml
experiment: SI-V2.2
authorized_checkpoint: 3935abf7026b7b66b2d52fdcbc2ff7fd40640cfc
baseline: d461d756c45c63b9f59d1cdc532d031244dc14af
model: qwen3.6-35b-a3b
endpoint_identity: 23afb5ebf67063154bcf02ada6d25b2c929250b14c6a4cad06e8649d087bc980
rows: 48/48
provider_calls: 52
worker_program_calls: 0
infrastructure_failures: 0
endpoint_integrity: PASS
population_integrity: PASS
```

The run completed sequentially for all 24 requests with two attempts per
request. The endpoint identity was unchanged between PRE and POST, and the
finalizer reported no integrity reasons or endpoint drift.

## L1 Structural

```yaml
initial_structured_successes: 44/48
structural_retries: 4
retry_recoveries: 4
final_structural_successes: 48/48
terminal_structural_failures: 0
```

The provider-facing SemanticIRV2 contract was therefore structurally
recoverable for every row. Four initial structured failures required the
bounded generic format retry.

## L2 Semantic

```yaml
semantic_passes: 16/48
semantic_failures: 32/48
stable_semantic_passes: 8/24
stable_semantic_failures: 16/24
unstable_cases: 0/24
```

Stable semantic passes by family were:

```yaml
REPORT_ONLY: 1/4
SINGLE_SECTION: 3/4
REFERENCE_REQUIRED: 0/4
MULTITRACK_SINGLE_SECTION: 1/4
MULTI_SECTION_ALLOCATION: 2/4
MIXED_REPORT_SECTION: 1/4
```

Named-anchor stable passes were:

```yaml
Fig: 1/2
Linden: 0/2
Kestrel: 0/2
Xenon: 0/2
```

The frozen qualification threshold required at least 22/24 stable semantic
passes, at least 3/4 in every family, and 2/2 for each named anchor. The
semantic layer is therefore the primary limiting layer.

## L3 Compiler

```yaml
compile_successes: 48
expected_fail_closed: 0
compiler_invariant_failures: 0
semantic_pass_compile_failures: 0
semantic_pass_signature_mismatches: 0
gold_signature_matches: 18
```

Every structurally valid intent compiled. There was no compiler invariant
failure, semantic-pass compile failure, or semantic-pass signature mismatch.
Deterministic SI-V2 lowering behaved correctly for this population; the 18
gold signature matches are reported separately from semantic scoring and do
not upgrade a semantic failure.

## L4 CM58

```yaml
no_action: 22
safe_repairs: 12
safety_rescues: 10
safe_rejections: 14
wrong_final_escapes: 6
safety_regressions: 0
```

CM58 produced 10 safety rescues and therefore improved final system outcomes
for some semantically incorrect model outputs. Those rescues do not improve
the recorded L2 semantic score. No CM58 safety regression occurred.

## Final System

```yaml
correct_safe_planner_outcomes: 28/48
final_system_passes: 28/48
decision: SI_V2_MODEL_SEMANTIC_REJECTED
```

The complete remediated path was operationally stable and produced no
compiler or safety regressions, but the model did not meet the frozen semantic
qualification thresholds. For the reduced semantic planner role under this
qualification contract, model capability is **NO**.

## Evidence

```yaml
raw_jsonl_sha256: 1b95ebe42ed5227dd134e122c739ca6c6ec90aa72520fc745ffbb622c5527fd7
pre_fingerprint_sha256: dd390c16413d8d538274fd33860df75cf7313322020756925d32456c5673247f
post_fingerprint_sha256: bba2cde27bc2f7baf307c0e2040649f97b89ae23e81d43d41a1b73e157d7b375
```

The raw JSONL and endpoint fingerprint artifacts remain outside Git at their
frozen `/tmp` paths. This document records only their finalizer-produced
hashes and bounded aggregate metrics.

## Status

```yaml
SI-V2.1: COMPLETE / ACCEPTED
SI-V2.2: COMPLETE / MODEL_SEMANTIC_REJECTED
production_adoption: NOT_AUTHORIZED
ADR-CM57: UNCHANGED
next: INDEPENDENT REVIEW
```

No prompt, schema, compiler, CM58, production route, or acceptance criterion
was changed as a result of this population. No follow-up experiment or
remediation is started by this result.
