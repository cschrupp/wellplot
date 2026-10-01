# SI-V2.1 Provider-Free Result

## Decision

```yaml
experiment: SI-V2.1
baseline_sha: d77649765dee81ebd0b8f460ac28515b244f70da
implementation_checkpoint: 5c9de13d20a418cb50e51992413b2c35c29d7f8b
branch: research/semantic-ir-v2
worktree: /tmp/wellplot-si-v2
provider_calls: 0
endpoint_calls: 0
worker_calls: 0
decision: SI_V2_ACCEPTED_FOR_MODEL_QUALIFICATION
live_model_qualification: NOT RUN
si_v2_2: NOT AUTHORIZED
```

This is a provider-free architecture result. It qualifies the SI-V2 contract
and compiler for a future model-generation experiment; it does not qualify a
provider, activate the typed route, or authorize production cutover.

## Scope and Boundary

The active production graph, planner, provider adapters, capability registry,
CM-58 safety layers, compiler routing, persistence, and MCP behavior were not
changed. The three new modules under `src/wellplot/agent/code_mode/` are
dormant prototype modules: they are not imported by the active graph and no
runtime path calls them. Existing production route delta is therefore zero.

The prototype boundary is:

```text
SemanticIRV2
    -> registry-driven pure lowering
    -> existing SemanticPlan
    -> existing plan validation
```

The input IR contains semantic intent only. It contains no provider fields,
host paths, generated IDs, renderer concepts, capability IDs, or filesystem
state. The compiler owns deterministic lowering, generic parent closure, and
host-owned plan roots. Ambiguous or unknown semantic mappings fail closed.

The registry is persistent and immutable: registration returns a new registry
without mutating the prior instance. Built-in rules cover report, log plot,
ordinary/reference curve and raster, fill, and annotation semantics. The
fixture envelope carries `case_id` only for review indexing; it is stripped
before IR validation and is not part of the worker-facing semantic payload.

## Evidence

The manually authored fixture reproduces all 24 CM-59A system-reevaluation
canonical signatures exactly:

```text
24 / 24 exact signature matches
24 / 24 fixture cases compiled and revalidated as SemanticPlan
```

The tests prove:

- semantic multiplicity and ordering survive compilation;
- report/section composition and multi-section allocation survive;
- reference and raster distinctions survive;
- roots are host-owned and are not requested in the IR;
- built-in capability coverage includes fill and annotation;
- unknown semantics, categories, ambiguous parents, duplicate IDs, and
  invalid fill targets fail deterministically;
- explicit parent choices resolve ambiguity without mutable registry state;
- the same input compiles deterministically;
- the IR schema has required discriminator tags and no provider/host mechanism;
- fixture topology and payload content contain no capability-ID or path leakage.

### Responsibility metrics

These are bounded static proxies over the 24 frozen CM-59A cases, not live
model measurements.

```text
Current SemanticPlan choices:       min 1, max 10, mean 4.208, median 4
Current structural capability IDs:  min 1, max 10, mean 4.208, median 4
Current mandatory roots:             min 1, max 3, mean 1.417, median 1
Current parent-closure decisions:   min 0, max 7, mean 2.792, median 2.5

SI-V2 semantic choices:             min 1, max 3, mean 1.667, median 2
SI-V2 deterministic lowering IDs:   min 1, max 13, mean 5.292, median 5
SI-V2 structural capability IDs:    min 0, max 0, mean 0, median 0
SI-V2 mandatory roots:               min 0, max 0, mean 0, median 0
SI-V2 parent-closure decisions:     min 0, max 0, mean 0, median 0
```

### Schema metrics

```text
SemanticPlan schema: 1871 canonical bytes, 2 defs, 2 refs, depth 6
SemanticIRV2 schema:  5344 canonical bytes, 7 defs, 7 refs, depth 8
```

The historical `PlanIntent` v1 metrics in the report are contextual evidence
supplied by the project record; that historical source is not claimed as a
locally reproducible implementation artifact.

## Regression Comparison

The same-environment baseline was captured before SI-V2 source changes:

```text
Baseline full suite: 2276 passed, 23 failed, 3 skipped, 11 subtests passed
Post full suite:     2290 passed, 23 failed, 3 skipped, 11 subtests passed
```

The post suite adds the 14 passing SI-V2 tests. The exact 23 failing node IDs
are unchanged from the baseline; therefore SI-V2 introduced zero new
attributable failures. The six focused Xenon anchor failures remain the
previously recorded baseline condition, as do the other repository-level
failures.

The focused adjacent run was:

```text
Baseline focused set: 369 passed, 6 failed
Post focused set:     383 passed, 6 failed
```

The six focused failures are the same historical
`test_cm59a_r2a_l1_xenon_diagnostic.py` production-anchor failures.

## Validation Gates

```yaml
exact_cm59a_signatures: PASS
builtin_registry_coverage: PASS
plugin_registry_extension: PASS
ambiguous_parent_fail_closed: PASS
deterministic_compilation: PASS
focused_tests: PASS
adjacent_regression_comparison: PASS
changed_file_ruff: PASS
changed_file_formatting: PASS
managed_python_compilation: PASS
json_fixture_validation: PASS
git_diff_check: PASS
provider_calls: 0
endpoint_calls: 0
worker_calls: 0
```

Repository-wide Ruff and formatting checks retain pre-existing debt outside
this slice: the baseline had 23 Ruff diagnostics and 20 files requiring
formatting. The literal `python` executable is unavailable in this
environment; the equivalent managed `uv run python -m compileall` check passed
for the changed Python files.

## Research Basis

The design is an adaptation, not a claim of direct equivalence, of established
declarative and constrained-generation patterns:

- Vega-Lite keeps a concise declarative specification separate from compiler
  lowering and derives presentation details downstream.
- Flint describes a semantics-driven visualization intermediate language in
  which data meaning remains explicit while a compiler derives configuration.
- PICARD separates incremental schema/syntax acceptance from later semantic
  validation.

The source URLs and the WellPlot-specific adaptation notes are recorded in
`02-external-research.md`.

## Stop Rule

No provider generation, prompts, retries, repairs, orchestration changes,
production routing, SI-V2.2, or live model qualification was started. The next
slice requires separate authorization and must begin with a provider-facing
input contract review rather than silently activating this prototype.
