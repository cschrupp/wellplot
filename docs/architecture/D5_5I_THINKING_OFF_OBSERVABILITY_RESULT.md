# D5-5I Thinking-Off Observability Qualification Result

```yaml
authority: WELLPLOT-D5-5I-THINKING-OFF-OBSERVABILITY-QUALIFICATION-AUTH-001
analysis_checkpoint: 3af28dd4629ddf6d06c21fb53707db3248c12c67
question: Can the permitted /props observation establish thinking_off=true?
result: NOT_OBSERVABLE
metadata_endpoint_calls: 0
provider_model_calls: 0
production_changes: 0
```

## Scope

This is a read-only source and documentation analysis. No request was made to
the `.141` server. No `/v1/models`, `/props`, or `/chat/completions` call was
issued. No historical artifact, harness, configuration, or production source
was changed.

## Observed WellPlot Contract

At the analyzed checkpoint, `scripts/nlp_d5_live_semantic_qualification.py`
projects `/props` into:

```text
model_path_basename
model_path_fingerprint_sha256
context_size
build_info
total_slots
chat_template_sha256
runtime_defaults_sha256
structured_output_contract
gguf_byte_identity
```

It does not project a `thinking_off` field or any documented Boolean equivalent.
The readiness validator returns `thinking_off=True` only when all of the
following are already supplied or matched:

```text
authorization.thinking_off is True
observed chat_template_sha256 == authorized value
observed runtime_defaults_sha256 == authorized value
```

That is an external authorization/configuration invariant combined with
identity matching. It is not an observation of thinking mode from `/props`.

The source also currently carries the D4 helper endpoint constants for
`http://192.168.2.140:8888`, while the accepted D5-5I target design names
`http://192.168.2.141:8888`. This is a separate target-configuration
provenance discrepancy. It must be reconciled before any metadata execution;
this analysis does not change either value.

## llama.cpp Documentation Check

The official llama.cpp server documentation describes the GET `/props`
projection as including `default_generation_settings`, `total_slots`,
`model_path`, `chat_template`, `chat_template_caps`, modalities, build
information, and sleep state. It does not document a Boolean representing the
current thinking-disabled state:

[llama.cpp server `/props` documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#-get-props-get-server-global-properties)

The same documentation exposes reasoning controls as configuration/request
controls, including server `--reasoning on|off|auto`, request
`chat_template_kwargs.enable_thinking`, and `reasoning_effort`. Those controls
do not establish that a GET `/props` response contains a Boolean proof of the
currently active mode:

[llama.cpp reasoning and chat-completion controls](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#openai-compatible-chat-completions-api)

This source/documentation result is bounded to the documented contract. It
does not claim that an undocumented `.141` build cannot expose additional
metadata; it establishes only that no admissible field is currently known and
pre-reviewed.

## Deterministic Predicate

Under the accepted runtime-pin design, success would require:

```text
the observed /props payload contains a documented Boolean field at a
pre-reviewed path whose semantics explicitly mean "thinking disabled", and
that Boolean equals true
```

No such field path, type, or documented mapping is present in the analyzed
WellPlot contract or the authoritative llama.cpp documentation. Therefore the
permitted two-GET runtime-pin attempt cannot currently establish
`thinking_off=true`.

The following are explicitly rejected as proof:

- absence of a `thinking` request parameter;
- model name or model path;
- historical generation behavior;
- absence of visible `<think>` output;
- matching chat-template and runtime-default fingerprints alone;
- a new interpretation of template text or `chat_template_caps`.

## Structured Output Classification

`structured_output_contract: json_schema` remains an inherited frozen WellPlot
provider-adapter configuration invariant. This qualification does not and
cannot empirically establish provider acceptance of structured generation,
because generation probes are forbidden. The first scientific generation,
under a separately authorized campaign, remains the measurement boundary for
provider structured-output acceptance.

## Terminal Classification

```yaml
outcome: NOT_OBSERVABLE
terminal_if_attempted: INCOMPLETE_PROPS
reason: EXTENDED_RUNTIME_IDENTITY_UNAVAILABLE
thinking_off: NOT_ESTABLISHED
runtime_defaults_sha256: NOT_ESTABLISHED
structured_output_contract: INHERITED_CONFIGURATION_ONLY
target_endpoint_configuration: REQUIRES_RECONCILIATION
```

The metadata GETs must not be issued merely to rediscover this known absence.
The existing two-GET runtime-pin design is therefore insufficient as written
for establishing the complete Gate-B prerequisite.

## Required Next Boundary

Gate-B remains blocked. A future design must choose and explicitly authorize
one admissible source for thinking-off, such as a documented serving
configuration attestation or another metadata mechanism with a deterministic
Boolean predicate. It must also reconcile the executable endpoint target with
the accepted `.141` configuration before any credentialed observation.

No production or harness change is authorized by this result.

```yaml
thinking_off_observability: NOT_OBSERVABLE
metadata_endpoint_execution: NOT_AUTHORIZED
gate_b_authorization_record: BLOCKED
model_generation: NOT_AUTHORIZED
live_campaign: NOT_AUTHORIZED
```
