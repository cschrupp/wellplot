# CM-57P9A Endpoint-Session Reproducibility Characterization

## Status

CM-57P9A is a provider-free pre-live implementation slice based on the
accepted P8 evidence checkpoint:

```text
baseline: e8f19141e6dd349d44ddd9cb97305a856216a6fa
experiment: CM-57P9A
implementation status: PRE-LIVE CORRECTION READY
provider calls: 0
production changes: 0
P9B: blocked
```

The post-checkpoint correction preserves the same experiment and controls
while tightening evidence validity: finalized rows must bind to the PRE
fingerprint and authorized checkout, terminal failures receive stable
structural fact hashes, and the reference diagnostic is populated from the
bounded production result. Host PID, binary, and GGUF access are intentionally
not required. Live inference remains unauthorized pending review of this
correction.

Initial structured-success diagnostics are derived specifically from the
`INITIAL` call trace entry. A retry-recovered plan therefore remains an initial
failure, while a semantic correction after an initial plan preserves initial
success.

No live inference, runtime fingerprint capture, provider construction, or
production routing change is part of this checkpoint.

## Question

The future live experiment will characterize whether repeated executions in
one endpoint/model session reproduce the same result under the production
planner. It compares the production prompt (`P`) with the frozen RC prompt
(`RC`) while keeping planner, schema, provider, model, and execution controls
unchanged. It does not prove that a single remote llama.cpp process remained
unchanged because the host is outside this execution environment.

The population is six hash-bound P7 cases, eight sequential repetitions per
case and arm, for 96 planner executions. The case manifest retains request and
gold hashes plus bounded historical P7/P8 anchors; it does not retain request
prose or provider output.

## Measurement Boundary

Each future row records bounded evidence only:

- raw assistant-content SHA-256, finish reason, token counts, and latency;
- final `SemanticPlan` SHA-256;
- a bounded planner-facts SHA-256;
- a complete response-inclusive call-trace hash;
- a structural call-path hash that excludes response text, so text variation
  does not get misclassified as a path change;
- provider category, planner outcome, correction/retry use, and worker-call
  count.

Provider response text, request payloads, exception text, document paths, and
raw provider responses are not retained in the evidence rows. Accidental
program generation is fail-closed and invalidates the population.

The runtime fingerprint helper supports endpoint/model provenance through a
non-inference `/v1/models` request. The PRE and POST records contain the
endpoint, configured model label, available model identifiers, and a hash of
the returned model catalog. They are compared descriptively and are a
population-integrity gate for future finalization. The older host-local
fingerprint helper remains available, but is not required by this P9A mode.

## Frozen Controls

```text
model: qwen3.6-35b-a3b
planner temperature: 0.0
max output tokens: 16384
token parameter: max_tokens
timeout: 900 seconds
arms: P, RC
repetitions: 8
worker/program calls: 0
```

The P9A script verifies the P9A manifest, P7/P8 artifacts, production planner
and provider artifacts, prompt hashes, response schema hash, source-summary
hash, capability catalog, and exact reviewed checkout before any future
provider construction. The default CLI path is provider-free.

## Decision Rules

The future completed population is classified hierarchically:

```text
ENDPOINT_SESSION_EXACT_REPRODUCIBLE
ENDPOINT_SESSION_PLAN_REPRODUCIBLE
ENDPOINT_SESSION_CONTRACT_REPRODUCIBLE
ENDPOINT_SESSION_NOT_REPRODUCIBLE
INCONCLUSIVE_REPRODUCIBILITY_EVALUATION
```

Provider text may vary while the semantic plan, planner facts, outcomes, and
structural call path remain stable. Historical P7/P8 anchors are descriptive
diagnostics only; they are not decision gates for P9A.

## Hard Stop

This checkpoint does not authorize model calls. Do not run the endpoint probe,
start the P9A matrix, modify production code, begin P9B, or start
typed-worker/routing work. A separate review and explicit live authorization
are required after the provider-free tests and artifact checks pass.
