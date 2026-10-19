# Hosted smoke corrective preparation (offline)

```
AUTHORITY: WP-DC02-03-HOSTED-SMOKE-CORRECTIVE-PREP-AUTH-001
PARENT: ace0e46b72801b243da9ce5f684ccfbf0f43a506
CANDIDATE SHA: 8dd74b0f5871ff6b0e9a052bd2ba305ba4811925
TIP SHA: 6d2c3a2aef90911e6ee40444bc2c0aaaef8d2dd3
API CALLS: 0
FULL RUN: NOT AUTHORIZED
```

## DeepSeek corrective pin (proposed)

- Provider: Morph (unchanged)
- `max_tokens`: **4096** (was 1024)
- `reasoning.effort`: **low** (Morph-supported)
- Prompt/oracle/case unchanged
- Original empty-content smoke retained immutable

## Cost accounting

- Observed charge := OpenRouter `usage.cost`
- Pre-run estimate retained for comparison
- Gemini 2× gap: flex $1/$5 estimate vs reported catalog-equivalent $2/$10

## Gemini schema

Offline re-freeze confirms `DECOMPOSITION_SCHEMA_INVALID`. Do not treat
`semantically_equivalent=false` as a completed semantic comparison.

STATUS:
STOP FOR INDEPENDENT CORRECTIVE-PREP REVIEW
