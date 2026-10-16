# NL-PROGRAM-EVAL-HARNESS-01R2 — integrity rework closeout

```
SLICE:
NL-PROGRAM-EVAL-HARNESS-01R2

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-NL-PROGRAM-EVAL-HARNESS-01-REWORK2-AUTH-001

STARTING SHA:
66ff818e4c11be74d3afb6851047b4b95a55e44d

PRIOR CANDIDATE (HARNESS-01R):
848c1053c3c16ee3c32555a95dc01d7a9d49e290

CANDIDATE SHA:
<pending commit>

HISTORICAL GOLD:
UNCHANGED

MB-02R / SCOPE-RUNTIME / ORACLE-01:
UNCHANGED

STATUS:
STOP FOR INDEPENDENT NL-PROGRAM-EVAL-HARNESS-01R2 REVIEW
```

## CLAIM

These artifacts are **harness test vectors**, not decomposer predictions.

The slice proves that frozen or hand-authored candidate `ScopeNormalizedProgram`s can be
evaluated reproducibly under the frozen Q3 relation. It does **not** demonstrate
English→Program generation performance.

## Rework (R5–R7)

| id | correction |
|----|------------|
| R5 | `FrozenCandidate` public `__init__` blocked; sealed only via `freeze_candidate` → `_create_sealed` (closed-schema + canonical + digest). Bypass test included. |
| R6 | `BENIGN_REDUNDANT_TASK` = exactly the frozen six predicates; removed entity-addressed-elsewhere; dependency edges stripped only after semantic need is disproven |
| R7 | Closeout attests harness suite count separately from adjacent SCOPE-RUNTIME suite |

## Test attestation (R7)

| suite | path | collected / passed |
|-------|------|--------------------|
| harness (this slice) | `tests/test_nl_program_eval_harness.py` | **24** |
| adjacent (unchanged SCOPE-RUNTIME) | `tests/test_scope_runtime.py` | 12 |
| combined (not the harness closeout claim) | both | 36 |

## Acceptance matrix (18 fixtures)

Preserved corpus. `all_expected_fixture_outcomes_match = true`.

`oracle_access_before_freeze = 0` · digest collisions = 0 · decomposer calls = 0

## Explicit exclusions

- No real decomposer / model / T5 / Luna / LangGraph
- No MB-03 / production path
- No English→Program accuracy claim
