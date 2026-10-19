# DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01 — Authorization

```
AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01-AUTH-001

SLICE:
DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01

MODE:
BOUNDED ENGINE BAKEOFF

STARTING TIP:
d34c904f82ad35ed30ed723661a87d95fc908acc

PARENT:
DECOMPOSER-PILOT-CONSTRAINT-CFG-GENERATOR-01R
HUMAN ACCEPTED / CLOSED

ACCEPTED GRAMMAR SHA256:
f8cfd0c2b8a2cb2c708e464147080ebd7400e40e8060fa0426e423d70396d9d3

MODEL CALLS:
0

PILOT-01:
NOT AUTHORIZED
```

## Objective

Compare hard-constraint engines against the **same immutable accepted WELL-EBNF-1
artifact** and the **same pinned Qwen3-1.7B tokenizer**, without loading model
weights or generating.

The slice answers one question:

> Can a hard-constraint backend consume an exact deterministic lowering of the
> accepted grammar and produce correct token masks for the pinned tokenizer?

It does **not** test Qwen decomposition capability.

## Backends in scope

1. **XGrammar** — native EBNF / grammar mode only.
   - The previously rejected JSON-Schema route remains forbidden.
2. **llguidance** — deterministic WELL-EBNF-1 → Lark-style grammar lowering.

Do not add a third backend unless SOL separately authorizes it after a genuine
technical blocker.

## Authoritative inputs

Accepted grammar:

`experiments/nlp_gate_modernbert/evidence/decomposer_pilot_constraint_cfg_generator_01.well_ebnf1`

SHA-256:

`f8cfd0c2b8a2cb2c708e464147080ebd7400e40e8060fa0426e423d70396d9d3`

Tokenizer identity:

- model id: `Qwen/Qwen3-1.7B`
- source: **existing local ModelScope snapshot only**
- `tokenizer.json` SHA-256:
  `aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4`
- `tokenizer_config.json` SHA-256:
  `d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101`
- `merges.txt` SHA-256:
  `8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5`
- `vocab.json` SHA-256:
  `ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910`

No tokenizer or model autodownload.

If the pinned local tokenizer is absent or any required hash mismatches:

```
STOP: PINNED_TOKENIZER_UNAVAILABLE
```

Do not substitute another snapshot.

## Authorized work

- isolated experimental install of XGrammar and llguidance
- pin exact resolved versions in evidence
- implement one pure deterministic backend lowering per candidate
- hash backend-native grammar artifacts and lowerer source
- construct tokenizer metadata from the pinned local tokenizer
- compile/construct each backend grammar against that tokenizer
- construct and inspect token masks
- replay fixed positive/negative strings through backend matcher/mask APIs
- collect construction time, resource observations, and mask-step latency
- write tests/evidence
- provide a backend recommendation

These engine packages must remain experimental dependencies. Do not add them to
the public `wellplot` runtime dependency set.

## Lowering contract

```
immutable WELL-EBNF-1
        ↓
pure deterministic backend lowering
        ↓
backend-native grammar bytes
        ↓
backend parser/compiler
```

Each backend records:

- accepted source grammar SHA
- lowerer semantic/version id
- lowerer source SHA
- backend-native grammar SHA
- backend/package version

The lowering may change syntax only. It may not change the language.

If exact lowering cannot be demonstrated, reject the backend. Do not hand-edit
or semantically patch the backend grammar.

## Parity and token-mask proof

Use the existing CFG-generator positive/negative corpus plus any narrowly
required backend-boundary cases.

Mandatory:

- every positive source-language case is accepted
- every negative source-language case is rejected
- tokenized positive cases can be replayed token-by-token with every next token
  allowed until valid completion
- negative cases must become impossible before the full invalid string can be
  accepted
- source-language expectations remain grounded by the independent test-only
  WELL-EBNF-1 recognizer

Do not use a backend's own lowering code as its semantic oracle.

## Mandatory gates

| Gate | Requirement |
|---|---|
| G1 | grammar + tokenizer hashes match |
| G2 | deterministic language-preserving lowering |
| G3 | 100% fixed positive/negative text parity |
| G4 | tokenizer + complete grammar construction succeeds |
| G5 | 100% positive token replay / negative rejection |
| G6 | deterministic repeated construction/replay results |
| G7 | bounded resource evidence recorded; pathological construction rejects backend |
| G8 | model calls = 0; model weights loaded = false |

Any backend failing G1–G5 or G8 is rejected.

If both pass, final technical ranking is SOL-owned and uses, in order:

1. semantic fidelity
2. construction/resource behavior
3. mask latency
4. dependency footprint
5. operational simplicity

A passing bakeoff does **not** authorize model inference.

## Explicit non-authorizations

```
modify accepted WELL-EBNF-1:        NOT AUTHORIZED
semantic patch/widen/narrow:        NOT AUTHORIZED
XGrammar JSON-Schema route:         NOT AUTHORIZED
llguidance JSON-Schema substitute:  NOT AUTHORIZED
Qwen/tokenizer autodownload:        NOT AUTHORIZED
Qwen model-weight load:             NOT AUTHORIZED
model forward/generate:             NOT AUTHORIZED
prompt/schema changes:              NOT AUTHORIZED
semantic repair:                    NOT AUTHORIZED
public wellplot dependency changes: NOT AUTHORIZED
PILOT-01:                           NOT AUTHORIZED
```

## Execution protocol

Proceed autonomously inside this contract.

Do not stop for routine module layout, helper factoring, fixture organization,
or backend-adapter implementation choices.

Only stop with one **batched SOL blocker handoff** if exact language preservation,
pinned-tokenizer use, or another frozen contract cannot be satisfied.

## Required handoff

Return:

- candidate SHA / remote head
- exact changed paths
- backend and lowerer versions/hashes
- text parity per backend
- token-mask replay per backend
- compile/construction resource evidence
- performance measurements
- recommendation, or `NO_QUALIFIED_BACKEND`
- explicit `model_calls=0`
- explicit `model_weights_loaded=false`

Then STOP for independent review.
