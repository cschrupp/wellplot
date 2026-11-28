# WellPlot V2 — Reasoning-Mode Diagnostic Preparation

**Status:** Provider-free implementation and mock qualification prepared;
non-generative LAN qualification and operational smokes remain pending.
**Implementation checkpoint:** `9898823e3d367e73061f7668e883e053f63f93b4`.
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
  schemas, separation of reasoning from final structured content, and the
  runtime's accounting of reasoning tokens against the 4,096 output cap.

Official references consulted:

- [Qwen3 official quickstart](https://github.com/QwenLM/Qwen3/blob/main/docs/source/getting_started/quickstart.md)
  documents `enable_thinking` and separates thinking and final text in its
  example. It is general Qwen documentation, not proof for this exact local
  build/model combination.
- [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
  documents request `chat_template_kwargs`, reasoning formats, and optional
  reasoning budgets. The current upstream page is not version-matched evidence
  for the deployed runtime; the exact runtime must be verified non-generatively
  and by separately authorized operational smokes.

## Frozen Experimental Package

Panel file:
`docs/research/WELLPLOT_V2_REASONING_MODE_PANEL.json`

| Identity | SHA-256 |
| --- | --- |
| Panel file | `b8293d3c2a7978c9fa566dc46c82ca98f52a9e07cb23983f3138e0f7eae59ac1` |
| Ordered rendered input pairs | `46a427e1454140dcc624513ada6f40f3870f915e9ff38affec5b7cf13623d550` |
| Planner prompt (accepted S03) | `807797c9e776c47cd980e7423686c0bec5e4b8dd194a50b8b2d9c4e9218fadca` |
| Section manual (accepted specialist) | `f2522ae3d1191eb6db265af04c230e93d7f71a03b3194027e334d69a724088e0` |
| Prompt bundle authority | `09f06538949bbb077472f2b5c05756923dcb65f0a3f2b5d917657857215a8330` |
| Planner schema | `8fe2dffed215069f2ec28672c218db45b405efa059b3c5aacf2356b515d582c0` |
| Section schema | `ac2928f97643f08becb002a5229a950ecbfa6adae62140bb40d39c5ae1e401a1` |
| Schema bundle authority | `0790c3dc9ae06ed1a6964240e38593e8e63d6ed1acdf2906e5bb80b9368db6d6` |

The panel is six exact input pairs, each sent once in both conditions:

| Pair | Role | Failure class under test | Order |
| --- | --- | --- | --- |
| P1 | Planner | Ambiguous source identity; clarify rather than choose SAL dataset | off, on |
| P2 | Planner | Preserve same-track GR/RHOB and blue between-curves relationship | on, off |
| P3 | Planner | Preserve literal CALX, Northern Survey, linear 5–25 in, unchanged title | off, on |
| S1 | Section | Ambiguous eligible SAL sources; no unsupported source selection | on, off |
| S2 | Section | Select UPPER prerequisite and retain dependent blue between-curves shading; no premature fill | off, on |
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

The change uses the existing `reasoning-mode-development` population in
`D5CampaignRunner`, `planner_only` observation, `SemanticPlanner.plan`,
canonical provider construction, D4 `CountingBackend`, D5 logical/physical
accounting, raw HTTP model-I/O custody, stage tracing, and terminal
verification. Per-turn role attribution remains pinned to the frozen panel.
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
  downstream worker/mutation/publication calls.

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
| P1-OFF | `29c961910718481dc82b55baefd21e8983975a8b6c96eef08233ad207b6fd733` |
| P1-ON | `c698d47e9779e816537944b50c6da739738160f67ebd2757cf6d031b60f66a92` |
| P2-ON | `4b90838916610c27a59a3ccf69991d3c8af1ce2f46cca349ebbb9ed226f46b16` |
| P2-OFF | `3b0f730778f7c894ae7c6bf739253a14a9fb652bbb3d0b33ac6eec3513500d70` |
| P3-OFF | `8b9d4c35208930a8fc84390436ee859238220e045f806dcd4be0de40b3e77e7c` |
| P3-ON | `06af06d8016c0b49b6cb2680a8d4d8da1281eaeac548d9457a8dd93be398a6d7` |
| S1-ON | `b3c1bf24af7b8e9b2d63cb6fea7995572c263b1e8a3ed97a788808e0bc624f86` |
| S1-OFF | `1f6ee45993d4ad31c6a0d3cc0236b69bc58eba1dc44d5aa69e2c1a35a70539b8` |
| S2-OFF | `748696c3d9524c04b6a3b65bc68e43aa91f59305861144fbf0ed28d8bdf892e2` |
| S2-ON | `2cc99193bd86a4ef295d5c69b675f8d27c9741c2a461a36bac73c2750afadb4b` |
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

**Status: NOT PERFORMED.** This environment did not provide an approved
escalation mechanism for the configured LAN endpoint. No `/v1/models`,
`/props`, `/apply-template`, or `/tokenize` request was sent. No credentials
were loaded or exposed. Do not infer runtime identity, template identity,
thinking suffix, schema overhead, input token counts, structured-output
compatibility, or reasoning-token budget semantics from local/mock evidence.

Before the smoke proposals can be converted into executable authorities, the
existing approved non-generative procedure must verify current runtime
identity, apply the exact captured SDK request bodies to the matching chat
template, tokenize every panel and smoke body, and report schema-related
overhead and the 60,000-input/4,096-output/1,440-margin budget. The operational
smokes then test enabled reasoning with the actual planner and section
contracts. Only those real smokes can establish operational compatibility;
they are not scientific panel observations.

Reasoning-token accounting remains explicitly open. Preserve provider-reported
usage fields verbatim in raw custody. Report reasoning-token usage separately
only if the deployed runtime exposes it. Do not add hidden/visible token
estimates or claim the relation between reasoning tokens and the output cap
until the runtime's behavior is observed/documented for its exact build.

## Authority and Stop Boundary

No inference, completion endpoint, campaign execution, or measured panel was
run in this preparation. The two proposed smokes are the next separately
authorized operational activities after non-generative LAN readiness and
tokenization. They must run through the canonical D5 launcher, sequentially,
each under fresh authority and namespace, and stop after the first response or
any interruption. Their acceptance is required before a separate 12-call
measured authority. This record does not close S06, unblock H2/S04 or S05, or
authorize production changes.
