# WellPlot V2 — Reasoning-Mode Diagnostic Preparation

**Status:** Provider-free implementation, mock qualification, and approved
non-generative LAN readiness are complete; operational smokes remain separately
unauthorized.
**Implementation checkpoint:** `f6e8331167bf9fa8e434c4aff719ae250dd9804d`.
**Superseded preparation checkpoint:**
`9898823e3d367e73061f7668e883e053f63f93b4` (retained in Git history).
**Active objective:** Prepare a finite six-pair, twelve-generation diagnostic
of the existing planner and section-specialist observation contracts, changing
only `chat_template_kwargs.enable_thinking`.
**DRIFT_CHECK: PASS** — no production routing, prompt, schema, action, or host
lifecycle change is included. S06 remains open; integrated H2/S04 and S05
remain blocked.

## Decision Context and Scope

The accepted early S06 consolidation at
`48e08885de80245a06a11b60cde22ce5d70d65eb` retained the canonical engine,
accepted the isolated role evidence as component evidence only, and proposed a
paired reasoning-mode diagnostic without authorizing generation. This package
implements that narrow preparation in the existing D4/D5 observation path.

The diagnostic asks whether the documented Qwen reasoning-mode setting changes
first-response quality, failure type, token use, or latency on three fresh
planner and three fresh section-specialist cases. It does not test a new prompt
or schema, repair S03's negative progression result, establish integrated
workflow competence, or authorize production activation.

Evidence classification:

- **ADAPTED:** D4/D5's existing first-response accounting, canonical provider,
  mock HTTP transport, role ledger, smoke boundary, and sealed custody are
  reused for this mixed-role comparison.
- **EMPIRICALLY_SUPPORTED:** the frozen pair definitions and accepted failure
  classes are motivated by WellPlot's S03 and isolated-specialist evidence;
  those prior observations do not predict the result of this comparison.
- **ESTABLISHED, limited to documented control semantics:** Qwen documents
  `enable_thinking` as a chat-template control and shows separate decoding of
  thinking and final content. This does not establish behavior of this
  deployed Qwen/llama.cpp build.
- **UNVERIFIED:** deployed runtime handling of the toggle with these structured
  schemas, separation of reasoning from final structured content, effective
  reasoning-budget defaults, and generation usage accounting. These require
  generation and are intentionally not inferred from readiness/tokenization.

Official references consulted:

- [Qwen3.6-35B-A3B model card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)
  is the model-specific reference for the selected Qwen family/model. Its
  presence does not establish how the deployed llama.cpp build accounts for
  reasoning tokens or combines thinking with either structured schema.
- [Qwen3 official quickstart](https://github.com/QwenLM/Qwen3/blob/main/docs/source/getting_started/quickstart.md)
  documents `enable_thinking` and separates thinking and final text in its
  example. It is general Qwen documentation, not proof for this exact local
  build/model combination.
- [llama.cpp b12340 server README](https://github.com/ggml-org/llama.cpp/blob/8954f194837d2ec4d5f67f20c81b84abe63883ba/tools/server/README.md)
  documents `max_tokens` as the maximum generation count and a separate
  reasoning-block budget (`--reasoning-budget`, default `-1`, unrestricted).
  Its release tag is `b12340`, but that tag resolves to commit
  `8954f194837d2ec4d5f67f20c81b84abe63883ba`, whereas the running server reports
  `b12340-b8645ddda`. The suffix could not be resolved to that release commit;
  therefore this is version-label-matched documentation, **not proof of the
  exact running binary's implementation or configured reasoning-budget value**.
- The b12340-tagged
  [`server-task.cpp`](https://github.com/ggml-org/llama.cpp/blob/8954f194837d2ec4d5f67f20c81b84abe63883ba/tools/server/server-task.cpp)
  emits `completion_tokens` from `n_decoded`, with no separate reasoning-token
  detail field in the usage object. The tagged
  [`reasoning-budget.cpp`](https://github.com/ggml-org/llama.cpp/blob/8954f194837d2ec4d5f67f20c81b84abe63883ba/common/reasoning-budget.cpp)
  counts tokens inside the reasoning block for its distinct reasoning budget.
  Because the server's reported source suffix does not match the release-tag
  commit and no generation was permitted, neither behavior is asserted for the
  exact deployed binary or its runtime response accounting.

## Frozen Experimental Package

Panel file:
`docs/research/WELLPLOT_V2_REASONING_MODE_PANEL.json`

| Identity | SHA-256 |
| --- | --- |
| Panel file | `bbad629ff86201d924a04869acfe5dc87325eda3fe6bd2bbc634ce19fd5a8e1c` |
| Ordered rendered input pairs | `685ffac5090c90ceaeb421f84c7a78cb8516003fc7a8a141f07ad4f01e2262d0` |
| Planner prompt (accepted S03) | `807797c9e776c47cd980e7423686c0bec5e4b8dd194a50b8b2d9c4e9218fadca` |
| Section manual (accepted specialist) | `f2522ae3d1191eb6db265af04c230e93d7f71a03b3194027e334d69a724088e0` |
| Prompt bundle authority | `09f06538949bbb077472f2b5c05756923dcb65f0a3f2b5d917657857215a8330` |
| Planner schema | `8fe2dffed215069f2ec28672c218db45b405efa059b3c5aacf2356b515d582c0` |
| Section schema | `ac2928f97643f08becb002a5229a950ecbfa6adae62140bb40d39c5ae1e401a1` |
| Schema bundle authority | `0790c3dc9ae06ed1a6964240e38593e8e63d6ed1acdf2906e5bb80b9368db6d6` |
| Independent scientific rubric | `a1ae9a052addd6ac09fb89046a42ea42a05ea540fbeccecbbfbd4605ecbd21a0` |

The panel fixtures were corrected before any measured response. The earlier
P1 accidentally repeated the R03 source-ambiguity class, so it could not test
the intended independent-outcome preservation failure. The replacement uses
fresh Facies Survey content and separately requests physical GR in Gamma and
physical DEN in Density, without requesting a relationship. S1's previous
assigned objective explicitly stated the expected ambiguity response; the
neutral objective now leaves that decision to the specialist while retaining
both inspected, eligible SAL inventories. S2 previously described an existing
LOWER binding while omitting LOWER from inspected source provenance; the
corrected inventory consistently exposes both UPPER and LOWER. The prior
preparation checkpoint remains in Git history; no measured observation is
superseded or rewritten.

The panel is six exact input pairs, each sent once in both conditions:

| Pair | Role | Failure class under test | Order |
| --- | --- | --- | --- |
| P1 | Planner | Preserve independent GR-in-Gamma and DEN-in-Density outcomes; do not invent a relationship | off, on |
| P2 | Planner | Preserve same-track GR/RHOB and blue between-curves relationship | on, off |
| P3 | Planner | Preserve literal CALX, Northern Survey, linear 5–25 in, unchanged title | off, on |
| S1 | Section | Neutral SAL assignment with two eligible inspected sources; assess safe source handling | on, off |
| S2 | Section | Select UPPER prerequisite and retain dependent blue between-curves shading; both source channels are inspected | off, on |
| S3 | Section | Preserve explicit East Survey FLOW, Hydraulics scope, PRES and presentation | on, off |

Counterbalancing is frozen per pair. The serialized request, context, role
manual, typed response schema, temperature, output cap and other sampling
controls remain identical within a pair. The only cell-level request change is
the boolean `chat_template_kwargs.enable_thinking`. Temperature is zero;
maximum output is 4,096 tokens per cell. One first response, zero retries and
zero corrections. Maximum: 12 logical generations and 12 physical attempts.
There are no selective reruns or replacements.

The separate human grading instrument is
[`WELLPLOT_V2_REASONING_MODE_RUBRIC.md`](WELLPLOT_V2_REASONING_MODE_RUBRIC.md),
SHA-256 recorded in the proposed authority. It is not included in model-facing
context and does not establish host execution outcomes.

## Canonical D4/D5 Adaptation

The bounded corrective at
`f6e8331167bf9fa8e434c4aff719ae250dd9804d` uses the existing
`reasoning-mode-development` population in `D5CampaignRunner`, `planner_only`
observation, `SemanticPlanner.plan`, canonical provider construction, D4
`CountingBackend`, D5 logical/physical accounting, raw HTTP model-I/O custody,
stage tracing, and terminal verification. Per-turn role attribution remains
pinned to the frozen panel.
The active role is selected through D4's existing observation role flag; no
new provider, runner, semantic engine, scorer, compiler, or execution path is
introduced.

Planner cases use the already accepted exact-case capture-only boundary so
the original compiler outcomes are preserved and first responses stop at the
planner observation DTO. The smoke cases are separate non-panel fixtures,
both with `NO_SUPPORTED_SEMANTICS`; they cannot load the measured panel and
never proceed to executable plan conversion. This is observation containment,
not a production admission change. Normal request admission, C2 fail-closed
guards, workers, lowering, mutation, persistence, and publication remain
unchanged.

Provider-free mock qualification proves:

- all 12 frozen cells run through the canonical D5 runner and real provider
  serialization boundary under mock HTTP;
- each pair's full JSON request body is byte-semantically equal after removing
  only `chat_template_kwargs`, and the remaining flag is exactly its assigned
  condition;
- role-specific response schema selection and role accounting are correct;
- the panel has one request per cell, no retries/corrections, and first
  structural failures remain recorded;
- raw response bodies retain mock `reasoning_content`, final structured
  content, finish reason, and `usage`, while validated response DTOs contain
  only final structured content;
- custody and terminal digests verify; cross-role generation is rejected;
- each smoke role makes one mock request, valid and invalid first responses
  terminate, and smoke custody verifies with no measured-population load or
  downstream worker/mutation/publication calls;
- the reasoning population's normal and interrupted campaign paths run through
  `execute_live_campaign`, and both paths close every created HTTP client;
- the two reasoning smoke modes bind logical and physical limits of one in the
  existing D5 custody ledger and seal those limits in state and terminal
  records; and
- static preflight binds the independent rubric SHA-256, following the existing
  response-agent precedent.

The scoped `tests/test_nlp_d5_live_semantic_qualification.py` qualification
passes 183 tests, including corrected-fixture parity, complete and interrupted
campaign cleanup, request-body identity, and the smoke custody ceilings. The
production manifest changes only the attested `planner.py` source digest for
the exact frozen planner-case allowlist. This package adds no prompt, response
schema, production routing, or lifecycle semantics.

The mock demonstrates how WellPlot's current adapter handles a synthetic
response with separate reasoning and final-content fields. It does **not**
demonstrate that the deployed llama.cpp build emits those fields in this
contract, supports structured output while thinking is enabled, or counts
reasoning tokens inside/outside the `max_tokens=4096` budget.

## Exact Mock Request Identities

These SHA-256 values are over the exact `request.content` bytes captured at
the mock HTTP boundary. They are not token counts and do not substitute for
the runtime's `/apply-template` and `/tokenize` operations.

| Cell | SDK body SHA-256 |
| --- | --- |
| P1-OFF | `fbaa832ab30982ae9c9dd05ac2094009d4fcaa066e9e5483a9ba76b7d033fd4b8` |
| P1-ON | `c48d9ea1f3cd9df03aa413b49dfccc6d1f6ad66cd1ee85a8bf21d6b27a8dc471` |
| P2-ON | `4b90838916610c27a59a3ccf69991d3c8af1ce2f46cca349ebbb9ed226f46b16` |
| P2-OFF | `3b0f730778f7c894ae7c6bf739253a14a9fb652bbb3d0b33ac6eec3513500d70` |
| P3-OFF | `8b9d4c35208930a8fc84390436ee859238220e045f806dcd4be0de40b3e77e7c` |
| P3-ON | `06af06d8016c0b49b6cb2680a8d4d8da1281eaeac548d9457a8dd93be398a6d7` |
| S1-ON | `9a1fb32f7278ec43d9c9d96565bd0c9a573566cce565228ba03006faf02119fb` |
| S1-OFF | `cd44e57faf863caba89b8a4cd978722097067ece06b41ddc046ca8c599d35f74` |
| S2-OFF | `c1340ab7f6bcf72e55d5b741918adc70638de771fdfd528dfac0ee6156c97907` |
| S2-ON | `cdbb07185344a7fa83a83835e2489127b5edc814c61cb758028156c8c25a1664` |
| S3-ON | `cadbcb64e6d7e2665c3419ee3ca721c4acc14326382126012527cd0ba74029a4` |
| S3-OFF | `715ba36d7bceeabf9f1440d72c7a32045e32201b821fbac6ac5f040b0794ba2d` |

## Operational Smokes — Proposed Only

The non-panel fixtures are in
`docs/research/WELLPLOT_V2_REASONING_MODE_SMOKES.json` (file SHA-256
`7a24d26142c24409e3c37c7a741edad4b0c881801933b043b54776dc9a69dde3`).
Each is a synthetic informational/low-risk observation with
`NO_SUPPORTED_SEMANTICS`; planner and section capture terminate before
conversion or downstream work.

| Smoke | Role contract | Fixture object SHA-256 | Rendered input SHA-256 | Mock SDK body SHA-256 | Schema SHA-256 |
| --- | --- | --- | --- | --- | --- |
| RM-PLANNER-SMOKE | S03 planner observation DTO | `caf954398686fedf4e19998000f6ac5ba0edd77ff08ee80aea4a2cbc58212b94` | `0f2e3b140782d13821bc944cfeeebfb7b1621ab8775eefcdfbb3cb6cc2e935f2` | `c3d9f5971d9255e148ade98ab81ef79794ec5348dbee08433430ceedf76ac5a7` | `8fe2dffed215069f2ec28672c218db45b405efa059b3c5aacf2356b515d582c0` |
| RM-SECTION-SMOKE | Section specialist observation DTO | `619dec251e12166648e3fe1041a91a96e82159634228b163895ed22baf56fcb6` | `bb776a47caf9a4477b5bf4b63ac55b26ba74ac9b149ca434fb089e592d453368` | `a9af08eee7db575275854bccf0a76e1939afb6d60c1837c9268c7eb69a8c346c` | `ac2928f97643f08becb002a5229a950ecbfa6adae62140bb40d39c5ae1e401a1` |

The human-readable proposal descriptors are in
`docs/research/WELLPLOT_V2_REASONING_MODE_SMOKE_AUTHORITY_PROPOSALS.json`.
They are deliberately not D5-consumable authorization documents. They record
`PROPOSED_NOT_AUTHORIZED`, have no executable authority status, and must never
be passed to the launcher. Each separately proposed smoke allows one logical
and physical generation, zero retries/corrections, 4,096 output tokens, and
thinking enabled. Each requires its own Human Authority and fresh namespace.

## Non-Generative LAN Readiness and Tokenization

**Status: PASS, 2026-11-28.** Using the canonical checkout and D4 credential
loading, the approved run made only `GET /v1/models`, `GET /props`, 28
`POST /apply-template`, and 14 `POST /tokenize` calls. Every call returned
HTTP 200. No completion, chat-completion, generation, or provider-generation
call occurred. Credentials were neither recorded nor printed.

Readiness evidence:

- Exact execution HEAD: `9f1aeb9648ffe60991336c84cd4a1a4111713f5c`.
- Sanitized runtime identity SHA-256:
  `84416cbce1b861cc978f24df56385f2ab09bb112deb4ed321a4368ccee8a4045`.
- Runtime: `qwen3.6-35b-a3b`; model path basename
  `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`; model-path fingerprint
  `3a6fd986bebd4047876869e8b079f9f9b7b15fb2429853ba0501b5f6ea480b21`;
  context `65,536`; build `b12340-b8645ddda`; one slot; structured-output
  contract `json_schema`.
- Chat-template SHA-256:
  `55d4931433fe502b794226ee7f4d206a6bdd436ac9f80eb7d8ebb4c639f9ea0c`.
- Runtime-defaults SHA-256:
  `5136c0f2b22a73572fe88f44e8cf32159ffb3b345ced2e33ba7507d612f7f8c3`.
- GGUF byte identity was unavailable. The model-path fingerprint is not a
  substitute for a byte-level GGUF digest.
- Project configuration fingerprint:
  `14357a627f060572e73a822ab9efe9ed3a6cca6727b7247361a2a5adfa5bd498`.

All 14 exact captured SDK request-body SHA-256 identities matched their
preflight captures. For every request, schema-present and schema-omitted
`/apply-template` outputs were byte-identical, so measured schema-related
prompt overhead was zero tokens. All six enabled/disabled paired rendered
prompts differed; disabled rendering ended with `<think>\n\n</think>\n\n`,
enabled rendering ended with `<think>\n`. This verifies the template
transformation, not structured-output compatibility while thinking is enabled.

| Cell | Exact input tokens |
| --- | ---: |
| P1-OFF | 1,742 |
| P1-ON | 1,740 |
| P2-ON | 1,427 |
| P2-OFF | 1,429 |
| P3-OFF | 1,430 |
| P3-ON | 1,428 |
| S1-ON | 1,875 |
| S1-OFF | 1,877 |
| S2-OFF | 2,109 |
| S2-ON | 2,107 |
| S3-ON | 2,120 |
| S3-OFF | 2,122 |
| RM-PLANNER-SMOKE (thinking enabled) | 1,385 |
| RM-SECTION-SMOKE (thinking enabled) | 1,796 |

The largest input is 2,122 tokens. Adding the reserved 4,096 output tokens and
1,440 margin gives 7,658 of 65,536 context tokens; all requests are below the
60,000 input-token ceiling without truncation.

The version-label-matched b12340 source documents a distinct optional
reasoning-block budget and a completion-wide `max_tokens` ceiling; the tagged
usage implementation reports aggregate `completion_tokens` based on decoded
tokens without a separate reasoning-token detail field. The running build
suffix does not match the release tag's commit, and runtime defaults do not
reveal an effective reasoning-budget setting. Consequently the deployed
reasoning-budget value and actual usage accounting are **UNVERIFIED**. No
generation was made to resolve them. The enabled-mode operational smokes are
still needed to qualify structured-output compatibility and actual reasoning
separation; they are not authorized by this readiness record.

The private machine evidence is
`workspace/evaluations/wellplot-v2-reasoning-mode-readiness-20261128-001/reasoning-mode-readiness-tokenization.json`,
SHA-256 `6646f47594c276be75ddcbdcf7c431e00612d539b47a694cef8e2481e673b335`.
The exact SDK-body capture is
`workspace/evaluations/wellplot-v2-reasoning-mode-readiness-20261128-001/captured-sdk-bodies.json`,
SHA-256 `6e273588b05678a3775b2ea09bf3a1b954b4afcf4b94021dcc23f34f241a7544`.
Both are local, private evidence artifacts; the committed record includes
sanitized identities and counts only.

The canonical provider-free D5 preflight passed at the above HEAD with the
frozen 12 case IDs, rubric digest, harness, schemas, source/configuration
attestations, and exact current worktree allowlist. It reported a 12 logical /
12 physical ceiling and zero provider, model, or endpoint calls. The preflight
must be repeated after this readiness record is committed so the final
unapproved smoke descriptors bind the resulting exact HEAD and worktree.

## Authority and Stop Boundary

No inference, completion endpoint, campaign execution, or measured panel was
run in this preparation. The two proposed smokes are the next separately
authorized operational activities after non-generative LAN readiness and
tokenization. They must run through the canonical D5 launcher, sequentially,
each under fresh authority and namespace, and stop after the first response or
any interruption. Their acceptance is required before a separate 12-call
measured authority. This record does not close S06, unblock H2/S04 or S05, or
authorize production changes.
