# A10-SEM-53 Canonical Measurement Qualification

Status: `A10_SEM_53_CANONICAL_MEASUREMENT_HANDOFF — HA_REVIEW_REQUIRED`

This record covers a provider-free implementation that makes the accepted
frozen 53-case A10 planner population available through the existing D5
campaign machinery. It does not execute the benchmark, call a provider, expose
holdout data, or make a planner-quality claim.

## Scope

- Starting checkpoint: `b3ef3f655030d166c5af3cd7846a06d017ea5201`.
- Population: `a10-53`, exactly 53 immutable cases.
- Benchmark SHA-256:
  `595839779e9ca59d9ce8ff20cbbdaf006ad41138b4510acc0ea26733e080067a`.
- Source-inventory SHA-256:
  `21f11462696af7a9f1d9b18d625a6a311794912b9ef10a70106f0267e83c19b0`.
- Diagnostic case: `B01`, retained as an explicitly identified exposed case.
- Maximum logical planner calls: `106` (one initial generation plus one
  native correction per case).
- Maximum physical attempts: `318` under the existing SDK retry ceiling.

The benchmark and source inventory are authenticated before campaign setup.
Each case validates its source path, format and host-computed source digest.
Expected semantic outcomes are retained as case metadata only and are not sent
to the planner or used to produce a semantic score.

## Canonical path

The extension is contained in the existing
`scripts/nlp_d5_live_semantic_qualification.py` campaign path:

```text
D5CampaignRunner
  -> existing D5CampaignCustody and D5LogicalCallLedger
  -> existing create_live_adapter / SemanticPlanner.plan
  -> existing provider, structured validation and native correction
  -> stop at validated planner wire output
```

`planner_only` is an additional mode of the existing runner, not a second
orchestrator. A10 rejects non-planner-only execution. The adapter stops at the
existing `PLANNER_GENERATION_PASS` boundary, so workers, reconciliation,
execution, persistence and rendering are not entered.

Planner wire events and existing model-I/O custody retain the case turn ID.
Observation rows record structural/provider outcomes, correction usage, source
provenance, call counts and first structural/provider divergence. Semantic,
host-resolution, authoring and persistence dimensions remain explicitly
`NOT_ESTABLISHED` or `NOT_REACHED`; no downstream scorer or semantic engine was
added.

## Provider-free qualification

Exact commands:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_nlp_d5_live_semantic_qualification.py
```

Result: `134 passed in 38.30s`.

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_a10_semantic_corpus_adapter.py \
  tests/test_nlp_d5_live_semantic_qualification.py
```

Result: `162 passed in 35.84s`.

Additional checks:

- targeted Ruff check: PASS;
- targeted Ruff format check: PASS;
- Python compilation of changed script and test: PASS;
- `git diff --check`: PASS;
- `scripts/d5_single_engine_attestation.py --check`: PASS;
- provider/model/endpoint calls: `0`;
- benchmark execution: not run;
- holdout access: not run;
- workers, persistence and rendering: not entered by the provider-free
  qualification.

The new regressions authenticate the 53-case population, preserve B01's
position and diagnostic identity, enforce the planner-only call ceilings, use
the shared `D5CampaignRunner`, and keep semantic status unestablished. The
existing planner-only custody tests cover the stop-at-wire boundary and
fail-closed provider-free behavior.

## Changed files

- `scripts/nlp_d5_live_semantic_qualification.py`: adds the A10 population
  contract to the existing campaign runner and planner-only custody boundary.
- `tests/test_nlp_d5_live_semantic_qualification.py`: adds provider-free
  population and shared-runner regressions.
- This qualification record: records the implementation handoff only.

Pre-existing notebook edits and untracked `examples/families/` are unrelated
and are intentionally excluded.

## Boundary and next step

This handoff is not live authorization. Independent review must inspect the
committed diff and evidence before any separate live smoke or 53-case
execution authority is considered. Historical A10 scope-recovery artifacts,
Smoke 003, the frozen benchmark and source inventory remain immutable.
