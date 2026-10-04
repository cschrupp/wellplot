# SI-V2R-SR7-C0 Configuration Freeze

## Authorization

This slice freezes the two serving configurations proposed for SR7 and probes
only the structured-output capability needed by the future comparison. The
authorized baseline is `fef690452c00dcaea6fa41df0e0af779269372ba` on
`research/semantic-v2r-sr7-c0-config-freeze`.

No 24-case comparison, SR7-P0 harness, historical regrade, prompt experiment,
production change, or semantic scoring change is authorized by C0.

## Frozen Contract

The repository-side inputs are authenticated before any endpoint call:

- `SemanticIRV2R.model_json_schema()`;
- the existing V2R system and structural-retry prompts;
- the existing V2R gold corpus;
- the OpenAI-compatible `response_format=json_schema` and `strict=true` shape.

The current Qwen configuration is probed once with a synthetic request and the
candidate NVIDIA configuration is probed first with a trivial strict JSON
Schema, then with the full V2R schema only if the first probe passes. There are
no retries, case loops, benchmark requests, or worker/program calls.

The candidate request uses the documented NVIDIA `reasoning_effort=low` control,
`temperature=1.0`, `top_p=0.95`, and `max_tokens=16384`. Configuration B is not
frozen unless its transport, full schema, decoding parameters, reasoning
control, and returned model identity are all observed successfully.

## Evidence Boundary

Artifacts retain normalized endpoint/model identity, request/response hashes,
bounded status metadata, latency, finish reason, usage, and validation status.
They never retain authorization headers, credentials, raw response content, or
environment dumps. A successful C0 result would permit SR7-P0 to be scoped;
it would not authorize SR7-P0 or production adoption.

The final C0 decision must be one of:

- `SI_V2R_SR7_C0_CONFIGURATIONS_FROZEN`;
- `SI_V2R_SR7_C0_CANDIDATE_SCHEMA_INCOMPATIBLE`;
- `SI_V2R_SR7_C0_CONFIGURATION_UNRESOLVED`;
- `SI_V2R_SR7_C0_EVIDENCE_INSUFFICIENT`;
- `SI_V2R_SR7_C0_REWORK_REQUIRED`.

SR7-P0 remains unauthorized until independent review of the resulting
configuration records and probe evidence.
