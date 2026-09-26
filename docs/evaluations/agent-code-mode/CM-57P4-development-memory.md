# CM-57P4 Development Memory

## Status

CM-57P4 is an evaluation-only planner prompt interaction and ordering
micro-bisect against the completed CM-57P3 evidence checkpoint
`ad870d94b62e297585c29867debd40f556489f05`. The purpose is to isolate the
remaining `mixed_curve_raster_section` interaction without changing the
production planner, planner schema, capability catalog, typed worker, or
routing. Pre-live implementation is complete; live inference remains
unauthorized.

CM-57P3's contemporaneous residual was:

- R: `2/2` final contract passes for `mixed_curve_raster_section`.
- WR: `0/2` final contract passes for `mixed_curve_raster_section`.
- WR's final residual omitted `binding.curve` and `binding.raster` after
  correction.

The P3 evidence remains frozen at:

- Decision: `PROMPT_CONTRACT_PARTIAL_RECOVERY`.
- Authorized checkpoint: `2e4f26f94670b8fa43cd7bea1246cb414c87bc41`.
- Raw rows: `32`.
- Raw SHA-256:
  `84dd0a9b9a9b6288f7442211cc72b427512db39128d8b976c12e378888aca1a0`.

## Experimental Arms

The four contemporaneous P4 arms execute in fixed order:

- `R`: the exact P3 report-boundary control.
- `WR`: the exact P3 combined control, W followed by R.
- `RW`: the exact R and W instructions with their order reversed.
- `RC`: R followed by the new compact section-composition instruction; C
  replaces W rather than accumulating another instruction.

The new C instruction is:

```text
SectionTask composition:

A SectionTask represents one independently compilable logical section.

When one requested section contains multiple tracks, including tracks of
different kinds, keep those tracks in the same SectionTask and include the
complete capability type set needed for the section container, every requested
track, and every requested binding.

Create another SectionTask only for another independently compilable section.
```

It is generic, short, and contains no benchmark-specific capability IDs or
examples.

Frozen prompt hashes:

- W instruction:
  `e0ce6bf0fe598dc438a65ecb08a8a88a45f1aeda8e66e85158d90f1f46dac5c4`.
- R instruction:
  `12fd2c40e407cb7d5d0e21effd66493e20e99468e3a97b89ac0186b40648c5b5`.
- C instruction:
  `b69c47063b6da13e4f5857609708efe0becc901b989a1a65c503dd277cdc8205`.
- R prompt:
  `fe8db9c9cba4cf7bf13d79c3e838eaa53e19770fbf6dd764cdcf93020008c563`.
- WR prompt:
  `5a0e49f077e45587e19470f962b09528a4a485a0d05725eb285cef676de1035f`.
- RW prompt:
  `d9043041fdc651d613c67a2a77a825be1d52b1940a2f82d0ff73e03d914116ca`.
- RC prompt:
  `e1710cb516a96c47ec1d0593752e83aacc1bb4502c3026b2b6a9a676c90e4d34`.

R and WR are byte-identical to their P3 controls. Across all arms, the
evaluation-only wrapper asserts the frozen production base prompt and changes
only `system_prompt`. User prompt, response model, timeout, temperature,
token budget, source summary, validation, correction behavior, and provider
result are unchanged.

## Frozen Matrix

The harness reuses the 16 frozen CM-57C cases with two attempts per case:

- Shared rows: `32`.
- Planner executions: `128`.
- Provider calls: `128` to `256` depending on production correction use.
- Worker/program calls: `0`.
- Model: `qwen3.6-35b-a3b`.
- Planner temperature: `0.0`.
- Maximum output tokens: `16384` using `max_tokens`.
- Timeout: `900` seconds.
- Raw evidence path: `/tmp/cm57p4-prompt-interaction-qwen.jsonl`.

Before any future provider construction, the harness requires the evidence
path to be empty, the exact authorized checkout, the unchanged P3 harness and
live summary, the unchanged planner/catalog/corpus anchors, and all prompt
hashes. The default CLI path performs these checks and deterministic self-tests
with zero provider calls.

The P4 harness uses the production `SemanticPlanner.plan()` for every arm. It
does not invoke enrichment, typed workers, semantic compilation, program
generation, graph orchestration, rendering, or routing. It records initial and
final bounded plan facts, terminal outcomes, correction use, availability-aware
semantic pair tables, six full-contract pair tables, repeatability, and the
historical mixed-case/P3 recovery sentinels.

## Decision Contract

The allowed future decisions are:

- `PROMPT_INTERACTION_FULL_RECOVERY`.
- `PROMPT_INTERACTION_PARTIAL_RECOVERY`.
- `PROMPT_INTERACTION_NO_RECOVERY`.
- `PROMPT_INTERACTION_REGRESSION`.
- `INCONCLUSIVE_PROMPT_INTERACTION_BISECT`.

Only candidate arms `RW` and `RC` affect the primary decision. `R` and `WR`
remain contemporaneous controls. A complete candidate at `32/32` is full
recovery; a candidate that exceeds WR without reaching 32 is partial recovery.
If the best candidate does not exceed WR, the result is no recovery unless the
frozen regression or inconclusive conditions apply. A poor candidate does not
invalidate an independent candidate. Provider infrastructure failure,
incomplete population, checkpoint/hash drift, control drift, evidence
corruption, or prompt-wrapper isolation failure is inconclusive.

No result authorizes production prompt adoption. CM-57D remains blocked.

## Boundaries and Validation

Production changes: `0`.

The implementation adds only the P4 harness, focused tests, and this
development memory. CM-57P3, CM-57P2, the corpus, planner schema/catalog,
typed-worker artifacts, and routing remain unchanged. Provider calls remain
`0` during pre-live implementation, and live inference has not started.

Validation completed before the pre-live checkpoint:

- Focused P4 tests: `15 passed`.
- Adjacent planner/capability/workflow/CM-57C tests: `125 passed`.
- EXP-TW regression selection: `134 passed`.
- Provider-free CLI: `PRELIVE_READY`.
- Ruff: `PASS`.
- Formatting: `PASS`.
- Python compilation: `PASS`.
- JSON validation: `PASS`.
- Redaction/path scan: `PASS`.
- `git diff --check`: `PASS`.
- Full repository suite: `1816 passed, 12 failed, 3 skipped, 11 subtests
  passed`.

The full-suite failures are outside the P4 file boundary and are retained as
repository-level baseline/worktree issues. They cover the known legacy MCP
helper signature tests, the tool-budget threshold, the unavailable R6
evidence artifact, and unrelated report/section fixture tests. No P4 test or
P4 implementation file failed.

Hard stop: do not run Qwen, a smoke case, RW, RC, or any other provider call
until separate live authorization. Do not begin CM-57D or typed-worker
remediation from this slice.
