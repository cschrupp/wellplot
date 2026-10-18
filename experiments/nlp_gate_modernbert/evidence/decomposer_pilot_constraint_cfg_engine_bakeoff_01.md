# DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01 — Closeout

```
SLICE:
DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01-AUTH-001

STARTING TIP:
928d77672afcbb00cc514940b5ce3935847496ee

CANDIDATE SHA:
0fd552bc527aa56b68fa17220288530e02471316

TIP:
(pending SHA-record commit)

MODEL CALLS:
0

MODEL WEIGHTS LOADED:
false

PILOT-01:
NOT AUTHORIZED
```

## Recommendation

**xgrammar** (native EBNF / grammar mode)

llguidance is **REJECTED** under G7: matcher construction panics with
`grammar.symbols.len() < u16::MAX` (symbol-table overflow on the accepted
WELL-EBNF-1 artifact’s hex-trie rule volume). Lowering itself succeeds; the
backend cannot construct a matcher for this grammar size.

## Packages (experiment venv only)

| Package | Version |
|---------|---------|
| xgrammar | 0.2.8 |
| llguidance | 1.9.1 |

Not added to public `wellplot` runtime dependencies.

## Gates

| Backend | G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | Result |
|---------|----|----|----|----|----|----|----|----|--------|
| xgrammar | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| llguidance | PASS | PASS* | — | FAIL | — | — | FAIL | PASS | **REJECTED** |

\*llguidance lowering is deterministic; construction fails.

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
STOP FOR INDEPENDENT DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01 REVIEW
