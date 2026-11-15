# A10 Semantic Planner Evaluation Readiness

Status: `A10_SEM_53_EXECUTION_PATH_01_CANDIDATE_READY — HA_REVIEW_REQUIRED`

This is a provider-free readiness audit for the accepted frozen 53-case A10
semantic planner evaluation. It does not execute the evaluation and does not
make a planner-quality claim.

## Accepted Inputs

- Current repository HEAD: `a1b29cef9a47d51afd58613b4a41207221b98a9c`.
- Accepted operational smoke: checkpoint
  `29bbcfe7c8ecbb9da49674240996499a20a5f183`; its production source paths
  are unchanged at the current HEAD.
- Benchmark: `workspace/evaluations/a10-sem-01-20261110/benchmark.json`.
- Benchmark SHA-256:
  `595839779e9ca59d9ce8ff20cbbdaf006ad41138b4510acc0ea26733e080067a`.
- Source inventory:
  `workspace/evaluations/a10-sem-01-20261110/source-inventory.json`.
- Source-inventory SHA-256:
  `21f11462696af7a9f1d9b18d625a6a311794912b9ef10a70106f0267e83c19b0`.
- Planner source SHA-256:
  `790121ab7b75a0fd2bdd27bec83bb543d6926455297f0ae7a498c4543431f1ba`.
- Planner wire-schema SHA-256:
  `b6b05fec2caabbc62708d17b1d752d8888e6cf7e2b91b4b67889eb583b080cbb`.
- Project configuration fingerprint:
  `14357a627f060572e73a822ab9efe9ed3a6cca6727b7247361a2a5adfa5bd498`.

The benchmark contains 53 unique IDs (`A01`–`A53`), with 35 production-
grounded (`P`) cases and 18 exploratory (`E`) cases. Its eight declared
classes are explicit physical, authorized semantic, similar-channel
distractor, unsupported semantic, ambiguous/unauthorized, multi-operation,
mutation, and language variation. Source assignment is 37 `approved_las`, 14
`cbl_repeat_dlis`, and 2 `cbl_main_dlis` cases.

The existing exact-request audit identifies `Plot Gamma Ray.` as an exposed
diagnostic case in this fixture and reports 52 fresh cases. That fact is
preserved; the benchmark must not be silently rewritten or supplemented.

## Readiness Findings

### Corpus custody

PASS. The benchmark and source inventory bytes match their accepted digests,
case IDs are unique, and the metadata-only source inventory is available.

### Canonical planner identity

PASS for the accepted smoke lineage. The current HEAD differs from the Smoke
003 checkpoint only outside `src/wellplot`, and the planner source and wire
schema identities are recorded above.

### Provider-free harness and corpus checks

PASS: the canonical corpus-adapter and live-qualification suites reported
`160 passed` with no provider, endpoint, or model calls.

### Executable 53-case campaign path

The bounded execution-path candidate now exposes one additional mode in the
existing canonical live qualification CLI:

- `execute_live_planner_smoke`, which remains pinned to one planner case
  (`B01`);
- `execute_live_campaign --population d4`, which uses the older D4 turn set;
- `execute_live_campaign --population final`, which uses the separate ten-turn
  D5 final population.
- `execute_live_a10_planner_evaluation`, which processes the exact A10
  benchmark population through the existing planner-smoke/provider/custody
  path, with one case namespace per request.

### Scoring binding

The candidate adds an A10-specific adapter without changing the historical
scorer. `scripts/a10_semantic_corpus_adapter.py` still loads a separate 96-case
historical corpus and joins a 12-case P8 population. Its `score_plan()` accepts
that corpus's `AdaptedCase` contract and intentionally leaves historical
operation and source comparisons unscorable. It is not currently bound to the
53 A10 benchmark fields (`id`, `gold`, `class`, `source`, `structured_channel`,
and `expected`). The candidate now loads and validates those fields through
`load_a10_benchmark()` and scores only the bounded planner dimensions through
`score_a10_plan()`. Host resolution, source binding, and host execution remain
explicitly unscorable because this evaluation stops at the planner wire DTO.

### Adjacent P8 status

The provider-free command including the CM-57P8 suite reported `209 passed,
5 failed`. The five failures are stale P8 frozen hashes/identities against
current provider, schema, and planner bytes. They are not evidence about the
53-case A10 planner population and were not refreshed. They remain a separate
P8 authorization blocker.

## Candidate Qualification

The candidate was qualified without provider calls:

- Focused A10 corpus-adapter and canonical live-harness tests: `165 passed`.
- Ruff lint: PASS.
- Ruff format check: PASS.
- Python compilation: PASS.
- `git diff --check`: PASS.
- Single-engine attestation: PASS.
- Provider/model/endpoint calls: `0`.
- Live 53-case evaluation: not run.

The adjacent CM-57P8 suite remains separately classified at `209 passed, 5
failed` because of stale historical frozen hashes. Those pins were not changed
by this candidate.

## Required Canonical Completion Before Live Authorization

The next implementation slice must remain inside the existing canonical live
qualification and corpus-adapter infrastructure. It must not create a second
runner, semantic engine, provider path, or scoring workflow.

It must provide, and provider-free-test, all of the following:

1. Exact ordered execution of the 53 benchmark IDs, with no implicit D4/D5/P8
   population substitution and no access to the 52 fresh holdout cases beyond
   their frozen benchmark records.
2. Host-owned source selection from the benchmark and accepted source
   inventory, with source identity checked before each case.
3. One initial planner generation and at most the existing native correction
   per case, for a declared maximum of 106 logical planner calls.
4. Case-scoped custody of the complete permitted request/response evidence,
   validation diagnostics, final `_PlannerWirePlan`, first divergence, call
   counts, and terminal result.
5. A downstream A10 scorer that maps the frozen `expected` dispositions and
   structural constraints without importing P8 gold or inventing semantic
   authority. Exploratory (`E`) cases must remain non-authorizing diagnostics.
6. Fail-closed population, source, schema, revision, call-cap, evidence, and
   holdout checks before any provider delegation.
7. A bounded terminal report with per-case outcomes and aggregate counts. No
   workers, authoring mutations, YAML publication, rendering, scientific
   grading, or C02 access are part of this planner evaluation.

The live authorization should pin the canonical repository, exact production
checkpoint, planner and wire-schema digests, benchmark and inventory digests,
provider/runtime identity, request population, correction ceiling, evidence
namespace, timeout, and terminal classification rules. The accepted Smoke 003
record supplies operational readiness evidence but does not authorize these
53 model evaluations.

## Decision

`A10_SEM_53_EXECUTION_PATH_01_CANDIDATE_READY — HA_REVIEW_REQUIRED`

The frozen inputs, canonical execution path, bounded A10 scorer, and
provider-free custody qualification are ready for independent review. Do not
run the benchmark, call the provider, access holdouts, or create a parallel
workflow until a separate live authorization is issued.
