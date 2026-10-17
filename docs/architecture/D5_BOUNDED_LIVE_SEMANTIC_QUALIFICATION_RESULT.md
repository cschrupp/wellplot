# D5-4 Provider-Free Live-Qualification Harness Result

## Status

```yaml
slice: WELLPLOT-D5-4
authority: WELLPLOT-RUNTIME-CONFIG-YAML-IMPL-AUTH-001
frozen_design: 1658c1593330620501baa4a551b965fa209cc95b
accepted_d5_3_engine: 51fd23fe18ca77c067b0cdf702f88a57ba4c457d
branch: implementation/project-runtime-config-yaml
phase: PROJECT_RUNTIME_CONFIGURATION_REPAIR
status: COMPLETE / READY FOR INDEPENDENT REVIEW
live_qualification: AUTHORIZED / NOT RUN / PAUSED FOR CONFIG REPAIR REVIEW
campaign_started: NO
campaign_consumed: NO
production_promotion: NOT AUTHORIZED
```

This result records qualification of the D5-4 orchestration and evidence
harness only. It is not evidence that Qwen passed live qualification, that the
endpoint is ready, or that a real campaign was executed.

## 1. Authorized Footprint

The implementation changes only the authorized runtime-configuration files:

```text
config/wellplot.yaml
src/wellplot/project_config.py
tests/test_project_config.py
scripts/nlp_d5_live_semantic_qualification.py
tests/test_nlp_d5_live_semantic_qualification.py
docs/runtime-configuration.md
docs/architecture/D5_BOUNDED_LIVE_SEMANTIC_QUALIFICATION_RESULT.md
```

No D4 fixture/gold, source asset, dependency lockfile, production manifest,
accepted design document, provider implementation, or MCP adapter changed.

The new `config/wellplot.yaml` is non-secret infrastructure configuration.
`src/wellplot/project_config.py` validates it with a strict frozen Pydantic
model, derives `/v1`, `/v1/models`, and `/props`, and computes a deterministic
semantic SHA-256 fingerprint. D5 static preflight requires the external live
authorization to carry that exact fingerprint before credentials or endpoint
activity. The D5 adapter and readiness path consume the loaded config for the
server origin, model, timeout, retries, concurrency, and structured-output
contract; historical D4 endpoint constants and artifacts are unchanged.

## 2. Harness Contract Implemented

The provider-free harness now proves the following boundaries without network
or model activity:

- static preflight is fail-closed on the exact implementation/design/engine
  checkpoints, source/case/gold/lock custody, OpenAI version/retry contract,
  D5 attestation/reachability, and fresh artifact paths;
- readiness accepts only the ordered `/v1/models` then `/props` observations;
- readiness projects the documented llama.cpp `/props` identity fields:
  model path identity, context, slots, build, a SHA-256 chat-template
  identity, and runtime defaults without synthetic capability or thinking
  fields, credentials, raw responses, or absolute paths;
- readiness does not perform a structured-generation probe;
- actual `response_format` acceptance belongs to the first measured scientific
  generation, with rejection classified as
  `INCONCLUSIVE / PROVIDER_BOUNDARY / STRUCTURED_OUTPUT`;
- planner and worker decoder controls match the frozen production request
  builder, with optional controls absent on the wire and no model substitution;
- `STARTED` is created only after readiness, is bound to the external
  authorization, fixed campaign ID, and authorized artifact root, and cannot
  be bypassed by a new runner or relocated artifact namespace;
- logical call 46 is rejected before delegation, while each observed SDK/HTTP
  retry remains a physical attempt on the same logical call;
- the exact nine-turn D4 population executes in order through the canonical
  Direct Notebook adapter in the deterministic rehearsal;
- deterministic D4 grading remains the authority for semantic and safe-negative
  results; no second grader was introduced;
- state, journal, terminal, summary, and evidence artifacts are fresh,
  authorization-bound, cross-referenced through a recomputable acyclic hash
  chain, redacted, and terminally immutable;
- the explicit `--execute-live` path wires static preflight, the two readiness
  GETs, provider construction, fixed `STARTED` custody, and the canonical
  nine-turn adapter; live result and custody counts distinguish readiness
  endpoint calls from logical and physical generation calls;
- the real `AsyncOpenAI` transport, OpenAI-compatible backend, D4 counting
  backend, and canonical Direct Notebook composition are qualified through an
  in-memory HTTP transport for zero, one, and two SDK retries, including the
  physical-attempt ceiling;
- deterministic persistence/render failures are classified as
  `INCONCLUSIVE / PRODUCTION_OR_INFRASTRUCTURE`, while valid but wrong
  structured semantics remain `FAIL / SEMANTIC_CONTRACT`;
- semantic failures are `FAIL`, while provider, transport, production,
  persistence/render, evidence, interruption, and configuration failures are
  `INCONCLUSIVE`.

## 3. Provider-Free Validation

Focused configuration validation:

```text
tests/test_project_config.py
19 passed
```

Final focused D5 harness validation:

```text
tests/test_nlp_d5_live_semantic_qualification.py
33 passed
```

The deterministic rehearsal included in that suite proves:

```yaml
population: 9/9
CBL: PASS
LAS positive contracts: PASS
safe-negative contracts: PASS
persistence/reload/render: PASS
logical calls: 18
physical attempts: 18
provider calls: 0
endpoint calls: 0
model calls: 0
terminal: PASS
```

Rework regressions:

```yaml
authorization-bound one-shot: PASS
retry integration: 9 logical / 27 physical PASS
persistence/render attribution: PASS
five-artifact digest recomputation: PASS
artifact-root authorization binding: PASS
truthful live/provider-free call accounting: PASS
real transport retry qualification: PASS
physical-attempt ceiling on real transport path: PASS
chat-template fingerprint custody: PASS
real provider-bound failure attribution: PASS
semantic failure remains FAIL / SEMANTIC_CONTRACT: PASS
```

Adjacent validation:

```text
D5-3 parity/convergence and D4R1 integration: 18 passed
D4 acceptance/harness regressions: 78 passed
D5 production attestation: PASS
D5 reachability audit: PASS, 91 canonical components
```

Static validation:

```text
Ruff: PASS
Ruff format --check: PASS
Python compilation: PASS
git diff --check: PASS
```

The tests use deterministic/injected endpoint and model doubles only. No
credential was loaded, no endpoint identity request was made, and no provider
or model generation was attempted.

## 4. Governance Boundary

The harness is ready for independent implementation review at the exact
candidate commit. Human Gate B authorization already exists under
`WELLPLOT-D5-4-LIVE-RUN-AUTH-001`. The earlier readiness attempt returned
`NOT_READY` before `STARTED` was created, so the scientific campaign remains
unconsumed. This configuration repair requires independent acceptance before
the execution record is refreshed. After acceptance, the existing execution
authority continues without a new human Gate-B confirmation; the refreshed
machine record is custody, not a new decision. This implementation does not
execute or consume that authority:

```text
Qwen generation
real /v1/models or /props calls from this provider-free validation
live qualification from this provider-free validation
MCP live qualification
model comparison
prompt or decoder tuning
production promotion
```

## 5. Runtime Configuration Repair

The earlier Gate-B readiness attempt used the historical `.140` endpoint and
returned `NOT_READY` before `STARTED` was created. The campaign was therefore
not consumed and no scientific result was produced. This implementation moves
the operational endpoint into the canonical non-secret project configuration
at `http://192.168.2.141:8888`; the D5 source no longer owns an endpoint
literal. The refreshed execution record must pin the semantic configuration
fingerprint before the already-authorized readiness attempt.
