# CM-03 Development Memory

## Scope

CM-03 extends the existing agent evaluation harness so the same fixture-backed
task suite can emit comparable records for `v1` and `v2`. It establishes the
evidence contract before any Code Mode runtime exists.

- **Migration baseline SHA:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Slice base SHA:** `7ab6780802603a1caa539bfc4dd437ca58c11d27`
- **Scope:** evaluation scripts, deterministic tests, and migration evidence
  documentation only.

## Decisions And Invariants

- `scripts/run_agent_evals.py` accepts `--engine v1|v2` and defaults to `v1`.
  Engine identity appears at both report and task level. Historical matrix
  evidence with no engine label is interpreted as `v1`; historical files are
  not rewritten.
- Each task metrics object has six stable keys: `program_chars`,
  `program_ast_nodes`, `program_calls`, `program_repairs`,
  `dynamic_schema_chars`, and `legacy_core_reached`.
- `not_available` means the architecture cannot produce a measurement. It is
  intentionally different from omitted data, `null`, and a measured zero.
- Deterministic and adapter modes continue to grade supplied documents without
  pretending to execute either authoring engine. Their engine metrics are
  `not_available`.
- A successful live v1 task records `legacy_core_reached: true`, because this
  harness calls the current legacy session. Other fields are left
  `not_available` until a later slice supplies trustworthy measurements.
- Live v2 returns one `not_implemented` record for each active selected task,
  with the original task and fixture identity and all six metrics set to
  `not_available`.
- The v2 CLI branch is selected before `_run_live`, provider construction,
  fixture preflight, or importing `wellplot.agent.notebook`. `_run_live` also
  retains a defensive v2 guard for direct callers.
- Matrix provider totals retain the previous shape and add
  `not_implemented`. New engine totals and case-first comparisons are keyed by
  task ID, fixture, provider, and model. `not_implemented` is neither a
  failure nor an eligible pass-at-one case. A missing v1 or v2 counterpart is
  represented as `null`.

## Validation

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q tests/test_agent_evals.py tests/test_agent_v2_architecture.py tests/test_agent_reachability.py`
  passed: `34 passed in 4.80s`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check scripts/agent_eval_support.py scripts/agent_eval_matrix.py scripts/run_agent_evals.py tests/test_agent_evals.py`
  passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check scripts/agent_eval_support.py scripts/agent_eval_matrix.py scripts/run_agent_evals.py tests/test_agent_evals.py tests/test_agent_reachability.py`
  passed: `5 files already formatted`.
- `git diff --check` passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run python scripts/run_agent_evals.py --mode live --engine v2 --task initial_open_hole --output /tmp/cm03-v2.json`
  produced a deterministic `not_implemented` v2 record with
  `live_execution: false` and no provider opt-in.

An initial combined test run correctly found that the CM-02 historical-manifest
test compared its immutable snapshot with the current worktree. CM-03 changes
evaluation-script imports, so that comparison would require rewriting frozen
evidence. The test now validates CM-02's recorded baseline, analysis SHA,
unresolved count, and required classifications, while existing tests still
rebuild the current inventory deterministically. The CM-02 JSON file was not
modified.

## Runtime And Production Delta

- `src/wellplot` production runtime delta: zero.
- Public API, provider, MCP, LangGraph, capability, routing, dependency, and
  legacy-deletion delta: zero.
- The only behavior change is evaluation evidence formatting and deterministic
  v2 placeholder records in development scripts.

## Limitations And Deferrals

CM-03 does not execute Code Mode and does not calculate program metrics. It
does not create a v2 provider interface, parser, interpreter, SDK, capability,
LangGraph graph, session, MCP route, or feature flag. The v2
`not_implemented` record is an evidence placeholder, not an opt-in execution
path.

CM-10 owns the pure Authoring Program models and error taxonomy. It may begin
to replace `not_available` program measurements only when actual v2 program
artifacts exist. CM-03 does not authorize any legacy removal described by the
CM-02 inventory.

## Decision

**PROCEED to CM-10 only after this slice is committed and pushed.**
