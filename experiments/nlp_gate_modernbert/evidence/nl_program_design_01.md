# NL-PROGRAM-DESIGN-01R — Evaluation-spec consistency rework

```
SLICE:
NL-PROGRAM-DESIGN-01R

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-NL-PROGRAM-DESIGN-01-REWORK-AUTH-001

STARTING SHA:
c22fa4f0487ff7d612f2a8294923c246ab40fffd

PRIOR NL-PROGRAM-DESIGN CANDIDATE:
b696e974b9ea6a2c8cda5ec80441db0d7726adea

ACCEPTED PREDECESSORS:
MB-02R              c2f158b8222e3c1b4ae3ae737c2544fc3b25f994
ORACLE-01           fd2f0443ad18a76542d3577928dde80c6928fa11
SCOPE-DESIGN-01R    0c1e6c8420ced10da5aea691f6ceecc5ac7cd2e8
SCOPE-RUNTIME-01R   1026c1356ee39c52e439544167d4a6f03e5e04e2

CANDIDATE SHA:
9e7e638b5525ece924ffd227d045823089ca264d

CODE:
NONE

STATUS:
STOP FOR INDEPENDENT NL-PROGRAM-DESIGN-01R REVIEW
```

## CLAIM

This slice freezes how raw utterance + projected workspace may be transformed
into and evaluated as a ScopeNormalizedProgram.

It does not implement or validate any decomposer.
It establishes no English→NormalizedProgram accuracy claim.

## Rework

**R1 — Coverage atom classes**

- `REQUIRED_REPRESENTABLE` — gates semantic equivalence; must fit frozen `ScopeNormalizedProgram`
- `OBSERVED_OUT_OF_SCOPE` — recorded from utterance; does **not** gate equivalence; do not expand schema/runtime here

D5GAP-0085: fill styling `blue` → `OBSERVED_OUT_OF_SCOPE` (no fill-color operand).

**R2 — Ordering atoms**

Ordering is a coverage atom only if the utterance encodes it (temporal language, anaphora, or other stated semantic dependency). Oracle task serialization alone is insufficient.

D5GAP-0096: removed GR-before-RT ordering atom.

Q3 alignment preserves required causal/utterance order; it does not treat arbitrary independent-op serialization as accuracy.

## Frozen contract (Q1–Q4)

| Q | Freeze |
|---|--------|
| Q1 | utterance + ProjectedWorkspace only; case_id/fixture_id harness-only |
| Q2 | schema-closed ScopeNormalizedProgram; unknown fields invalid |
| Q3 | runtime gate + REQUIRED_REPRESENTABLE coverage + semantic spine; not JSON equality |
| Q4 | EvaluationSpec with classified coverage atoms; candidate frozen before oracle lookup |

## EvaluationSpec inventory (6)

| case_id | REQUIRED_REPRESENTABLE | OBSERVED_OUT_OF_SCOPE |
|---------|-----------------------:|----------------------:|
| D5GAP-0085 | 3 | 1 (blue styling) |
| D5GAP-0089 | 3 | 0 |
| D5GAP-0117 | 5 | 0 |
| D5GAP-0096 | 6 | 0 |
| D5GAP-0101 | 5 | 0 |
| SEED-cm-9643c020e2e02463 | 8 | 0 |

## Explicit exclusions

no decomposer code · no heuristic parser · no Luna/frontier · no T5 · no Qwen · no LangGraph · no MB-03 · no production · no runtime changes · no witness/gold mutation · no schema expansion for out-of-scope atoms

## Artifacts

- `nl_program_design_01.json`
- `nl_program_design_01.md`
