# DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01R — Corrective rework closeout

```
SLICE:
DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01R

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01-AUTH-001

MODE:
BOUNDED IMPLEMENTATION REWORK

PRIOR CANDIDATE:
0fd552bc527aa56b68fa17220288530e02471316
RESULT: REVISE (F001–F004)

STARTING TIP:
b814a0996efa87163239b9b4c5538ea27de50108

CANDIDATE SHA:
(pending commit)

TIP:
(pending SHA-record commit)

MODEL CALLS:
0

MODEL WEIGHTS LOADED:
false

PILOT-01:
NOT AUTHORIZED
```

## Corrective scope (R1–R5)

| ID | Correction |
|----|------------|
| R1 | G2 evidence-derived: lowering audit (rule count/ids/START/1:1/authorized rewrites/byte-identical) + source-oracle↔backend corpus parity |
| R2 | Independent WELL-EBNF-1 recognizer invoked on every fixed positive/negative case |
| R3 | G6: rebuild + second mask replay; compare semantic traces (acceptance + per-step mask digests), not latency |
| R4 | G5 completion semantics: positive requires `is_completed` + stop allowed; negative requires blocked token OR incomplete + stop blocked; no `tokens_consumed_but_string_rejected` PASS |
| R5 | Persist per-case replay evidence (label, token count, rejection index/reason, completed, stop, digests) |

## Recommendation

**xgrammar** (native EBNF / grammar mode)

llguidance remains **REJECTED** under G7: matcher construction panics with
`grammar.symbols.len() < u16::MAX` (symbol-table overflow). Lowering succeeds;
backend cannot construct a matcher for this grammar size. No third backend.

## Packages (experiment venv only)

| Package | Version |
|---------|---------|
| xgrammar | 0.2.8 |
| llguidance | 1.9.1 |

Not added to public `wellplot` runtime dependencies.

## Gates (evidence-derived)

| Backend | G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | Result |
|---------|----|----|----|----|----|----|----|----|--------|
| xgrammar | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| llguidance | PASS | — | — | — | — | — | FAIL | PASS | **REJECTED** |

G2 is no longer hard-coded: lowering audit + independent oracle + oracle/backend agreement.
G3 requires oracle labels and backend text parity with the oracle.
G5 uses XGrammar `is_completed()` / stop-token mask semantics.
G6 compares dual-construction semantic mask traces.

pytest: `tests/test_cfg_engine_bakeoff_01.py` — 4 passed.

## Evidence artifacts

- `decomposer_pilot_constraint_cfg_engine_bakeoff_01.json` — machine handoff
- `decomposer_pilot_constraint_cfg_engine_bakeoff_01_raw.json` — full run report
- `decomposer_pilot_constraint_cfg_engine_bakeoff_01_xgrammar.ebnf` — lowered native grammar
- `decomposer_pilot_constraint_cfg_engine_bakeoff_01_llguidance.lark` — lowered Lark (construct fails)

Accepted source grammar SHA-256 unchanged:

`f8cfd0c2b8a2cb2c708e464147080ebd7400e40e8060fa0426e423d70396d9d3`

## Explicit non-authorizations (still)

```
model weight load / forward / generate: NOT AUTHORIZED
tokenizer autodownload:                 NOT AUTHORIZED
XGrammar JSON-Schema route:             NOT AUTHORIZED
schema / prompt / repair changes:       NOT AUTHORIZED
PILOT-01:                               NOT AUTHORIZED
```

## Terminal state

```
IMPLEMENTATION_COMPLETE_AWAITING_INDEPENDENT_REVIEW
```

STATUS:
STOP FOR INDEPENDENT DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01R REVIEW
