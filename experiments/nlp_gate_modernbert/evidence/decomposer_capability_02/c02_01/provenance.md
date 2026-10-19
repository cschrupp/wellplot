# C02-01 — Frozen benchmark and semantic oracle

```
PROGRAM:
WELLPLOT-DECOMPOSER-CAPABILITY-02

SLICE:
C02-01

AUTHORITY:
WP-DC02-01-BENCHMARK-ORACLE-AUTH-001

STARTING SHA:
a8ced8a69ee8c65e0bf292a6952d77b6ef9e2392

CANDIDATE SHA:
8965dfb3571f36f413359042238434dc7ee12a32

MODEL CALLS:
0

OPENROUTER CALLS:
0

DATASET EXPANSION:
false

C02-02:
NOT AUTHORIZED
```

## Deliverables

| Artifact | Path |
|----------|------|
| Benchmark references | `benchmark_manifest.json` + `oracle_refs/*.json` |
| Scoring contract | `semantic_scoring_contract.json` |
| Failure taxonomy | `failure_taxonomy.json` |
| Partition design | `split_manifest.json` |
| Repro vs deferred | `metrics_reproducibility.json` |
| Model inventory amend | `../model_inventory.json` (`WP-DC02-MODEL-INVENTORY-AMEND-001`) |

## Scientific notes

- Six-case gold inputs/oracles are immutable; DeepSeek addition does not alter gold.
- DeepSeek is a **planned budget-capability reference** in the model matrix only.
- Gemini remains the frontier ceiling; its OpenRouter id remains unresolved (C02-02 blocker).
- Diagnostic/sealed partitions are designed empty — population not authorized here.
- Primary judge remains the accepted NL-PROGRAM eval harness (`freeze_candidate` before oracle).

## Non-authorizations

```
Model inference / OpenRouter:   NOT AUTHORIZED
Dataset expansion / training:   NOT AUTHORIZED
C02-02 / G0:                    NOT AUTHORIZED
Production / WELL-IR changes:   NOT AUTHORIZED
```

STATUS:
STOP FOR INDEPENDENT C02-01 REVIEW
