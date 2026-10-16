# NL-PROGRAM-EVAL-HARNESS-01 — Q3 evaluator closeout

```
SLICE:
NL-PROGRAM-EVAL-HARNESS-01

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-NL-PROGRAM-EVAL-HARNESS-01-AUTH-001

STARTING SHA:
4aaf96ebd9275886608a3a9901f218206dca6551

PRIOR SUBJECT (NL-PROGRAM-DESIGN-01R2):
4aaf96ebd9275886608a3a9901f218206dca6551

CANDIDATE SHA:
<pending commit>

HISTORICAL GOLD:
UNCHANGED

MB-02R / SCOPE-RUNTIME / ORACLE-01:
UNCHANGED

STATUS:
STOP FOR INDEPENDENT NL-PROGRAM-EVAL-HARNESS-01 REVIEW
```

## CLAIM

These artifacts are **harness test vectors**, not decomposer predictions.

The slice proves that frozen or hand-authored candidate `ScopeNormalizedProgram`s can be
evaluated reproducibly under the frozen Q3 relation. It does **not** demonstrate
English→Program generation performance.

## Acceptance matrix (18 fixtures)

| class | n | required outcome |
|-------|---|------------------|
| `{case}_oracle_equivalent` | 6 | EQUIVALENT + terminal OK + all REQUIRED_REPRESENTABLE covered |
| wrong_operand | 1 | WRONG_OPERAND |
| missing_task | 1 | MISSING_TASK |
| wrong_binding | 1 | WRONG_BINDING |
| wrong_order | 1 | WRONG_ORDER |
| wrong_dependency | 1 | WRONG_DEPENDENCY |
| semantic_overreach | 1 | SEMANTIC_OVERREACH |
| runtime_mismatch | 1 | RUNTIME_TERMINAL_MISMATCH |
| benign_redundant | 1 | EQUIVALENT + BENIGN_REDUNDANT_TASK |
| alpha_renamed_bind | 1 | EQUIVALENT |
| independent_order_variant | 1 | EQUIVALENT |
| alias_equivalent | 1 | EQUIVALENT |
| schema_invalid | 1 | DECOMPOSITION_SCHEMA_INVALID; no digest; no oracle access |

`all_expected_fixture_outcomes_match = true`  
`oracle_access_before_freeze = 0`  
`candidate_digest_collisions = 0`  
`real_decomposer_calls = 0`  
`oracle_candidate_generation_at_runtime = 0`

## Evidence layout

```
evidence/nl_program_eval_harness_01_results.jsonl   ← replay.py
evidence/nl_program_eval_harness_01_summary.json    ← replay.py
evidence/nl_program_eval_harness_01.md              ← closeout-authored
evidence/nl_program_eval_harness_01/
  manifest.json                                     ← expected_evaluation for replay assertion only
  candidates/*.json                                 ← pure ScopeNormalizedProgram payloads
```

Manifest `expected_evaluation` is **not** passed to `freeze.py`, SCOPE-RUNTIME, or `compare.py`.

## Explicit exclusions

- No real decomposer / model / T5 / Luna / LangGraph
- No MB-03 / production path
- No English→Program accuracy claim
- Comparator complete only for the six frozen EvaluationSpec surfaces; unsupported constructs fail closed as `COMPARATOR_SCOPE_UNSUPPORTED`
