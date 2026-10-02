# SI-V2R Live Model Qualification Result

## Run Identity

```yaml
experiment: SI-V2R-LQ0
authorized_checkpoint: a6bf60369289a15f555f420c487580d5201c28e5
model: qwen3.6-35b-a3b
endpoint: http://192.168.2.140:8888/v1
rows: 48/48
provider_calls: 60
worker_program_calls: 0
concurrency: 1
temperature: 0.0
max_output_tokens: 16384
timeout_seconds: 900
decision: SI_V2R_PROVIDER_BOUNDARY_REJECTED
```

The population completed in the frozen case and attempt order. No
infrastructure terminal occurred, no row was resumed or appended, and endpoint
PRE/POST identity comparison passed.

```yaml
raw_evidence_sha256: 9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08
pre_fingerprint_sha256: 270d7ca20c0d09e3bd6e8338908fddbbdbec26869c451938bf942b70e7f57eb2
post_fingerprint_sha256: ebc7ab761e4f576effb77207a36a3292d0c6bf222c5306b65300d4178f247221
summary_sha256: 0b42bb5cdb8d14559817e92fc8051d47a75b73d9b1d001f417a5ebd0a29bc88a
endpoint_drift: []
infrastructure_failures: 0
```

## L1 Structural

```yaml
initial_structured_successes: 36/48
initial_structured_failures: 12/48
structural_retries: 12
retry_recoveries: 6
terminal_structural_failures: 6
terminal_failure_reason: schema_validation
```

The six terminal failures were structured-output failures after the single
format-only retry. They are provider-boundary evidence, not infrastructure
failures.

## L2 V2R Semantic

```yaml
semantic_passes: 28/48
semantic_failures: 14/48
stable_semantic_passes: 14/24
stable_semantic_failures: 7/24
unstable_cases: 3/24
required_context_miss_paths: 6
```

Stable family passes:

```yaml
REPORT_ONLY: 4/4
SINGLE_SECTION: 2/4
REFERENCE_REQUIRED: 3/4
MULTITRACK_SINGLE_SECTION: 2/4
MULTI_SECTION_ALLOCATION: 0/4
MIXED_REPORT_SECTION: 3/4
```

Named-anchor attempt passes:

```yaml
Fig: 2/2
Linden: 0/2
Kestrel: 2/2
Xenon: 2/2
```

The stable semantic failures were Tamarind, Verde, Willow, Amber, Garnet,
Iris, and Ruby. Umber, Quartz, and Linden were unstable across their two
attempts. Required-context misses were evaluated separately from topology and
remained ownership-scoped; CM58 output was not used to improve this score.

## L3 Compiler and Reference Preservation

```yaml
compile_successes: 42
compiler_invariant_failures: 0
reference_preservation_failures: 0
semantic_pass_compile_failures: 0
semantic_pass_capability_type_mismatches: 0
```

All structurally valid generated intents that reached compilation preserved
the V2R reference wrapper boundary. Duplicate capability IDs remained a
failure condition rather than being removed during type comparison.

## L4 CM58

```yaml
safe_repairs: 12
safety_rescues: 8
safe_rejections: 0
safety_regressions: 0
wrong_final_escapes: 2
reference_metadata_conflicts: 4
```

The final V2R system projection passed for 28 rows. The eight safety rescues
are reported as downstream system behavior only; they do not increase the L2
model-semantic score.

## Decision

```text
SI_V2R_PROVIDER_BOUNDARY_REJECTED
```

The decision is determined by the six terminal structural failures under the
frozen decision precedence. Production routing, ADR-CM57, CM58 policy, and
production adoption remain unchanged and unauthorized.
