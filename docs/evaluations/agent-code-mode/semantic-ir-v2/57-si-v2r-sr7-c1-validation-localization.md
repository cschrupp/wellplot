# SI-V2R-SR7-C1 Validation Localization

The single B2-style synthetic probe used the frozen NVIDIA configuration and
the exact `SemanticIRV2R` schema. It returned one normal HTTP 200 assistant
completion with valid JSON.

```yaml
transport_status: PASS
json_parse_status: PASS
local_json_schema_validator: jsonschema.Draft202012Validator
json_schema_conformance: PASS
pydantic_canonical_status: FAIL
validation_error_count: 1
primary_failed_path: []
primary_validator: SemanticIRV2R model_validator
failed_rule: work_required
rule_represented_explicitly: NO_PYTHON_ONLY
synthetic_semantic_status: NOT_EVALUATED
```

The bounded structural projection contains top-level keys `summary` and
`sections`, with `sections` length zero. No `report_work` is present. The
Pydantic error is the frozen top-level invariant that `SemanticIRV2R` must
contain report or section intent. The generated JSON Schema permits an empty
`sections` tuple and does not encode that cross-field requirement, so the exact
response is JSON-Schema-valid but canonically invalid at the WellPlot Python
boundary.

The response content itself was not persisted. Its sanitized evidence records
only length `33` and SHA-256
`1fe54f88498e4ce986ec56676e1bdb9faf7fe4d38995e822894e00a6e62dc1f3`.
