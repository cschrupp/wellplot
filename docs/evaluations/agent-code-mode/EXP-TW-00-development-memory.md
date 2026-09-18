# EXP-TW-00 Development Memory

## Status

Complete as an experimental corpus-freeze slice. The experiment remains before
EXP-TW-01; no typed worker generation has been run.

## Baseline

`48fafb958b85069295f88fc249b3b9b68158c52a` (CM-53R3 evidence baseline).

## Purpose

Freeze the full CBL report plus `main_pass` and `repeat_pass` semantic worker
context before observing typed-worker outputs. The corpus is replayable without
planner, enrichment, provider, public-route, source-discovery, or filesystem
search behavior.

## Files

- `scripts/exp_tw00_corpus.py`
- `tests/fixtures/typed_worker/exp_tw00_cbl/corpus.json`
- `tests/test_exp_tw00_corpus.py`

## Captured Corpus

- One report task and report header-slot context.
- Two section tasks and two indexed section contexts.
- Opaque candidates `source-1` and `source-2`.
- Exact per-source channel mnemonics and scalar/array kinds.
- Starter document in the host-only fixture block.
- Relative source provenance in the host-only block only.
- SHA-256 hashes for the worker projection and complete fixture payload.

## Gate A

Gate A is frozen before typed generations:

- 10 provider attempts.
- At least 9 schema-valid responses.
- Every validated source candidate must be host-approved.
- Every validated channel must belong to the selected source.
- Curve bindings require selected-source scalar channels.
- Raster bindings require selected-source array channels.
- At least 8 semantically usable responses.
- Repeated bindings are scored with multiplicity; `CBL, CBL` is not reduced to
  one channel.

## Validation

- `4 passed` in `tests/test_exp_tw00_corpus.py`.
- Ruff check passed for the new script and tests.
- Ruff format check passed.
- `git diff --check` passed.
- No provider calls or live experiments were made.

## Scope Evidence

Production runtime delta: `0`.

No SectionDraft model, typed provider call, compiler, worker, planner,
enricher, routing, MCP, notebook, persistence, or official CM-43 evidence
changed.

## Decision

PROCEED to review EXP-TW-00. Stop before EXP-TW-01 until the frozen corpus
and Gate A specification are accepted.
