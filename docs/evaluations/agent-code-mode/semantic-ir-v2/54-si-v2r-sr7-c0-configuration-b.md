# SI-V2R-SR7-C0 Configuration B

Configuration B is the hosted NVIDIA serving configuration proposed for the
future comparison. It is not treated as an independently authenticated model
weights artifact.

```yaml
configuration_id: B
role: CANDIDATE
provider: nvidia_cloud
base_url: https://integrate.api.nvidia.com/v1
requested_model: nvidia/nemotron-3-super-120b-a12b
observed_model_identifier: nvidia/nemotron-3-super-120b-a12b
model_artifact_sha256: UNAVAILABLE_FROM_HOSTED_PROVIDER
endpoint_identity_sha256: 2ae4e6da23bf02fbe1cf7b2d5d3e40bd40f8596336b19a67ed03e70bfffce58f
structured_output: response_format=json_schema
strict_json_schema: true
schema_converter: UNRESOLVED
temperature: 1.0
top_p: 0.95
max_output_tokens: 16384
max_tokens_parameter: max_tokens
reasoning_mode: EXPLICIT_LOW
reasoning_control:
  parameter: reasoning_effort
  value: low
  source: https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-super-120b-a12b-infer
configuration_fingerprint_sha256: a473cc25db1415373b81d7775c263170d7c6388fa45caa5572b11308e8b7d980
```

B1 passed the exact OpenAI-compatible strict JSON-Schema transport probe. B2
also returned HTTP 200, one assistant choice, valid JSON, and a normal finish,
but the content failed local `SemanticIRV2R` validation. The raw response was
not retained, so C0 cannot distinguish a hosted model response failure from a
schema-converter or constrained-decoding failure. This is recorded as an
observed full-schema validation failure, not as proof of a specific root cause.

The NVIDIA API documented `reasoning_effort=low` control was accepted and the
response exposed reasoning metadata. This resolves the intended request
control, but it does not resolve the failed B2 V2R validation.
