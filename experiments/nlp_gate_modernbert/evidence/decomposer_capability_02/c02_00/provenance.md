# C02-00 — Experimental provenance and baseline recovery

```
PROGRAM:
WELLPLOT-DECOMPOSER-CAPABILITY-02

SLICE:
C02-00

AUTHORITY:
WP-DC02-00-BASELINE-RECOVERY-AUTH-001

PHASE-0 DESIGN ACCEPTANCE:
WP-DC02-PHASE0-DESIGN-ACCEPT-001

STARTING REPOSITORY TIP:
b451d9ca431c235e5779340f9dcc188764cb1446

MODEL CALLS:
0

OPENROUTER CALLS:
0

MODEL WEIGHTS LOADED:
false

SYNTHETIC RECREATION:
false
```

## Baseline recovered

DECOMPOSER-PILOT-01 / RUN 1 (Human ACCEPTED / CLOSED at `b451d9c`).

| Property | Recovered value |
|----------|-----------------|
| Model | Qwen/Qwen3-1.7B |
| Runtime | CPU / FP32 |
| Calls | 6/6 |
| Reached freeze | 5/6 |
| Semantic equivalents among frozen | 0/5 |
| Mechanical verdict | INCONCLUSIVE |
| Original run candidate | 32edc35 |
| Classification correction | 96bbbbf (D5GAP-0101 → DECOMPOSITION_DECODE_FAILURE) |
| Accepted tip | 6f772b5 |
| Human acceptance commit | b451d9c |

## What was recovered (not invented)

- Six-case invocation order and per-case model-facing inputs via accepted `build_decomposer_input` + workspace serializer; digests verified against frozen preflight case hashes and Run 1 `input_hashes`.
- Run 1 raw outputs, token ids, failure labels, and freeze outcomes from `decomposer_pilot_01_results.jsonl`.
- Prompt, inference, serializer, and grammar pin digests from live code/constants and on-disk grammar artifacts.
- Authorization, summary, run manifest, and Human acceptance evidence files (SHA256 inventory in `recovered_pilot_manifest.json`).

Machine-readable archive: `case_archive/<case_id>/{recovered_input,run1_output,run1_generated_token_ids}.json`.

## Explicitly not recovered / deferred

See `missing_evidence_report.json`. Notably:

- Exact OpenRouter model id for Gemini 4 Argon — **NOT_RESOLVED** (required before C02-02 acceptance).
- Live re-hash of `rendered_model_input_sha256` — deferred (would require tokenizer load; not performed).
- Historical Phi/Gemma/monolithic SLM comparisons — out of scope for this decomposer baseline; must not be mixed into the pilot verdict.

## Non-authorizations

```
C02-01 / C02-02 execution:     NOT AUTHORIZED BY THIS SLICE
Scientific inference:          NOT AUTHORIZED
OpenRouter / Gemini calls:     NOT AUTHORIZED
Fine-tuning:                   NOT AUTHORIZED
C02-03..C02-17:                PROPOSED ONLY (not frozen inventory)
```

STATUS:
STOP FOR INDEPENDENT C02-00 REVIEW
