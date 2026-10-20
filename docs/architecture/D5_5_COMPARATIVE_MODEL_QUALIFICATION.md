# D5-5 Comparative Model Qualification

## Frozen Authority

```yaml
authority: WELLPLOT-D5-5-COMPARATIVE-QUALIFICATION-DESIGN-AUTH-001
slice: WELLPLOT-D5-5
provider_free_implementation: D5-5B
live_qualification: D5-5C / separate Gate B
baseline: 63aa1f9e0fecbfd15abefa20ab57e8e3d366a6a2
branch: implementation/d5-5-comparative-model-qualification
```

This document is the repository-resident scientific design and freeze for the
post-hardening comparative qualification. D5-5B may implement and rehearse
the boundary without provider or model calls. D5-5C requires a separate
explicit live authority and must not be inferred from D5-5B completion.

## Objective and Boundary

Measure the same bounded WellPlot semantic workload through the Qwen lane and
a replacement DeepSeek lane after D5 semantic hardening:

```text
lane configuration
  -> existing OpenAI-compatible provider boundary
  -> shared canonical composition root
  -> SemanticPlanner
  -> enrichment and source grounding
  -> canonical report/section workers
  -> deterministic lowering, reconciliation, execution
  -> persistence, reload, and render
```

The lanes differ only in provider endpoint, model identity, readiness contract,
credential namespace, and evidence namespace. No model-specific planner,
worker, lowerer, schema, retry, or reconciliation path is permitted.

## Frozen Lanes

```yaml
qwen:
  provider: openai_compat
  runtime: local llama.cpp
  model: qwen3.6-35b-a3b
  readiness: llama_cpp
  campaign_id: d5-5-qwen-001
  artifact_root: workspace/evaluations/d5-5/qwen

deepseek:
  provider: openai_compat
  runtime: OpenRouter OpenAI-compatible API
  endpoint: https://openrouter.ai/api/v1
  model: deepseek/deepseek-v4.1-flash-1017
  provider_route:
    order: [Morph]
    allow_fallbacks: false
    require_parameters: true
  readiness: openai_compat
  campaign_id: d5-5-deepseek-001
  artifact_root: workspace/evaluations/d5-5/deepseek
```

The earlier Luna campaign `d5-5-luna-001` is sealed historical evidence. It is
not reused or replayed. The historical `d5-4-live-qwen-001` campaign and all of
its artifacts remain untouched and cannot be reused by either lane.

## Scientific Population

The exact accepted D4/D5 nine-turn population, order, source custody, cases,
gold, deterministic graders, persistence/reload/render obligations, and safe
negative outcomes are unchanged:

```yaml
turns: 9
turn_order:
  - D4-C01:C01
  - D4-L01:T1
  - D4-L01:T2
  - D4-L01:T3
  - D4-L01:T4
  - D4-L02:T1
  - D4-L02:T2
  - D4-L03:C01
  - D4-L04:C01
cases_sha256: f710581831b29dcd7ab321dd91afc5dd2b4e40b729161f969f8802f3f7a84298
gold_sha256: 99ba5fc73dfd95d67c8a909cb75325a84ff1bbccc724fa524d7850f306d02968
las_sha256: 7e6c69c65713dc33303362ab91b767eb06371fd24a31856add8650e6d3bee1a9
uv_lock_sha256: 0076359f8f68da82efa5e800d61ef38032fad72742340f51b78b6d8e969ff1b6
```

Provider/runtime differences are observations, not changes to the scientific
acceptance object. The canonical grader remains authoritative for semantic,
preservation, safe-failure, persistence, reload, and render outcomes.

## Readiness Contracts

Qwen uses the existing D5-4 local readiness contract: credential loading,
credential-bearing `/v1/models`, credential-bearing `/props`, exact frozen
llama.cpp identity and runtime checks, then construction of the existing
provider boundary.

DeepSeek uses the existing OpenAI-compatible path with only provider-appropriate
readiness: credential loading, credential-bearing `GET
https://openrouter.ai/api/v1/models`, exact requested model identity, and
construction of the existing provider boundary. DeepSeek does not call
`/props` and does not invent llama.cpp model-path, GGUF, slots, or
thinking-mode identity fields. The existing provider boundary carries the
OpenRouter Morph route with fallback disabled and parameter requirements
enabled; no provider-specific adapter is added.

Structured-output compatibility is established by the first scientific
generation, not by an identity GET. A structured-output rejection is
`INCONCLUSIVE / PROVIDER_BOUNDARY / STRUCTURED_OUTPUT`; it is not replayed.

## Custody and Limits

Each lane has independent five-artifact custody: state, append-only journal,
terminal, summary, and redacted evidence. A lane may create `STARTED` only
after its own readiness succeeds. A second invocation, resume, cross-lane
artifact root, campaign-ID mismatch, or historical campaign reuse fails closed.

```yaml
concurrency: 1
generation_timeout_seconds: 900
logical_call_ceiling_per_lane: 45
physical_attempt_ceiling_per_lane: 135
sdk_max_retries: 2
provider_model_substitution: FORBIDDEN
semantic_replay_after_started: FORBIDDEN
```

Logical call 46 and physical attempt 136 are rejected before provider
delegation. Provider/runtime failures after `STARTED` are terminal
`INCONCLUSIVE` evidence; they are not semantic failures and are not replayed.

## D5-5B Provider-Free Proof

D5-5B must prove without endpoint, provider, or model calls that:

- the exact nine-turn population and all custody hashes remain unchanged;
- both lane descriptors resolve to the same canonical engine;
- Qwen selects llama.cpp readiness and DeepSeek does not call `/props`;
- both lanes construct the existing provider factory and D5-4 live adapter
  with injected in-memory transport;
- both lanes enter the shared `D5CampaignRunner` and shared STARTED/terminal
  custody boundary;
- campaign IDs and artifact roots are distinct and cannot cross-consume;
- logical call 46 and physical attempt 136 fail closed;
- `d5-4-live-qwen-001` cannot be reused;
- the single-engine attestation passes;
- the deterministic nine-turn rehearsal is 9/9 for each lane, with 18
  logical calls and zero provider/model calls per lane.

The fake transports are test infrastructure only. They must not be reported as
live model observations or qualification evidence.

## D5-5C Live Gate

D5-5C is not authorized by this document. A future Gate B must pin both model
identities, endpoint/readiness fingerprints, authorization IDs, campaign IDs,
artifact roots, and exact implementation checkpoint before any endpoint or
model request. The two campaigns remain one-shot and independently sealed.

```yaml
D5-5B: provider-free implementation and rehearsal only
D5-5C: separate live authority required
production_promotion: not authorized
```
