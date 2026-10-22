# D5-5I Runtime-Pin Establishment Design

```yaml
authority: WELLPLOT-D5-5I-RUNTIME-PIN-ESTABLISHMENT-DESIGN-AUTH-001
branch: design/d5-5g-inspectable-historical-claim-revalidation
historical_campaign: d5-5-qwen-inspectable-002
historical_identity: PARTIALLY_RECOVERED
metadata_endpoint_execution: NOT_AUTHORIZED
provider_model_calls_during_design: 0
endpoint_calls_during_design: 0
```

## Purpose And Boundary

This document defines one bounded metadata-only observation gate to establish
Qwen readiness fields that were not sealed by the historical inspectable
campaign. It does not amend the historical campaign, refresh its identity, or
authorize D5-5I live execution.

The future pin-establishment attempt is separate from the later D5-5I Gate-B
campaign authority. It may perform exactly two credential-bearing metadata
observations and no generation:

```text
one GET /v1/models
one GET /props
zero /chat/completions requests
zero provider/model generations
```

No production, harness, prompt, schema, frozen population, case/gold, source,
or dependency changes are part of this design.

## Historical Continuity Anchor

The following values are recovered historical evidence and remain continuity
constraints. They are not newly established by the future observation:

```yaml
historical_campaign: d5-5-qwen-inspectable-002
model_catalog:
  - qwen3.6-35b-a3b
model_path_basename: Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
model_path_fingerprint_sha256: 3a6fd986bebd4047876869e8b079f9f9b7b15fb2429853ba0501b5f6ea480b21
build_info: b11160-a3c12db9d
context_size: 65536
total_slots: 1
gguf_byte_identity: NOT_AVAILABLE
chat_template_sha256: 55d4931433fe502b794226ee7f4d206a6bdd436ac9f80eb7d8ebb4c639f9ea0c
historical_chat_format: Content-only
```

The historical evidence does not contain a sealed `runtime_defaults_sha256`
or explicit `thinking_off: true` attestation at the required granularity.
Neither value may be derived from `context_size`, inferred from model naming,
or attributed retroactively to the historical campaign.

## New Pin Qualification Contract

The future metadata-only attempt may establish only these new values:

```yaml
runtime_defaults_sha256: SHA256(canonical observed /props.default_generation_settings)
thinking_off: explicit evidence from the accepted serving/runtime metadata
structured_output_contract: observed/validated readiness identity
```

Newly observed values must be labeled:

```yaml
provenance: D5-5I_RUNTIME_PIN_QUALIFICATION
historical_campaign: d5-5-qwen-inspectable-002
historical_values: CONTINUITY_ONLY
```

The observation may not silently replace a historical value. The overlapping
historical fields must match exactly: model catalog, model path basename,
model path fingerprint, build info, context size, total slots, chat-template
fingerprint, and chat format where exposed. Any mismatch is a terminal
continuity failure, not a refreshed identity. `gguf_byte_identity` remains
`NOT_AVAILABLE` unless separately authorized and observed.

## Future Execution Sequence

The later execution authority must bind the exact project checkpoint, clean
worktree, project-config fingerprint, credential source, expected endpoint
origin/base URLs, historical continuity values, fresh pin-evidence artifact
root, and one-shot authorization ID before issuing a request.

After static checks pass, the sequence is fixed:

```text
1. credential-bearing GET /v1/models
2. credential-bearing GET /props
3. compare all historical overlaps
4. validate the extended readiness fields
5. seal D5-5I runtime-pin qualification evidence
```

There is no readiness retry, alternate endpoint, provider construction,
campaign state, `STARTED` transition, or live adapter construction in this
metadata-only gate. A request rejected before issuance consumes no endpoint
attempt; each issued GET consumes one endpoint attempt, including HTTP,
authentication, or transport failure. The execution ceiling is exactly two.

## Terminal Outcomes And Custody

Every future attempt must produce one immutable terminal record and retain
sanitized state/journal evidence without credentials, headers, or response
payloads beyond the accepted redaction policy.

```yaml
SUCCESS:
  historical_overlap: EXACT_MATCH
  extended_pins: SEALED
  generation_calls: 0

MISMATCH:
  reason: HISTORICAL_IDENTITY_MISMATCH
  historical_identity: PRESERVED
  extended_pins: NOT_ESTABLISHED
  generation_calls: 0

AUTHENTICATION_FAILURE:
  reason: ENDPOINT_AUTHENTICATION
  extended_pins: NOT_ESTABLISHED
  generation_calls: 0

TRANSPORT_FAILURE:
  reason: ENDPOINT_TRANSPORT
  extended_pins: NOT_ESTABLISHED
  generation_calls: 0

INCOMPLETE_PROPS:
  reason: EXTENDED_RUNTIME_IDENTITY_UNAVAILABLE
  extended_pins: NOT_ESTABLISHED
  generation_calls: 0
```

An issued first GET consumes the metadata-only authority. If either
observation fails, terminal evidence is retained and the same authorization
cannot be retried. A later attempt requires a new authority and new evidence
namespace. No result from this gate authorizes the D5-5I campaign.

Successful pin establishment is admissible for a later Gate-B record only
after independent review confirms the exact request count, zero generation,
historical overlap, concrete extended values, and custody digests.

## Decision Record

**Decision:** Establish missing Qwen readiness identity through a separate,
metadata-only, fail-closed observation gate.

**Scope:** Recover readiness facts needed by the accepted D5-5I authorization
record without changing the model, architecture, scientific population, or
historical evidence.

**Evidence class:** ADAPTED / EMPIRICALLY_SUPPORTED.

**Rejected alternatives:** Deriving a runtime-default hash from context size;
inferring thinking-off from absence of a request parameter; retroactively
attaching new values to the historical campaign; or issuing a live campaign
before the extended pins are sealed.

**Stop condition:** Any historical overlap mismatch, missing extended `/props`
field, authentication/transport failure, ambiguous thinking-off evidence, or
nonzero generation activity terminates the attempt and blocks Gate-B.

## Current Authorization State

```yaml
runtime_pin_establishment_design: READY_FOR_INDEPENDENT_REVIEW
metadata_endpoint_execution: NOT_AUTHORIZED
gate_b_authorization_record: BLOCKED
model_generation: NOT_AUTHORIZED
live_campaign: NOT_AUTHORIZED
```
