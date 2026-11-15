# A10 53-Case Execution Path Qualification

Status: `A10_SEM_53_EXECUTION_PATH_01_CANDIDATE_READY — HA_REVIEW_REQUIRED`

This record covers the provider-free implementation of the accepted frozen
53-case A10 semantic planner evaluation path. It does not execute the live
evaluation.

## Scope

The candidate extends the existing canonical live qualification harness and
read-only corpus adapter only:

- `scripts/nlp_d5_live_semantic_qualification.py`
- `scripts/a10_semantic_corpus_adapter.py`
- `tests/test_nlp_d5_live_semantic_qualification.py`
- `tests/test_a10_semantic_corpus_adapter.py`

The new mode processes the exact 53-case A10 benchmark through the existing
planner-only smoke boundary. Each case receives a case-scoped custody
namespace, one initial generation plus at most one native correction, and the
same provider construction, context preparation, structured validation and
raw-I/O custody used by Smoke 003. It never enters workers, reconciliation,
execution, persistence or rendering.

The existing historical 96-case/P8 scorer is unchanged. The A10 adapter
validates the accepted 53-case benchmark identity and scores only frozen
planner dimensions. Source binding, host resolution and host execution remain
explicitly `UNSCORABLE` at this planner-only boundary.

## Frozen identities

- Benchmark SHA-256:
  `595839779e9ca59d9ce8ff20cbbdaf006ad41138b4510acc0ea26733e080067a`.
- Source inventory SHA-256:
  `21f11462696af7a9f1d9b18d625a6a311794912b9ef10a70106f0267e83c19b0`.
- Planner source SHA-256:
  `790121ab7b75a0fd2bdd27bec83bb543d6926455297f0ae7a498c4543431f1ba`.
- Planner wire-schema SHA-256:
  `b6b05fec2caabbc62708d17b1d752d8888e6cf7e2b91b4b67889eb583b080cbb`.
- Population: 53 cases, 35 production-grounded and 18 exploratory.
- Maximum logical planner calls: 106.
- Maximum physical generation attempts: 106.
- SDK transport retries: disabled for the A10 mode.

## Qualification

Exact command:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_a10_semantic_corpus_adapter.py \
  tests/test_nlp_d5_live_semantic_qualification.py
```

Result: `165 passed`.

Additional checks:

- `ruff check` on the changed scripts and tests: PASS.
- `ruff format --check` on the changed scripts and tests: PASS.
- `PYTHONPATH=src .venv/bin/python -m py_compile` on changed scripts: PASS.
- `git diff --check`: PASS.
- `PYTHONPATH=src .venv/bin/python scripts/d5_single_engine_attestation.py --check`: PASS.
- Provider/model/endpoint calls: `0`.
- Live evaluation: not run.

The adjacent CM-57P8 provider-free suite remains separate: it reports
`209 passed, 5 failed` because its historical provider/schema/planner hashes
are stale against the current repository. No P8 hashes were refreshed or
waived by this candidate.

## Live authorization boundary

Independent review must authorize a fresh evidence namespace and exact
runtime/repository identities before invoking:

```bash
PYTHONPATH=src .venv/bin/python scripts/nlp_d5_live_semantic_qualification.py \
  --execute-a10-evaluation \
  --authorization-json <authorized-record> \
  --artifact-root <fresh-authorized-namespace>
```

That command is recorded for future authorization only. It was not run here.
No live authority, holdout access, provider call, or scientific result is
claimed by this qualification.
