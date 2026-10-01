# SI-V2.1 Scope And Constraints

## Decision Record

DECISION: Build and evaluate a provider-neutral Semantic IR v2 prototype in
an isolated research worktree. The prototype lowers semantic intent to the
existing SemanticPlan; it does not alter the production planner or graph.

PROJECT SCOPE: Determine the smallest semantic responsibility boundary that
can preserve current planner meaning while moving uniquely derivable structure
to deterministic WellPlot code.

BASELINE: d77649765dee81ebd0b8f460ac28515b244f70da.

BRANCH: research/semantic-ir-v2 in /tmp/wellplot-si-v2.

EVIDENCE CLASS: ADAPTED. The architecture is informed by established
declarative specification and compiler patterns, then bounded by WellPlot's
registry and planner contracts.

## Hard Boundaries

- Provider calls, endpoint calls, and worker/program calls: 0.
- No changes to SemanticPlanner, provider adapters, LangGraph routing, CM-58,
  workers, MCP, public APIs, or ADR-CM57.
- No production import makes SI-V2 reachable by default.
- The compiler ends at a validated production SemanticPlan.
- Ambiguous semantic choices fail closed; registry order is never semantics.
- The active eval/mcp-stabilization worktree and its unrelated dirty changes
  are untouched.

The historical overnight Phase A/B checkout is unavailable. Its supplied
results are treated only as HISTORICAL SUPPLIED EVIDENCE, not as locally
reproducible artifacts or source dependencies. The unavailable PlanIntent v1
source is therefore contextual evidence, not a verification gate.

## Same-Environment Baseline

The baseline was captured before SI-V2 source changes in this worktree.

Focused planner/provider/capability/CM-58/CM-59A selection:

- 369 passed
- 6 failed
- 0 skipped

The six failures are the pre-existing production-anchor drift failures in
tests/test_cm59a_r2a_l1_xenon_diagnostic.py:

- test_prelive_report_is_provider_and_endpoint_free
- test_finalization_is_provider_and_endpoint_free
- test_live_collision_guard_runs_before_endpoint_or_provider[evidence_path]
- test_live_collision_guard_runs_before_endpoint_or_provider[endpoint_fingerprint_pre]
- test_live_collision_guard_runs_before_endpoint_or_provider[endpoint_fingerprint_post]
- test_live_collision_guard_runs_before_endpoint_or_provider[summary_path]

Full suite (uv run --all-extras pytest -q):

- 2276 passed
- 23 failed
- 3 skipped
- 11 subtests passed

The exact full-suite failure identities are preserved in the baseline run
record at /tmp/si-v2-baseline-fullsuite.log and include the six focused
anchor failures plus the pre-existing fixture/path, MCP, notebook, tool
contract, CM-56R7, CM-57P7, graph, and CBL verifier failures reported by that
run. SI-V2 acceptance compares exact node identities against this same-worktree
baseline, not against the historical 13-failure count.

Static baseline:

- ruff check .: existing 23 diagnostics.
- ruff format --check .: existing 20 files requiring formatting.
- uv run python -m compileall -q src/wellplot/agent/code_mode src/wellplot/capabilities: pass.
- git diff --check: pass.

The literal python executable is not installed in this environment; the
project-managed uv run python command is the equivalent compile check.

## Exit Decisions

The slice must end with exactly one of:

- SI_V2_ACCEPTED_FOR_MODEL_QUALIFICATION
- SI_V2_REWORK_REQUIRED
- SI_V2_REJECTED

SI-V2.2 and all live model qualification remain outside this slice.
