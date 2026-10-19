# DECOMPOSER-PILOT-01 / RUN 1 — Closed

```
SLICE:
DECOMPOSER-PILOT-01 / RUN 1

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-01-AUTH-001

EXECUTION VALIDITY:
VALID

AUTHORIZED CALLS:
6/6

RUNTIME:
CPU / FP32

MODEL CALLS ADDED BY CORRECTION:
0

CORRECTION CANDIDATE SHA:
96bbbbf7f6105f03ef9fc559d506e40cb364a5e2

FROZEN CANDIDATES:
5/6

DECODE FAILURE:
1/6

SCHEMA INVALID:
0/6

SEMANTIC EQUIVALENTS:
0/5 frozen (0/6 overall)

FROZEN MECHANICAL VERDICT:
INCONCLUSIVE
```

## Evidence correction

D5GAP-0101 terminated at exactly `max_new_tokens=1024` without a complete legal
object. Per frozen design, that is `DECOMPOSITION_DECODE_FAILURE`, not
`DECOMPOSITION_SCHEMA_INVALID`. Raw tokens and payload bytes are unchanged.
No model calls were added.

## Layer 0 / 1 / 2

| Layer | Result |
|-------|--------|
| 0 reached_freeze | 5/6 |
| 0 decode failures | 1 |
| 0 schema-invalid | 0 |
| 1 semantically_equivalent | 0/6 |
| 2 veto A | False [] |
| 2 veto B | False [] |

## Per-case

| Case | Freeze | Equivalent | Labels | Termination |
|------|--------|------------|--------|-------------|
| D5GAP-0085 | FROZEN | False | MISSING_TASK,WRONG_ORDER | - |
| D5GAP-0089 | FROZEN | False | RUNTIME_TERMINAL_MISMATCH | - |
| D5GAP-0117 | FROZEN | False | RUNTIME_TERMINAL_MISMATCH | - |
| D5GAP-0096 | FROZEN | False | WRONG_BINDING,WRONG_OPERATION | - |
| D5GAP-0101 | DECOMPOSITION_DECODE_FAILURE | False | DECOMPOSITION_DECODE_FAILURE | max_new_tokens |
| SEED-cm-9643c020e2e02463 | FROZEN | False | RUNTIME_TERMINAL_MISMATCH | - |

## Scientific interpretation

Strong negative evidence against the exact Qwen3-1.7B zero-shot constrained-
decomposition hypothesis on this six-case probe. The frozen protocol yields
INCONCLUSIVE because Layer 0 was not 6/6; a formal ≤4/6 family-failure
verdict is therefore not issued from this run.

This CPU/FP32 run is retained permanently as Pilot Run 1. It is not invalidated
by the classification correction. A GPU rerun of the same experiment is not a
correction of this run.

## Independent review disposition

```
EXECUTION: VALID
CLASSIFICATION_CORRECTION: ACCEPTED (D5GAP-0101 → DECOMPOSITION_DECODE_FAILURE)
MECHANICAL_VERDICT: INCONCLUSIVE
RUN_1: CLOSED
NEXT: deliberately designed follow-on experiment (not silent CUDA substitution)
```

STATUS:
DECOMPOSER-PILOT-01 RUN 1 CLOSED
