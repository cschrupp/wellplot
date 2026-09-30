# CM-59A-R2C-A - Schema Validation Shape Diagnosis

## Status

- Baseline: `17540f98c9c035ae07385b28c71bd11dccff323b`
- Experiment: `CM-59A-R2C-A`
- Contract: `cm59a.r2c.a.schema-validation-shape.v1`
- Provider calls during implementation and verification: `0`
- Endpoint calls during implementation and verification: `0`
- Worker/program calls during implementation and verification: `0`
- Live diagnostic: not authorized
- CM-59A-E2: complete / valid rejection
- CM-57D: blocked

## Purpose

CM-59A-E2 showed identical observable planner paths for both stable failures:

```text
INITIAL
  -> invalid_response / schema_validation
SCHEMA_CORRECTION
  -> invalid_response / schema_validation
```

The accepted E2 raw evidence is bound to SHA-256
`2bb81a185c64700e6f283ad67fc985fa77b5329ba785af344347f5a5b56158af`.
R2C-A diagnoses whether the Kestrel and Xenon failures have the same bounded
Pydantic validation shape or different shapes. It does not attempt recovery.

## Diagnostic Boundary

Only these runtime files are instrumented:

- `src/wellplot/agent/providers/response_diagnostics.py`
- `src/wellplot/agent/providers/openai_compat_v2.py`

The adapter retains only a frozen, bounded shape containing sanitized error
types and locations. It never retains raw JSON, values, messages, context,
URLs, exception text, request prose, or undeclared model field names. Unknown
field locations become `<unknown_field>` and list indices become `*`. Root
validation becomes `$root`; locations are bounded to eight segments and issue
retention to sixteen after deterministic sorting.

The outer `INVALID_RESPONSE` category, `schema_validation` reason, safe
message, retryability, status, `diagnostic_metadata()`, planner call budget,
correction prompt, and planner behavior remain unchanged. Planner code does
not inspect the shape. E2's historical provider hashes and evidence remain
frozen and are not rewritten for this instrumentation.

## Frozen Population

The future diagnostic population is exactly:

- `cm59-report-kestrel-04`, two attempts;
- `cm59-mixed-xenon-21`, two attempts;
- four planner executions, four to eight provider calls;
- planner-only execution, zero CM-58 safety, enrichment, worker, or program calls.

The unchanged corpus SHA is
`b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b`.
The frozen endpoint identity is
`23afb5ebf67063154bcf02ada6d25b2c929250b14c6a4cad06e8649d087bc980`.
Prompt, schema, source-summary, model, token, timeout, and concurrency
controls remain those recorded in the authorization.

## Decision Rules

The provider-free finalizer uses this precedence:

1. population, endpoint, provenance, infrastructure, collision, or budget
   failure -> `INCONCLUSIVE_DIAGNOSTIC`;
2. missing or truncated schema shape -> `DIAGNOSTIC_INSTRUMENTATION_GAP`;
3. all four executions succeed without schema validation ->
   `FAILURES_NOT_REPRODUCED`;
4. two stable equal non-empty signatures ->
   `STABLE_SHARED_VALIDATION_SIGNATURE`;
5. two stable unequal non-empty signatures ->
   `STABLE_DISTINCT_VALIDATION_SIGNATURES`;
6. within-case variation -> `VARIABLE_VALIDATION_SIGNATURE`;
7. remaining combinations -> `MIXED_DIAGNOSTIC_OUTCOME`.

The ordered signature includes every schema-validation observation as
`(call_kind, validation_shape)`, not only the terminal correction failure.
No remediation recommendation is produced by the harness.

## Pre-Live Boundary

The new diagnostic script defaults to provider-free `PRELIVE_READY` checks.
Its future live path requires the exact reviewed checkout, frozen corpus and
contracts, empty evidence/PRE/POST/summary paths, valid PRE endpoint identity,
sequential Kestrel then Xenon attempts, immediate POST capture, and no resume,
append, smoke call, or selective rerun. Finalization reads local artifacts
only. Live execution is not authorized by this slice.

## Verification Requirements

Focused tests cover sanitized missing/extra/value/root/list diagnostics,
sixteen-issue truncation, extraction fallback, non-schema shape absence,
shared/distinct/variable/not-reproduced/mixed/gap decisions, endpoint drift,
artifact collision, provider-free pre-live behavior, and evidence redaction.

Historical scripts and the E2 summary are unchanged. Conditional isolation of
historical tests is allowed only if a full-suite failure is proven to be frozen
provider-source drift; unrelated failures stop the verification process.

## Pre-Live Verification Result

The conditional E2 test isolation was required and remained test-only. Four E2
success-path assertions failed solely because the two authorized provider
instrumentation files no longer matched the historical E2 bytes. The isolation
substitutes current bytes only for those exact two paths in those modern test
success paths; the historical E2 script, summary, raw evidence, and hashes are
unchanged. The provider-drift regression remains fail-closed.

```text
R2C-A focused/provider/planner tests: 114 passed
E2 and R2A adjacent tests: 112 passed
Full repository suite: 2293 passed, 13 accepted baseline failures, 3 skipped
New R2C-A-attributable failures: 0
Ruff: passed
Formatting: passed
Python compilation: passed
JSON validation: passed
git diff --check: passed
Provider calls: 0
Endpoint calls: 0
Worker/program calls: 0
```

The accepted baseline failures remain the unrelated MCP helper signature,
tool-budget, historical R6 evidence, stale P7 artifact, graph-worker, and
graph-section categories. No R2C-A live population was run.

## R2C-A-R1 Pre-Live Hardening

R2C-A-R1 is a harness-only correction on top of `c5ae4966ba2eeb2d8027627efb893a0ca4ff41a8`.
The provider instrumentation remains byte-frozen; no provider, planner, schema,
workflow, safety, capability, or worker source changed. Provider calls remain
zero.

The finalizer now treats `FAILURES_NOT_REPRODUCED` as conclusive only when all
four integrity-checked planner executions have a final plan, no final error,
and no infrastructure failure. Non-schema terminal outcomes such as invalid
JSON, provider rejection, and planner semantic failure produce
`MIXED_DIAGNOSTIC_OUTCOME` rather than success.

Evidence call traces now require contiguous indexes and the exact production
transitions: schema failures must use `SCHEMA_CORRECTION`, non-schema invalid
responses must use `INVALID_RESPONSE_RETRY`, and semantic correction must
follow initial structured success. A schema failure without correction is
`schema_correction_missing`.

Shape integrity now matches the provider producer: exact top-level and issue
fields, the bounded error-type vocabulary, declared `SemanticPlan` property
locations or fixed sentinels only, coherent truncated counts, and exact
location truncation representation. If population integrity fails, summary
shape projections and shape-derived counters are omitted rather than copying
tampered evidence into the final artifact.

R1 verification:

```text
R2C-A-R1 focused/provider/planner tests: 126 passed
E2 and R2A adjacent tests: 112 passed
Provider-free PRELIVE_READY audit: passed
Ruff: passed
Formatting: passed
Python compilation: passed
git diff --check: passed
Provider calls: 0
Endpoint calls: 0
Worker/program calls: 0
```

R2C-A-R1 remains pre-live only. Do not contact the endpoint or run Kestrel or
Xenon until an independent review authorizes the future population.

## R2C-A-R2 Final Pre-Live Closure

R2C-A-R2 is a harness/test/documentation-only correction on top of
`98f5135a939ad73cd8a0fbb8ef3041f2bf3277ff`. The imported historical helper
`scripts/cm59a_system_reevaluation.py` is now protected against byte drift
against the frozen behavioral baseline. The helper itself remains unmodified.

Summary validation shapes are rebuilt through a fresh bounded projection with
new issue dictionaries and location lists. The finalizer never returns raw
shape dictionaries by reference, and malformed populations continue to omit
all shape-derived summary output and remain inconclusive.

R2 verification:

```text
Focused/provider/planner tests: 128 passed
Adjacent E2/R2A tests: 112 passed
Historical-helper drift regression: PASS
Summary projection aliasing regression: PASS
Full repository suite: 2307 passed, 13 accepted baseline failures, 3 skipped
Full-suite failure identities: MATCH ACCEPTED BASELINE
New R2C-A-attributable failures: 0
Ruff: passed
Formatting: passed
Python compilation: passed
JSON validation: passed
git diff --check: passed
Provider calls: 0
Endpoint calls: 0
Worker/program calls: 0
```

The full repository suite is mandatory before the R2 checkpoint is frozen.
The accepted baseline remains the exact established 13 failure identities and
3 skipped tests; no R2C-A live population is authorized by this slice.

## Hard Stop

After the implementation checkpoint is committed and pushed, stop for
independent pre-live review. Do not contact the endpoint, run Kestrel or
Xenon, alter the schema or correction prompt, add retries, relax validation,
repair JSON, start R2C recovery, adopt the instrumentation into production, or
start CM-57D.
