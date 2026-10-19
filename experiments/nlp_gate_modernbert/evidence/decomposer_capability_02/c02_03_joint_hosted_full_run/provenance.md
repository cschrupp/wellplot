# Joint hosted full screening — Gemini + DeepSeek

```
AUTHORITY: WP-DC02-03-JOINT-HOSTED-FULL-RUN-AUTH-001
PARENT SHA: 27db77a3ca913b4298afef291f09064d9d1931d2
NEW LOGICAL CALLS: 10/10
CASE 1 RERUN: NO
BENCHMARK OBSERVATIONS: 12 (6 Gemini + 6 DeepSeek)
```

## Per-model summary

| Metric | Gemini | DeepSeek |
|--------|--------|----------|
| Reached freeze | 0/6 | 0/6 |
| Schema valid | 0/6 | 0/6 |
| Semantic eq (among frozen) | 0/0 | 0/0 |
| Semantic eq (overall) | 0/6 | 0/6 |
| Provider-reported USD | 0.03005 | 0.004802071 |
| Latency s (sum) | 76.049 | 66.017 |
| Prompt tokens | 4455 | 4304 |
| Completion tokens | 2114 | 7651 |

Decoding: `json_object` + freeze — **not** XGrammar hard-mask equivalent.

Original failed DeepSeek 1024-token smoke retained as qualification history only.

STATUS:
STOP FOR INDEPENDENT HOSTED SCREENING REVIEW
