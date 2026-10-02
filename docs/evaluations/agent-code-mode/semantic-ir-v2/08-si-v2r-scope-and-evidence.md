# SI-V2R Scope And Evidence

## Baseline

SI-V2R starts from `6249557de70f6f3b740e9ea17a96d600c6acf3f0` on
`research/semantic-ir-v2-reconciliation`. The SI-V2.1 and SI-V2.2 artifacts
remain frozen; this record is a new provider-free reconciliation.

The authenticated SI-V2.2 evidence is `/tmp/si-v2-2-live.jsonl`, SHA-256
`1b95ebe42ed5227dd134e122c739ca6c6ec90aa72520fc745ffbb622c5527fd7`.
It contains 48 rows for 24 cases and two attempts per case. It was read only.

## Provider-Free Boundary

Provider calls, endpoint calls, worker/program calls, and live inference: `0`.
No frozen SI-V2 module, raw JSONL, CM58 layer, production route, planner,
report worker, typed worker, or MCP implementation was modified.

The new artifacts are parallel V2R models/compiler, an evaluation-only
taxonomy and equivalence analysis, a fresh 24-case provider-free intent
fixture, focused tests, and these records. V2R is not imported by production
routing.

## Baseline Verification

The same-environment focused baseline was:

```text
398 passed, 6 failed
```

The six failures are the known CM-59A Xenon production-anchor failures in
`tests/test_cm59a_r2a_l1_xenon_diagnostic.py`; no new failure class was
observed.

The recovered full suite completed with:

```text
2306 passed, 23 failed, 3 skipped, 11 subtests passed
```

The 23 failures are the existing baseline categories, including the same six
CM-59A Xenon anchor failures, fixture/evidence availability failures, and
environment-dependent MCP/documentation checks. No SI-V2R code was present
when this baseline was run.

## Authorized Objective

Reconcile the rejected SemanticIRV2 planner contract with the existing
section-worker and report-worker ownership boundaries. The work does not
retroactively improve the SI-V2.2 score. It determines whether a repository-
aligned replacement is sufficiently specified for a later live qualification.

The selected V2R boundary is:

```text
provider-facing semantic intent
    -> deterministic registry-driven lowering
    -> validated SemanticPlan
```

Reference meaning is section-owned. Data features do not carry a per-feature
`reference: bool`. Report work is coarse (`goal`, `requirements`, and
`constraints`); titles, remarks, headers, pages, depth, output, and other
authoring details remain report-worker-owned.

## Required Stop

This slice ends after provider-free tests, taxonomy, equivalence analysis,
and review records. `SI_V2R_ACCEPTED_FOR_LIVE_QUALIFICATION` only means that a
future live qualification can be scoped; it does not authorize that run.
