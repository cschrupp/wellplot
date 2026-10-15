# D5-4 Bounded Live Semantic Qualification Design

## Status

```yaml
slice: WELLPLOT-D5-4
authorization: WELLPLOT-D5-4-LIVE-QUAL-DESIGN-AUTH-001
design_status: DESIGN_ONLY / READY FOR INDEPENDENT DESIGN REVIEW
starting_checkpoint: 51fd23fe18ca77c067b0cdf702f88a57ba4c457d
accepted_d5_3_checkpoint: 51fd23fe18ca77c067b0cdf702f88a57ba4c457d
branch: design/d5-4-bounded-live-semantic-qualification
production_implementation: NOT AUTHORIZED
live_qualification: NOT AUTHORIZED
provider_calls: 0
endpoint_calls: 0
model_calls: 0
```

This document defines the bounded live qualification that may follow the
accepted D5-3 provider-free parity result. It does not execute a provider,
change production code, alter the scientific population, or authorize a live
campaign.

## 1. Decision Record

### Decision

Run one finite live semantic qualification of the already accepted canonical
WellPlot engine against the exact frozen D4 nine-turn population. Keep the
Direct Notebook route as the sole live adapter in this slice. Treat the local
Qwen/llama.cpp deployment, structured-output contract, evidence custody, and
deterministic graders as qualification inputs rather than introducing a new
planner, worker, compiler, or provider abstraction.

### Project scope

WellPlot is a scientific well-log plot builder. The model is allowed to
perform bounded semantic planning and worker communication. Source grounding,
canonical reconciliation, mutation, persistence, reload, rendering, grading,
and failure containment remain deterministic and authoritative.

D5-4 therefore evaluates the real model/provider boundary only after D5-3 has
already established the canonical engine and adapter parity contract.

### External evidence

The design uses the following primary sources:

- The [llama.cpp server API documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md), which documents the OpenAI-compatible server surface, `/v1/models`, `/props`, model identity, context properties, chat templates, and structured response formats.
- The [llama.cpp structured-output server test](https://github.com/ggml-org/llama.cpp/blob/master/scripts/server-test-structured.py), which exercises JSON-object and JSON-schema response formats through the server boundary.
- The [OpenAI Python client documentation](https://github.com/openai/openai-python), which documents client timeout and retry behavior for the OpenAI-compatible transport.
- The [OpenAI Python client constants](https://github.com/openai/openai-python/blob/main/src/openai/_constants.py), which define the default ten-minute timeout and default retry count used by the reference client version.

### Established practice

Mature structured-generation systems qualify the serving endpoint and response
contract before attributing a bounded task result to model capability. They
also keep schema validation and application-level validation outside the model
and record runtime identity needed to reproduce a result. Transport retries
are bounded at the client boundary; application code does not replay a
semantic request after an uncertain response.

### WellPlot difference

WellPlot has stronger deterministic authority than a general chat or agent
benchmark. A valid model response is not a successful scientific result. It
must pass the existing canonical workers, reconciliation, persistence,
reload, rendering, and D4 graders. Conversely, a provider or engine failure
must not be misclassified as model semantic failure.

### Options considered

| Option | Description | Decision |
| --- | --- | --- |
| A | Re-run all D4 cases through Direct Notebook and MCP | Rejected: MCP parity was already bounded by D5-3 and would add another live variable without answering a D5-4 question. |
| B | Use a reduced hand-picked live smoke set | Rejected: it would not cover the accepted safe-rejection and persistence contracts. |
| C | Reuse the exact nine D4 turns through Direct Notebook only | Selected: finite, comparable with D4, and isolates the real model/provider boundary. |

### Selected approach

Use Option C. Reuse the exact D4 requests, sources, gold, deterministic graders,
call custody, redaction rules, and canonical route. Add only the live
qualification orchestration and runtime evidence needed to distinguish model
semantic outcomes from operational or production failures.

### Evidence class

`ADAPTED` from established structured-generation qualification and bounded
evaluation practice, with `EMPIRICALLY_SUPPORTED` WellPlot evidence from the
accepted D4 and D5-3 provider-free rehearsals.

### Risks

- A server identity can be syntactically valid while serving an unintended
  model artifact or incompatible chat template.
- A valid JSON response can still encode an invalid or unsafe WellPlot intent.
- SDK transport retries can obscure physical request counts unless separately
  recorded.
- A slow local DLIS/render path can be mistaken for model failure if phase and
  timeout evidence are not separated.
- A production defect can be incorrectly attributed to the model if terminal
  classification is not fail-closed.

### Reversible

Yes. This is a finite qualification design. It does not alter production
semantics, prompts, fixtures, gold, or the D5-3 engine. A failed qualification
preserves evidence and can be followed by a separately authorized correction
or model-selection decision.

### Validation

The future implementation must prove the exact population, runtime identity,
call limits, custody hashes, role-aware call accounting, deterministic
grading, persistence/reload/render obligations, safe rejection, and terminal
classification described below without provider calls during implementation.

### Stop / revisit condition

Stop immediately for independent review if any live result reveals a production
defect, unbounded retry/replay, identity drift, evidence-integrity failure,
unexpected mutation, or an architectural requirement that the frozen D5 route
cannot represent. Do not repair and continue the same campaign.

## 2. Qualification Question And Boundary

D5-4 answers exactly this question:

> With the accepted single-engine D5 route and frozen WellPlot contracts, can
> the configured local Qwen deployment produce safe, semantically correct
> outcomes for the finite accepted D4 population?

It does not answer whether Qwen is the best available model, whether MCP
should be qualified live, whether prompts should be tuned, or whether WellPlot
should adopt an external provider.

The accepted D5 route remains:

```text
Direct Notebook public adapter
  -> shared composition root
  -> SemanticPlanner
  -> deterministic enrichment / source inspection
  -> canonical report or section worker
  -> deterministic semantic lowering
  -> AuthoringDocumentIntent
  -> reconcile_authoring()
  -> AuthoringExecutor
  -> AuthoringService
  -> persistence / reload / render
```

No live call may bypass this route. No D4 retired engine, program worker,
Semantic-IR compiler, stable fallback, or visual-specific compiler may be
reintroduced.

## 3. Frozen Scientific Population

The live population is exactly the accepted D4 population: one CBL construction
case and eight LAS revision/negative-path turns, for nine scientist turns.
No turn may be added, removed, reordered, paraphrased, or selectively rerun.

| Order | Turn | Operation | Required live semantic result |
| ---: | --- | --- | --- |
| 1 | `D4-C01:C01` | CBL construction | Completed canonical artifact; `CBL-01` through `CBL-09` pass; persistence, reload, and real render pass. |
| 2 | `D4-L01:T1` | Report title mutation | Requested title changes; unrelated state is preserved; persistence and reload pass. |
| 3 | `D4-L01:T2` | Existing GR scale mutation | Requested minimum/maximum change; complete frozen before/after contract and preservation pass. |
| 4 | `D4-L01:T3` | Track and grounded ILD binding creation | Requested track and source-grounded binding are created; unrelated state is preserved. |
| 5 | `D4-L01:T4` | Grounded GR fill creation | Requested fill relation is created; binding ownership and persistence pass. This is the representative Direct Notebook render state. |
| 6 | `D4-L02:T1` | Ambiguous target rejection | Bounded ambiguity diagnostic; no worker mutation, persistence, or replay. |
| 7 | `D4-L02:T2` | Clarified target acceptance | Requested clarified target changes; full frozen semantic/preservation contract passes. |
| 8 | `D4-L03:C01` | Unavailable source rejection | Source grounding fails closed; no intent, mutation, or persistence. |
| 9 | `D4-L04:C01` | Unavailable channel rejection | Exact `channel_missing`-class failure; no substitution, mutation, or persistence. |

The exact request strings, request hashes, fixture path, gold path, and source
custody are inherited from D4 and are immutable inputs to the future run
authorization. The model must not receive gold expectations or hidden grader
data as prompt context.

## 4. Adapter And Parity Scope

Only the Direct Notebook adapter is live-qualified in D5-4. MCP remains
provider-free evidence from D5-3 and is not a second live population.

This is intentional: D5-3 already compared normalized Direct Notebook and MCP
canonical outcomes, raw allowlists, persistence, and the required render
subset. Repeating MCP live would confound model qualification with an adapter
comparison that has already been closed.

The future implementation must reuse the D5-3 canonical composition root and
the accepted D4 custody/grading primitives. A new D5-4 wrapper may orchestrate
the run, but it may not fork the worker route or implement a second semantic
lowerer.

## 5. Source And Fixture Custody

The following source and evaluation identities are frozen and must be checked
before readiness and recorded in sanitized evidence:

```yaml
LAS_source:
  relative_path: workspace/data/30-23a-3 8117_d.las
  byte_size: 5987785
  sha256: 7e6c69c65713dc33303362ab91b767eb06371fd24a31856add8650e6d3bee1a9
  required_channels: [GR, CALI, ILD, ILM, MSFL, NPHI]
  forbidden_channels: [RT]
fixture_cases:
  path: tests/fixtures/nlp_d4_live_cases.json
  sha256: f710581831b29dcd7ab321dd91afc5dd2b4e40b729161f969f8802f3f7a84298
gold:
  path: tests/fixtures/nlp_d4_live_gold.json
  sha256: 99ba5fc73dfd95d67c8a909cb75325a84ff1bbccc724fa524d7850f306d02968
uv_lock:
  path: uv.lock
  sha256: 0076359f8f68da82efa5e800d61ef38032fad72742340f51b78b6d8e969ff1b6
```

The CBL pair remains the exact accepted pair:

```text
workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis
workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis
```

Their accepted D3/D4 sizes and SHA-256 values remain the authority. A future
run must fail before `STARTED` if any source, fixture, gold, or dependency
identity differs. It must never create a synthetic replacement or alias a
scientifically different channel.

## 6. Provider, Runtime, And Model Identity

The canonical live target is the local llama.cpp OpenAI-compatible server:

```yaml
provider_boundary: openai_compat
runtime: local llama.cpp
server_origin: http://192.168.2.140:8888
openai_compat_base_url: http://192.168.2.140:8888/v1
model_catalog_url: http://192.168.2.140:8888/v1/models
props_url: http://192.168.2.140:8888/props
requested_model_id: qwen3.6-35b-a3b
fallback: NONE
model_substitution: FORBIDDEN
```

The future run authorization must provide exact expected values for the
following fields. It must not rely on a catalog identifier alone, because
llama.cpp permits a model ID derived from a path or a configured alias:

| Identity | Required evidence | Handling |
| --- | --- | --- |
| Provider boundary | `openai_compat` | Exact match. |
| Server origin/base URL | Origin and `/v1` base URL above | Exact match; do not conflate origin with API base URL. |
| Catalog | Exactly one model entry with ID `qwen3.6-35b-a3b` | Exact match. |
| Model path | Sanitized basename and path fingerprint | Exact match to authorization; never retain an absolute path. |
| Model artifact bytes | GGUF SHA-256 if host artifact access exists | Match when supplied; `NOT_AVAILABLE` is observational only and never replaces catalog/path/build identity. |
| llama.cpp build | Sanitized build identity from `/props` | Exact match to authorization. |
| Context | Runtime context size and deterministic request-budget fit | Exact observed value; the authorization must include the required minimum context budget. |
| Slots | `total_slots` | Exact match; concurrency remains one. |
| Chat template | Name/fingerprint and capability projection | Must be recorded and match the authorized serving contract. |
| Structured output | JSON-object/JSON-schema capability for the requested contract | Must be established before scientific grading; schema validation remains local and authoritative. |
| SDK | OpenAI Python version `2.34.0` | Exact match. |
| Retry policy | SDK `max_retries=2`, no WellPlot retry | Exact match. |

Credential-bearing `/v1/models` and `/props` observations occur only in the
future authorized readiness run. Record sanitized identity and bounded status,
not credentials, headers, raw response bodies, absolute model paths, or
prompt/payload contents.

The identity evidence must distinguish server authentication from client
credential use. Loading `OPENAI_COMPAT_API_KEY` proves only that the client can
present its configured credential; it does not claim server-side authentication
semantics beyond the successful bounded HTTP response.

## 7. Prompt, Schema, And Decoder Freeze

The exact D4 request strings and request hashes are frozen. No prompt tuning,
paraphrasing, system-message change, gold-aware context, or model-specific
prompt branch is allowed during qualification.

The structured worker contract is the accepted D5 typed worker contract. The
future live adapter must submit the same canonical request roles and validate
responses locally with the existing DTO/schema and canonical worker boundary.
The model does not receive gold, expected diffs, grader code, or hidden
preservation projections.

The client-side generation controls are frozen as follows:

```yaml
planner:
  temperature: 0.0
  max_output_tokens: ABSENT_OR_NONE
report_worker:
  temperature: ABSENT_OR_NONE
  max_output_tokens: ABSENT_OR_NONE
section_worker:
  temperature: ABSENT_OR_NONE
  max_output_tokens: ABSENT_OR_NONE
all_roles:
  max_tokens: ABSENT
  max_completion_tokens: ABSENT
  top_p: ABSENT_UNLESS_FROZEN_IN_RUN_AUTH
  top_k: ABSENT_UNLESS_FROZEN_IN_RUN_AUTH
  seed: ABSENT_UNLESS_FROZEN_IN_RUN_AUTH
  model_substitution: FORBIDDEN
```

Any server-side default that affects decoding must be captured in the
authorized runtime identity/configuration. It must not be tuned after the
first scientific call. The run authorization must also freeze the server's
reasoning/thinking mode explicitly; automatic mode selection is not allowed.
The selected D5-4 default is reasoning/thinking off so that the structured
worker output is the measured artifact. If the server cannot honor that
setting, readiness fails before `STARTED`.

Structured output is not accepted merely because JSON parses. The local
decoder, Pydantic/DTO validation, canonical semantic worker, reconciliation,
and deterministic graders remain authoritative.

## 8. Call Ceiling, Timeout, Retry, And Concurrency Contract

The scientific call ceiling is:

```yaml
max_logical_generation_calls: 45
expected_provider_free_rehearsal_calls: 18
max_sdk_retries: 2
max_physical_generation_attempts: 135
scientist_turn_concurrency: 1
generation_timeout_seconds: 900
wellplot_retry: NONE
```

The 45-call value is a ceiling, not a target. The provider-free D4 rehearsal
has nine planner/worker turns and 18 logical calls, but the live model may
take a different bounded role path. The future ledger must count every
logical structured generation request by role and reject logical call 46
before delegation.

The physical attempt upper bound is a custody calculation:
`45 * (1 + max_sdk_retries) = 135`. SDK transport retries may occur only under
the frozen client policy. WellPlot must not retry a semantic request, replay a
turn after an uncertain response, or silently invoke a second engine.

Endpoint identity calls are exactly two bounded credential-bearing GETs, in
order: `/v1/models`, then `/props`. They are readiness observations and are
excluded from the scientific generation ceiling. Each response read is bounded
to 1 MiB, matching the accepted D4 safety contract. The readiness HTTP timeout
and generation timeout must be recorded separately.

## 9. Readiness Gate And Campaign Boundary

The lifecycle is deliberately split at the scientifically meaningful boundary:

```text
static repository/source preflight
  -> credential discovery without value disclosure
  -> authenticated /v1/models
  -> authenticated /props
  -> exact runtime/model/structured-output contract verification
  -> OpenAI-compatible client construction
  -> LIVE_READY
  -> create fresh campaign state and journal with STARTED
  -> first frozen scientist turn
```

All checks before `STARTED` may be retried if they fail and no scientific
generation has occurred. A readiness failure is `NOT_READY`/`NOT_RUN`, not a
scientific model failure and does not consume the campaign.

Static preflight must verify, before credential-bearing calls:

- exact authorized checkout and clean working tree;
- accepted D5-3 implementation checkpoint and D5 single-engine attestation;
- D5 reachability audit pass and unchanged production component hashes;
- exact source, case, gold, and `uv.lock` custody;
- provider, endpoint, model, SDK, timeout, retry, and concurrency contract;
- fresh state, journal, terminal, summary, and evidence paths absent;
- no D4 historical artifact is reused as a current campaign file;
- no model substitution or fallback is configured.

Operational readiness then verifies credential availability, bounded endpoint
identity, chat-template/structured-output capability, context-budget fit,
client construction, and the exact expected identity. Raw credentials and raw
HTTP bodies are never persisted.

No provider or endpoint call is made by this design document or its design
review. The future implementation and run authorization must provide the
actual readiness command and its custody paths.

## 10. Evidence Custody And Redaction

The future campaign must create fresh, unique artifacts only after static and
operational readiness pass:

```text
<d5-4-campaign-root>/<campaign-id>.state.json
<d5-4-campaign-root>/<campaign-id>.journal.jsonl
<d5-4-campaign-root>/<campaign-id>.terminal.json
<d5-4-campaign-root>/<campaign-id>.summary.json
<d5-4-campaign-root>/<campaign-id>.evidence.jsonl
```

The campaign ID, state, journal, terminal, summary, and evidence hashes must
be mutually cross-referenced. State and journal are append/transition records;
they are not regenerated after a terminal result.

Each logical call record must retain only bounded, reviewable metadata:

```yaml
turn_id: frozen D4 turn ID
role: planner / report_worker / section_worker
logical_call_index: integer
physical_attempt_count: integer
provider: openai_compat
model: qwen3.6-35b-a3b
request_started_at: timestamp
request_finished_at: timestamp or absent
latency_ms: bounded value or absent
usage: public token fields only, or NOT_RECORDED
outcome: completed / failed / rejected
failure_category: bounded taxonomy value or absent
```

Evidence may include sanitized endpoint identity, source/case/gold hashes,
artifact hashes, canonical before/after projections, deterministic grader
results, persistence/reload/render evidence, and the terminal classification.

Evidence must not include credentials, authorization headers, raw endpoint
responses, absolute model paths, prompt text, generated payloads, hidden
reasoning, raw programs, or unbounded exception dumps. Redaction checks must
run before terminal publication.

Historical D4 state, journals, and results remain immutable historical
evidence. They must not be restored into D5-4 canonical paths or rewritten to
make the new campaign appear continuous.

## 11. Reuse, Adapt, Replace, And Do Not Reintroduce

| D4 capability | D5-4 disposition | Boundary |
| --- | --- | --- |
| Exact cases, requests, hashes, sources, and gold | REUSE | Immutable custody inputs. |
| Direct Notebook public path | REUSE | Sole live adapter. |
| D4 endpoint identity observations | ADAPT | Preserve two-call order, bounded reads, and sanitized identity; extend only the frozen D5 runtime projection. |
| D4 static preflight | ADAPT | Add D5 attestation/reachability and readiness-boundary ordering. |
| D4 state/journal/terminal custody | REUSE | Fresh D5 namespace and one-shot post-`STARTED` behavior. |
| D4 role-aware call ledger | REUSE | Keep logical/physical separation and 45-call cap. |
| D4 deterministic graders and CBL verifier | REUSE | No new model-dependent grader. |
| D4 redaction and integrity checks | REUSE | Preserve fail-closed behavior. |
| D4 failure taxonomy | ADAPT | Map readiness, model, production, and evidence failures to D5 terminal categories. |
| D4 historical provider/model configuration | REPLACE | The accepted local Qwen/llama.cpp contract is the only live target. |
| D4 retired engines and fallbacks | DO NOT REINTRODUCE | D5-2 attestation/reachability must remain PASS. |
| MCP live adapter | DEFER | D5-3 provider-free parity is sufficient for this slice. |

No new schema family, worker architecture, semantic IR, compiler, fallback
engine, provider abstraction, or workflow engine is authorized by this design.

## 12. Grading And Result Classification

The existing deterministic D4/D5 graders remain the acceptance authority.

### Positive turns

`D4-C01:C01`, `D4-L01:T1`, `D4-L01:T2`, `D4-L01:T3`, `D4-L01:T4`, and
`D4-L02:T2` must satisfy the complete frozen before/after gold, required
transition, allowed-change containment, preservation, canonical validation,
persistence/reload, and render obligations applicable to that turn. CBL must
return `CBL-01` through `CBL-09` PASS.

### Negative turns

`D4-L02:T1` must reject ambiguity before unsafe mutation. `D4-L03:C01` must
reject unavailable source grounding. `D4-L04:C01` must report the bounded
missing-channel class, perform no channel substitution, leave canonical and
persisted artifacts unchanged, and receive the expected safe-failure grade.

### Campaign PASS

The campaign is `PASS` only when all nine frozen turns have the expected
positive or safe-negative result, every required artifact/custody check passes,
the exact endpoint/model identity matches, the generation ceiling is obeyed,
and persistence/reload/render obligations pass.

### Campaign FAIL

`FAIL` means the runtime and evidence are valid, but the model-produced
semantic result does not satisfy a frozen scientific contract. Examples include
an incorrect title/scale/fill/track intent, an incomplete CBL artifact, an
unrelated mutation, an incorrect safe rejection, or an output that is validly
parsed but semantically wrong. This is evidence against the current model
qualification, not permission to tune and replay the same campaign.

### Campaign INCONCLUSIVE

`INCONCLUSIVE` covers readiness or infrastructure failures after the campaign
boundary, provider transport exhaustion, timeout without a valid semantic
result, endpoint/model drift, evidence-integrity failure, call-cap violation,
unhandled production exception, persistence/render infrastructure failure, or
unexpected process interruption. Preserve all evidence and stop.

### Architectural escalation

`ARCHITECTURAL_ESCALATION` is permitted only when a frozen requirement cannot
be represented by the accepted D5 route after ruling out model output, prompt
or schema contract, grounding/source data, runtime identity, and production
defects. It is not a synonym for "the model performed poorly."

## 13. Failure Attribution Matrix

| Observation | Attribution | Terminal action |
| --- | --- | --- |
| Credential absent or endpoint identity mismatch before `STARTED` | Operational readiness | `NOT_READY`; readiness may be retried without consuming a campaign. |
| Model catalog, props, chat template, context, or build drift | Runtime/configuration drift | `NOT_READY` before `STARTED`; `INCONCLUSIVE` if discovered after. |
| JSON/schema decode failure on a model response | Model/provider boundary | Record bounded failure; classify according to whether the request completed and whether the deterministic contract can grade it. No replay. |
| Valid structured output with wrong WellPlot semantics | Model capability/qualification | `FAIL`; preserve evidence. |
| Canonical worker, reconciler, executor, persistence, renderer, or attestation defect | Production defect | Stop immediately; `INCONCLUSIVE`; no repair in campaign. |
| Unexpected mutation or unsafe rejection | Model/production attribution pending deterministic evidence | Preserve before/after and diagnostics; do not continue after a production defect or integrity breach. |
| Evidence hash/redaction/custody failure | Evidence integrity | `INCONCLUSIVE`; preserve raw custody boundaries without publishing secrets. |
| Frozen D5 route cannot represent a requirement | Architecture | `ARCHITECTURAL_ESCALATION` only after bounded exclusion of the causes above. |

The first evidence source is the deterministic stage and diagnostic code. A
model failure must not be inferred merely because the final artifact is wrong,
and a production failure must not be hidden behind a model-failure label.

## 14. Restart, Resume, And Tuning Policy

Before `LIVE_READY`, readiness checks may be repeated when they fail without
creating a scientific campaign. A readiness retry must not issue a scientist
turn or write a campaign `STARTED` state.

Once fresh campaign state and journal record `STARTED`, the one-shot scientific
authorization is consumed. From that point there is:

- no resume;
- no selective rerun;
- no second invocation under the same authorization;
- no prompt, schema, model, provider, decoder, source, gold, or grader change;
- no manual cancellation solely because a generation is slow;
- no semantic replay after an uncertain provider response.

If `STARTED` exists but zero scientist calls complete, the campaign is still
consumed and the result is `INCONCLUSIVE`, not an invitation to restart.

## 15. Production-Defect Stop Rule

The model is not allowed to compensate for a defect in the canonical engine.
If a measured run exposes an unhandled exception, a wrong canonical route, an
attestation mismatch, an unexpected persistence/render mutation, a broken
source-grounding contract, or an evidence-custody violation, stop at the
first bounded observation. Preserve state, journal, and artifacts unchanged.

No production fix, manifest change, fixture change, prompt change, or retry is
allowed under the consumed campaign. A separately authorized correction must
be implemented and provider-free qualified before any new live authority is
considered.

## 16. Future Evidence And Result Structure

The future implementation must produce a result record with these sections:

```yaml
campaign:
  id: unique fresh identifier
  authorization_id: exact live-run authority
  implementation_checkpoint: exact accepted D5-4 harness checkpoint
  d5_3_engine_checkpoint: 51fd23fe18ca77c067b0cdf702f88a57ba4c457d
  status: PASS / FAIL / INCONCLUSIVE / ARCHITECTURAL_ESCALATION
population:
  scientist_turns: 9
  turn_ids: exact frozen ordered list
runtime:
  provider: openai_compat
  runtime: local llama.cpp
  model: qwen3.6-35b-a3b
  endpoint_identity: sanitized exact projection
  sdk_version: 2.34.0
  sdk_max_retries: 2
  generation_timeout_seconds: 900
calls:
  logical_generation_calls: bounded integer
  physical_generation_attempts: bounded integer
  readiness_identity_calls: 2
  by_role: planner/report_worker/section_worker
custody:
  source_cases_gold_lock_hashes: exact
  production_attestation: PASS
  redaction: PASS
  evidence_integrity: PASS
turn_results:
  - turn_id, stage, outcome, grader, artifact hashes, bounded diagnostics
terminal:
  decision: PASS / FAIL / INCONCLUSIVE / ARCHITECTURAL_ESCALATION
  reason: bounded code
```

The state machine must make `NOT_READY`, `STARTED`, and terminal custody
unambiguous. The terminal artifact must include the state/journal/evidence
hashes and must be written once. The result document must distinguish
implementation-reported execution counts from independently reviewed source
evidence.

## 17. Future Implementation And Run Footprint

This design authorizes no implementation. If independently accepted, the next
implementation authorization must be bounded to an orchestration/evidence
adapter and its tests, with no production `src/**` changes:

```text
scripts/nlp_d5_live_semantic_qualification.py
tests/test_nlp_d5_live_semantic_qualification.py
docs/architecture/D5_BOUNDED_LIVE_SEMANTIC_QUALIFICATION_RESULT.md
```

The wrapper must import and reuse existing D4/D5 custody, identity, ledger,
worker, grader, and rendering primitives. It must not copy them into a second
implementation. Any need to modify the D5 production engine, D4 fixtures/gold,
source assets, or accepted manifest is a stop for a separate authorization.

The future live command must be one explicit `--execute-live` invocation with
an external authorization file and fresh D5-4 artifact paths. The provider-free
preflight and readiness command may be repeated before `STARTED`; the live
scientific command may be invoked once after `LIVE_READY`.

## 18. Model-Escalation Gate

Qwen remains the canonical reference model. A poor result does not authorize
automatic substitution.

Only the following finite evidence can justify a separate model-selection
decision:

1. The exact frozen nine-turn campaign reaches a valid terminal result with
   complete custody.
2. Any failed turns are reproducible from preserved evidence or a separately
   authorized repeat, not inferred from an operational failure.
3. The D5 route, source grounding, schemas, decoder settings, runtime identity,
   and deterministic graders are shown correct.
4. Bounded remediation of a demonstrated prompt/schema/adapter defect has
   either closed the issue or been explicitly ruled out without tuning the
   scientific population.
5. The remaining semantic failures are model-capability failures across the
   frozen cases, not isolated infrastructure or production defects.

If those conditions hold, a new human-authorized model-comparison design may
compare Qwen with a named alternative. It must define a new frozen population,
provider custody, cost/latency limits, and no-substitution rule. D5-4 itself
does not authorize that comparison.

## 19. Q1-Q14 Closure Matrix

| Question | Frozen D5-4 answer |
| --- | --- |
| Q1 Population | Exact nine D4 turns, in frozen order; no additions or reductions. |
| Q2 Adapter scope | Direct Notebook only; MCP remains provider-free D5-3 evidence. |
| Q3 Model/runtime | Local llama.cpp, OpenAI-compatible boundary, Qwen3.6-35B-A3B; exact catalog/path/build/context/slots/template contract. |
| Q4 Prompt/decoder | Exact D4 requests/hashes; accepted typed worker schemas; fixed client controls; explicit reasoning mode; no tuning. |
| Q5 Calls/retries | 45 logical generation ceiling, SDK max retries 2, 135 physical-attempt upper bound, concurrency 1, 900-second generation timeout, no WellPlot retry. |
| Q6 Readiness | Static custody and D5 attestation, credential, `/v1/models`, `/props`, identity, structured-output contract, context fit, client construction, then `LIVE_READY` before `STARTED`. |
| Q7 Evidence | Fresh state/journal/terminal/summary/evidence namespace; sanitized identity, bounded ledger, hashes, redaction, immutable terminal custody. |
| Q8 D4 relationship | Reuse cases, gold, sources, graders, custody, route, ledger, and safe-failure contracts; adapt identity/preflight/taxonomy; replace inherited provider target. |
| Q9 Grading | Existing deterministic CBL/LAS/D5 graders; complete gold and persistence/reload/render obligations; no new model-dependent grader. |
| Q10 Outcomes | PASS, FAIL, INCONCLUSIVE, ARCHITECTURAL_ESCALATION with the attribution matrix above. |
| Q11 Restart | Readiness retries before `STARTED`; no resume/replay/selective rerun after `STARTED`; one-shot campaign custody. |
| Q12 Production defects | Stop immediately, preserve evidence, classify `INCONCLUSIVE`, and require separate correction authority. |
| Q13 Artifacts | Exact state/journal/terminal/summary/evidence structure and redaction/cross-hash requirements above. |
| Q14 Footprint | Future wrapper, focused tests, and result document only unless a separate production authorization is issued; zero provider calls in implementation. |

## 20. Governance Boundary And Handoff

```yaml
WELLPLOT-D5-4-LIVE-QUAL-DESIGN:
  status: COMPLETE / READY FOR INDEPENDENT DESIGN REVIEW
  authority: WELLPLOT-D5-4-LIVE-QUAL-DESIGN-AUTH-001
  branch: design/d5-4-bounded-live-semantic-qualification
  starting_checkpoint: 51fd23fe18ca77c067b0cdf702f88a57ba4c457d
  accepted_d5_3_checkpoint: 51fd23fe18ca77c067b0cdf702f88a57ba4c457d
  changed_file: docs/architecture/D5_BOUNDED_LIVE_SEMANTIC_QUALIFICATION_DESIGN.md
  production_files_changed: 0
  tests_changed: 0
  provider_calls: 0
  endpoint_calls: 0
  model_calls: 0
  implementation: NOT AUTHORIZED
  live_qualification: NOT AUTHORIZED
  production_promotion: NOT AUTHORIZED
```

The next gate is independent review of this document. No implementation branch,
live endpoint readiness, model call, MCP qualification, or production
promotion may begin before that review and a separate implementation
authorization.
