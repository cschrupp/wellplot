# CM-59A — Production Planner and Safety System Reevaluation

## Status

- Baseline: `d8a49996125b48a7fd1c8385059ddaae97978069`
- Implementation checkpoint: the commit containing this corrected pre-live slice
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

## Pre-Live Review Corrections

The Lichen P anchor is section-only with a spurious empty report task. Its
gold contains no report capability, CM-58.2 removes the report task, and the
three original section signatures then pass unchanged. The Lichen RC anchor
remains a mismatch because it lacks the normal track in its reference section.

The two Lichen and two Mariner population requests were independently
re-authored for semantic freshness while retaining their exact capability gold
and residual classes. The corrected corpus SHA is:

`b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b`

Decision tests cover the stable-pass and family floors, both residual floors,
terminal model and infrastructure failures, wrong escapes, safety regressions,
unnecessary raw-pass actions, instability, endpoint drift, population shape
corruption, and frozen prompt/schema/source/policy provenance drift.

The provider-free corpus audit runs each gold plan through all three safety
layers and requires no layer to change it while the final facts remain
contract-correct. Finalization reconciles stored raw/final facts,
classifications, plan-terminal state, safety-layer evidence, and action counts;
contradictory redundant fields are inconclusive rather than decision-bearing.

Before the first PRE endpoint request, the live runner rejects populated
evidence, PRE, POST, or summary paths. It never deletes or overwrites prior
live artifacts.

## First Live Population and Bounded Harness Correction

The first authorized live population stopped after 8 of 48 rows because the
harness attempted to score a transient planner result after a deterministic
safety rejection. The population is operationally inconclusive and is not
decision-bearing:

```text
checkpoint: aabf651957d603549b34ef10173c71bae5061e58
completed rows: 8 / 48
provider infrastructure failures: 0
partial evidence SHA-256: b4d41b874a5ddfafee5f67ab4c4fcab46b6f6247fbb7bdea74d9ccbb5468367e
partial evidence: preserved / non-decision-bearing
resume: forbidden
append: forbidden
replacement: requires independent reauthorization
```

The bounded correction establishes that a deterministic CM-58.1, CM-58.2, or
CM-58.3 rejection has no final executable plan. The rejected intermediate
plan is cleared before final facts or semantic contract scoring, the final
projection is `None`, final facts are absent, final contract status is false,
and classification is `SAFE_REJECTION`. Planner-terminal failures retain
their separate planner classification, while accepted plans continue through
the normal facts scorer.

The correction is evaluation-only. The corpus remains frozen at
`b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b`, and
production, prompts, schema, CM-58 policies, thresholds, and execution
controls remain unchanged. Provider and endpoint calls during correction
validation are zero. A replacement population must use distinct evidence
paths and execute all 48 rows from the beginning only after independent
reauthorization.

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
