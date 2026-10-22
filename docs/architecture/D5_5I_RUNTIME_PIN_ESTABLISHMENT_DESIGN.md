# D5-5I Runtime-Pin Establishment Design

```yaml
authority: WELLPLOT-D5-5I-RUNTIME-PIN-ESTABLISHMENT-DESIGN-AUTH-001
branch: design/d5-5g-inspectable-historical-claim-revalidation
historical_campaign: d5-5-qwen-inspectable-002
historical_identity: PARTIALLY_RECOVERED_AND_PROVENANCE_SPLIT
target_server_origin: http://192.168.2.141:8888
target_openai_compat_base_url: http://192.168.2.141:8888/v1
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

## Historical Evidence And Provenance

The surviving D5-5 inspectable evidence supports the following facts:

```yaml
campaign: d5-5-qwen-inspectable-002
provider_path: openai_compat
model: qwen3.6-35b-a3b
successful_generation_observed: YES
generation_result: provider/structured boundary evidence only
endpoint_identity_for_pin_values: NOT_PROVEN_BY_SURVIVING_D5-5_ARTIFACT
```

The following values come from the **older D4 Qwen endpoint qualification**
against server origin `http://192.168.2.140:8888`. They remain secondary
continuity constraints only; they are not sealed D5-5 inspectable pins and must
not be attributed to `d5-5-qwen-inspectable-002`:

```yaml
provenance: D4_QWEN_ENDPOINT_QUALIFICATION
server_origin: http://192.168.2.140:8888
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

The surviving evidence does not contain a sealed `runtime_defaults_sha256` or
explicit `thinking_off: true` attestation at the required granularity for the
frozen D5-5I target origin. Neither value may be derived from `context_size`,
inferred from model naming, or attributed retroactively to the D5-5 inspectable
campaign.

The future observation target is the frozen D5-5I project configuration:

```yaml
server_origin: http://192.168.2.141:8888
openai_compat_base_url: http://192.168.2.141:8888/v1
model_catalog_url: http://192.168.2.141:8888/v1/models
props_url: http://192.168.2.141:8888/props
```

The older `.140` values may be compared for continuity only where the future
authority explicitly declares the comparison applicable. A `.141` mismatch,
an unavailable overlap, or an ambiguous cross-origin comparison is not a
silent refresh.

## New Pin Qualification Contract

The future metadata-only attempt may establish only these new values:

```yaml
runtime_defaults_sha256: SHA256(canonical observed /props.default_generation_settings)
thinking_off: ESTABLISHED_ONLY_BY_EXPLICIT_DOCUMENTED_PROPS_BOOLEAN_TRUE
```

`structured_output_contract: json_schema` is an inherited frozen
WellPlot/provider-adapter configuration invariant. It is carried into the
eventual Gate-B record but is not established by `/v1/models` or `/props` and
must not be described as empirically proven by this metadata gate.

The exact `thinking_off` success predicate is:

```text
SUCCESS only if the observed /props payload contains a pre-reviewed,
documented boolean field explicitly representing reasoning/thinking mode and
that field is exactly true for thinking-off.
```

The field path and server documentation must be named in the later execution
authority before the GETs are issued. Absence of that explicit boolean,
presence of only defaults/context/template data, absence of a documented
mapping, or any ambiguity produces:

```yaml
terminal: INCOMPLETE_PROPS
reason: EXTENDED_RUNTIME_IDENTITY_UNAVAILABLE
thinking_off: NOT_ESTABLISHED
```

The following are not admissible proof: absence of a request parameter, model
name, historical behavior, absence of visible `<think>` output, or a newly
invented interpretation of the chat template.

Newly observed values must be labeled:

```yaml
provenance: D5-5I_RUNTIME_PIN_QUALIFICATION
historical_campaign: d5-5-qwen-inspectable-002
historical_values: CONTINUITY_ONLY
```

The observation may not silently replace a historical value. The applicable
overlapping fields must match exactly, with provenance retained for each:
model catalog, model path basename, model path fingerprint, build info,
context size, total slots, chat-template fingerprint, and chat format where
exposed. Any mismatch is a terminal continuity failure, not a refreshed
identity. `gguf_byte_identity` remains `NOT_AVAILABLE` unless separately
authorized and observed.

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
  thinking_off: NOT_ESTABLISHED
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
