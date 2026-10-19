# WELL-IR Encoder Gate / Runtime V2 Experiment

**Authority (current):** `WELLPLOT-NLP-RUNTIME-V2-MB02-DETERMINISTIC-RESOLVER-FACT-PROJECTOR-AUTH-001`  
**Prior:** MB-00 ACCEPTED; MB-01R ACCEPTED (`NO_LEARNED_GATE_REQUIRED`)

## MB-02 claim

`NormalizedRequest` + `ProjectedWorkspace` → derived facts → deterministic envelope.  
**No** claim about English → `NormalizedRequest`.

## Gate viability

| Metric | Value |
|---|---|
| Learned residual (MB-01R) | **0 / 300** |
| `learned_gate_status` | **`NO_LEARNED_GATE_REQUIRED`** |
| MB-03 bake-off | **BLOCKED / NOT JUSTIFIED** |

## Slice status

| Slice | Status |
|---|---|
| MB-00 | ACCEPTED |
| MB-01R | ACCEPTED |
| MB-02 Deterministic resolver / fact projector | **DONE — STOP FOR REVIEW** |
| MB-03 Encoder bake-off | BLOCKED |
| MB-04 / MB-05 / T5 / LangGraph / SLM-04 | NOT AUTHORIZED |

## Commands

```bash
cd experiments/nlp_gate_modernbert
PYTHONPATH=src:../nlp_slm_01:../../src ../nlp_slm_01/.venv/bin/python -m nlp_gate_modernbert mb02-normalize
PYTHONPATH=src:../nlp_slm_01:../../src ../nlp_slm_01/.venv/bin/python -m nlp_gate_modernbert mb02-replay
PYTHONPATH=src:../nlp_slm_01:../../src ../nlp_slm_01/.venv/bin/python -m pytest tests -q
```

Handoff: `evidence/mb02_handoff.md`
