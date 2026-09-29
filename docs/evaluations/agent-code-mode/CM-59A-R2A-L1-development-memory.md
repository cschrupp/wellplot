# CM-59A-R2A-L1 - Xenon Structured-Response Diagnostic

## Status

- Production anchor: `866037452f6c1944297d62270756b4e3a5322125`
- Diagnostic: `CM-59A-R2A-L1`
- Target: `cm59-mixed-xenon-21`
- Request SHA-256: `c0f175abcb01eb875126d2bd3a2a8a6cd2efcf2207494419ce27edc82d8802c5`
- Corpus SHA-256: `b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b`
- Attempts: `2`
- Future planner executions: `2`
- Future provider calls: `2-4`
- Future worker/program calls: `0`

## Purpose

L1 characterizes the historical Xenon planner failure using the accepted
CM-59A-R2A structured-response diagnostics. It uses the frozen corpus case
without paraphrase, runs only `SemanticPlanner.plan()`, and records bounded
call classifications and response reasons. It is not a remediation, prompt
experiment, promotion gate, or production-adoption gate.

The nine authorized local response reasons are:

- `unusable_choice`
- `missing_message`
- `non_assistant_message`
- `incomplete_output`
- `unexpected_finish_reason`
- `tool_call`
- `missing_content`
- `invalid_json`
- `schema_validation`

## Evidence Boundary

Rows retain no request prose, safe messages, provider response text, raw JSON,
validation details, tool arguments, headers, credentials, or endpoint secrets.
Successful plans are reduced to bounded semantic projections and facts. The
existing production retry behavior is used unchanged; L1 adds no retry,
repair, safety layer, worker, or program call.

Future live provenance uses the v2 endpoint fingerprint with PRE and POST
normalized identity comparison. The first inference after PRE is Xenon attempt
zero. There is no warm-up request, resume, append, or replacement behavior in
this harness.

## Pre-Live Result

The implementation phase made zero provider, endpoint, worker, or program
calls. The default command is provider-free and reports `PRELIVE_READY` only
after validating the frozen corpus, prompt, schema, source summary, response
reason taxonomy, and production-anchor bytes.

Live inference is not authorized by this slice. `CM-59A-R2B`, `CM-59A-E2`, and
`CM-57D` remain blocked pending independent review and separate authorization.

## R1 Verification Hardening

Baseline: `47843e62466fde9a4813a8fc53f5601993a07c9d`.

R1 adds provider-free verification coverage without changing the diagnostic
harness or production code. The tests cover one-call transport failures,
artifact collision guards, exact checkpoint validation, incomplete CLI
authorization, population tampering, partial populations, diagnostic-gap
classification, provider-free finalization, and bounded summary redaction.

The harness remains unchanged from the baseline, and live inference remains
unauthorized. No provider, endpoint, worker, or program calls are made by R1.
