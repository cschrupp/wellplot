# CM-57P3 Development Memory

## Status

CM-57P3 is an evaluation-only planner micro-bisect against the frozen CM-57P2
evidence checkpoint `be6297fe710ffa59d5e0fa222db0d37544ea6455`. This
pre-live implementation checkpoint authorizes zero provider calls and zero
production changes. Live inference remains separately unauthorized.

CM-57P2 closed as `PLANNER_CONTRACT_REGRESSION`: the production planner's
parent-closure validation was effective, but the live result still showed
logical SectionTask fragmentation and unexpected report-task creation. P3
isolates those two prompt-contract factors without changing planner code.

## Frozen Experiment

The four arms are fixed and ordered `P`, `W`, `R`, `WR`:

- `P`: the exact production planner prompt.
- `W`: P plus the frozen logical work-unit instruction.
- `R`: P plus the frozen report-task boundary instruction.
- `WR`: P plus W and R, in that order.

The actual production `SemanticPlanner.plan()` is used in every arm. An
evaluation-only provider wrapper asserts the production prompt and replaces
only `system_prompt`; user prompt, response model, timeout, temperature, and
token budget are unchanged. The same wrapper applies to initial and semantic
correction requests. It never modifies plans or diagnostics.

The frozen instructions are:

```text
Work-unit boundary:

A SectionTask represents one independently compilable logical section, not one
capability. Capabilities describing that section's container, tracks, and
bindings belong together in that same SectionTask.

Do not create separate SectionTasks merely because capabilities have different
categories or structural levels.

Create multiple SectionTasks only when the user's request actually describes
multiple independently compilable logical sections.
```

```text
Report-task boundary:

Use report_task only for genuinely report-wide work explicitly requested by the
user.

If the request consists only of creating, modifying, or describing one or more
plot/log sections, report_task must be null.

Do not create an empty, placeholder, summary-only, or bookkeeping report_task
for section-local work.
```

## Future Live Matrix

The future matrix reuses all 16 frozen CM-57C cases and runs two attempts per
case, producing 32 paired shared rows and 128 planner executions. Each shared
row constructs the request and path-free source summary once, then runs arms in
the fixed order `P`, `W`, `R`, `WR`. The frozen controls are model
`qwen3.6-35b-a3b`, planner temperature `0.0`, `max_tokens=16384`, and a
900-second timeout. No workers, enrichment, typed output, or graph execution
are part of P3.

Evidence is bounded to plan shape, capability IDs, counts, classifications,
metrics, and hashes. Provider payloads, prose, paths, and hidden reasoning are
not retained. The future runner flushes each completed paired row to a new
`/tmp/cm57p3-work-unit-bisect-qwen.jsonl` file and refuses a non-empty file.
The P2 summary anchor is
`0aa20622e319117a1920f2a9809404fc00f087582c6c90786a159229c7b5e6fe`, with raw
evidence SHA
`33361e0ec2020b2215793fac87df52547a86d542fd6ed886def77871a5e79d38`.

## Measurements and Decisions

P3 records initial and final planner facts, semantic-correction use and
recovery, work-unit fragmentation, fragmentation with a capability gap,
single-task closure omission, report pollution, parent closure, wrong
selection, and the four paired factor transition tables. Population integrity
requires exactly 32 rows, 16 cases, attempts `{0, 1}`, one checkpoint, and all
four arms per row.

The only allowed primary decisions are:

- `PROMPT_CONTRACT_FULL_RECOVERY`
- `PROMPT_CONTRACT_PARTIAL_RECOVERY`
- `PROMPT_CONTRACT_NO_RECOVERY`
- `PROMPT_CONTRACT_REGRESSION`
- `INCONCLUSIVE_PLANNER_MICRO_BISECT`

Infrastructure failure, incomplete population, hash drift, control mismatch,
or wrapper isolation failure is inconclusive. The decision does not authorize
production adoption. Scientific typed-worker semantics remain out of scope.

## Boundaries and Validation

P3 preserves the EXP-TW semantic representation, required discriminators,
semantic validation, deterministic compiler, CM-57IB typed input boundary, and
CM-57B capability metadata boundary. It does not modify
`src/wellplot/**`, P2, the corpus, planner schema/catalog, routing, enrichment,
typed workers, or graph topology. CM-57D remains blocked.

The implementation checkpoint must pass focused P3 tests, adjacent P2 and
planner tests, Ruff, formatting, Python compilation, JSON validation,
redaction/path scans, and `git diff --check`. Provider calls remain zero until
a separate live authorization review.
