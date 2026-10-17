# Runtime Configuration

WellPlot runtime infrastructure is configured by `config/wellplot.yaml`. The
file contains non-secret deployment settings only. Credentials remain in the
existing local credential mechanism and are never stored in YAML.

The configuration is loaded and validated with a strict, immutable Pydantic
model. Unknown keys, secrets, unsupported providers, malformed origins, and
invalid runtime values fail closed before readiness or model activity.

`provider.server_origin` is the only endpoint value stored in YAML. The
loader derives the OpenAI-compatible base URL, `/v1/models`, and `/props`
URLs. A canonical JSON projection of the normalized values is SHA-256 hashed;
the D5 live authorization must carry the same fingerprint.

The current non-secret deployment contract is:

```yaml
schema_version: 1
provider:
  name: openai_compat
  model: qwen3.6-35b-a3b
  server_origin: http://192.168.2.141:8888
  timeout_seconds: 900
  max_retries: 2
runtime:
  concurrency: 1
  structured_output: json_schema
```

The YAML file is intentionally not a replacement for the D5 authorization.
The authorization still freezes endpoint identity, source and gold custody,
runtime identity, and the campaign artifact namespace.
