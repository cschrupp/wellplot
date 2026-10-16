# SCOPE-DESIGN-01 — Multi-clause contract design (six residue cases)

```
SLICE:
SCOPE-DESIGN-01

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-SCOPE-CONTRACT-DESIGN-AUTH-001

STARTING SHA:
fd2f0443ad18a76542d3577928dde80c6928fa11

ACCEPTED MB-02R SUBJECT:
c2f158b8222e3c1b4ae3ae737c2544fc3b25f994

ACCEPTED ORACLE-01 SUBJECT:
fd2f0443ad18a76542d3577928dde80c6928fa11

CASES:
D5GAP-0085
D5GAP-0089
D5GAP-0096
D5GAP-0101
D5GAP-0117
SEED-cm-9643c020e2e02463

HISTORICAL GOLD:
UNCHANGED

MB-02R:
UNCHANGED

ORACLE-01:
UNCHANGED

CODE:
NONE

IMPLEMENTATION:
NOT AUTHORIZED

STATUS:
STOP FOR INDEPENDENT SCOPE-DESIGN REVIEW
```

Machine-readable authority: `scope_contract_design_01.json`.

## CLAIM

This slice establishes only whether the six cases are representable under
NormalizedProgram + deterministic projected-state semantics.

It does not establish raw English → NormalizedProgram.

## Frozen contract (Q1–Q5)

| Q | Freeze |
|---|--------|
| Q1 | `NormalizedProgram` = composition; `NormalizedTask` wraps one `NormalizedRequest`; binds/deps at task layer |
| Q2 | Array order = execution order; linear `depends_on` only; order/deps contradiction → schema-domain |
| Q3 | Effects only after OK: CREATE_TRACK / PLACE_CURVE / CONFIGURE scale facts; DEFINE_FILL deferred |
| Q4 | `SemanticQuery`: exactly one of `text` \| `local_ref`; bind-contract errors → schema-domain; `LocalBindingTable` is execution state |
| Q5 | Fail-fast; first non-OK is sole public terminal; all-OK → program `ok` |

## Representability (six witnesses)

| case_id | tasks | key transitions | representability |
|---------|------:|-----------------|------------------|
| D5GAP-0085 | 3 | dual CBL scale configure → BETWEEN_INSTANCES | REPRESENTABLE_UNDER_CONTRACT |
| D5GAP-0089 | 2 | narrow CBL scale → BETWEEN_INSTANCES | REPRESENTABLE_UNDER_CONTRACT |
| D5GAP-0096 | 5 | CREATE_TRACK+$track1 → place/configure GR, RT | REPRESENTABLE_UNDER_CONTRACT |
| D5GAP-0101 | 3 | CREATE_TRACK+$track1 → place/configure CALI | REPRESENTABLE_UNDER_CONTRACT |
| D5GAP-0117 | 2 | configure RHOB → BASELINE_SPLIT | REPRESENTABLE_UNDER_CONTRACT |
| SEED-cm-9643c020e2e02463 | 5 | CREATE_TRACK+$track1 → place/configure GR, RT | REPRESENTABLE_UNDER_CONTRACT |

**CONTRACT_INSUFFICIENT:** 0

Operand notes (single-op allowlist completeness, not composition gaps): `SemanticQuery.local_ref`; CREATE_TRACK `track_title` / optional `track_width_mm`. DEFINE_FILL projected effects not required by these six.

## Explicit exclusions

resolver implementation · effect projector · executable replay · English→NormalizedProgram · LangGraph · T5 · Luna · MB-03 · SLM-04 · gold mutation · production changes · non-linear graphs · document/renderer simulation

## Next decision (not authorized here)

Whether to authorize a bounded projector / program-runtime implementation slice now that design-level representability is 6/6.
