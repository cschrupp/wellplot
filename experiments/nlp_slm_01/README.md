# experiments/nlp_slm_01

Isolated WELL-IR semantic-compiler feasibility study (SLM-01).

## Setup

```bash
cd experiments/nlp_slm_01
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
# optional model runners:
# uv pip install -e ".[eval]"
```

## Key commands

```bash
python scripts/build_inventory.py
python scripts/schema_compat_probe.py
python scripts/generate_gold_corpus.py
python scripts/run_lowerer_gold.py
python scripts/freeze_and_gate.py
pytest -q
```

## Layout

- `well_ir/` — Pydantic WELL-IR v1
- `lowerer/` — deterministic apply + contracts
- `benchmark/` — gold, splits, fixtures, inventory, evidence
- `eval/` — metrics / gate helpers
- `runners/` — historical / cloud / Qwen arms
- `scaffold/qlora/` — SLM-02 handoff only (no training)

## Artifact policy

`artifacts/` is gitignored. Commit evidence summaries under `benchmark/evidence/`, never model weights.
