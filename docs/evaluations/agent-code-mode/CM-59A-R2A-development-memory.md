# CM-59A-R2A - Structured Invalid-Response Discrimination

## Status

- Slice: `CM-59A-R2A`
- Baseline: `d9c8774140b79c9bb7252bef2637d84db84c3ec3`
- Purpose: observability only
- Initial implementation: blocked and superseded before commit
- Revision 1: compatibility-preserving diagnostic isolation
- Revision 2: historical-harness test isolation
- Provider calls: `0`
- Endpoint calls: `0`
- Worker/program calls: `0`

## Contract

`ProviderResponseFailureReason` and `StructuredResponseProviderError` add
bounded provider-neutral diagnostics without changing the existing
`ProviderRequestError` contract.

Authorized reasons:

- `unusable_choice`
- `missing_message`
- `non_assistant_message`
- `incomplete_output`
- `unexpected_finish_reason`
- `tool_call`
- `missing_content`
- `invalid_json`
- `schema_validation`

The subclass always has the outer `invalid_response` category. Its dedicated
`diagnostic_metadata()` projection contains only the enum string. Ordinary
`public_metadata()`, `str()`, `repr()`, and retryability remain unchanged. No
raw provider content, validation details, tool arguments, headers,
credentials, or endpoint-specific payloads are retained.

The OpenAI-compatible adapter now separates completion-envelope failures,
JSON parsing failures, and response-model validation failures using the
subclass. Refusals, transport, authentication, rate-limit, timeout,
configuration, and generic provider-mapping behavior remain unchanged.

The initial implementation was blocked because it changed `base.py` and the
normal public metadata projection, which broke frozen provenance guards and
experimental TW consumers. Revision 1 isolates the reason in the new
`response_diagnostics.py` module. `base.py`, historical guards, TW consumers,
and normal persistence remain unchanged.

Revision 1 verification also exposed that the closed P9A/P10 unit tests called
their frozen pre-live checks against the current adapter bytes. Revision 2
keeps the historical scripts, constants, evidence, and fail-closed guards
unchanged, while making only the unit-test success paths simulate the frozen
adapter hash. Separate tests continue to prove that a synthetic adapter drift
is rejected. This keeps historical evidence immutable without coupling normal
repository tests to an obsolete production checkout.

## Preserved Boundaries

- Planner source and its one invalid-response retry are unchanged.
- Semantic correction behavior is unchanged.
- Prompts, `SemanticPlan`, capability registry, facade diagnostics, graph
  state, safety layers, persistence, and routing are unchanged.
- Historical CM-59A artifacts remain frozen and receive no retroactive reason.
- CM-59A remains `CLOSED / VALID REJECTION`.
- CM-59A-R1 remains `COMPLETE / ACCEPTED`.
- CM-59A-R2B and CM-59A-E2 are not authorized.
- CM-57D remains blocked.

## Hard Stop

This is a provider-free implementation checkpoint. No Qwen invocation,
endpoint request, Xenon retry, or live diagnostic is authorized in R2A.
