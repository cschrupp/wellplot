# DECOMPOSER-PILOT-CONSTRAINT-CFG-GENERATOR-01 — Implementation closeout

```
SLICE:
DECOMPOSER-PILOT-CONSTRAINT-CFG-GENERATOR-01

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-CONSTRAINT-CFG-GENERATOR-01-AUTH-001

MODE:
BOUNDED IMPLEMENTATION

PARENT:
DECOMPOSER-PILOT-CONSTRAINT-CFG-DESIGN-01R2
ACCEPTED (Human design acceptance recorded)

STARTING TIP:
8e84a8f41650a221a4ef247bd7d78bceaa43687d

CANDIDATE SHA:
1b5ccbc49862c8184b1bad1acfd76024040b0aa0

TIP:
0683167707088d4446ecc74ed2e0283740579135

MODEL CALLS:
0

ENGINE CALLS:
0
```

## Purpose

```
pinned patched ClosedNormalizedProgram schema
        ↓
deterministic generator (library)
        ↓
canonical WELL-EBNF-1 bytes
        ↓
parity / determinism / containment evidence
```

## Library authority

Semantic entrypoint:

`nlp_gate_modernbert.decomposer_pilot.cfg_generator.generate.generate_from_schema_bytes`

No CLI semantic authority. No engine-native lowering.

Independent test oracle (production import forbidden):

`tests/support/well_ebnf1_recognizer.py`

## Acceptance checklist (mechanical)

| Gate | Result |
|------|--------|
| pinned schema hash matches | PASS |
| all encountered schema constructs accounted for | PASS |
| unrecognized semantic keywords = 0 | PASS |
| silently ignored semantic keywords = 0 | PASS |
| generator fail-closed (integer / unknown keyword) | PASS (fail paths encoded) |
| WELL-EBNF-1 syntax self-validation | PASS |
| deterministic replay / byte identity | PASS |
| grammar hash identity | PASS |
| positive lexical/structural probes | PASS |
| negative lexical/structural probes | PASS |
| grammar → freeze_candidate containment | PASS |
| hand-edit detection | PASS |
| model_calls | 0 |
| engine_calls | 0 |

pytest: `tests/test_cfg_generator_01.py` — 47 passed.

## Artifacts

| File | Role |
|------|------|
| `decomposer_pilot_constraint_cfg_generator_01.well_ebnf1` | canonical WELL-EBNF-1 bytes |
| `decomposer_pilot_constraint_cfg_generator_01_ledger.json` | transform ledger |
| `decomposer_pilot_constraint_cfg_generator_01_coverage.json` | coverage report |
| `decomposer_pilot_constraint_cfg_generator_01_provenance.json` | provenance pins |
| `decomposer_pilot_constraint_cfg_generator_01.json` | machine handoff |
| `decomposer_pilot_constraint_cfg_generator_01.md` | this document |

## Explicit non-authorizations

```
XGrammar / llguidance / other engine install:  NOT AUTHORIZED
engine-native grammar lowering:               NOT AUTHORIZED
engine grammar compilation:                   NOT AUTHORIZED
tokenizer / token-mask construction:          NOT AUTHORIZED
Qwen load / forward / generate:               NOT AUTHORIZED
prompt / schema / semantic repair changes:    NOT AUTHORIZED
PILOT-01:                                     NOT AUTHORIZED
CFG-ENGINE-BAKEOFF-01:                        NOT AUTHORIZED
```

## Terminal state

```
IMPLEMENTATION_COMPLETE_AWAITING_INDEPENDENT_REVIEW
```

STATUS:
STOP FOR INDEPENDENT DECOMPOSER-PILOT-CONSTRAINT-CFG-GENERATOR-01 REVIEW
