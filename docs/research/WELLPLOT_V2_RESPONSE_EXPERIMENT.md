# Isolated Response-Agent Experiment — Provider-Free Preparation

Status: implementation candidate; independent review required. No live calls
have been made or authorized by this package.

This is a six-case response-agent competence experiment, isolated from S03,
integrated H2, and S05. It does not establish integrated workflow competence
or production response-agent authority. Existing `AuthoringResult` outcome,
coverage, and clarification concepts and the canonical `AuthoringDocumentSpec`
are reused. The existing D4 `CountingBackend` and D5 campaign/custody boundary
carry the observation; no new runner or semantic grader is introduced.

The panel JSON has no grading answers. Its saved-document snapshots are parsed
and reserialized by `AuthoringDocumentSpec`. The rendered model input contains
only the original request, ordered dialogue, saved document, inspected facts,
and verified outcome record. Private candidates appear only as explicitly
identified candidate fields in the verified outcome record, never as saved
state. The independent rubric is in
[`WELLPLOT_V2_RESPONSE_AGENT_RUBRIC.md`](WELLPLOT_V2_RESPONSE_AGENT_RUBRIC.md).

## Frozen identities

| Artifact | SHA-256 |
| --- | --- |
| Six-case panel file | `1b8351647ee6802beb46f9b5bd5992df5b806a588d7e6faaaf2e876205c97e0b` |
| Ordered rendered input pairs | `ccf521c307f82f7f5ce75b7473d2b38f04a52342b79c461f85888053156e3185` |
| Role instructions, exact transmitted UTF-8 bytes | `782a1cf6b463b57211d3231aeb62214b50a681d5e4e69b68e6781c2555d33bcd` |
| Response DTO JSON Schema | `7cfe35615916d50c78f293870b72d72538b8e71b91d54c6ada4dc14a469f74ea` |
| Independent scientific rubric | `8f8c267f2941c26052ac59fec224135febb1e5d745f96f93717c4ed65983079f` |

The DTO is exactly one required `response` string, with additional properties
forbidden and non-empty content enforced by the advertised schema. The
generation role is recorded as `response_agent`, never as planner or worker.

| Case | Original objective and final question | Verified record and context | Required answer |
| --- | --- | --- | --- |
| CR01 | Retitle the report Mesa Review. "Was it saved?" | Published title Mesa Review, previous title Mesa Draft; title verified after reload. | Confirm the title was saved and verified; claim no other edit. |
| CR02 | Change subtitle to Shift 4. "What title and subtitle are saved now?" | Saved title Ridge Report and subtitle Shift 3; private candidate Shift 4 was verified but not published. | Name saved title and subtitle; distinguish unpublished candidate from saved state. |
| CR03 | Save title Core Check and plot physical CALX from Ridge. "Which parts did you finish?" | Title Core Check verified and saved; complete Ridge inventory lacks CALX; no binding added. | Distinguish saved title from blocked curve; state exact reason without substituting. |
| CR04 | Plot physical POR in the Review section. "What do you still need?" | Eligible North and South both contain exact POR; neither selected; verified pending clarification; no edit saved. | Ask which source to use, presenting both; do not choose or claim completion. |
| CR05 | Check whether literal VELX is available in East and West. "Can you confirm it in either?" | East inspected completely: contains VEL but not VELX. West inspection failed; inventory unknown. | Distinguish confirmed East absence from unknown West; do not substitute VEL. |
| CR06 | "What depth units does this report display?" | Published report displays depth in ft; inspected source depth is m; no edit requested or made. | Answer ft, distinguish source units if useful, no conversion or edit claim. |

## Response instructions

The response role communicates authoritative state. Answer the current user
question using the saved document, inspected facts and verified outcome
records. Preserve the distinction between proposed, attempted, privately
verified, saved, blocked and pending work. Never describe a private result
as saved. Do not infer missing scientific facts from an inspection error.
If a consequential choice is pending, ask only the question supported by
the verified record; never resolve it yourself. Do not propose mutations,
tool calls, replacements or execution. Return one object with a non-empty
`response` string and no other properties.

Independent demonstrations:

- A verified candidate renamed Blue Ridge to Quartz, but publication did
  not run: "Quartz was verified in a draft but was not saved. The saved
  title is still Blue Ridge."
- An inspected complete inventory does not list literal RATE7; a second
  source could not be inspected: "RATE7 is absent from the inspected first
  source. I couldn't confirm whether it is present in the second."

## Qualification and decision

Proposed threshold: all six truthful on saved, unsaved or pending status,
zero fabricated facts or execution claims, and at least five complete,
useful replies. Score independently; typed validity alone does not count.
One first response per case, six logical/physical attempts maximum, no
retries or corrections, existing qualified thinking-disabled runtime.

Provider-free qualification is bounded to the six frozen cases and covers
complete mock HTTP capture, one malformed first response, and an interrupted
request. It must prove six maximum logical/physical calls, one first response
per case, zero retries/corrections, truthful role attribution, sealed D5
custody, and no planner, worker, lowering, mutation, or publication execution.
An invalid model response remains an observation and does not trigger a
correction. An infrastructure interruption stops the campaign while retaining
completed observations and exact transport evidence.

The proposed live experiment, if separately authorized after review, uses the
qualified thinking-disabled runtime and the same Qwen model; it permits six
logical and physical attempts maximum, one response per case, zero retries,
and zero corrections. The progression criteria above are assessments, not
claims established by provider-free qualification. S03's negative result,
integrated H2, and S05 remain unchanged and blocked.

Evidence classification: **ADAPTED** — a non-mutating response observation is
adapted to the existing typed D4/D5 call accounting and custody boundary. It
does not add a production role route or a second semantic engine.

## Provider-Free Implementation Qualification

The candidate uses the existing D5 `planner_only` observation stop boundary
and the existing canonical D4 structured backend. The authority binds the
six ordered CR IDs, panel and rendered-input digests, exact manual bytes, DTO
schema, implementation/harness checkpoint, runtime/configuration, zero SDK
retries, 4,096 output-token ceiling, and the existing shared campaign custody.
The campaign ledger permits only the distinct `response_agent` role, at most
one logical call and one physical attempt per case. It rejects planner and
worker roles for this population.

The provider-free HTTP qualification exercised:

- Six valid first responses with exact system/user payloads and response
  schema verification.
- An invalid first response retained as a structural observation; the other
  cases continue, with no correction or retry.
- A transport interruption on case two; case one remains sealed and no later
  case is called.
- D5 custody verification for successful, structurally invalid, and
  interrupted campaigns.
- A guarded production boundary: planner generation, report/section worker
  observation/compilation and `D4CampaignAdapter.execute_turn` are forbidden
  in the test. The response path emits no compilation or wire-conversion
  trace and every row says authoring was not reached.
- Authority rejection for changed prompt/schema, reordered case IDs, and
  nonzero SDK retries; six logical/physical ceilings and role accounting are
  asserted before mock generation.

Focused command:

```sh
PYTHONPATH="$PWD:$PWD/src" .venv/bin/pytest -q \
  tests/test_nlp_d5_live_semantic_qualification.py \
  -k 'response_agent_campaign_uses_canonical_d5_observation_boundary'
```

The complete D5 qualification file reported **169 passed**. Ruff check,
Ruff format check, Python compilation, panel JSON parsing, and
`git diff --check` also passed. All HTTP traffic in this qualification uses
`httpx.MockTransport`; no LAN endpoint, provider, credential, live model, or
measured response-agent campaign was used. These results qualify collection
and custody only; semantic progression remains unmeasured and requires its
own authority after independent review.
