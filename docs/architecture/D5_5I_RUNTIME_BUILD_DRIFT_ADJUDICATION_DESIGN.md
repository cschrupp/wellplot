# D5-5I Runtime-Build Drift Adjudication Design

```yaml
authority: WELLPLOT-D5-5I-RUNTIME-BUILD-DRIFT-ADJUDICATION-DESIGN-AUTH-001
branch: design/d5-5g-inspectable-historical-claim-revalidation
historical_pin_authority: WELLPLOT-D5-5I-RUNTIME-PIN-ESTABLISHMENT-AUTH-001
historical_pin_status: MISMATCH / ACCEPTED / CLOSED
scientific_executable_checkpoint: fa3bfe59819d9b5e4cac9821b7770d7f4b4b3a0b
runtime_pin_tooling_checkpoint: aeb2ad07e9e4430efe60098a58629201f19cbaee
metadata_calls_during_design: 0
provider_model_calls_during_design: 0
live_generation: NOT_AUTHORIZED
```

## Decision

The D5-5I runtime-pin attempt is permanently closed as:

```yaml
outcome: MISMATCH
reason: HISTORICAL_IDENTITY_MISMATCH
mismatched_field: build_info
historical_build_info: b11160-a3c12db9d
observed_current_build_info: b11669-378a347ce
```

The observed `.141` runtime must not be made to match the historical `.140`
identity by refreshing, editing, or reattributing the historical record. This
design defines a separate, prospective adjudication of whether the observed
runtime can be recorded as an explicitly identified successor. It does not
authorize metadata calls, a compatibility probe, a live campaign, or any
production change.

The selected outcome may be:

```text
historical identity: preserved
current successor identity: separately observed and labeled
request-control compatibility: separately demonstrated or left unresolved
Gate-B: blocked until both records are independently reviewed
```

## Scope Check

### Problem

The first metadata qualification established that the target `.141` server
matches the historical continuity values except for `build_info`. It also
established a new runtime-default fingerprint that was not available in the
historical evidence:

```yaml
target_server_origin: http://192.168.2.141:8888
model: qwen3.6-35b-a3b
observed_build_info: b11669-378a347ce
observed_runtime_defaults_sha256: 358285bb3448909823ca884f7806b42e81cc4a96841004fa3c903437d0714b30
historical_pin_terminal: MISMATCH / HISTORICAL_IDENTITY_MISMATCH
```

The question is not whether the old value can be replaced. It cannot. The
question is whether the exact observed runtime can be treated as a new current
runtime identity, with its build provenance and request-control compatibility
reported honestly.

### Out of scope

This design does not authorize or change:

- the historical D4 or D5-5 evidence;
- the accepted D5-5I executable or tooling checkpoints;
- the canonical WellPlot engine or provider boundary;
- prompts, schemas, cases, gold, source assets, graders, or budgets;
- `thinking_off` request-control semantics;
- `/chat/completions` or any model generation;
- a Gate-B authorization record;
- production source or harness implementation.

## Provenance Classes

The records must retain these provenance classes separately.

### Historical continuity evidence

The following values were recovered from the older D4 Qwen endpoint
qualification for `.140`. They remain historical continuity constraints only:

```yaml
source: D4_QWEN_ENDPOINT_QUALIFICATION
server_origin: http://192.168.2.140:8888
model_catalog:
  - qwen3.6-35b-a3b
model_path_basename: Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
model_path_fingerprint_sha256: 3a6fd986bebd4047876869e8b079f9f9b7b15fb2429853ba0501b5f6ea480b21
build_info: b11160-a3c12db9d
context_size: 65536
total_slots: 1
chat_template_sha256: 55d4931433fe502b794226ee7f4d206a6bdd436ac9f80eb7d8ebb4c639f9ea0c
```

These values are not D5-5I `.141` pins and must not be labeled as evidence
from `d5-5-qwen-inspectable-002`.

### Current `.141` observation

The following values came from the sealed AUTH-001 observation and remain
immutable evidence of the `.141` server at that time:

```yaml
source: D5-5I_RUNTIME_PIN_ESTABLISHMENT-AUTH-001
server_origin: http://192.168.2.141:8888
model_catalog:
  - qwen3.6-35b-a3b
model_path_basename: Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
model_path_fingerprint_sha256: 3a6fd986bebd4047876869e8b079f9f9b7b15fb2429853ba0501b5f6ea480b21
build_info: b11669-378a347ce
context_size: 65536
total_slots: 1
chat_template_sha256: 55d4931433fe502b794226ee7f4d206a6bdd436ac9f80eb7d8ebb4c639f9ea0c
runtime_defaults_sha256: 358285bb3448909823ca884f7806b42e81cc4a96841004fa3c903437d0714b30
```

These are current observations, not a successful historical pin. The
`build_info` value is an exact server-reported string, not an upstream source
identity.

### Upstream provenance

The public llama.cpp attestation for an official b11669 artifact identifies
upstream commit `620d2225cc436ab0b001e3200e590e3b286ef9ab`. It does not
authenticate the local suffix `378a347ce`. Therefore the current runtime must
be recorded as:

```yaml
exact_server_reported_build: b11669-378a347ce
upstream_source_provenance: UNVERIFIED
official_b11669_attestation: NOT_A_MATCH_FOR_LOCAL_SUFFIX
```

No claim that `.141` is the official upstream b11669 build is admissible until
an independently trusted host/process or binary provenance record connects the
observed server to that source.

## External Evidence And Applicability

The current llama.cpp server documentation provides two relevant boundaries:

1. `GET /props` reports runtime identity and default-generation metadata,
   including build information, context-related defaults, slots, model path,
   and chat template.
2. `POST /apply-template` formats a fixed message list using the server chat
   template and returns a prompt without performing inference. The chat
   completion contract documents `chat_template_kwargs`, including
   `{"enable_thinking": false}`.

Sources:

- https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- https://github.com/ggml-org/llama.cpp/attestations/56338993

The first item supports using the existing AUTH-001 observations as runtime
identity evidence. The second supports a bounded compatibility probe, but it
does not prove that an unknown deployed build accepts every documented option.
The exact `.141` build must therefore demonstrate acceptance rather than
inherit current upstream behavior by assumption.

Evidence classification:

```yaml
documented_props_and_apply_template_boundaries: ESTABLISHED
successor_identity_from_exact_.141_observation: EMPIRICALLY_SUPPORTED
apply_template_pair_as_compatibility_probe: ADAPTED
upstream_provenance_of_378a347ce: NOT_ESTABLISHED
```

## Successor-Runtime Rule

A future successor adjudication may accept the observed `.141` runtime as a
new current identity only if all of the following are true:

1. The historical AUTH-001 terminal record remains unchanged and is joined by
   digest, not overwritten.
2. The target origin, project configuration, model catalog, model path
   basename, model-path fingerprint, context size, slot count, and chat
   template fingerprint are recorded from the same `.141` observation set.
3. The new `build_info` and `runtime_defaults_sha256` are recorded as current
   successor fields, never as historical replacements.
4. The exact server-reported build is retained even if its upstream commit
   cannot be authenticated.
5. The frozen request-control contract remains unchanged:

   ```yaml
   mechanism: chat_template_kwargs.enable_thinking
   value: false
   canonical_request_options_sha256: 220b99e47feb82851cab428f86b8fe977ae7c605400d421a91e99d4a35ec9c26
   semantics: thinking_off = STATIC_REQUEST_CONTRACT
   ```

6. A separate compatibility review demonstrates that the exact `.141`
   server/template accepts the request control, or records that compatibility
   as unresolved and blocks Gate-B.

The rule deliberately permits a new current runtime identity without making
an unsupported source-provenance claim. Exact identity and upstream
provenance are different fields.

## Bounded Compatibility Probe

### Purpose

The probe answers one question only:

```text
Does the exact observed `.141` server/template recognize and apply the
frozen `chat_template_kwargs.enable_thinking=false` control at its template
boundary without model generation?
```

It is not a scientific campaign and cannot establish semantic model quality.

### Future authority and fixed budget

The probe requires a separate one-shot execution authority. That authority
must bind the successor observation digest, target origin, model, tooling and
scientific checkpoints, and a fresh evidence namespace.

The fixed request budget is:

```yaml
requests:
  - POST /apply-template with enable_thinking: false
  - POST /apply-template with enable_thinking: true
max_apply_template_requests: 2
chat_completions: 0
other_generation_endpoints: 0
retries: 0
replays: 0
```

The `true` arm is a control comparison, not a production setting. It exists
only to detect whether the exact deployed template responds to the control.
No response body or raw prompt may be retained. The evidence stores only
bounded request-control facts, response status/shape, prompt lengths, and
hashes of redacted prompt projections.

### Fixed request

Both requests use the same minimal, non-scientific message sequence and model
identity. The messages must be frozen before execution and contain no WellPlot
case, gold, source, or answer content. The only allowed difference is:

```json
{"chat_template_kwargs":{"enable_thinking":false}}
```

versus the same object with `true`.

The future runner must verify the serialized request body before issuance and
must not accept a server response as evidence if the request control was
omitted, mutated, or placed in an unsupported location.

### Acceptance predicate

The probe can produce `COMPATIBLE_FOR_GATE_B_REVIEW` only when:

1. both calls receive successful, bounded JSON responses with a string
   `prompt` field;
2. the exact request controls are present and differ only in Boolean value;
3. the deployed endpoint's documented/source contract for that exact build
   confirms that the field is interpreted by the template path; and
4. the two prompt projections exhibit the documented control-sensitive
   difference, recorded as bounded hashes/predicates rather than raw text.

If the endpoint ignores unknown fields, returns identical prompt projections,
rejects the field, or the exact build's contract cannot be established, the
result is not compatibility success. It is `COMPATIBILITY_UNESTABLISHED`.

The probe must not infer compatibility from a successful HTTP status alone,
from the presence of the field in the request, from model naming, or from the
absence of visible reasoning text in a generated response. There is no
generated response in this probe.

## Terminal Outcomes

The future adjudication and probe must seal one immutable terminal outcome.

```yaml
SUCCESSOR_IDENTITY_ESTABLISHED:
  historical_auth_001: MISMATCH / CLOSED / PRESERVED
  current_identity: SEALED_FROM_.141_OBSERVATION
  upstream_provenance: VERIFIED | UNVERIFIED
  compatibility: PENDING_OR_COMPATIBLE_FOR_GATE_B_REVIEW
  gate_b: BLOCKED_UNTIL_INDEPENDENT_REVIEW

NON_BUILD_CONTINUITY_MISMATCH:
  historical_auth_001: PRESERVED
  current_identity: NOT_ACCEPTED
  gate_b: BLOCKED

COMPATIBILITY_UNESTABLISHED:
  successor_identity: PRESERVED_AS_OBSERVED
  request_control: NOT_PROVEN_COMPATIBLE
  gate_b: BLOCKED

AUTHENTICATION_OR_TRANSPORT_FAILURE:
  successor_identity: NOT_ESTABLISHED
  model_generation: 0
  gate_b: BLOCKED

PROBE_CONTRACT_FAILURE:
  successor_identity: PRESERVED_AS_OBSERVED
  compatibility: NOT_ESTABLISHED
  model_generation: 0
  gate_b: BLOCKED
```

`SUCCESSOR_IDENTITY_ESTABLISHED` is not live readiness and is not Gate-B
authorization. It means only that the exact observed `.141` identity has been
recorded without rewriting history. A compatibility-success result still
requires independent review and a later Gate-B record.

## Custody Requirements

Any future execution must preserve:

- the immutable AUTH-001 state, journal, terminal record, and digests;
- the exact `.141` projected identity values and their observation timestamp;
- the authorization and fresh successor/probe namespace identities;
- request method, endpoint path, status, bounded response shape, and request
  control digest;
- prompt projection lengths/hashes only, never credentials, headers, or raw
  prompt/response bodies;
- zero `/chat/completions` and zero model-generation count;
- first failure and terminal outcome without retry or replay.

No evidence may merge a successor identity into the historical continuity
record. The join must be explicit and digest-based.

## Decision Record

**Decision:** Treat `.141` as a prospective, separately identified successor
runtime rather than a refreshed historical runtime.

**Project scope:** Resolve build drift and request-control compatibility before
the D5-5I Gate-B record, without changing the accepted engine or scientific
population.

**External evidence:** llama.cpp documents `/props` identity metadata,
non-generative `/apply-template`, and `chat_template_kwargs` at the chat
completion boundary. The public b11669 attestation identifies upstream commit
`620d2225...`, which does not authenticate the observed `378a347ce` suffix.

**Options considered:**

- A: silently refresh the historical build pin. Rejected; destroys provenance.
- B: classify `.141` as an exact observed successor and review compatibility
  separately. Selected.
- C: claim official upstream b11669 provenance from the version prefix.
  Rejected; insufficient evidence.
- D: use a non-generative paired template probe. Selected as the bounded
  compatibility mechanism, subject to the exact-build acceptance predicate.

**Evidence class:** ADAPTED / EMPIRICALLY_SUPPORTED.

**Reversible:** YES. The historical record is immutable and no production
  change is required.

**Stop/revisit conditions:** Any non-build continuity mismatch, inability to
  establish exact `.141` request-control compatibility, unexpected endpoint
  behavior, missing custody, or any generation request blocks Gate-B and
  requires independent adjudication rather than automatic experimentation.

## Current State

```yaml
historical_runtime_pin_auth_001: MISMATCH / ACCEPTED / CLOSED
historical_identity: PRESERVED
observed_.141_runtime: SUCCESSOR_CANDIDATE / PROVENANCE_UNVERIFIED
compatibility_probe: DESIGNED / NOT_EXECUTED
metadata_calls_after_auth_001: 0
provider_model_calls: 0
gate_b: BLOCKED
live_generation: NOT_AUTHORIZED
d5_5h: NOT_AUTHORIZED
status: READY_FOR_INDEPENDENT_DESIGN_REVIEW
```
