# NL-PROGRAM-DESIGN-01 — English→NormalizedProgram contract (design only)

```
SLICE:
NL-PROGRAM-DESIGN-01

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-NL-PROGRAM-DESIGN-01-AUTH-001

STARTING SHA:
cdb5886881b4e42740fa09d864f27cbda522183a

ACCEPTED PREDECESSORS:
MB-02R              c2f158b8222e3c1b4ae3ae737c2544fc3b25f994
ORACLE-01           fd2f0443ad18a76542d3577928dde80c6928fa11
SCOPE-DESIGN-01R    0c1e6c8420ced10da5aea691f6ceecc5ac7cd2e8
SCOPE-RUNTIME-01R   1026c1356ee39c52e439544167d4a6f03e5e04e2

CANDIDATE SHA:
PENDING

CODE:
NONE

STATUS:
STOP FOR INDEPENDENT NL-PROGRAM-DESIGN-01 REVIEW
```

## CLAIM

This slice freezes how raw utterance + projected workspace may be transformed
into and evaluated as a ScopeNormalizedProgram.

It does not implement or validate any decomposer.
It establishes no English→NormalizedProgram accuracy claim.

## Frozen contract (Q1–Q4)

| Q | Freeze |
|---|--------|
| Q1 | Decomposer sees only utterance + ProjectedWorkspace facts; case_id/fixture_id harness-only; gold/oracle/program metadata forbidden |
| Q2 | Output = exactly one schema-closed ScopeNormalizedProgram; unknown fields ⇒ DECOMPOSITION_SCHEMA_INVALID |
| Q3 | Equivalence = runtime terminal match + utterance coverage + order-preserving semantic spine (not JSON equality); BENIGN_REDUNDANT_TASK non-failing only under strict rules |
| Q4 | One EvaluationSpec per case; coverage checklist is utterance-level; candidate frozen before oracle lookup |

## EvaluationSpec inventory (6)

| case_id | oracle_witness_id | coverage atoms (count) |
|---------|-------------------|------------------------:|
| D5GAP-0085 | D5GAP-0085 | 4 |
| D5GAP-0089 | D5GAP-0089 | 3 |
| D5GAP-0117 | D5GAP-0117 | 5 |
| D5GAP-0096 | D5GAP-0096 | 7 |
| D5GAP-0101 | D5GAP-0101 | 5 |
| SEED-cm-9643c020e2e02463 | SEED-cm-9643c020e2e02463 | 8 |

Normative detail: `nl_program_design_01.json`.

## Explicit exclusions

no decomposer code · no heuristic parser · no Luna/frontier calls · no T5 · no Qwen training · no LangGraph · no MB-03 · no production integration · no runtime changes · no witness mutation · no gold mutation · no new NormalizedProgram features · no new runtime effects

## Artifacts

- `nl_program_design_01.json`
- `nl_program_design_01.md`
