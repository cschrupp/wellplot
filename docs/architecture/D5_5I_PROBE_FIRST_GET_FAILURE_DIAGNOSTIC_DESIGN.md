# D5-5I First-GET Failure Diagnostic Design

~~~yaml
authority: WELLPLOT-D5-5I-PROBE-FIRST-GET-FAILURE-DIAGNOSTIC-DESIGN-AUTH-001
branch: design/d5-5g-inspectable-historical-claim-revalidation
failed_probe_authority: WELLPLOT-D5-5I-RUNTIME-BUILD-DRIFT-PROBE-AUTH-001
failed_probe_status: TERMINAL / ACCEPTED / CLOSED / CONSUMED
failed_probe_attempts: 1
failed_probe_endpoint: GET /v1/models
failed_probe_generation_calls: 0
diagnostic_design_calls: 0
endpoint_execution: NOT_AUTHORIZED
provider_model_calls: 0
live_generation: NOT_AUTHORIZED
~~~

## Decision

The failed runtime-build probe is preserved as immutable infrastructure evidence:

~~~yaml
outcome: AUTHENTICATION_OR_TRANSPORT_FAILURE
reason: FIRST_IDENTITY_GET_FAILED
endpoint_attempts: 1
authority_replay: FORBIDDEN
~~~

The unused request budget is not reusable. AUTH-001 must never be retried,
resumed, or partially replayed. This design defines a separate diagnostic that
may classify the first-request failure, but it does not reopen the probe or
authorize a new successor-compatibility observation.

The diagnostic must distinguish, to the extent supported by bounded evidence:

~~~text
LOCAL_PRECONDITION
TCP_UNREACHABLE
HTTP_REACHABLE_AUTH_FAILURE
HTTP_REACHABLE_OTHER_FAILURE
ENDPOINT_REACHABLE
~~~

No result from this diagnostic establishes runtime identity, request-control
compatibility, thinking-off semantics, Gate-B readiness, or scientific model
quality.

## Scope And Invariants

### Problem

The exact first probe request was:

~~~text
GET http://192.168.2.141:8888/v1/models
~~~

The accepted probe produced no usable HTTP response or status. The accepted
terminal therefore correctly combines authentication and transport failure.
This diagnostic separates local invocation/configuration errors from TCP
failure and bounded HTTP response classes without changing the sealed result.

### Preserved scope

The diagnostic must not change or exercise:

- the accepted scientific executable, probe tooling, or projection baseline;
- AUTH-001 artifacts or digests;
- the probe's fresh namespace;
- /props;
- /apply-template;
- /chat/completions or /completion;
- provider construction or model generation;
- prompts, schemas, cases, gold, source assets, graders, or budgets;
- production source or the canonical engine.

The diagnostic is not a readiness retry. If the endpoint is reachable, the
result is only evidence for preparing a new probe authority and namespace.

## Decision Record

### PROJECT SCOPE

This slice explains an infrastructure/precondition terminal in the bounded
D5-5I runtime-build compatibility sequence. It does not decide whether the
.141 runtime is an accepted successor or whether the frozen request control
is compatible with it.

### EXTERNAL EVIDENCE

The diagnostic uses ordinary layered HTTP observability:

1. local configuration and credential resolution are checked before socket
   activity;
2. TCP connection/refusal/timeout errors are separated from HTTP responses;
3. HTTP status is classified without retaining response bodies or credentials.

This is an adapted operational diagnostic pattern, not a scientific result.
The WellPlot-specific boundary is that only the exact /v1/models URL is
eligible and all later scientific routes are prohibited.

### OPTIONS CONSIDERED

A — Replay the failed probe. Rejected. It would violate one-shot custody and
could mix a new runtime observation into the closed authority.

B — Immediately issue /props or /apply-template. Rejected. A first identity
request failed, so later routes cannot establish interpretable successor
compatibility.

C — Run a separate, staged first-request diagnostic. Selected. It preserves
the sealed failure, limits observations to the failed route, and provides the
minimum evidence needed to decide whether a fresh probe authority is useful.

~~~yaml
evidence_class: ADAPTED
reversible: YES
provider_model_calls: 0
scientific_generation: 0
~~~

## Stage 0: Offline And Static Checks

Stage 0 is authorized as part of implementation of this design, but it must
not contact the endpoint. It records only bounded booleans and identities.

Required checks:

~~~yaml
target_origin:
  expected: http://192.168.2.141:8888
  observed: exact configured value
model_catalog_url:
  expected: http://192.168.2.141:8888/v1/models
  observed: exact constructed URL
credential_source:
  mechanism: d4.load_d4_api_key(repo_root)
  available: true/false
credential_value:
  retained: false
  printed: false
project_config_fingerprint:
  compared: true
target_worktree_identity:
  compared: true
tooling_worktree_identity:
  compared: true
~~~

The check must also verify that the URL has no query or fragment, the model
catalog path is exactly /v1/models, and the target/tooling worktrees are the
expected clean checkouts. It must not issue a credential-bearing request.

### Stage 0 classifications

~~~yaml
LOCAL_PRECONDITION:
  examples:
    - missing credential file or empty resolved credential
    - project/config fingerprint mismatch
    - target or tooling checkpoint mismatch
    - dirty or indistinguishable worktrees
    - URL/origin construction mismatch
  network_observation: 0

STATIC_PASS:
  meaning: local prerequisites pass; network diagnostic requires separate authority
  network_observation: 0
~~~

No credential value, hash, header, or raw configuration secret may appear in
the diagnostic artifact.

## Stage 1: Minimum Network Diagnostic

Stage 1 is not authorized by this design. A later authority must bind a fresh
diagnostic ID, fresh evidence namespace, exact target URL, and bounded
observation budget before any network call.

If authorized, Stage 1 may perform exactly one request:

~~~text
GET http://192.168.2.141:8888/v1/models
~~~

It must use the existing credential-loading mechanism and an Authorization:
Bearer header, but must not retain or print the credential or request headers.
It must not follow an alternate endpoint, retry, probe /props, or issue any
generation request.

The request is a diagnostic observation, not a probe replay. A successful
diagnostic does not consume or alter AUTH-001; it only supports a future fresh
authorization decision.

## Bounded Classification

The first applicable classification is terminal for the diagnostic.

### LOCAL_PRECONDITION

Use when failure occurs before a socket attempt, including missing/empty
credential, invalid URL construction, wrong local project configuration, or
worktree/checkpoint failure.

~~~yaml
network_request_issued: false
http_status: NOT_REACHED
~~~

### TCP_UNREACHABLE

Use when the request cannot establish or complete transport and no HTTP status
is received, including connection refusal, timeout, DNS/routing failure, or
other bounded socket/URL transport failure.

~~~yaml
network_request_issued: true
http_status: NOT_RECEIVED
~~~

The diagnostic may retain only a normalized transport class, not exception
text that could contain credentials or host-specific unbounded data.

### HTTP_REACHABLE_AUTH_FAILURE

Use only when the server returns an HTTP 401 or 403 for the exact request.

~~~yaml
network_request_issued: true
http_status: 401_or_403
response_body: NOT_RETAINED
~~~

### HTTP_REACHABLE_OTHER_FAILURE

Use when the exact endpoint returns a bounded non-authentication HTTP status
other than 200, or when an HTTP response is received but its bounded body is
malformed, oversized, or otherwise unusable for the reachability shape check.

~~~yaml
network_request_issued: true
http_status: bounded_status
response_body: NOT_RETAINED
~~~

No semantic interpretation of a non-200 response is permitted.

### ENDPOINT_REACHABLE

Use when the exact endpoint returns HTTP 200 and a bounded JSON response that
passes only the model-catalog shape check required to establish reachability.
This does not assert that the model identity matches, that /props is usable,
or that apply-template is compatible.

~~~yaml
network_request_issued: true
http_status: 200
bounded_json_shape: model_catalog_observable
~~~

Malformed JSON, oversized bodies, redirects away from the exact URL, and
unexpected response shapes are therefore HTTP_REACHABLE_OTHER_FAILURE evidence
or a bounded endpoint-identity failure under the future execution authority.
They must never trigger a retry or a second route.

## Custody And Redaction

Any future diagnostic execution must create a fresh namespace before the
credential-bearing request and consume its one-shot authority before issuance.
It must seal one immutable terminal record containing:

~~~yaml
diagnostic_authorization_id:
target_url: http://192.168.2.141:8888/v1/models
classification:
network_request_issued: true/false
http_status: bounded status or NOT_RECEIVED
credential_resolution: d4.load_d4_api_key(repo_root)
endpoint_attempts: 0_or_1
provider_calls: 0
model_calls: 0
auth001_replayed: false
~~~

The record must not contain credentials, Authorization headers, raw response
bodies, full model paths, or unrestricted exception text. It may contain
bounded response-shape and normalized transport-class fields.

Custody verification must prove:

1. the diagnostic authority and fresh namespace match;
2. the authority was consumed before the network attempt;
3. no request beyond the exact /v1/models observation occurred;
4. the sealed AUTH-001 artifacts remain unchanged;
5. no provider/model calls occurred.

## Stop And Revisit Conditions

Stop without further requests when:

- Stage 0 is LOCAL_PRECONDITION;
- no HTTP response is received;
- any HTTP response is received, regardless of classification;
- the exact URL redirects or response bounds are violated;
- custody cannot prove the one-shot sequence.

If the result is ENDPOINT_REACHABLE, the next action is not to rerun AUTH-001.
The next action is to prepare a fresh runtime-build probe authorization with a
fresh namespace and independently reviewed identity bindings. If the result is
any other network classification, infrastructure remediation or a separately
bounded diagnostic design is required before a new probe is considered.

## Acceptance Boundary

This design is complete when independently reviewed as a diagnostic contract.
It does not authorize Stage 1 network execution, /props, /apply-template, or
any model generation.

~~~yaml
failed_probe_authority: CLOSED / CONSUMED
diagnostic_design: READY_FOR_INDEPENDENT_REVIEW
diagnostic_network_calls: 0
provider_model_calls: 0
Gate-B: BLOCKED
live_generation: NOT_AUTHORIZED
~~~
