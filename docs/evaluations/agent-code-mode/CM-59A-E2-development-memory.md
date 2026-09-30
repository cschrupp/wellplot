# CM-59A-E2 - Remediated System Reevaluation

## Status

- Parent baseline: `37234cb33b64c34291f96690a211150ce447b532`
- Provider calls: `0`
- Endpoint calls: `0`
- Production changes: `0`
- Live inference: not authorized in this slice
- CM-57D: blocked

CM-59A-E2 is the first fresh evaluation harness for the complete remediated
planner and deterministic safety stack. It reuses the unchanged CM-59A corpus
and the historical execution/evaluation primitives without modifying the
historical CM-59A harness, corpus, raw evidence, summary, or endpoint
fingerprints.

## Frozen Evaluation

The population remains 24 cases, two attempts per case, six families, and four
cases per family. The original CM-59A acceptance contract remains unchanged:
22/24 stable passes, 3/4 per family, both Lichen and Mariner residual cases
passing, zero planner terminal failures, wrong final-plan escapes, safety
regressions, unstable cases, unexpected references, missing required
references, parent-closure violations, and duplicate capability types.

The E2 harness binds its own provenance to the parent checkpoint and requires
the current production bytes to match that checkpoint before any future
finalization. The corpus remains:

`b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b`

The safety policy versions under evaluation are:

- `cm58.reference-admissibility.v1`
- `cm58.report-boundary.v2`
- `cm58.section-leaf-admissibility.v1`

## Remediation Targets

The three previously identified residuals are hard gates in addition to the
general acceptance threshold. Each must be `STABLE_PASS` across both attempts;
a stable safe rejection cannot consume the general two-case allowance.

- Fig: `cm59-single-fig-05`
- Linden: `cm59-reference-linden-10`
- Xenon: `cm59-mixed-xenon-21`

The target gold remains sourced from the unchanged corpus. No new corpus label,
request, semantic expectation, or provider-specific exception was introduced.

## Harness Boundary

The E2 harness delegates planner execution and the three safety layers to the
current production implementation, but defines its own E2 provenance,
checkpoint guard, v2 policy verification, target validation, population
integrity, target-aware decision, and provider-free finalization. It does not
provide a live execution path in this pre-live slice, so no endpoint or model
request can occur accidentally.

Provider-free tests cover corpus and target integrity, the pre-live audit,
current production/policy provenance, planner and safety-layer composition,
the Fig report-boundary repair, accepted complete populations, target hard-gate
rejection, incomplete populations, worker-call rejection, infrastructure
inconclusiveness, planner-failure classification, and provenance drift.

## Verification

- E2 focused suite: `13 passed`
- Adjacent suite: `194 passed`
- Full repository suite: `2229 passed, 13 accepted pre-existing failures, 3 skipped`
- Ruff: passed
- Formatting: passed
- Python compilation: passed
- `git diff --check`: passed
- Pre-live CLI: `PRELIVE_READY`

The full-suite failures remain the established baseline categories and are not
attributable to E2. No provider, endpoint, worker, or program calls were made.

## Hard Stop

This slice stops at the provider-free implementation checkpoint. Do not run
the E2 live population, Xenon-only retest, production adoption, CM-58.4, P11,
or CM-57D without separate authorization and independent review.
