# CM-56 Post-R4 Typed Shadow Development Memory

## Status

- Slice: post-CM-56R4 typed-worker shadow gate
- Baseline: `f11b595`
- Implementation status: pre-live checkpoint
- Production changes: none
- CM-57: blocked

## Purpose

CM-56R4 closed with `FORENSICS_NO_REPRODUCTION` for the earlier planner and
source-selection observations. This evaluation-only wrapper now runs the full
frozen CM-56 planner/enricher boundary followed by the existing typed worker.
It does not change the planner, enricher, typed worker, compiler, routing, or
public engine.

The question is whether the current production planner source-summary boundary
and the frozen typed-worker input are sufficient for a clean shadow gate.

## Frozen Controls

- Case corpus: unchanged CM-56 ten-case corpus.
- Corpus SHA-256: `4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e`.
- Planner temperature: `0.0`.
- Worker temperature: `1.0`.
- Maximum output tokens: `16384`.
- Request timeout: `900` seconds.
- Typed system prompt SHA-256: `19b0e289d2fa8ea362840aa94d90ad43cdea5b2ebdc866363df1ef28a38f2d49`.
- Typed response schema SHA-256: `93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4`.

The planner receives the exact production source-summary shape: source labels
only, with empty channel arrays. The worker receives the existing frozen typed
input serialization and response schema. Paths, canonical IDs, and raw
provider responses are not written to evidence.

## Gate

Stage one runs three sequential attempts for every frozen case. Stage two is
allowed only if stage one is clean and completes the remaining attempts: seven
additional CBL attempts (ten total) and two additional attempts for each other
case (five total). Main and repeat sections remain separate within the CBL
case.

Decision precedence is:

```text
planner failure             -> STOP_PLANNER_RELIABILITY
enrichment/input failure    -> STOP_INPUT_CONTRACT
typed structured failure    -> STOP_SCHEMA_COMPATIBILITY
typed provider infra        -> STOP_PROVIDER_RELIABILITY
context validation failure  -> STOP_TYPED_CONTEXT_GROUNDING
compiler/representability   -> STOP_DETERMINISTIC_BOUNDARY
semantic mismatch           -> STOP_TYPED_WORKER_SEMANTICS
otherwise                   -> proceed to the next stage
```

Every completed attempt is flushed to JSONL immediately. Stage summaries are
written only after their requested stage completes; an interrupted run remains
partial evidence and cannot be interpreted as a completed gate.

## Hard Stop

This slice is evaluation-only. Do not modify production routing or worker
behavior, add repair/retry policy, alter the acceptance contract, or begin
CM-57. Run stage one first, review its summary, and stop before stage two unless
the stage-one gate is clean.

**PROCEED to the stage-one live gate only after review of this checkpoint.**
