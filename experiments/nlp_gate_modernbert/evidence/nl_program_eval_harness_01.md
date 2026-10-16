# NL-PROGRAM-EVAL-HARNESS-01R — integrity rework closeout

```
SLICE:
NL-PROGRAM-EVAL-HARNESS-01R

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-NL-PROGRAM-EVAL-HARNESS-01-REWORK-AUTH-001

STARTING SHA:
4cfa047a7cf548dcdc31f315f0ccd74c04884a63

PRIOR CANDIDATE (HARNESS-01):
84212ab70b9b910f449211a93f1a140374e0f584

CANDIDATE SHA:
848c1053c3c16ee3c32555a95dc01d7a9d49e290

HISTORICAL GOLD:
UNCHANGED

MB-02R / SCOPE-RUNTIME / ORACLE-01:
UNCHANGED

STATUS:
STOP FOR INDEPENDENT NL-PROGRAM-EVAL-HARNESS-01R REVIEW
```

## CLAIM

These artifacts are **harness test vectors**, not decomposer predictions.

The slice proves that frozen or hand-authored candidate `ScopeNormalizedProgram`s can be
evaluated reproducibly under the frozen Q3 relation. It does **not** demonstrate
English→Program generation performance.

## Rework (R1–R4)

| id | correction |
|----|------------|
| R1 | `load_oracle_program(frozen, case_id)` requires verified `FrozenCandidate`; no case_id-only oracle path |
| R2 | `FrozenCandidate` is a frozen dataclass; canonical JSON is source of truth; `.program` / `to_runtime_program()` re-parse; post-freeze mutation cannot change the digest |
| R3 | `BENIGN_REDUNDANT_TASK` uses the frozen six predicates only (no duplicate-only gate); fixture is non-identical alias reconfigure with effect already true |
| R4 | Canonicalization tests: key-order, whitespace, null↔omitted, semantic digest change; plus pre-freeze oracle hard-fail |

## Acceptance matrix (18 fixtures)

Preserved corpus. `all_expected_fixture_outcomes_match = true`.

`oracle_access_before_freeze = 0` · digest collisions = 0 · decomposer calls = 0

## Evidence layout

```
evidence/nl_program_eval_harness_01_results.jsonl   ← replay.py
evidence/nl_program_eval_harness_01_summary.json    ← replay.py
evidence/nl_program_eval_harness_01.md              ← closeout-authored
evidence/nl_program_eval_harness_01/
  manifest.json
  candidates/*.json                                 ← pure ScopeNormalizedProgram payloads
```

## Explicit exclusions

- No real decomposer / model / T5 / Luna / LangGraph
- No MB-03 / production path
- No English→Program accuracy claim
- Comparator scoped to the six frozen EvaluationSpec surfaces
