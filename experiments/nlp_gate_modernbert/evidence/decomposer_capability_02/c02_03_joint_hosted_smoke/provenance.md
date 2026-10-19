# Joint hosted smoke — Gemini + DeepSeek

```
AUTHORITY: WP-DC02-03-JOINT-HOSTED-SMOKE-AUTH-001
PARENT SHA: ab6fcd29f4545e0128afaefb2c1b032df8f30bc7
SMOKE CASE: D5GAP-0085
LOGICAL CALLS: 2/2
TRANSPORT ATTEMPTS: 2/4
ESTIMATED USD: 0.0043264
CASES 2–6: NOT EXECUTED
BOTH OPERATIONAL PASS: False
```

## Outcomes

| Arm | Operational | Semantic eq | Provider | Tokens (p/c) | Error |
|-----|-------------|-------------|----------|--------------|-------|
| Gemini | True | False | Google AI Studio | 614/615 | None |
| DeepSeek | False | None | Morph | 575/1024 | parse_error:ValueError:empty_generation |

### DeepSeek note

Empty `message.content` after 1024 completion tokens (`finish_reason=length`). Operational smoke **FAIL**.

### Gemini note

Operational smoke **PASS**. Semantic non-equivalence does not fail the smoke gate.

XGrammar hard-mask equivalence is not claimed.

STATUS:
STOP FOR INDEPENDENT JOINT SMOKE REVIEW
