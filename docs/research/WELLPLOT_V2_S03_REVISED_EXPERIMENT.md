# S03 Revised Planner Experiment

Preparation and mock qualification only. The accepted design is
[`eb0daf80`](../architecture/WELLPLOT_V2_CONVERSATIONAL_REFINEMENT.md).
H1a (9/10) and the consumed negative H1b condition (6/8) are unchanged.
P01–P08 are exposed evidence and were not rerun. The response-role experiment,
H2 and the full conversational runtime are out of scope.

## Exact package

- [Planner manual and response DTO](../../src/wellplot/agent/code_mode/planner.py):
  `_S03_SYSTEM_PROMPT` (3,432 UTF-8 bytes, no trailing newline) and
  `_S03ObservationResponse.model_json_schema()`.
- [Ordered six-case input panel](WELLPLOT_V2_S03_REVISED_PANEL.json):
  exact requests, synthetic metadata and canonical model inputs, ordered dialogue
  and host-verified state. The planner renders the full validated document,
  including defaults, without truncation. Source IDs match the document's source
  references; these are synthetic labels, not files opened by the campaign.
- Prompt SHA-256: `807797c9e776c47cd980e7423686c0bec5e4b8dd194a50b8b2d9c4e9218fadca`.
- Panel SHA-256: `890951d0f56d7464e88385131cd89537fb0175fbe17fe547a694c4ff83f0ba17`.
- Advertised schema SHA-256: `8fe2dffed215069f2ec28672c218db45b405efa059b3c5aacf2356b515d582c0`
  (sorted compact JSON). Authority binds all three, ordered R01–R06 and the six
  attempts. Planner additionally checks each complete case digest and recompiles
  the exact request. R03 is `EXTRACTION_COMPLETE`; the remaining five are
  `NO_SUPPORTED_SEMANTICS`. All six have empty diagnostic and compiler-dependency
  lists and are outside C2. No new compilation exception.

The response reuses H1b task/reference checks, adds a required
`informational|authoring` intent discriminator and permits only requested
intent or clarification, not feasibility certification. Questions and edits
are objectives, not tool calls. The only selection path is the existing
non-executable H1 observation branch, which stops on the first response even
without a capture callback. Existing application planner wire, H1a/H1b prompts,
workers, compiler, resolver and authoring paths are unchanged.

## Rubric (not sent to the model)

| Case | Complete scientifically correct interpretation |
| --- | --- |
| R01 | Section Deep, informational only: ask for the displayed RT scale unit (`ohm*ft`), not the source physical unit (`ohm*m`). An accurate delegated lookup is enough; if stating the unit, it must be the display unit. No conversion or plot change. |
| R02 | Exact report title `Morning Review` and a separate informational objective about SP in Pass B, not Pass A. No dependency. If the plan mentions availability, SP is absent in the complete Pass B inventory; the inquiry is still retained. |
| R03 | Pilot RHOB green only; separate independent Repeat NPHI/GR co-location; protect other styles and sections. Equivalent grounded scientific labels are acceptable. |
| R04 | East PA/PB on one track and shade between them only after co-location. Explicit required dependency; no fill direction, calibration or implementation prerequisite invented. |
| R05 | Replace the source of literal DT in Sonic with Repeat, not an additional curve or global source change. Retain 1200–1250 m and the report title. The second source is established by ordered dialogue and Base is the currently published source. |
| R06 | Preserve exact report remark and SP presentation; retain literal XCAL from Run West as an objective to investigate or discuss despite inspected absence. No CALI substitution, fabricated availability or executable authority claim. Independent report work must not be dropped. |

Grade typed validity and scientific outcome separately; compare complete meaning,
not output wording or task order. Progression requires at least 5/6 complete usable
interpretations and no consequential wrong worker/scope, lost scientific dependency,
substitution, destructive addition or unsafe handling of ambiguity/preservation.
An incomplete panel cannot progress. Host rejections and infrastructure fault are
not model failures. This is a combined responsibility/context intervention, not
an isolated causal comparison or a production qualification.

## Context sizing

Metadata-only `LogfileSourceLoader.load` and `load_authoring_document` on the local
qualification examples. Sizes are UTF-8 bytes of each compact, sorted JSON block
without its heading. Metadata rows use the existing channel DTO including unit,
kind, addressability, frame indexes and shape where present. Depth coverage and
inspection completeness cannot be inferred merely from a channel list. This is
an offline size sample, not proposed redistribution or model exposure of real assets.

| Block | Open-hole LAS / Notebook-003 | CBL_Repeat.dlis / A09 attempt 007 |
| --- | ---: | ---: |
| Inspected inventory (20 / 79 channels) | 5,168 | 27,257 |
| Full canonical plot JSON | 12,332 | 17,617 |
| Representative three-message transcript | 191 | 224 |
| Workflow state sample | 75 | 75 |
| System manual | 3,432 | 3,432 |
| Compact response schema | 1,110 | 1,110 |
| Subtotal before headings, current request and chat wrapper | 22,308 | 49,715 |

No compatible local Qwen tokenizer/chat template was available for an exact
count. The byte totals are not token estimates. Before any live authority,
qualify the exact rendered six payloads with the matching tokenizer and chat
template, include structured-output overhead, and require input at or below
60,000 tokens in the qualified 65,536-token window (4,096 output reserve and
1,440 tokens of margin). If counting remains unavailable, do not propose live
authority. No truncation, summarization, endpoint costing or prompt optimization
was used.

## Provider-free qualification

383 focused tests passed:

```sh
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_nlp_d5_live_semantic_qualification.py tests/test_code_mode_planner.py \
  tests/test_code_mode_workflow.py tests/test_d5_5j_obligations.py \
  tests/test_d5_single_engine_convergence.py -k 'not (final_population or c02)'
```

The canonical mock HTTP campaign captured all six cases in order and checked
actual prompt blocks, advertised schema, typed results, raw I/O, custody and
zero native corrections. It also exercised an invalid first response and a
separate interrupted run, and verified that capture never entered wire-to-plan
conversion. Direct tests reject altered custody and stop even without a capture
callback. The three synthetic demonstrations passed JSON Schema and typed
validation. Targeted Ruff, formatting, compilation, shell syntax, diff checks,
single-engine attestation and reachability passed.

## Remaining readiness

Existing launcher preflight for `s03-revised-development` is provider-free.
Future measured execution requires independent review of this package, exact
checkpoint static preflight, compatible context budget verification, approved LAN
readiness, separately authorized and independently accepted non-panel operational
smoke using the canonical boundary, and separate measured authority. The smoke
adaptation, if needed, is not part of this slice. No replay or replacement after
an interruption. S03/S03.3 stay in progress; H2 stays blocked.
