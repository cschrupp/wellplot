# CM-57P7 Development Memory

## Status

CM-57P7 is authorized only through the provider-free pre-live checkpoint.
The frozen implementation baseline is `19e971740de9214a47b56afee4891ca82e8e32b5`.
This slice must stop after deterministic validation, commit, and push.

## Purpose

P7 evaluates the complete production candidate on a fresh promotion-quality
holdout. It keeps the production planner path as `P`, the exact P5 RC prompt
as `RC`, the P6 non-empty-report validator as `RCV`, and the P6 response-schema
substitution as `RCS`. All four arms use the same fresh request and source
summary per row. No arm reaches a worker or production routing.

The fresh corpus has 24 cases, four per family:

- `REPORT_ONLY`
- `SINGLE_SECTION`
- `HETEROGENEOUS_SECTION`
- `MULTI_SECTION`
- `MIXED_REPORT_SECTION`
- `CAPABILITY_MULTIPLICITY`

Requests are new relative to the complete P5/P6 request corpus, contain no
internal planner/evaluator vocabulary, and contain no paths or capability IDs.
The cases were independently authored and human-reviewed for semantic
freshness: they are not sentence-level paraphrases or copied case templates
from P5/P6. The family-level topology remains comparable by design. The gold
is validated with the existing P5 registry and parent-closure checks.

## Frozen Boundary

The future population is 48 shared rows, two attempts for each case. It has
192 planner executions and an expected provider-call range of 192 to 384.
The future controls are model `qwen3.6-35b-a3b`, planner temperature `0.0`,
`max_tokens=16384`, and a 900 second timeout. Worker/program calls must remain
zero.

The P arm uses the unchanged `SemanticPlanner` and production schema. RC uses
the exact P5 RC system prompt and production schema. RCV changes only the P6
validator invariant. RCS changes only the P6 structured response schema and
converts the result back to the production `SemanticPlan`. The P6 mechanism,
provider base interface, and artifact hashes are guarded rather than copied or
modified.

## Promotion Gates

Before candidate comparison, RC must reproduce an empty-report activation on
at least two distinct cases spanning `REPORT_ONLY` and
`MIXED_REPORT_SECTION`, with both attempts available. Missing activation,
provider infrastructure failure, population drift, or comparison-invalidating
instability makes the result `INCONCLUSIVE_PROMOTION_EVALUATION`.

Each candidate is compared against P, not RC. A viable candidate must preserve
report presence/capabilities, section count and multiset, parent closure,
unresolved correctness, and the no-duplicate property without any P-pass to
candidate-fail transition. It must recover both attempts on at least four
cases spanning at least two families, remain stable across all 24 case pairs,
and produce no terminal, infrastructure, or worker failures.

Activation recovery checks only the repaired report invariant on the required
RC activation rows; unrelated section failures shared by P and a candidate do
not invalidate that specific activation claim. Efficiency is reported only
after a validated or partial candidate decision; inconclusive and no-candidate
populations report `NOT_APPLICABLE`.

The future labels are:

- `PROMOTION_BOTH_VALIDATED`
- `PROMOTION_SCHEMA_ONLY_VALIDATED`
- `PROMOTION_VALIDATOR_ONLY_VALIDATED`
- `PROMOTION_NO_CANDIDATE_VALIDATED`
- `INCONCLUSIVE_PROMOTION_EVALUATION`

Efficiency is secondary and compares candidate provider-call totals only
after viability. No live summary is created during this pre-live slice.

## Live Result

The authorized live matrix ran once at checkpoint
`f952c64f735b6c3bc7519677c2d36ca80e980609` using the frozen local Qwen
controls. The raw evidence remains unchanged at
`/tmp/cm57p7-fresh-promotion-qwen.jsonl` with SHA-256
`b4cb75aaf6a5ffe8c7f88c6e730d32247d973ea974269132a76b814633ff4d2f`.

The population is complete: 48/48 rows, 192 planner executions, 224 provider
calls, zero infrastructure failures, and zero worker/program calls. The P arm
had 4 terminal failures and 2 unavailable repeatability pairs, so the frozen
decision is `INCONCLUSIVE_PROMOTION_EVALUATION`. RCV and RCS each recovered
stable candidate gains, but each also had 2 protected field regressions against
P; neither candidate is promotion-validated. Efficiency is `NOT_APPLICABLE`.

The bounded aggregate is recorded in `CM-57P7-live-summary.json`. Production
adoption remains unauthorized and CM-57D remains blocked.

## Hard Stop

Provider calls are `0` for this implementation checkpoint. There are no
production changes, prompt changes, planner changes, capability changes,
routing changes, retries, repairs, or fallback behavior. CM-57D remains
blocked. A separate review and explicit live authorization are required for
the future 48-row matrix.
