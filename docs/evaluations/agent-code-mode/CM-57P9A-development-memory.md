# CM-57P9A Endpoint-Session Reproducibility Characterization

## Status

CM-57P9A live execution completed at the accepted endpoint-session
checkpoint:

```text
baseline: 00d0b54a96369ecb5c05230596e4bb517885d974
experiment: CM-57P9A
implementation status: LIVE EVIDENCE RECORDED
provider calls: 112
production changes: 0
P9B: blocked
decision: INCONCLUSIVE_REPRODUCIBILITY_EVALUATION
```

The endpoint-session re-scope preserves meaningful remote provenance without
requiring PID, binary, or GGUF access on the llama.cpp host. The completed
population contains 48 rows from 96 sequential planner executions and 112
provider calls, with zero worker/program calls. The raw JSONL and bounded
summary are recorded in `CM-57P9A-endpoint-session-live-summary.json`.

The population itself is complete and all twelve arm/case groups are
classified as exact-reproducible at the recorded plan/outcome/provider levels.
However, the PRE and POST `/v1/models` fingerprints expose different model
catalog hashes (`36713c...e4799` versus `7a67f0...a357`) even though both
expose `qwen3.6-35b-a3b`. Under the frozen fail-closed rule this makes the
overall result `INCONCLUSIVE_REPRODUCIBILITY_EVALUATION`. This run therefore
does not prove stable endpoint/model provenance for promotion.

The endpoint-session result also cannot prove that the remote llama.cpp
process, binary, GGUF, or hardware state remained identical. No production
route, prompt, schema, model control, or P9B behavior was changed.

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

## Live Evidence and Hard Stop

The authorized matrix ran once at the reviewed checkpoint. The raw evidence
must remain unchanged at:

```text
/tmp/cm57p9a-endpoint-session-qwen.jsonl
sha256: 2e13a0c4f973f2ba36fa3bd2c460d49b83591746fb626b1c0d2702f692c661a2
```

PRE and POST provenance were captured only through non-inference `GET
/v1/models` requests. No smoke request, selective rerun, resume, or append was
used. The result is evidence-only: do not modify production code, begin P9B,
or start typed-worker/routing work. A separate review is required before any
follow-up reproducibility run or promotion decision.
