# A10-SEM-53 Canonical Measurement Qualification

Status: `A10_SEM_53_CANONICAL_MEASUREMENT_IMPLEMENTATION_ACCEPTED — B01_LIVE_DIAGNOSTIC_PREPARATION_ONLY`

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
- Maximum physical attempts: `106`; A10 pins the existing adapter to zero SDK
  retries.

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

## R1 Measurement-Integrity Corrective

R1 preserves the same canonical path and makes four bounded corrections:

- A10 authorizations require `sdk_max_retries=0`; the existing adapter receives
  that override, and the 53-case physical ceiling is `106` rather than being
  expanded by the general D4/D5 retry default.
- Only final `INVALID_RESPONSE` provider results are recorded as model
  structural observations. Runtime, call-cap, custody and unexpected failures
  propagate to the existing campaign terminal and stop further cases.
- Planner-wire and stage-trace files are bound by SHA-256 in the existing
  campaign terminal and verified by `verify_custody_artifacts()`. An empty
  planner-wire file is valid when no response crossed the wire boundary, but
  its bound artifact must still exist.
- The direct observed-adapter regression exercises the production
  `SemanticPlanner` boundary with a provider double.

R1 qualification:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_a10_semantic_corpus_adapter.py \
  tests/test_nlp_d5_live_semantic_qualification.py
```

Result: `166 passed in 29.61s`.

Targeted R1 selection: `6 passed`.

R1 static checks:

- Ruff check: PASS;
- Ruff format check: PASS;
- Python compilation: PASS;
- `git diff --check`: PASS;
- single-engine attestation: PASS;
- provider/model/endpoint calls: `0`;
- live smoke, 53-case benchmark and holdout access: not run.

## Request-Compilation Classification Corrective

The final R1 correction distinguishes deterministic request-compilation
rejections from provider/model observations. When the canonical
`SemanticPlanner.plan()` raises a `request_compilation_*` failure before any
provider call, the existing planner-only adapter records the canonical code,
trace and source provenance with `observation_status` set to
`REQUEST_COMPILATION_REJECTION`. The observation has `schema_valid=None`, zero
initial-generation and native-correction usage, zero logical generation calls
and zero physical attempts. It is visible in campaign accounting and does not
terminate otherwise valid observation collection. Provider failures, custody
errors, call-cap errors and unexpected faults retain the R1 terminal behavior.

The planner-only custody boundary is activated before pre-provider compilation
so a zero-call rejection still seals its trace and terminal evidence. The
provider-free regression exercises the real canonical compilation-rejection
path with a synthetic request and verifies that no provider request occurs.

Final corrective qualification:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_a10_semantic_corpus_adapter.py \
  tests/test_nlp_d5_live_semantic_qualification.py
```

Result: `167 passed in 36.10s`.

Targeted regression selection: `2 passed`.

The benchmark, live smoke, provider/model/endpoint calls and holdout access
remain at zero/not run.

## Implementation Acceptance and B01 Diagnostic Preparation

The provider-free implementation is accepted at checkpoint
`8c9612700a55f4f78197b38b1d871b430e35365e`, parent
`3409d92816286b9b94e6fb1813be9239e3a40863`. This acceptance promotes the
implementation contract, not a planner-quality result. The existing
`execute_live_planner_smoke()` path is the only proposed live entrypoint.

The next separately authorized operation is one non-scientific B01 diagnostic:

- request: `Plot Gamma Ray.`;
- case: `B01` only;
- source: `workspace/data/30-23a-3 8117_d.las`;
- source SHA-256:
  `7e6c69c65713dc33303362ab91b767eb06371fd24a31856add8650e6d3bee1a9`;
- benchmark SHA-256:
  `595839779e9ca59d9ce8ff20cbbdaf006ad41138b4510acc0ea26733e080067a`;
- source-inventory SHA-256:
  `21f11462696af7a9f1d9b18d625a6a311794912b9ef10a70106f0267e83c19b0`;
- implementation checkpoint: `8c9612700a55f4f78197b38b1d871b430e35365e`;
- planner harness SHA-256:
  `1be6b409de0e0e28b0bac1bc7f9c93d1389ed47524636209145cc7076fdd8ab1`;
- planner wire-schema SHA-256:
  `b6b05fec2caabbc62708d17b1d752d8888e6cf7e2b91b4b67889eb583b080cbb`;
- logical generation maximum: `2`;
- physical attempt maximum: `2`;
- SDK retries: `0`;
- downstream stages: not entered.

Proposed authority descriptor:

```text
authorization_id=A10-SEM-53-B01-DIAGNOSTIC-20261117-001
campaign_id=a10-sem-53-b01-diagnostic-20261117-001-b01
artifact_root=workspace/evaluations/a10-sem-53-b01-diagnostic-20261117-001
planner_smoke_mode=planner_only
planner_smoke_case_id=B01
provider=openai_compat
model=qwen3.6-35b-a3b
server_origin=http://192.168.2.140:8888
planner_smoke_sdk_max_retries=0
```

The authority descriptor must also bind the exact project configuration
fingerprint `14357a627f060572e73a822ab9efe9ed3a6cca6727b7247361a2a5adfa5bd498`,
thinking-off control, production-component digests, and the exact current
`expected_worktree_porcelain` allowlist. The endpoint identity is intentionally
not guessed here: the existing readiness policy must observe `/v1/models` and
`/props` from the configured server and bind the current rolling runtime
identity before any generation is authorized. A changed build is therefore a
new runtime observation, not a silent reuse of historical Smoke 003 identity.

The prepared invocation, to be run only after separate live authorization, is:

```bash
cd /home/user/projects/well_log_os
timeout --signal=TERM --kill-after=10s 300s \
  .venv/bin/python scripts/nlp_d5_live_semantic_qualification.py \
  --repo-root /home/user/projects/well_log_os \
  --execute-planner-smoke \
  --planner-case-id B01 \
  --artifact-root /home/user/projects/well_log_os/workspace/evaluations/a10-sem-53-b01-diagnostic-20261117-001 \
  --authorization-json /home/user/projects/well_log_os/workspace/evaluations/a10-sem-53-b01-diagnostic-20261117-001.authorization.json
```

The authorization JSON is a sibling input to the fresh evidence namespace so
freshness admission can prove that the target namespace is absent before the
run. It is not created or consumed by this preparation. The command must prove
the canonical checkout, branch/checkpoint, exact worktree allowlist, readable
credential source without disclosure, local source identity, current endpoint
identity, and exact harness/schema identities before the first generation.

The expected custody includes complete system/user prompts, structured-output
schema, raw provider requests and responses, validation diagnostics, native
correction feedback, stage traces, source before/after identity, call counts,
terminal verification, and orderly client/process cleanup. A successful run
stops at the validated planner-wire boundary; it does not execute workers,
reconciliation, persistence, rendering, the frozen 53-case population, or
holdouts. This preparation itself performed none of those live operations.

## Changed files

- `scripts/nlp_d5_live_semantic_qualification.py`: adds the A10 population
  contract to the existing campaign runner and planner-only custody boundary.
- `tests/test_nlp_d5_live_semantic_qualification.py`: adds provider-free
  population and shared-runner regressions.
- This qualification record: records the implementation handoff only.

Pre-existing notebook edits and untracked `examples/families/` are unrelated
and are intentionally excluded.

## Boundary and next step

This preparation is not live authorization. Historical A10 scope-recovery
artifacts, Smoke 003, the frozen benchmark and source inventory remain
immutable. The B01 diagnostic requires its own authority and fresh namespace;
the 53-case scientific campaign remains separately gated and must not be
started by this record.
