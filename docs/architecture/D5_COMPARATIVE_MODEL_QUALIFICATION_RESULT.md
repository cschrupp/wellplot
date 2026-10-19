# D5-5 Comparative Post-Hardening Model Qualification Result

## Status

```yaml
slice: WELLPLOT-D5-5B
authority: WELLPLOT-D5-5-COMPARATIVE-QUALIFICATION-DESIGN-AUTH-001
starting_checkpoint: 63aa1f9e0fecbfd15abefa20ab57e8e3d366a6a2
branch: implementation/d5-5-comparative-model-qualification
phase: HARNESS_REBIND_AND_PROVIDER_FREE_REHEARSAL
live_model_calls: 0
historical_campaign: d5-4-live-qwen-001
historical_campaign_status: PRESERVED / TERMINAL FAIL / NOT REPLAYED
status: COMPLETE / READY FOR INDEPENDENT REVIEW
```

This artifact records the D5-5B harness boundary only. It does not authorize
or perform Qwen or Luna endpoint activity. Live execution remains a separate
Gate-B decision after independent review.

The frozen design is repository-resident at
`docs/architecture/D5_5_COMPARATIVE_MODEL_QUALIFICATION.md`.

## Comparative Boundary

The two lanes vary only at the existing OpenAI-compatible provider boundary:

```text
lane configuration
  -> existing create_provider_backend()
  -> shared canonical composition root
  -> SemanticPlanner
  -> deterministic enrichment/source inspection
  -> CanonicalReportWorker / CanonicalSectionWorker
  -> deterministic lowering/reconciliation/execution
  -> persistence / reload / render
```

The lanes are:

```yaml
qwen:
  model: qwen3.6-35b-a3b
  readiness: llama_cpp
  campaign_id: d5-5-qwen-001
  artifact_root: workspace/evaluations/d5-5/qwen

luna:
  model: openai/gpt-6-luna
  base_url: https://openrouter.ai/api/v1
  readiness: openai_compat
  campaign_id: d5-5-luna-001
  artifact_root: workspace/evaluations/d5-5/luna
```

No model-specific planner, worker, lowerer, schema, retry, or reconciliation
path was added. Qwen local readiness and Luna OpenAI-compatible readiness are
represented as lane metadata; neither readiness path runs in D5-5B.

## Frozen Scientific Contract

The exact D4/D5 nine-turn population, order, source custody, cases, gold,
`uv.lock`, deterministic graders, safe-negative behavior, persistence/reload,
rendering, and call limits are reused unchanged:

```yaml
turns: 9
logical_call_ceiling_per_lane: 45
physical_attempt_ceiling_per_lane: 135
concurrency: 1
generation_timeout_seconds: 900
cases_sha256: f710581831b29dcd7ab321dd91afc5dd2b4e40b729161f969f8802f3f7a84298
gold_sha256: 99ba5fc73dfd95d67c8a909cb75325a84ff1bbccc724fa524d7850f306d02968
las_sha256: 7e6c69c65713dc33303362ab91b767eb06371fd24a31856add8650e6d3bee1a9
uv_lock_sha256: 0076359f8f68da82efa5e800d61ef38032fad72742340f51b78b6d8e969ff1b6
```

Each live lane will own separate state, journal, terminal, summary, and
evidence namespaces. The historical `d5-4-live-qwen-001` namespace is not
reused.

## Provider-Free Evidence

The D5-5B focused suite runs the same deterministic Direct Notebook route for
both lane descriptors. It proves:

- CBL construction and CBL-01 through CBL-09 grading;
- all four cumulative LAS revisions;
- ambiguity, unavailable-source, and unavailable-channel safe rejection;
- persistence/reload and real rendering;
- exactly nine turns and 18 logical fixture calls per lane;
- zero endpoint, provider, and model calls;
- distinct lane campaign/artifact identities;
- single-engine attestation and post-hardening checkpoint ancestry.

The provider-free rehearsal does not claim semantic equality between future
heterogeneous models. Latency, token usage, endpoint identity, and provider
runtime metadata remain lane observations. The acceptance object remains the
same deterministic WellPlot outcome contract.

The executable provider-free boundary also exercises lane-specific readiness
with injected endpoint responses, existing provider-factory construction, the
existing D5-4 live adapter with in-memory transport, and the shared
`D5CampaignRunner` STARTED/terminal custody. Qwen performs the two llama.cpp
identity observations; Luna performs only its OpenAI-compatible model-catalog
observation. No provider or model request is sent.

## Validation Handoff

```yaml
implementation_checkpoint: 1f347c854c2a8911b7776dd712c5ff9bf514d48a
parent: d90b769782eaa864fe944fac3d277192da4e0b57
changed_files:
  - scripts/d5_5_comparative_model_qualification.py
  - tests/test_d5_5_comparative_model_qualification.py
  - docs/architecture/D5_COMPARATIVE_MODEL_QUALIFICATION_RESULT.md
provider_free_qwen_rehearsal: 9/9 PASS / 18 logical calls
provider_free_luna_rehearsal: 9/9 PASS / 18 logical calls
single_engine_attestation: PASS
provider_calls: 0
model_calls: 0
live_execution: NOT AUTHORIZED IN D5-5B
```
