# WELL-IR Encoder Gate Experiment

**Authority (current):** `WELLPLOT-NLP-RUNTIME-V2-MB01-GATE-CORPUS-AUDIT-REWORK-AUTH-001`  
**Prior:** MB-00 **ACCEPTED**; MB-01 initial audit **REVISE** → MB-01R  
**Plan amendment:** **R1** — MB-03 bake-off remains blocked; encoder viability under review  
**Parent plan:** `docs/experiments/nlp-runtime-v2-codex-execution-plan.md`

## Gate viability (MB-01R)

| Metric | Value |
|---|---|
| Deterministic/static authority | **300 / 300** |
| `LEARNED_SEMANTIC_GATE` | **0** |
| `learned_gate_status` | **`NO_LEARNED_GATE_REQUIRED`** |

Do not manufacture learned examples to justify an encoder bake-off. Next scientific step after MB-01 acceptance: **MB-02** deterministic resolver/capability layer.

## Slice status

| Slice | Status |
|---|---|
| MB-00 Bootstrap | **ACCEPTED / CLOSED** |
| MB-01 Gate corpus audit | REVISE → **MB-01R DONE — STOP FOR RE-REVIEW** |
| MB-02 Deterministic fact projector | NOT AUTHORIZED |
| MB-03 3-arm encoder bake-off | **BLOCKED** (+ no learned residual on this corpus) |
| MB-04 / MB-05 | NOT AUTHORIZED |

## Commands

```bash
cd experiments/nlp_gate_modernbert
PYTHONPATH=src ../nlp_slm_01/.venv/bin/python -m nlp_gate_modernbert mb01-publish
PYTHONPATH=src ../nlp_slm_01/.venv/bin/python -m pytest tests -q
```

## Deliverables

`evidence/` (and `evidence/mb01_gate_corpus/`): the six MB-01 JSON/JSONL artifacts plus `uq_resolutions.json`.  
Handoff: `evidence/mb01_handoff.md`

## HARD STOP

Do not start MB-02 without explicit acceptance of the MB-01R handoff.
