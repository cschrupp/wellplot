# NL-PROGRAM-DESIGN-01R2 — D5GAP-0117 ordering correction

```
SLICE:
NL-PROGRAM-DESIGN-01R2

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-NL-PROGRAM-DESIGN-01-REWORK2-AUTH-001

STARTING SHA:
bcdba373e0dcb6c744e35a4d6edf6e7cc8f5e85f

PRIOR NL-PROGRAM-DESIGN-01R CANDIDATE:
9e7e638b5525ece924ffd227d045823089ca264d

ACCEPTED PREDECESSORS:
MB-02R              c2f158b8222e3c1b4ae3ae737c2544fc3b25f994
ORACLE-01           fd2f0443ad18a76542d3577928dde80c6928fa11
SCOPE-DESIGN-01R    0c1e6c8420ced10da5aea691f6ceecc5ac7cd2e8
SCOPE-RUNTIME-01R   1026c1356ee39c52e439544167d4a6f03e5e04e2

CANDIDATE SHA:
c88545e20cd8e453cd8c40cf41a3b2f55813f9f0

CODE:
NONE

STATUS:
STOP FOR INDEPENDENT NL-PROGRAM-DESIGN-01R2 REVIEW
```

## CLAIM

This slice freezes how raw utterance + projected workspace may be transformed
into and evaluated as a ScopeNormalizedProgram.

It does not implement or validate any decomposer.
It establishes no English→NormalizedProgram accuracy claim.

## Rework (R3 only)

D5GAP-0117: removed configure-before-fill ordering from `REQUIRED_REPRESENTABLE`.

Utterance “Set RHOB … and split-fill it …” coordinates two semantics; “it” binds
RHOB identity. It does not establish temporal order. Oracle serialization alone
cannot impose that order as coverage.

Preserved from 01R: R1 atom classes; D5GAP-0085 blue → `OBSERVED_OUT_OF_SCOPE`;
D5GAP-0096 no GR-before-RT order; Q1–Q4 rules; other EvaluationSpecs.

## EvaluationSpec inventory (6)

| case_id | REQUIRED_REPRESENTABLE | OBSERVED_OUT_OF_SCOPE |
|---------|-----------------------:|----------------------:|
| D5GAP-0085 | 3 | 1 (blue styling) |
| D5GAP-0089 | 3 | 0 |
| D5GAP-0117 | 4 | 0 |
| D5GAP-0096 | 6 | 0 |
| D5GAP-0101 | 5 | 0 |
| SEED-cm-9643c020e2e02463 | 8 | 0 |

## Explicit exclusions

no decomposer code · no parser/model · no runtime/witness/gold changes · no schema expansion

## Artifacts

- `nl_program_design_01.json`
- `nl_program_design_01.md`
