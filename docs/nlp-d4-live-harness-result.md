# WellPlot NLP D4A Provider-Free Harness Result

## Status

```yaml
decision: WELLPLOT_NLP_D4A_QWEN_HARNESS_REWORK_001_COMPLETE_REVIEW_PENDING
authorization: WELLPLOT-NLP-D4A-QWEN-HARNESS-REWORK-001
implementation_base: 94a373c292178d21613853ef57f74a81c8e17986
rework_parent: 3b2b10e017c7380fec336a30ad5283fa21221914
design_authority: 0d0158fc3ddb8844b866444a8b6192be3f5aa93f
production_baseline: 2c8e851fcd8b315e5d1861652a97984202db7488
provider: openai_compat
runtime: local llama.cpp
model: qwen3.6-35b-a3b
live_inference: NOT_STARTED
provider_calls: 0
endpoint_identity_calls: 0
model_calls: 0
D4B: NOT_AUTHORIZED
D4C: NOT_AUTHORIZED
production_promotion: NOT_AUTHORIZED
```

This record describes the provider-free D4A harness only. It is not an
independent acceptance of the harness and does not authorize D4B execution.
The implementation performed no real endpoint identity observation: real
`/v1/models` calls, `/props` calls, provider generation calls, and model calls
are all zero. Synthetic endpoint identity is test evidence only, not observed
llama.cpp provenance.

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
- OpenAI-compatible package version `2.34.0` and runtime `max_retries = 2`
  inspection;
- a 45-call logical-generation ceiling with call 46 rejected before delegation;
- zero harness retries and distinct logical/transport accounting;
- atomic `STARTED` state creation before credential/provider construction;
- rejection of any existing state or journal, including zero-length artifacts;
- bounded evidence redaction with no credentials, headers, raw programs, or raw provider payloads;
- deterministic safe-failure, semantic-failure, and infrastructure decision precedence.

The amended live target is fixed to local llama.cpp through the existing
production `OpenAICompatibleBackendV2` and production `_provider_backend(...)`
boundary. The harness accepts only the credential names
`OPENAI_COMPAT_API_KEY`, `OPENAI_COMPAT_API_KEY.txt`, and
`openai_compat_api_key.txt` (including the same key in `.env` or `.env.local`);
it does not fall back to `OPENAI_API_KEY`. The token is loaded only after
durable `STARTED` state exists, passed explicitly to the production provider
factory, and never stored, hashed, or serialized.

The fixed endpoint contract is:

```text
server origin:       http://192.168.2.140:8888
OpenAI-compatible:   http://192.168.2.140:8888/v1
model catalog:       http://192.168.2.140:8888/v1/models
properties:          http://192.168.2.140:8888/props
requested model:     qwen3.6-35b-a3b
```

The two credential-bearing, non-generation GETs are projected into a bounded
identity containing the exact Qwen-only catalog, model-path basename and
fingerprint, context size, build information, slot count, and
`gguf_byte_identity: NOT_AVAILABLE` unless a host-level artifact hash is
separately available. Each response body is read with a fixed one-MiB cap
plus one byte to detect overflow; `build_info` must be non-empty and no more
than 256 characters and is persisted without truncation. Raw `/props`,
absolute model paths, chat templates, and credentials are not persisted.
Server authentication is not claimed.

The accepted future-live orchestration is implemented as `run_campaign()` and
the campaign-owned `D4CampaignAdapter` in the harness script. The adapter
composes the existing `DirectNotebookSession`, stages each frozen starting
artifact, executes the CBL/LAS turn branches, renders the exact generated CBL
artifact and successful LAS post-turn artifact, and supplies artifact paths to
the unchanged graders. CBL uses its artifact verifier contract rather than the
LAS canonical-diff contract. The runner creates the exclusive STARTED
sentinel, binds logical-call start and completion custody before the first
turn, executes the frozen nine-turn order sequentially, appends the complete
bounded turn schema, and derives the terminal decision without retries or
resume behavior. D4A exercises this same adapter with deterministic backends
only.

The `CountingBackend` records only operation kind, call index, configured
provider/model, request controls, bounded outcome/category, and provider usage
metrics. Turn rows include aggregate bounded token/latency usage, and both
pre-delegation starts and post-delegation completions are written
through durable campaign custody. It never stores generated program text or
structured response data. Exact endpoint/HTTP and remote model call counts are
not claimed; the SDK retry setting and physical-attempt upper bound remain the
available transport evidence.

Logical-call indexes are reserved at start time from one shared lock-protected
ledger used by the planner, report-worker, and section-worker wrappers. The
45-call ceiling is enforced against reserved calls before delegation, and
completion records retain the reserved index even when worker calls overlap.

The L02 starting artifact instantiates the accepted shared-boundary windows:
`Main Log – Upper` uses `8400.0..9300.0` ft and `Main Log – Lower` uses
`9300.0..10200.0` ft, both from the same authenticated LAS source.

## Frozen Artifact Hashes

```yaml
cases_fixture_sha256: f710581831b29dcd7ab321dd91afc5dd2b4e40b729161f969f8802f3f7a84298
gold_fixture_sha256: 99ba5fc73dfd95d67c8a909cb75325a84ff1bbccc724fa524d7850f306d02968
uv_lock_sha256: 0076359f8f68da82efa5e800d61ef38032fad72742340f51b78b6d8e969ff1b6
production_component_hashes: 23
```

The final harness checkpoint is intentionally not embedded here because a
commit cannot contain its own SHA. The implementation handoff supplies the
exact candidate commit and parent.

## Provider-Free Validation

The focused D4A suite uses only deterministic backends and reports:

```text
tests/test_nlp_d4_live_acceptance.py: 65 passed, 1 skipped
provider calls: 0; real endpoint identity calls: 0; model calls: 0
```

The D0-D4 delivery regression reports `120 passed, 2 skipped`. The full
repository suite reports `2625 passed, 36 failed, 12 skipped, 11 subtests`;
the 36 failures reproduce the established repository baseline and none is
attributable to the three authorized D4A files. Ruff, formatting, Python
compilation, and `git diff --check` pass.

The provider-free campaign rehearsal also passes all nine frozen turns in the
required order. It writes the real campaign state and journal, records 16
logical generation calls through the shared `CountingBackend` and durable
custody boundary, invokes the real LAS verifier for every positive LAS turn and
the real CBL verifier for the accepted deterministic CBL artifact, preserves the
redaction boundary, and derives
`WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_PASSED`. The rehearsal uses deterministic
backends and therefore performs zero external provider activity; this is not
used as a claim about endpoint or remote-model instrumentation in a future live
campaign. No evaluator gold is sent to a provider prompt.

The provider-free preflight requires an external authorization record before
execution. That record supplies the accepted implementation checkpoint,
design authority, harness-source SHA-256, fixture/gold/lockfile hashes,
production-component manifest, source hashes, provider/model, fixed endpoint
URLs, expected endpoint identity projection, and SDK retry settings. Preflight
compares every value before campaign state, credentials, or endpoint access.
It records endpoint identity as not observed; it does not probe the real
server.

After `STARTED`, runtime construction is inside the protected custody boundary:

```text
STARTED
→ load OPENAI_COMPAT_API_KEY
→ persist identity request #1, then GET /v1/models
→ persist identity request #2, then GET /props
→ validate sanitized identity
→ persist endpoint_identity_verified
→ construct production OpenAICompatibleBackendV2
→ bind logical-call custody
→ run the nine turns
```

Every catchable post-`STARTED` exception produces durable terminal state with
decision `WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_INCONCLUSIVE` and one allowlisted
reason code such as `credential_unavailable`,
`endpoint_identity_mismatch`, `provider_construction_failed`,
`provider_execution_failed`, `call_cap_exceeded`, or
`evidence_integrity_failure`. Exception text and tracebacks are not persisted.
If terminal journal append fails, the state file remains terminal with
`evidence_integrity_failure` as the decision-bearing reason.

The grader contract is explicit per turn. CBL requires `CBL-01` through
`CBL-09`; positive LAS turns declare required before/after assertions, allowed
change paths, and verifier requirements; safe-failure turns require byte and
canonical-state identity, actionable diagnostics, no intent/persistence/render,
and no source/channel substitution. The unchanged CBL/LAS verifiers are used
when canonical artifact paths are supplied, and their input bytes are checked
for non-mutation.

## REWORK-005/006 taxonomy, evidence, and call-custody corrections

The final outcome taxonomy is derived only after the deterministic grader has
inspected the observed artifact. A persisted and rendered artifact that fails
its scientific contract is therefore `UNDETECTED_INCORRECT_OUTPUT`, while an
unexpected mutation is `UNINTENDED_MUTATION`. A non-persisted unsafe proposal
is `DETECTED_INCORRECT_OUTPUT` unless the observed diagnostics establish the
case-specific `SAFE_ACTIONABLE_FAILURE`; correct graded artifacts remain
`DIRECT_CORRECT` or `CORRECT_AFTER_CLARIFICATION`.

Safe-actionable classification uses observed diagnostic codes and bounded
diagnostic messages only. It does not use scientist request wording. The
accepted anchors are `enrichment.section_hint_ambiguous`,
`enrichment.source_missing`, and the exact `program.dry_run_error` evidence
for missing `RT` through `channel_missing`.

The live CBL branch records the scaffold as the starting artifact and the
generated CBL logfile as the ending artifact, so both artifact hashes are
concrete. Canonical journal rows retain only stable diagnostic fields; free-
form diagnostic messages remain transient and are not persisted.

These are local implementation-validation results, not independent CI
evidence. No real endpoint, provider, or model calls occurred during this
implementation.

Static checks required for this slice are `ruff check`, `ruff format --check`,
Python compilation, and `git diff --check`. No production source under
`src/wellplot` is authorized to change. Any full-suite failure must be
classified as D4A-attributable, known baseline reproduction, or unclassified;
unrelated failures must not be repaired under this authorization.

## Governance Boundary

This artifact stops at independent D4A review. D4B live execution remains
unauthorized, and the canonical state/journal paths must remain absent until a
separate live authorization permits a campaign.
