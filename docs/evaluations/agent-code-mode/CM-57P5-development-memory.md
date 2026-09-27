# CM-57P5 Development Memory

## Status

CM-57P5 is a provider-free pre-live implementation checkpoint for fresh
holdout planner-contract generalization. Its R1 review baseline is
`c39068ccab1b470c7a325649d59f4e9a42114f52`, the initial CM-57P5 checkpoint.
The preceding CM-57P4 evidence baseline remains
`f7ffdf1382c0a4f57ee05b11b5cc3af2943d5b4f` and records
`INCONCLUSIVE_PROMPT_INTERACTION_BISECT`.

The purpose is to test the already-selected P4 `RC` planner contract on a new
corpus rather than tune the prompt again. P5 evaluates report work-unit
presence, report capability selection, section count, section capability
multisets, parent closure, duplicate capability types within one task, and
unresolved requirements. It does not evaluate scientific values, source
selection, typed-worker semantics, compilation, persistence, or routing.

## Frozen Design

The two arms are:

- `P`: the unchanged production `SemanticPlanner` and production system prompt.
- `RC`: the same planner and controls with only the exact P4 report-boundary
  and section-composition instructions appended to the system prompt.

The exact frozen instruction hashes are:

- BASE prompt: `5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18`.
- R instruction: `12fd2c40e407cb7d5d0e21effd66493e20e99468e3a97b89ac0186b40648c5b5`.
- C instruction: `b69c47063b6da13e4f5857609708efe0becc901b989a1a65c503dd277cdc8205`.
- RC prompt: `e1710cb516a96c47ec1d0593752e83aacc1bb4502c3026b2b6a9a676c90e4d34`.

The P5 holdout is version `cm57p5.holdout.v1` with 24 new cases, six
families, four cases per family, two attempts per case, and 48 future shared
rows. The future matrix has 96 planner executions and 96-192 provider calls.
Requests do not contain capability IDs, planner/evaluator field names, paths,
or reused CM-57C request hashes.

The gold representation is an optional report work unit plus a multiset of
independently compilable section signatures. Section order is irrelevant, but
section count and duplicate identical signatures are significant. Capability
types must remain unique within each work unit.

The fixed production-safe source summary is the path-free
`cm56r3.source-summary.v1` summary with a combined source label. Its SHA-256
is:

`ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e`

The initial holdout corpus SHA-256 was:

`5f1e44e0eb511c78160c596c982be5dd9b04efdfb58d0af176b4327286f15f76`

## CM-57P5-R1 Corrections

R1 corrects seven requests that were too generic to make their frozen report
and section gold independently unambiguous. The revised corpus keeps every
case ID, family, capability gold set, section topology, and zero-unresolved
gold field unchanged. Its frozen SHA-256 is:

`29e85998481ce9bcc6eab9ecb7959d470cefbf3a84e5273309c6004aacae334d`

The seven requests now state the required page/depth/output, remarks/tail,
report settings, report-plus-section, independent-panel, and combined-panel
semantics directly. No prompt, model, timeout, token, temperature, source
summary, capability, planner, or evaluator behavior changed.

R1 also makes the provider-free evidence checks stricter. The runtime source
summary hash is derived from the actual `FIXED_SOURCE_SUMMARY` object rather
than a separately cached serialization. The live gate compares its actual
model, temperature, output-token, token-parameter, and timeout constants to
one frozen controls object before provider construction. The provider-free
self-test compares a direct `SemanticPlanner` production invocation with the
actual P arm on both initial and semantic-correction calls, then verifies that
RC changes only the system prompt. Reviewed-checkout tests cover harness and
corpus byte drift plus prompt, source-summary, and execution-control drift;
all abort before provider construction. A fixture regression compares the
complete gold projection with the initial CM-57P5 checkpoint, and an explicit
test rejects merging two independently expected sections into one task.

## Evidence Guards

The future live path requires an empty evidence file and an exact reviewed
checkout before constructing a provider. It byte-guards the P5 harness and
corpus, P4 harness and summary, planner and capability registry artifacts, the
CM-57C corpus, the frozen source summary, prompt hashes, and execution
controls. Rows carry the full provenance and population integrity rejects
drift, missing arms, duplicate case/attempt pairs, or mixed checkpoints.

P4 provenance remains frozen:

- P4 summary SHA-256:
  `571c1c98d4043ad174fe8000f2affc5dec93ec1d90a5fffa100d2cc98d51ae0d`.
- P4 raw evidence SHA-256:
  `84984fe9903e43396633c87682eb341342f8ac406d296d29dfb47b32b02cd001`.
- P4 authorized checkpoint:
  `c44f163ef605f8d892bf6d114c6a6a3258756ca5`.

Provider result prose, hidden reasoning, full prompts, secrets, and host paths
are not retained in future evidence rows. Each completed shared row is flushed
immediately; a partial run is evidence and is not resumed by appending.

## Decision Contract

The future decision labels are:

- `HOLDOUT_GENERALIZATION_VALIDATED` only for RC `48/48`, no infrastructure or
  terminal failures, no wrong selections, and no P-only pass.
- `HOLDOUT_GENERALIZATION_PARTIAL` when RC improves on P without any P-only
  pass but remains below `48/48`.
- `HOLDOUT_GENERALIZATION_NO_GAIN` when P and RC have equal final pass counts,
  with no P-only pass and no inconclusive condition.
- `HOLDOUT_GENERALIZATION_REGRESSION` whenever P passes and RC fails on any
  paired row.
- `INCONCLUSIVE_HOLDOUT_EVALUATION` for infrastructure failure, incomplete or
  corrupted evidence, checkpoint/corpus/prompt/control drift, or wrapper
  isolation failure.

The regression and inconclusive conditions dominate aggregate gains. No result
will authorize production prompt adoption automatically.

## Live Evidence

The authorized live matrix ran once at checkpoint
`aea88a0611804b88bf1694448283cd5818977c55` using the frozen local Qwen
controls. The raw JSONL is preserved outside the repository at
`/tmp/cm57p5-fresh-holdout-qwen.jsonl`; it contains 48 rows, is 309413 bytes,
and has SHA-256
`b9ce5e164d98ff18586d01ee561d83e43da023afca2f63b95de0170f8fb97cb2`.

The population is complete with zero terminal failures, zero provider
infrastructure failures, and zero worker/program calls. P produced 4 initial
and 6 final passes from 56 provider calls, with 8 corrections. RC produced 36
initial and 38 final passes from 50 provider calls, with 2 corrections. The
paired full-contract outcomes were BOTH_PASS 2, P_ONLY_PASS 4, RC_ONLY_PASS
36, and BOTH_FAIL 6. All 24 cases were stable across their two attempts for
both arms.

RC improved substantially across the fresh holdout, including single-section,
heterogeneous-section, multi-section, mixed-report-section, and
capability-multiplicity families. However, the frozen promotion rule treats
any P-only pass as a regression. Because four P-only passes occurred, the
final decision is `HOLDOUT_GENERALIZATION_REGRESSION`, not a promotion result.
The raw evidence is summarized in `CM-57P5-live-summary.json`.

## Pre-Live Boundary

Production changes: `0`.

Provider calls: `106` (`P=56`, `RC=50`).

Worker/program calls: `0`.

Live inference: `COMPLETED; HOLDOUT_GENERALIZATION_REGRESSION`.

Production adoption: `NOT AUTHORIZED`.

CM-57D: `BLOCKED`.

The pre-live harness and tests are in:

- `scripts/cm57p5_fresh_holdout.py`
- `tests/fixtures/typed_worker/cm57p5_fresh_holdout.json`
- `tests/test_cm57p5_fresh_holdout.py`

Hard stop after the completed live evidence. Do not edit the raw JSONL, rerun
individual cases, modify the production prompt, or begin CM-57D without
separate authorization.
