# DECOMPOSER-PILOT-DESIGN-01 — experimental hypothesis freeze

```
SLICE:
DECOMPOSER-PILOT-DESIGN-01

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-DESIGN-01-AUTH-001

STARTING SHA:
b819852653ca891f7d5575521212321f5d4d3877

ACCEPTED PREDECESSORS:
MB-02R                         c2f158b8222e3c1b4ae3ae737c2544fc3b25f994
ORACLE-01                      fd2f0443ad18a76542d3577928dde80c6928fa11
SCOPE-DESIGN-01R               0c1e6c8420ced10da5aea691f6ceecc5ac7cd2e8
SCOPE-RUNTIME-01R              1026c1356ee39c52e439544167d4a6f03e5e04e2
NL-PROGRAM-DESIGN-01R2         c88545e20cd8e453cd8c40cf41a3b2f55813f9f0
NL-PROGRAM-EVAL-HARNESS-01R2   a2dce439a9bcaddeb91f02fc44b9ff77467b77c8

CANDIDATE SHA:
96cecfbb66249d3ace6933764a656ae77fe31410

CODE:
NONE

MODEL CALLS:
0

PREFLIGHT-01:
NOT AUTHORIZED

PILOT-01:
NOT AUTHORIZED

STATUS:
STOP FOR INDEPENDENT DECOMPOSER-PILOT-DESIGN-01 REVIEW
```

## CLAIM

DECOMPOSER-PILOT-DESIGN-01 freezes an experimental hypothesis and its evaluation
protocol. It provides **no** evidence of English→ScopeNormalizedProgram model
performance because **no model inference has occurred**.

## Frozen hypothesis (Q1–Q6)

| Q | Freeze |
|---|--------|
| Q1 | Untuned local `Qwen/Qwen3-1.7B` instruction; thinking off; no SLM-02/03 adapters; no fallback/auto-download; exact snapshot+hashes mandatory before inference |
| Q2 | Zero-shot; one immutable contract prompt; zero exemplars; one attempt/case; no retry/repair/feedback; general contract semantics only; sealed-six hints forbidden |
| Q3 | Hard structural constrained decode from `ClosedNormalizedProgram` (incl. XOR parity); semantic-neutral; `freeze_candidate()` authoritative; distinct decode vs schema failures |
| Q4 | Layer 0: 6/6 reach freeze (else semantic INCONCLUSIVE); Layer 1: EQUIVALENT/6; Layer 2: critical-mechanism veto; 6/6 strong / ≥5 continue / ≤4 stop; harness sole judge |
| Q5 | Immutable probe map + deterministic `(case_id, failure_label)→mechanism`; Veto A/B; no post-hoc classes |
| Q6 | Preflight hard barrier; immutable run manifest; fixed six-case order; per-case rendered-input hashes; contamination attestation; mechanical decision |

Machine-readable detail: `decomposer_pilot_design_01.json`.

## Explicit non-authorizations

```
PREFLIGHT CODE:                         NOT AUTHORIZED
MODEL CALLS:                            0
DECOMPOSER-PILOT-PREFLIGHT-01:          NOT AUTHORIZED
DECOMPOSER-PILOT-01:                    NOT AUTHORIZED
MODEL DOWNLOAD:                         NOT AUTHORIZED
CONSTRAINT BACKEND IMPLEMENTATION:      NOT AUTHORIZED
PROMPT IMPLEMENTATION:                  NOT AUTHORIZED
INFERENCE IMPLEMENTATION:               NOT AUTHORIZED

MB-03:                                  NOT AUTHORIZED
T5:                                     NOT AUTHORIZED
Luna/frontier:                          NOT AUTHORIZED
LangGraph:                              NOT AUTHORIZED
fine-tuning:                            NOT AUTHORIZED
SLM-02/03 adapters:                     FORBIDDEN FOR PILOT
production / runtime / evaluator /
  oracle changes:                       NOT AUTHORIZED
repair/postprocess:                     NOT AUTHORIZED
old D5 corpus as development data:      NOT AUTHORIZED
```

## Governance after acceptance

```
DECOMPOSER-PILOT-DESIGN-01
    ACCEPTED / CLOSED
            ↓
separate new AUTH
            ↓
DECOMPOSER-PILOT-PREFLIGHT-01
    pins model/backend/prompt/schema/serializer/inference
    proves decoder parity
    model calls = 0
            ↓
independent review
            ↓
separate new AUTH
            ↓
DECOMPOSER-PILOT-01
    exactly six inference calls
```

## Artifacts

- `decomposer_pilot_design_01.json`
- `decomposer_pilot_design_01.md`
