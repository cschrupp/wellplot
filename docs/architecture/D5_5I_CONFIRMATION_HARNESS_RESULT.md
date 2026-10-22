# D5-5I Confirmation Harness Result

```yaml
authority: WELLPLOT-D5-5I-CONFIRMATION-HARNESS-ADAPTATION-AUTH-001
fixture_correction_authority: WELLPLOT-D5-5I-CBL02-FIXTURE-CORRECTION-AUTH-001
design: docs/architecture/D5_5I_REPAIRED_BASELINE_LIVE_CONFIRMATION_DESIGN.md
branch: design/d5-5g-inspectable-historical-claim-revalidation
implementation_commit: 4cf78369516bda8dbfb10991f6d7b915c43ebd85
implementation_parent: c0a44b6432b01dffeb614246cfacb1c9deb705c5
accepted_h_implementation_checkpoint: e72e726b7f52c1975d862980543cd3f217ee6aa8
thinking_control_implementation_authority: WELLPLOT-D5-5I-THINKING-OFF-REQUEST-CONTROL-IMPL-AUTH-001
thinking_control_rework_authority: WELLPLOT-D5-5I-THINKING-OFF-REQUEST-CONTROL-IMPL-REWORK-AUTH-001
thinking_control_code_commit: 8fad94761176026a0d60bd19622c06b1c022968a
review_candidate_checkpoint: FINAL_PUBLISHED_HEAD
thinking_control_mechanism: chat_template_kwargs.enable_thinking
thinking_control_value: false
thinking_control_options_sha256: 220b99e47feb82851cab428f86b8fe977ae7c605400d421a91e99d4a35ec9c26
thinking_off_readiness_semantics: STATIC_REQUEST_CONTRACT
historical_d5_identity: PRESERVED_SEPARATELY
changed_files:
  - scripts/nlp_d5_live_semantic_qualification.py
  - tests/test_nlp_d5_live_semantic_qualification.py
  - tests/_d4_canonical_fixtures.py
  - docs/architecture/D5_5I_CONFIRMATION_HARNESS_RESULT.md
provider_model_calls: 0
endpoint_calls: 0
live_execution: NOT_AUTHORIZED
```

## Adaptation

The D5-5I harness adaptation extends the accepted D4/D5 custody path without
adding an engine, provider adapter, planner, worker, compiler, or evaluator.
It records the D5-5I scientific terminal taxonomy and first-divergence value
in turn, journal, state, terminal, and summary evidence. It also exposes the
independent evidence dimensions and bounded correction-preservation evidence
without retaining prompts, headers, credentials, or raw payloads outside the
existing model-I/O custody artifact.

Campaign evidence is identified as `WELLPLOT-NLP-D5-5I` and binds the accepted
H implementation checkpoint above. Historical D5-4 engine/design identifiers
remain compatibility/provenance fields and are not used as the active H
authority.

Logical generation calls remain capped at 45 and physical generation attempts
at 135. A logical call counts one semantic generation invocation by the
planner, report worker, section worker, or an existing authorized correction;
an SDK retry of that same generation does not add a logical call. A physical
attempt counts every generation HTTP attempt, including failed or retried
attempts; with `sdk_max_retries = 2`, one logical call can consume at most
three physical attempts.

The `/v1/models` and `/props` readiness requests are identity endpoint calls
tracked separately from both generation ceilings. A request rejected before
provider delegation consumes neither a physical generation attempt nor an
endpoint call. Once an HTTP generation request is attempted, it consumes one
physical attempt even if transport or provider execution fails. Planner,
report-worker, and section-worker calls remain limited to two per applicable
turn. Logical call 46 and physical attempt 136 are rejected before provider
delegation. No replay or selective rerun is introduced.

## Provider-Free Evidence

The provider-free tests cover:

- all D5-5I first-divergence classes and scientific terminal classifications;
- provider/structured and local-harness failure separation;
- independent evidence dimensions, safe-negative grading, and correction
  preservation projections;
- per-turn role limits, global logical/physical ceilings, and fresh custody;
- existing model-I/O custody and redaction behavior;
- canonical adapter wiring and the existing D4 regression surfaces.

The canonical nine-turn rehearsal now passes with the required local LAS/DLIS
assets provisioned from the canonical checkout. The exact frozen source hashes
were verified before and after provisioning, and the source-dependent suite
completed with:

```yaml
provider-free D5-5I focused suite: 66 passed, 0 skipped
canonical nine-turn rehearsal: 9/9 PASS
CBL requirements: CBL-01..CBL-09 PASS
post-control D5-5I focused file: 64 passed
post-control wire/retry validation: 10 passed
```

The deterministic CBL response fixture preserves the frozen object-level
reconstruction scope required by CBL-02. No source asset was modified,
synthesized, committed, or substituted, and no endpoint or model call was
made.

The historical D5-5G provider-free proof remains an adjacent baseline check,
not a D5-5I claim. Its existing source-delta guard compares the current H
baseline against the earlier D5-5G design checkpoint and therefore reports the
accepted H production changes as a baseline mismatch. The current D5 single-
engine attestation passes; no H source was changed by this adaptation.

## Thinking-Off Request Control

The D5-5I executable now binds the exact request options below at the
OpenAI-compatible adapter boundary:

```json
{"chat_template_kwargs":{"enable_thinking":false}}
```

The canonical JSON SHA-256 is
`220b99e47feb82851cab428f86b8fe977ae7c605400d421a91e99d4a35ec9c26`.
Authorization parsing and static preflight reject missing, malformed, changed,
or caller-overridden control information.
The existing model-I/O observer verifies the serialized
`/chat/completions` body for planner, report-worker, and section-worker
requests, including SDK retries. `/v1/models` and `/props` remain runtime
identity observations; they do not claim to establish thinking mode.

## Scope Boundary

The live Qwen confirmation remains separately unauthorized. The exact frozen
nine-turn population, source/gold custody, accepted H baseline, canonical
composition path, and deterministic graders remain unchanged. This artifact
records provider-free implementation evidence only and does not claim live
scientific acceptance.

```yaml
src_wellplot_changes: 0
thinking_control: FROZEN / PROVIDER_FREE_VERIFIED
historical_campaigns_mutated: false
D5-5G_replay: NOT_AUTHORIZED
D5-5J: NOT_AUTHORIZED
```
