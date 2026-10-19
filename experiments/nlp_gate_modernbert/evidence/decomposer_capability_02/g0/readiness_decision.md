# G0 — Phase 0 readiness decision

```
PROGRAM:
WELLPLOT-DECOMPOSER-CAPABILITY-02

SLICE:
G0

AUTHORITY:
WP-DC02-G0-PHASE0-READINESS-REVIEW-AUTH-001

STARTING TIP:
a11c99c4691899d82ee33c9b150e487c688f2036

DECISION:
WP-DC02-G0-READINESS-DECISION-001

MODEL CALLS:
0

OPENROUTER CALLS:
0
```

## Phase 0 inventory (3/3 accepted)

| Slice | Subject | Status |
|-------|---------|--------|
| C02-00 | Baseline integrity | CLOSED / ACCEPTED |
| C02-01 | Semantic oracle / benchmark | CLOSED / ACCEPTED |
| C02-02 | Adapter qualification | CLOSED / ACCEPTED |

## Two readiness levels

### 1. Phase 0 technical readiness — READY

Supported by accepted C02-00/01/02 evidence: recovered Pilot Run 1 baseline, frozen six-case oracle/scoring, and mock-qualified adapters with resolved OpenRouter ids for Gemini (`google/gemini-4-argon`) and DeepSeek (`deepseek/deepseek-v4.1-flash-1017`).

### 2. Live scientific execution readiness — NOT ESTABLISHED

Primary blockers before any inference:

1. **Decoding parity disclosure** — Pilot used XGrammar hard mask; Capability-02 hosted/local paths currently use prompted JSON / `json_object` + `freeze_candidate`. These are not equivalent conditions and must be frozen explicitly in the next experiment design.
2. **Provider routing pin** — must be in the request, not inferred from response identity.
3. **Parse-failure accounting** — preserve raw usage; charge attempted calls even when parse/freeze fails.
4. **Exact frontier-ceiling protocol** — not yet designed/frozen (provisional C02-03).

Deferred (not G0 blockers for Phase 0 closure): rendered-input live rehash; local 4B weight presence hashes.

## Gate disposition

```
PHASE 0:                                      CLOSED — TECHNICALLY READY
AUTHORIZE PREPARATION OF NEXT EXPERIMENT DESIGN: YES
AUTHORIZE INFERENCE:                          NO
AUTHORIZE C02-03 EXECUTION:                   NO
AUTHORIZE C02-03..C02-17:                     NO
```

G0 closes Phase 0 and permits preparation of the next **design** (Gemini frontier-ceiling protocol). It does **not** authorize Gemini, DeepSeek, or local Qwen inference.

## Recommended next authority (not granted here)

Separate design authority to freeze the first frontier-ceiling run protocol, including decoding regime disclosure, routing pins, call budget, and accounting rules — then a further execution authority for any OpenRouter calls.

STATUS:
STOP FOR INDEPENDENT G0 REVIEW
