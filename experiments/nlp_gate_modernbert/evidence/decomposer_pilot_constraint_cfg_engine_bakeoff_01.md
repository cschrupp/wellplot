# DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01R2 — Corrective rework closeout

```
SLICE:
DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01R2

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01-AUTH-001

MODE:
BOUNDED IMPLEMENTATION REWORK

PRIOR CANDIDATE:
3b58f28cfea7a84dd2e5e4cb3122df27e11ad16d
RESULT: REVISE (G2 independent rewrite proof)

STARTING TIP:
43c05042c7a427c1b268e7357fb18165f6f5090e

CANDIDATE SHA:
d680a315b5cf11ef7c89c70cf6222dd1d62b9a84

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
| R1 | G2 audit accepts source WELL-EBNF-1 + already-produced XGrammar EBNF |
| R2 | Audit does not import/call `lower_well_ebnf1_to_xgrammar_ebnf`, `_rewrite_body`, or other lowerer helpers |
| R3 | Independent per-rule proof: same ids, 1:1 mapping, terminator strip only structural change, only authorized lit/class scalar escapes may differ |
| R4 | Adversarial audit tests: delete/rename/mutate literal/mutate class/unauthorized escape → FAIL |
| R5 | Regenerated G2 evidence; G3–G8 re-executed unchanged in semantics |

## Recommendation

**xgrammar** (native EBNF / grammar mode)

llguidance remains **REJECTED** under G7 (`u16` symbol-table overflow).

## Gates (evidence-derived)

| Backend | G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | Result |
|---------|----|----|----|----|----|----|----|----|--------|
| xgrammar | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| llguidance | PASS | — | — | — | — | — | FAIL | PASS | **REJECTED** |

G2 `authorized_syntax_rewrites_only` is now proven by an independent lockstep
source↔target checker (`audit_mode=independent_source_vs_produced_target`), not
by replaying the lowerer under test.

pytest: `tests/test_cfg_engine_bakeoff_01.py` — 12 passed.

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
STOP FOR INDEPENDENT DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01R2 REVIEW
