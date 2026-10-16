# SCOPE-DESIGN-01R — Contract rework (Q1A + recomputed representability)

```
SLICE:
SCOPE-DESIGN-01R

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-SCOPE-CONTRACT-DESIGN-REWORK-AUTH-001

STARTING SHA:
e1e3fa23bd7f0ce94c56682cecd94f7fecfed44b

ACCEPTED MB-02R SUBJECT:
c2f158b8222e3c1b4ae3ae737c2544fc3b25f994

ACCEPTED ORACLE-01 SUBJECT:
fd2f0443ad18a76542d3577928dde80c6928fa11

PRIOR SCOPE-DESIGN CANDIDATE:
e1e3fa23bd7f0ce94c56682cecd94f7fecfed44b

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
STOP FOR INDEPENDENT SCOPE-DESIGN-01R REVIEW
```

Machine-readable authority: `scope_contract_design_01.json`.

## CLAIM

This slice establishes only whether the six cases are representable under
NormalizedProgram + deterministic projected-state semantics (Q1–Q5 + Q1A).

It does not establish raw English → NormalizedProgram.

## Prior defect (corrected)

`e1e3fa23…` claimed 6/6 representable while three witnesses used `track_title` /
`track_width_mm` that were **not** frozen in Q1–Q5 (only `SemanticQuery.local_ref`
was authorized in Q4).

Strict pre-amendment accounting:

| Result | Count | Cases |
|--------|------:|-------|
| REPRESENTABLE_UNDER_CONTRACT | 3 | D5GAP-0085, 0089, 0117 |
| CONTRACT_INSUFFICIENT | 3 | D5GAP-0096, 0101, SEED-cm-9643… |

## Q1A — CREATE_TRACK semantic operands (frozen amendment)

For `requested_operation == CREATE_TRACK` only, successor `NormalizedRequest` may carry:

- `track_title: str | None`
- `track_width_mm: float | None`

Basis: WELL-IR `CreateTrack` already has `title` and `width_mm`.

Forbidden: general metadata bag; arbitrary payloads on other ops; composition fields inside `NormalizedRequest`.

Q2–Q5 unchanged.

### Utterance word “normal” (SEED)

| Finding | Value |
|---------|--------|
| Adjudication | `DEFAULT_SEMANTICS` |
| Operand required | **No** (`track_kind` not added) |
| Rationale | WELL-IR / WellPlot default `kind="normal"` |

The word is recorded, not silently dropped.

## Frozen surface used for recompute

Q1 program/task/request separation · **Q1A CREATE_TRACK operands** · Q2 linear order/deps · Q3 projected effects · Q4 `local_ref` + bind table · Q5 fail-fast terminal

## Representability (recomputed)

| case_id | representability | frozen extras used |
|---------|------------------|--------------------|
| D5GAP-0085 | REPRESENTABLE_UNDER_CONTRACT | — |
| D5GAP-0089 | REPRESENTABLE_UNDER_CONTRACT | — |
| D5GAP-0117 | REPRESENTABLE_UNDER_CONTRACT | — |
| D5GAP-0096 | REPRESENTABLE_UNDER_CONTRACT | Q1A `track_title`, Q4 `local_ref` |
| D5GAP-0101 | REPRESENTABLE_UNDER_CONTRACT | Q1A `track_title`+`track_width_mm`, Q4 `local_ref` |
| SEED-cm-9643c020e2e02463 | REPRESENTABLE_UNDER_CONTRACT | Q1A `track_title`, Q4 `local_ref`; `normal`=DEFAULT_SEMANTICS |

**6 / 6 REPRESENTABLE_UNDER_CONTRACT**  
**0 / 6 CONTRACT_INSUFFICIENT**

## Explicit exclusions

resolver / projector implementation · executable replay · English→NormalizedProgram · LangGraph · T5 · Luna · MB-03 · SLM-04 · gold mutation · production changes · non-linear graphs · document simulation · unfrozen op payloads beyond Q1A

## Next decision (not authorized here)

Whether to authorize a bounded projector / program-runtime implementation slice under the now-complete frozen surface (Q1–Q5 + Q1A).
