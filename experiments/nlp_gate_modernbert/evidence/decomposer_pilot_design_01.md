# DECOMPOSER-PILOT-DESIGN-01R — Q5 attribution + Q1 wording rework

```
SLICE:
DECOMPOSER-PILOT-DESIGN-01R

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-DESIGN-01-REWORK-AUTH-001

STARTING SHA:
6602a2856b5641bab49423175da6e5fc1bd2f8b1

PRIOR CANDIDATE (DESIGN-01):
96cecfbb66249d3ace6933764a656ae77fe31410

ACCEPTED PREDECESSORS:
MB-02R                         c2f158b8222e3c1b4ae3ae737c2544fc3b25f994
ORACLE-01                      fd2f0443ad18a76542d3577928dde80c6928fa11
SCOPE-DESIGN-01R               0c1e6c8420ced10da5aea691f6ceecc5ac7cd2e8
SCOPE-RUNTIME-01R              1026c1356ee39c52e439544167d4a6f03e5e04e2
NL-PROGRAM-DESIGN-01R2         c88545e20cd8e453cd8c40cf41a3b2f55813f9f0
NL-PROGRAM-EVAL-HARNESS-01R2   a2dce439a9bcaddeb91f02fc44b9ff77467b77c8

CANDIDATE SHA:
1ad45677418cccdde7f7e432d8defc2fe2d28b3c

CODE:
NONE

MODEL CALLS:
0

PREFLIGHT-01:
NOT AUTHORIZED

PILOT-01:
NOT AUTHORIZED

STATUS:
STOP FOR INDEPENDENT DECOMPOSER-PILOT-DESIGN-01R REVIEW
```

## CLAIM

DECOMPOSER-PILOT-DESIGN-01R freezes an experimental hypothesis and its evaluation
protocol. It provides **no** evidence of English→ScopeNormalizedProgram model
performance because **no model inference has occurred**.

## Rework

| id | Correction |
|----|------------|
| R1 | Composition attribution case-scoped to D5GAP-0096 + D5GAP-0101; all mechanisms use uniform `(case_id, failure_label) → mechanism` encoding (`labels` + `only_on_cases`) |
| R2 | Q1 role = `zero-shot constrained autoregressive decomposer` (removed `zero/few-shot`) |

Q1–Q6 otherwise preserved (Q2 already zero-shot operationally).

## Frozen hypothesis (Q1–Q6)

| Q | Freeze |
|---|--------|
| Q1 | Untuned local `Qwen/Qwen3-1.7B` instruction; **zero-shot** role; thinking off; no SLM-02/03 adapters; no fallback/auto-download; exact snapshot+hashes mandatory before inference |
| Q2 | Zero-shot; one immutable contract prompt; zero exemplars; one attempt/case; no retry/repair/feedback |
| Q3 | Hard structural constrained decode from `ClosedNormalizedProgram`; `freeze_candidate()` authoritative |
| Q4 | Layer 0/1/2 scoring; harness sole judge; 6/6 ≠ production claim |
| Q5 | Immutable probe map + **pair-scoped** attribution (every mechanism has `only_on_cases`); Veto A/B |
| Q6 | Preflight hard barrier; immutable run manifest; fixed six-case order; contamination attestation |

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

MB-03 / T5 / Luna / LangGraph:          NOT AUTHORIZED
fine-tuning:                            NOT AUTHORIZED
SLM-02/03 adapters:                     FORBIDDEN FOR PILOT
production / runtime / evaluator /
  oracle changes:                       NOT AUTHORIZED
repair/postprocess:                     NOT AUTHORIZED
old D5 corpus as development data:      NOT AUTHORIZED
```

## Governance after acceptance

```
DECOMPOSER-PILOT-DESIGN-01R
    ACCEPTED / CLOSED
            ↓
separate new AUTH
            ↓
DECOMPOSER-PILOT-PREFLIGHT-01
    pins + decoder parity
    model calls = 0
```

## Artifacts

- `decomposer_pilot_design_01.json`
- `decomposer_pilot_design_01.md`
