# SI-V2R-BR1 Provider-Free Result

## Result

- Baseline: `4f37ef8d6fa441d138f399dd3ac1c45da331fb86`
- Historical decision: `SI_V2R_PROVIDER_BOUNDARY_REJECTED`
- Raw evidence SHA-256: `9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08`
- Provider calls: 0
- Endpoint calls: 0
- Worker/program calls: 0
- Production changes: 0
- Historical scores changed: no

## Derived Mechanisms

- `NONE`: 28 rows / 14 stable cases
- `REPORT_FALSE_POSITIVE`: 10 rows / 5 stable cases
- `ANNOTATION_ERROR`: 4 rows / 2 stable cases
- `STRUCTURAL_UNAVAILABLE`: 6 rows / 3 stable cases
- Allocation-family actual allocation errors: not established; available rows
  preserve count/order, while Umber is unavailable.
- Garnet negative-reference failure established: no.
- Primary residual: report false-positive routing.
- Qwen intrinsic incapability: `NOT_ESTABLISHED`.

## Structural Boundary

Initial structural successes remain 36/48, terminal failures remain 6, and
all six terminal rows remain `UNKNOWN_SCHEMA_VALIDATION_FAILURE` because raw
invalid payloads were not retained. The canonical invariant inventory and
malformed matrix are frozen in the BR1 fixture directory. Runtime relational
rules are not silently attributed to the decoder schema.

Exact deployed converter: no. Status:
`DEPLOYED_CONVERTER_VERSION_UNRESOLVED`.

## Terminal Decision

`SI_V2R_BR1_BOUNDARY_MECHANISM_UNRESOLVED`

No live inference, adapter qualification, CM58 change, ADR-CM57 change, or
production integration follows from this result. The next bounded step, if
authorized, is a provider-free pinned converter/schema audit. If that audit
identifies a concrete unsupported construct, select the smallest lossless
projection and validate its round-trip and malformed-input behavior before any
new model calls.
