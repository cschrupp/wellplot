# SR7-P0 Configuration Contract

## Configuration A

`A` is the current baseline Qwen model-plus-serving configuration. Its frozen
configuration fingerprint is:

`154513f15bba419aae7ce87c8a0e26a601f45829281e385c599d597fc810711a`

The material contract is temperature `0.0`, `max_tokens=16384`, timeout `900`
seconds, concurrency `1`, and strict `response_format=json_schema`. Artifact
provenance not exposed by the serving interface remains unavailable.

## Configuration B

`B` is NVIDIA Nemotron served through the NVIDIA OpenAI-compatible endpoint.
Its frozen configuration fingerprint is:

`a473cc25db1415373b81d7775c263170d7c6388fa45caa5572b11308e8b7d980`

The material contract is temperature `1.0`, `top_p=0.95`,
`reasoning_effort=low`, `max_tokens=16384`, timeout `900` seconds, concurrency
`1`, and strict `response_format=json_schema`. Hosted weights and backend
artifact identity remain unavailable. The comparison must not be described as
isolating model weights independently of serving configuration.

## Drift

Material runtime identity is attested separately from the research fingerprint.
Any mismatch in model, decoding controls, timeout, schema/prompt/gold hashes,
structured-output mode, or concurrency aborts before the first semantic call or
produces `INCONCLUSIVE_CONFIGURATION_DRIFT`. Unrelated hosted catalog changes
are not material drift.
