# CM-59A — Production Planner and Safety System Reevaluation

## Status

- Baseline: `d8a49996125b48a7fd1c8385059ddaae97978069`
- Implementation checkpoint: the commit containing this pre-live slice
- Provider/endpoint calls: `0`
- Production changes: `0`
- Live inference: not authorized in this slice
- CM-58.4, P11, and CM-57D: blocked

## Purpose

CM-59A is the single system-level reevaluation gate after the production
planner and CM-58.1, CM-58.2, and CM-58.3 deterministic safety layers. It
measures the composed production path without invoking workers or changing
routing:

```text
SemanticPlanner
    -> capability safety
    -> report-boundary safety
    -> section-leaf safety
    -> bounded work-unit evaluation
```

The live population is one fresh 24-case corpus, two sequential attempts per
case, and the production planner only. Six families are represented with four
cases each. Two cases retain the Lichen residual class and two retain the
Mariner residual class so those known boundary classes remain visible rather
than being silently discarded.

## Frozen Contract

The harness binds each future row to the reviewed checkpoint, the exact corpus
and harness hashes, the production source hashes, the production planner prompt
and `SemanticPlan` schema hashes, the fixed source-summary hash, all three
CM-58 policy versions, and the frozen execution controls.

The future live sequence is:

```text
PRE GET /v1/models
    -> 48 sequential planner executions
    -> POST GET /v1/models
    -> provider-free finalization
```

Only endpoint/model-list provenance is claimed. The gate does not claim a
stable remote PID, binary, GGUF, or hardware process. Provider infrastructure
failures, endpoint drift, row corruption, provenance drift, worker calls, and
population corruption are inconclusive. Stable model/planner failures are
valid experimental failures and produce rejection, not inconclusive results.

## Decision Rules

The only terminal decisions are:

- `SYSTEM_REEVALUATION_ACCEPTED`
- `SYSTEM_REEVALUATION_REJECTED`
- `INCONCLUSIVE_SYSTEM_REEVALUATION`

Acceptance requires at least 22 of 24 stable passes, at least three stable
passes in every family, both fresh Lichen cases, both fresh Mariner cases,
zero planner terminal failures, wrong final-plan escapes, safety regressions,
unnecessary safety actions on raw-pass plans, reference violations, parent
closure violations, duplicate capability types, and unstable cases.

The historical Lichen and Mariner shapes in the pre-live report are
diagnostic-only anchors. They do not contribute to the future population or
decision.

## Hard Boundaries

This slice does not modify `src/wellplot`, prompts, schemas, capability
metadata, provider adapters, routing, workers, persistence, or graph topology.
It adds no retries, repair behavior, fallback, CM-58.4 logic, P11 work, or
typed-worker promotion. The pre-live implementation must be reviewed before
any endpoint is contacted.

## Pre-Live Result

The provider-free audit validates the fresh corpus, six-family balance,
historical freshness, production-byte equality with the baseline, frozen
planner/schema/source/catalog hashes, safety policy versions, and zero live
calls. The implementation stops here pending independent review and separate
live authorization.
