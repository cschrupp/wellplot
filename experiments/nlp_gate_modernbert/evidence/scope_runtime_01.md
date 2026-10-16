# SCOPE-RUNTIME-01 — Executable NormalizedProgram replay

```
SLICE:
SCOPE-RUNTIME-01

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-SCOPE-RUNTIME-01-AUTH-001

STARTING SHA:
0c1e6c8420ced10da5aea691f6ceecc5ac7cd2e8

ACCEPTED SCOPE-DESIGN-01R SUBJECT:
0c1e6c8420ced10da5aea691f6ceecc5ac7cd2e8

CANDIDATE SHA:
PENDING

HISTORICAL GOLD:
UNCHANGED

MB-02R:
UNCHANGED (adjudication adapter only)

ORACLE-01:
UNCHANGED

STATUS:
STOP FOR INDEPENDENT SCOPE-RUNTIME-01 REVIEW
```

## CLAIM

This slice proves executable NormalizedProgram → deterministic program terminal
behavior for the six frozen witnesses. It does not prove or exercise raw
English → NormalizedProgram.

## Replay (6/6)

| case_id | program terminal | notes |
|---------|------------------|-------|
| D5GAP-0085 | OK | scale configure → BETWEEN_INSTANCES |
| D5GAP-0089 | OK | narrow scale → fill on Workspace₁ |
| D5GAP-0096 | OK | `$track1` → `track N` adapter |
| D5GAP-0101 | OK | CREATE_TRACK + place/configure CALI |
| D5GAP-0117 | OK | configure RHOB → BASELINE_SPLIT |
| SEED-cm-9643c020e2e02463 | OK | ordered place/configure on `$track1` |

**n_program_ok: 6 / 6**

## Negative tests

| test | result |
|------|--------|
| failed task → no effect / no bind / later not run | PASS |
| illegal local_ref → DETERMINISTIC_SCHEMA_DOMAIN / zero tasks | PASS |

## Aggregate counters

- frontier_calls: 0
- gold_decision_inputs: 0
- mb02r_modified: false
- historical_gold_modified: false
- all_task_effects_post_ok_only: true
- all_local_ref_adapters_resolved_from_binding_table: true
- tests: 41 passed (suite)

## Epistemic boundary

Witness programs loaded from `scope_contract_design_01.json` (`normalized_program` + fixture only). Gold ops are never translated into tasks at runtime.

## Explicit exclusions

English→NormalizedProgram · LangGraph · T5 · MB-03 · SLM-04 · general DAG · production integration · document/renderer simulation · new ops/effects beyond frozen surface

## Artifacts

- `scope_runtime_01_results.jsonl`
- `scope_runtime_01_summary.json`
- `scope_runtime_01.md`
