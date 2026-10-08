# WellPlot NLP D4A Provider-Free Harness Result

## Status

```yaml
decision: WELLPLOT_NLP_D4A_IMPLEMENTATION_COMPLETE_REVIEW_PENDING
authorization: WELLPLOT-NLP-D4A-AUTH-002
authorized_parent: 8618c3ef2207236ad50d5fc576cf1c96badbfb95
production_baseline: 2c8e851fcd8b315e5d1861652a97984202db7488
live_inference: NOT_STARTED
provider_calls: 0
endpoint_calls: 0
model_calls: 0
D4B: NOT_AUTHORIZED
D4C: NOT_AUTHORIZED
production_promotion: NOT_AUTHORIZED
```

This record describes the provider-free D4A harness only. It is not an
independent acceptance of the harness and does not authorize D4B execution.

## Scope

The harness freezes five cases and nine ordered scientist turns:

```text
D4-C01:C01
D4-L01:T1
D4-L01:T2
D4-L01:T3
D4-L01:T4
D4-L02:T1
D4-L02:T2
D4-L03:C01
D4-L04:C01
```

The corrected LAS contract uses the real external source
`workspace/data/30-23a-3 8117_d.las`, size `5987785`, with SHA-256
`7e6c69c65713dc33303362ab91b767eb06371fd24a31856add8650e6d3bee1a9`.
The provider-free preflight requires `GR`, `CALI`, `ILD`, `ILM`, `MSFL`, and
`NPHI`, and requires `RT` to be absent. The LAS seed is loaded from the gold
fixture and validated directly with `AuthoringDocumentSpec.model_validate()`.

The two accepted D3 DLIS sources are authenticated by size and SHA-256 and
parsed before a future provider can be constructed. Source bytes are not
written to D4 evidence.

## Interlocks

The harness implements and tests:

- exact request identities and execution order;
- rejection of D3 request reuse;
- production-tree comparison against the D3 baseline;
- OpenAI package version `2.34.0` and runtime `max_retries = 2` inspection;
- a 45-call logical-generation ceiling with call 46 rejected before delegation;
- zero harness retries and distinct logical/transport accounting;
- atomic `STARTED` state creation before credential/provider construction;
- rejection of any existing state or journal, including zero-length artifacts;
- bounded evidence redaction with no credentials, headers, raw programs, or raw provider payloads;
- deterministic safe-failure, semantic-failure, and infrastructure decision precedence.

The `CountingBackend` records only operation kind, call index, configured
provider/model, request controls, bounded outcome/category, and provider usage
metrics. It never stores generated program text or structured response data.

## Frozen Artifact Hashes

```yaml
cases_fixture_sha256: f710581831b29dcd7ab321dd91afc5dd2b4e40b729161f969f8802f3f7a84298
gold_fixture_sha256: 05f920b5212d589d6c3763f003ab0465630408cf44539202bc45ecbf56648f24
```

The final harness checkpoint is intentionally not embedded here because a
commit cannot contain its own SHA. The implementation handoff supplies the
exact candidate commit and parent.

## Provider-Free Validation

The focused D4A suite uses only fake backends and reports:

```text
tests/test_nlp_d4_live_acceptance.py: 11 passed
provider / endpoint / model calls: 0
```

The D0–D2E delivery suite completed with `53 passed`. D3's real-DLIS/render
integration suite was invoked separately; its terminal result must be recorded
in the implementation handoff rather than inferred from partial progress.

Static checks required for this slice are `ruff check`, `ruff format --check`,
Python compilation, and `git diff --check`. No production source under
`src/wellplot` is authorized to change. Any full-suite failure must be
classified as D4A-attributable, known baseline reproduction, or unclassified;
unrelated failures must not be repaired under this authorization.

## Governance Boundary

This artifact stops at independent D4A review. D4B live execution remains
unauthorized, and the canonical state/journal paths must remain absent until a
separate live authorization permits a campaign.
