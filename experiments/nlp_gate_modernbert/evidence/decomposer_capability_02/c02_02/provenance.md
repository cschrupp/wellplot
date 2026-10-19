# C02-02 — Model/provider harness qualification

```
PROGRAM: WELLPLOT-DECOMPOSER-CAPABILITY-02
SLICE: C02-02
AUTHORITY: WP-DC02-02-PROVIDER-HARNESS-QUALIFICATION-AUTH-001
STARTING SHA: 9025ecbb6c2ceaf4a2ee89da53a1242eb96d7f67

LIVE INFERENCE CALLS: 0
BILLABLE OPENROUTER CALLS: 0
MODEL WEIGHTS LOADED: false

GEMINI ENDPOINT: RESOLVED → google/gemini-4-argon
DEEPSEEK ENDPOINT: RESOLVED → deepseek/deepseek-v4.1-flash-1017
```

## Qualified adapter paths

| Path | Transport | Structured output |
|------|-----------|-------------------|
| Gemini 4 Argon | OpenRouter (mocked) | json_object + freeze |
| DeepSeek V4.1 Flash 1017 | OpenRouter (mocked) | json_object + freeze |
| Qwen3-4B-Instruct-2507 | Local HF contract (mocked) | prompted JSON (+ future constraint) |
| Qwen3-4B-Thinking-2507 | Local HF contract (mocked) | prompted JSON; grade final answer only |

Hard XGrammar parity with Pilot Run 1 is **unsupported** for these paths in C02-02.

## Snapshots

Public OpenRouter catalog/endpoints snapshots under `openrouter_snapshots/` (not inference).

## Non-authorizations

```
C02-03..C02-17: NOT AUTHORIZED
G0: NOT AUTHORIZED
Fine-tuning / benchmark expansion / production changes: NOT AUTHORIZED
```

STATUS:
STOP FOR INDEPENDENT C02-02 REVIEW
