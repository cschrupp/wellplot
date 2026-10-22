# D5-5I Thinking-Off Control Design

```yaml
authority: WELLPLOT-D5-5I-THINKING-OFF-CONTROL-DESIGN-AUTH-001
branch: design/d5-5g-inspectable-historical-claim-revalidation
current_executable_checkpoint: 661a7eeeabcfa4e6364aeb3e74bf55859ac48539
target_server_origin: http://192.168.2.141:8888
provider: openai_compat
model: qwen3.6-35b-a3b
design_endpoint_calls: 0
design_provider_model_calls: 0
implementation: NOT_AUTHORIZED
live_execution: NOT_AUTHORIZED
```

## Decision Boundary

The current D5-5I runtime-pin design cannot establish `thinking_off` from
`/props`: the endpoint does not document a Boolean with that meaning, and the
accepted executable treats thinking-off as an externally supplied invariant
combined with matching runtime/template fingerprints.

This record evaluates two admissible controls. It does not change the
provider boundary, modify production code, issue metadata GETs, or authorize a
live campaign.

## Fixed Constraints

Both approaches must preserve:

```text
single canonical WellPlot engine
existing OpenAI-compatible provider boundary
Qwen qwen3.6-35b-a3b
target origin http://192.168.2.141:8888
json_schema local validation and grading
frozen nine-turn D5-5I population
45 logical generation calls
135 physical generation attempts
sdk_max_retries = 2
no fallback, replay, selective rerun, or model substitution
exact wire-level custody
```

The accepted executable checkpoint remains `661a7eee...` until an explicitly
authorized implementation change is reviewed and frozen.

## Approach A: Serving-Configuration Attestation

The server host would be independently inspected and would provide immutable,
sanitized evidence that the exact `.141` serving instance is configured for
thinking off, for example an exact documented `llama-server --reasoning off`
configuration or equivalent runtime configuration.

The attestation would need to bind, at minimum:

```yaml
server_origin: http://192.168.2.141:8888
server_process_or_launcher_identity: REQUIRED
llama_cpp_build_identity: REQUIRED
model_path_and_fingerprint: REQUIRED
reasoning_control: off
configuration_evidence_digest: REQUIRED
observation_time: REQUIRED
```

The evidence must be obtained from a trusted host/configuration source, be
immutable for the campaign, and be independently reviewable. `/props` alone is
not sufficient unless the exact deployed build documents and exposes an
explicit Boolean whose semantics are reviewed in advance.

**Advantages:** no change to the accepted WellPlot executable; the client
wire contract stays unchanged.

**Risks:** host/process inspection may be unavailable or mutable; a launch
configuration may not prove the effective template behavior if overrides,
router configuration, or per-request controls intervene; it creates an
operational evidence dependency outside the HTTP contract.

**Status:** not currently admissible. No independently sealed `.141`
serving-configuration evidence is available in the reviewed artifacts.

## Approach B: Explicit Per-Request Control

The Qwen generation request would carry a documented llama.cpp control that
explicitly disables thinking, such as:

```yaml
chat_template_kwargs:
  enable_thinking: false
```

or another documented equivalent accepted by the frozen server/model contract.
The accepted provider/composition boundary already supports this generic path:
`OpenAICompatibleBackendV2.request_options` is serialized as `extra_body`,
the shared `create_provider_backend()` forwards it, and D5-5I's
`create_live_adapter()` accepts it. No `src/wellplot/agent/providers/*`
capability change is implied.

The current gap is D5-5I executable wiring: its default live provider factory
does not yet supply the request options. The bounded implementation scope is
therefore harness/executable configuration only, unless implementation
evidence proves the existing generic path insufficient.

The implementation must freeze one canonical request-control contract:

```yaml
thinking_control:
  mechanism: chat_template_kwargs.enable_thinking
  value: false
  canonical_request_options:
    chat_template_kwargs:
      enable_thinking: false
  canonical_request_options_sha256: FROZEN_BY_IMPLEMENTATION
```

The digest must be computed from the canonical serialized request-options
object and recorded in the new executable checkpoint and later authorization.
Every planner, report-worker, section-worker, and authorized correction
request, including every SDK retry, must contain the exact control and digest-
bound value. Omission or mutation is a contract failure, not an environmental
assumption.

**Advantages:** the control is deterministic, visible in exact wire custody,
and directly bound to each generation request. It does not require trust in an
unobservable server launch environment.

**Risks:** the D5-5I executable must wire the already-supported option, create a
new executable checkpoint, and pass provider-free request-custody tests before
independent review and Gate-B rebinding. The documented control must also be
verified against the exact `.141` build and Qwen template.

**Status:** preferred if serving-configuration attestation cannot be made
independently inspectable, but implementation is not authorized by this
design.

## Selection Rule

The later Gate-B path must select exactly one control:

```text
trusted immutable serving attestation available and independently reviewable
    -> Approach A may be authorized

otherwise
    -> Approach B requires bounded implementation and provider-free review

neither control admissible
    -> thinking_off remains NOT_ESTABLISHED and Gate-B remains blocked
```

The absence of a `/props` Boolean cannot be converted into success by relying
on model name, historical behavior, absence of `<think>` output, template
inspection alone, or an omitted request parameter.

If Approach B is selected, `thinking_off` is established by the frozen request
contract, not by `/props`. The readiness invariant becomes:

```text
authorized canonical request-options digest matches the executable's
static request-control contract, and wire custody proves the exact control
on every generation role and every issued retry
```

`/props` remains responsible only for observed model, runtime, template,
context, slots, build, and default-generation identity. It does not establish
thinking mode. The new executable checkpoint must be recorded before any
Gate-B authorization record is prepared; the old `661a7eee...` checkpoint
cannot remain the executable target after this implementation.

## Required Evidence For Either Path

The future authority must preserve:

- exact `.141` endpoint and model identity;
- accepted runtime-default and chat-template fingerprints;
- the selected control and its provenance;
- a deterministic `thinking_off: true` predicate;
- zero generation during any metadata/attestation preparation;
- exact request custody if Approach B is selected;
- provider-free proof for planner, report-worker, section-worker, and
  correction requests, including SDK retries;
- no silent substitution between controls.

If the selected control cannot be proven before scientific generation, the
campaign terminates `INCOMPLETE_PROPS / EXTENDED_RUNTIME_IDENTITY_UNAVAILABLE`
before `STARTED`.

## Decision Record

**Decision:** Do not infer thinking-off from `/props`; require either an
independently sealed serving attestation or explicit per-request control.

**Project scope:** Make the D5-5I Qwen readiness predicate scientifically
interpretable without changing the canonical semantic architecture.

**External evidence:** llama.cpp documents reasoning controls at the serving
and request boundary, including `--reasoning off`,
`chat_template_kwargs.enable_thinking`, and `reasoning_effort`; its documented
`/props` response does not define a thinking-off Boolean.

**Evidence class:** ADAPTED / EMPIRICALLY_SUPPORTED.

**Selected direction:** Prefer Approach B when Approach A cannot be made
independently inspectable. This is a design preference, not implementation
authorization. The existing generic provider boundary is reused; only the
D5-5I executable wiring and its attestation/tests are in scope.

**Reversible:** YES before implementation and live readiness.

**Stop condition:** Missing trusted serving evidence, unspecified request
control, digest mismatch, missing role/retry wire proof, exact-build
incompatibility, or any ambiguity about effective thinking mode blocks Gate-B.

## Current State

```yaml
thinking_off_control_design: READY_FOR_INDEPENDENT_REVIEW
approach_a_serving_attestation: NOT_AVAILABLE
approach_b_request_control: PREFERRED_IF_A_UNAVAILABLE
current_executable_checkpoint: 661a7eeeabcfa4e6364aeb3e74bf55859ac48539
approach_b_provider_boundary_change: NO
approach_b_d5i_executable_wiring: REQUIRED_IF_SELECTED
implementation: NOT_AUTHORIZED
metadata_endpoint_execution: NOT_AUTHORIZED
gate_b_authorization_record: BLOCKED
live_generation: NOT_AUTHORIZED
```
