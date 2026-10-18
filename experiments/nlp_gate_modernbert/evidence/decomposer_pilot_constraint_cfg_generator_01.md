# DECOMPOSER-PILOT-CONSTRAINT-CFG-GENERATOR-01R — Corrective rework closeout

```
SLICE:
DECOMPOSER-PILOT-CONSTRAINT-CFG-GENERATOR-01R

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-CONSTRAINT-CFG-GENERATOR-01-AUTH-001

MODE:
BOUNDED IMPLEMENTATION REWORK

PRIOR CANDIDATE:
1b5ccbc49862c8184b1bad1acfd76024040b0aa0
RESULT: REVISE (F001–F004)

STARTING TIP:
f0ede93c9885915b7430fa391901cc561d72f811

CANDIDATE SHA:
f3607ff9d0733712ecd86742496620e4aa77d9a4

TIP:
a74b4e5b6be6d99d2bdf70006d1bb0bc54a1d7e7

MODEL CALLS:
0

ENGINE CALLS:
0
```

## Corrective scope (R1–R5)

| ID | Correction |
|----|------------|
| R1 | Ledger attribution by entry index; coverage/ledger congruence |
| R2 | T14: only ClosedSemanticQuery oneOf; fail-closed tests |
| R3 | T18 provenance: patcher SHA, Unicode DB, JSON, pydantic(+core) |
| R4 | Explicit surrogate lexical narrowing (pairs OK; lone halves REJECT) |
| R5 | Regenerated grammar / ledger / coverage / provenance / closeout |

Also: independent recognizer ASCII Identifier + UnsignedInt hardening.

## Acceptance checklist

| Gate | Result |
|------|--------|
| pinned schema hash matches | PASS |
| constructs accounted for | PASS |
| unrecognized / silently ignored = 0 | PASS |
| ledger ↔ coverage congruence | PASS |
| fail-closed: hash / keyword / integer / oneOf | PASS |
| WELL-EBNF-1 self-validation | PASS |
| deterministic replay | PASS |
| positive / negative probes (incl. surrogates) | PASS |
| grammar → freeze containment (incl. valid pair) | PASS |
| T18 provenance complete | PASS |
| hand-edit detection | PASS |
| model_calls / engine_calls | 0 / 0 |

pytest: `tests/test_cfg_generator_01.py` — 59 passed.

## R4 lexical narrowing (explicit)

Ordinary `\uXXXX` surrogate halves are **not** legal standalone atoms on the
canonical generation surface. Valid high+low surrogate pairs remain legal.
Unpaired high/low surrogate escapes are grammar-rejected.

This is an explicit permitted canonical lexical narrowing (alongside Q2/Q10/R3).

## Non-authorizations

```
engine install / lowering / compile: NOT AUTHORIZED
tokenizer / token-mask:              NOT AUTHORIZED
model load / forward / generate:     NOT AUTHORIZED
PILOT-01 / ENGINE-BAKEOFF:           NOT AUTHORIZED
```

## Terminal state

```
IMPLEMENTATION_COMPLETE_AWAITING_INDEPENDENT_REVIEW
```

STATUS:
STOP FOR INDEPENDENT DECOMPOSER-PILOT-CONSTRAINT-CFG-GENERATOR-01R REVIEW
