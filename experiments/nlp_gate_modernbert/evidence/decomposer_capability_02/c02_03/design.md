# C02-03 — Gemini 4 Argon capability ceiling (DESIGN ONLY)

```
PROGRAM: WELLPLOT-DECOMPOSER-CAPABILITY-02
SLICE: C02-03
AUTHORITY: WP-DC02-03-GEMINI-CEILING-DESIGN-AUTH-001
STARTING SHA: 2db64aa96549e96161ff8cb2e7df2f03c885be55
CANDIDATE SHA: 8225f5d8da629927bc240ac79177c3d75457d0ba
TIP SHA: 07825ac43d3e7f1a5db619b126ef7825c7f86721

MODEL: google/gemini-4-argon
MODEL CALLS: 0
OPENROUTER CALLS: 0
INFERENCE: NOT AUTHORIZED
```

## Claim

This slice freezes the frontier-ceiling **protocol**. It is not evidence of Gemini performance.

## Scientific question

Can Gemini 4 Argon, under the frozen six-case semantic contract and disclosed non-XGrammar decoding, produce programs the accepted harness judges semantically equivalent?

## Frozen protocol (summary)

| Element | Freeze |
|---------|--------|
| Cases | Same six, same order as Pilot Run 1 |
| Prompt | Exact pilot system/user template hashes |
| Oracle/scoring | Unchanged nl_program_eval; freeze before oracle |
| Decoding | `response_format: json_object` + `freeze_candidate` — **not** XGrammar hard mask |
| Provider | Request-pinned (preferred Google AI Studio); record requested + observed |
| Calls | 6 logical cases; 0 semantic retries; transport retries ≤2 for eligible HTTP only |
| Accounting | Retain usage always; charge attempts on parse/freeze failure |
| Decision | Pilot Layer 0/1/2 + CEILING_PASS / REPRESENTATION_SUSPECT / PROTOCOL_DEFECT / INCONCLUSIVE |

## Comparability with Pilot Run 1

Pilot used XGrammar hard-constrained decode. This design **does not claim** decoding identity. Results remain scientifically informative as a disclosed-decoding capability ceiling, and the run report must state the mismatch explicitly.

## Unresolved execution blockers

See `design.json` → `unresolved_execution_blockers` (B1–B5 blocking for any live run; D1 deferred; D2 accepted non-equivalence).

## Non-authorizations

No Gemini/DeepSeek/Qwen inference. No C02-04+. No training. No dataset expansion.

STATUS:
STOP FOR INDEPENDENT C02-03 DESIGN REVIEW
