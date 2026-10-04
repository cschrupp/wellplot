# SI-V2R-SR7-C0 Configuration A

Configuration A is the observed current Qwen serving endpoint, not an
assumption that it is identical to the historical LQ0 server.

```yaml
configuration_id: A
role: CURRENT_BASELINE
provider: openai_compat
base_url: http://192.168.2.140:8888/v1
requested_model: qwen3.6-35b-a3b
observed_model_identifier: qwen3.6-35b-a3b
server_backend: llama.cpp
model_artifact_sha256: UNAVAILABLE_FROM_SERVING_INTERFACE
server_version_build: UNAVAILABLE
endpoint_identity_sha256: 848fa23072c3e9af9f4ccdc2a1ba9aa73e88a15695380226118b0bcedbb543a6
historical_lq0_endpoint_identity_sha256: 23afb5ebf67063154bcf02ada6d25b2c929250b14c6a4cad06e8649d087bc980
historical_identity_match: false
structured_output: response_format=json_schema
strict_json_schema: true
schema_converter: UNRESOLVED
parser: WellPlot local json.loads + Pydantic model_validate
temperature: 0.0
top_p: SERVER_DEFAULT_UNRESOLVED
max_output_tokens: 16384
max_tokens_parameter: max_tokens
timeout_seconds: 900.0
reasoning_mode: UNRESOLVED
reasoning_control: UNRESOLVED
structured_output_status: PASS
full_v2r_schema_status: PASS
configuration_fingerprint_sha256: 154513f15bba419aae7ce87c8a0e26a601f45829281e385c599d597fc810711a
```

The one synthetic A1 request returned one assistant choice, valid JSON, and a
`SemanticIRV2R` model-valid response. A reasoning field was exposed by the
endpoint, but C0 does not infer a reasoning mode from that field. The current
endpoint therefore freezes as the A request/schema configuration while keeping
server defaults and artifact provenance explicit.
