# A10 53-Case Execution Path Qualification

Status: `A10_SEM_53_CANONICAL_SCOPE_RECOVERY_COMPLETE — HA_REVIEW_REQUIRED`

This record covers the provider-free corrective of the accepted frozen 53-case
A10 semantic planner evaluation path. It does not execute the live evaluation.
The R1/R2 implementation evidence below is retained as historical record. The
R2 execution-path implementation was subsequently retired because it
introduced a separate campaign orchestrator and partial semantic scorer.

## Scope

The candidate extends the existing canonical live qualification harness and
read-only corpus adapter only:

- `scripts/nlp_d5_live_semantic_qualification.py`
- `scripts/a10_semantic_corpus_adapter.py`
- `tests/test_nlp_d5_live_semantic_qualification.py`
- `tests/test_a10_semantic_corpus_adapter.py`

The mode processes the exact 53-case A10 benchmark through the existing
planner-only smoke boundary. Each case receives a case-scoped custody
namespace, one initial generation plus at most one native correction, and the
same provider construction, context preparation, structured validation and
raw-I/O custody used by Smoke 003. A parent campaign boundary is durably
started before delegation, updated after each case, and sealed on normal or
caught failure termination. It never enters workers, reconciliation,
execution, persistence or rendering.

The existing historical 96-case/P8 scorer is unchanged. The A10 adapter
validates the accepted 53-case benchmark identity and scores only frozen
planner dimensions. Scoring requires exact channel tokens, operation
verbs/kinds, operation counts, and explicit scale components where the frozen
expectation supports them. Safe-rejection cases cannot pass with executable
work. Source binding, host resolution and host execution remain explicitly
`UNSCORABLE` at this planner-only boundary.

## Frozen identities

- Benchmark SHA-256:
  `595839779e9ca59d9ce8ff20cbbdaf006ad41138b4510acc0ea26733e080067a`.
- Source inventory SHA-256:
  `21f11462696af7a9f1d9b18d625a6a311794912b9ef10a70106f0267e83c19b0`.
- Planner source SHA-256:
  `790121ab7b75a0fd2bdd27bec83bb543d6926455297f0ae7a498c4543431f1ba`.
- Planner wire-schema SHA-256:
  `b6b05fec2caabbc62708d17b1d752d8888e6cf7e2b91b4b67889eb583b080cbb`.
- Each case authority carries the accepted wire-schema digest and derives its
  source digest from the host-owned frozen source inventory before preflight.
- Population: 53 cases, 35 production-grounded and 18 exploratory.
- Maximum logical planner calls: 106.
- Maximum physical generation attempts: 106.
- SDK transport retries: disabled for the A10 mode.

## R1 Qualification

Exact command:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_a10_semantic_corpus_adapter.py \
  tests/test_nlp_d5_live_semantic_qualification.py
```

Result: `175 passed`.

Additional checks:

- `ruff check` on the changed scripts and tests: PASS.
- `ruff format --check` on the changed scripts and tests: PASS.
- `PYTHONPATH=src .venv/bin/python -m py_compile` on changed scripts: PASS.
- `git diff --check`: PASS.
- `PYTHONPATH=src .venv/bin/python scripts/d5_single_engine_attestation.py --check`: PASS.
- Provider/model/endpoint calls: `0`.
- Live evaluation: not run.

The provider-free regressions cover all three source families, missing and
wrong per-case authority identities, exact GR/CGR/GRD separation, operation
kind and scale false positives, unsafe rejection plans, P/E partition metrics,
model-structural versus infrastructure classification, exact call caps, and
durable parent terminal custody after a caught mid-campaign interruption.

The authorizing verdict is computed only from the 35 production (P) cases.
The 18 exploratory (E) cases remain visible with independent denominators,
structural-validity counts, correction counts, scored outcomes, unscorable
counts, and failure classes; they cannot independently determine the
production verdict.

The adjacent CM-57P8 provider-free suite remains separate: it reports
`209 passed, 5 failed` because its historical provider/schema/planner hashes
are stale against the current repository. No P8 hashes were refreshed or
waived by this candidate.

## R2 Historical Qualification (Retired)

The R2 candidate closed its review findings in provider-free testing, but it is
not current implementation authority. Its operation-local scoring and campaign
verdict machinery were retired during canonical scope recovery because planner
wire evidence cannot replace host-owned resolution and execution semantics.

- Channel evidence is scored within the operation that supplies it; `CGR` and
  `GRD` cannot satisfy an exact `GR` requirement through substring matching.
- Explicit scale components remain within one target group, so unrelated
  operations cannot be combined into a passing scale assertion.
- Ordered multi-operation cases require operation order and the corresponding
  validated presentation constraint.
- Unsupported mutation expectations fail when executable operations are
  present, even if unresolved evidence is also declared.
- Every frozen expected label has an explicit `PARTLY_SCORABLE` disposition;
  source grounding, host resolution, and host execution remain unscorable.
- Campaign integrity is reported separately from the production verdict.
  Production `HARNESS_CONTRACT_FAILURE`, infrastructure interruption,
  unknown failure, incomplete coverage, duplicate case IDs, or missing case IDs
  produce an inconclusive production verdict rather than a planner failure.
  Exploratory infrastructure failures make campaign integrity inconclusive but
  cannot independently fail a complete production partition.

Exact command:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_a10_semantic_corpus_adapter.py \
  tests/test_nlp_d5_live_semantic_qualification.py
```

Result: `182 passed`.

Additional R2 checks:

- `ruff check` on the changed scripts and tests: PASS.
- `ruff format --check` on the changed scripts and tests: PASS.
- `PYTHONPATH=src .venv/bin/python -m py_compile` on the changed scripts and
  tests: PASS.
- `git diff --check`: PASS.
- `PYTHONPATH=src .venv/bin/python scripts/d5_single_engine_attestation.py
  --check`: PASS.
- Provider/model/endpoint calls: `0`.
- Live evaluation, P8, and holdout access: not run.

## Historical Live Authorization Boundary (Not Current)

The following historical command was never authorized or run. Any future A10
measurement must be designed under the accepted canonical planner-smoke path;
the retired R2 command is not an active entrypoint. Independent review must
authorize a fresh evidence namespace and exact
runtime/repository identities before invoking:

```bash
PYTHONPATH=src .venv/bin/python scripts/nlp_d5_live_semantic_qualification.py \
  --execute-a10-evaluation \
  --authorization-json <authorized-record> \
  --artifact-root <fresh-authorized-namespace>
```

No live authority, holdout access, provider call, or scientific result is
claimed by this historical record.
