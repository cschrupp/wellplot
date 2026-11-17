# A10 Semantic Planner Evaluation Readiness

Status: `A10_SEM_53_CANONICAL_MEASUREMENT_IMPLEMENTATION_ACCEPTED — B01_LIVE_DIAGNOSTIC_PREPARATION_ONLY`

This is a provider-free readiness audit for the accepted frozen 53-case A10
semantic planner evaluation. It does not execute the evaluation and does not
make a planner-quality claim. The R1/R2 readiness candidate is preserved as
historical evidence, but the R2 execution path was retired because it created
an additional campaign workflow and partial semantic authority.

## Accepted Inputs

- Previous accepted repository HEAD: `a1b29cef9a47d51afd58613b4a41207221b98a9c`.
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

PASS: the R2 canonical corpus-adapter and live-qualification suites reported
`182 passed` with no provider, endpoint, or model calls.

### Historical 53-case campaign path (Retired)

The retired bounded execution-path candidate exposed one additional mode in the
existing canonical live qualification CLI:

- `execute_live_planner_smoke`, which remains pinned to one planner case
  (`B01`);
- `execute_live_campaign --population d4`, which uses the older D4 turn set;
- `execute_live_campaign --population final`, which uses the separate ten-turn
  D5 final population.
- `execute_live_a10_planner_evaluation`, which processes the exact A10
  benchmark population through the existing planner-smoke/provider/custody
  path, with one case namespace per request and a durable parent campaign
  boundary.

### Historical scoring binding (Retired)

The retired candidate added an A10-specific adapter without changing the historical
scorer. `scripts/a10_semantic_corpus_adapter.py` still loads the separate 96-case
historical corpus and joins a 12-case P8 population. Its `score_plan()` accepts
that corpus's `AdaptedCase` contract and intentionally leaves historical
operation and source comparisons unscorable. It is not currently bound to the
53-case A10 benchmark as an active scoring population. The retired candidate's
benchmark loader and `score_a10_plan()` were removed. Host resolution, source
binding, and host execution remain host-owned and are not reproduced here.

### Adjacent P8 status

The provider-free command including the CM-57P8 suite reported `209 passed,
5 failed`. The five failures are stale P8 frozen hashes/identities against
current provider, schema, and planner bytes. They are not evidence about the
53-case A10 planner population and were not refreshed. They remain a separate
P8 authorization blocker.

## Candidate Qualification (Historical, Retired)

The candidate was qualified without provider calls:

- Focused A10 corpus-adapter and canonical live-harness tests: `182 passed`.
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

### R2 integrity corrections (Historical, Retired)

The retired scorer bound channel and scale evidence to operation-local targets and
requires validated presentation constraints for ordered edits. Unsupported
mutation expectations reject executable work. The benchmark loader rejects any
expected label without an explicit scoring disposition, and all 53 frozen
labels are declared `PARTLY_SCORABLE` at this planner-only boundary.

The retired campaign custody code distinguished three outcomes: campaign status,
integrity, and the independent production (`P`) verdict. Exact case-ID
coverage is required. Production infrastructure or harness-contract failures,
missing/duplicate cases, and incomplete production coverage are inconclusive;
exploratory (`E`) infrastructure failures make campaign integrity inconclusive
without changing a complete production verdict.

## Historical Requirements (Retired)

The following requirements belonged to the retired execution-path candidate.
They are preserved for historical traceability, not as an active implementation
plan. Any future measurement must be separately designed around the existing
canonical planner-smoke path and independently authorized.

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

## Scope-Recovery Decision

`A10_SEM_53_CANONICAL_SCOPE_RECOVERY — PASS / CLOSED`

The frozen benchmark, source inventory, Smoke 003 evidence, and existing
canonical planner-smoke path remain preserved. The separate A10 orchestrator,
its private campaign lifecycle, and its heuristic semantic scorer are retired.
No benchmark, provider call, holdout access, or replacement workflow is
authorized by this record.

## Current implementation acceptance

The canonical 53-case measurement implementation is accepted at
`8c9612700a55f4f78197b38b1d871b430e`. The execution authority must bind
`implementation_checkpoint` to the exact repository `HEAD` immediately before
launch, separately from the accepted implementation commit. Its provider-free
qualification reported 167 passing tests and passing static,
formatting, compilation, diff, and single-engine gates. The implementation uses the existing
`D5CampaignRunner`/custody/planner-only path and preserves the separation
between provider structural outcomes, infrastructure failures, and
pre-generation request-compilation rejections.

The next prepared operation is not the 53-case evaluation. It is a separate,
B01-only operational diagnostic using the existing `execute_live_campaign()`
entrypoint with `population="a10-53"`, `mode="planner_only"`, and
`turn_ids=("A10-SEM-53:B01",)`, with at most two logical generations, two
physical attempts and zero SDK retries. The loader may authenticate the frozen
corpus internally, but only B01 is selected for provider submission. It remains
unauthorized until a fresh namespace and current rolling llama.cpp readiness
identity are independently authorized.
