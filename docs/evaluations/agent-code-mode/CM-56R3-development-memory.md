# CM-56R3 Development Memory

## Status

- Slice: planner temperature and source-grounding correction
- Baseline: `69422dc`
- Implementation checkpoint: `9cd0071`
- Evidence correction: `26086cd`
- Live evidence: complete; decision `STOP_PLANNER_RELIABILITY`
- Production section routing: unchanged; `ProgramSectionCompiler` remains active
- Typed section worker: not invoked by this slice

## Scope

CM-56R2 showed a strong temperature effect and left source selection
insufficiently grounded. CM-56R3 makes only the three authorized boundary
corrections:

1. The v2 graph plans at fixed `temperature=0.0`; worker temperature remains a
   separate state value and is unchanged.
2. Enrichment selects the only explicit source candidate when a section has no
   source hint. Zero candidates remain empty, while multiple candidates without
   a hint fail as `source_ambiguous` rather than being guessed.
3. `SemanticPlanner.plan()` accepts a separate bounded source summary. The
   provider sees only source labels and channel mnemonic/kind facts; candidate
   IDs, paths, formats, and parser details are excluded. When multiple sources
   are relevant, the planner is instructed to copy an exact supplied label into
   `source_hints`.

The source summary is passed as structured planner context in both initial and
semantic-correction requests. It is not appended to the natural-language
request, and it does not change the typed worker, schema, compiler, routing,
repair, or graph topology.

## Deterministic Evidence

- `92 passed` across the focused planner, enrichment, workflow, facade, shadow,
  and session tests.
- Ruff check passed for all changed Python files.
- Ruff format check passed.
- `git diff --check` passed.
- Production implementation commit: `9cd0071`.
- Evidence bookkeeping correction: `26086cd`.
- Production route remains unchanged apart from planner temperature and the
  bounded source-selection/context contract described above.

The full repository suite completed with `1555 passed, 10 failed, 2 skipped,
11 subtests passed`. The ten failing node IDs match the documented baseline
failure set, including the unrelated untracked graph-worker tests; CM-56R3 did
not add a new full-suite failure.

The live CM-56R3 gate used the frozen ten-case corpus, three sequential attempts
per case, the controlled local llama.cpp `qwen3.6-35b-a3b` endpoint, planner
temperature `0.0`, `16384` output tokens, and a 900-second request timeout. It
stopped after planner/enricher evidence and did not invoke the typed worker.

Raw evidence remains outside Git at `/tmp/cm56r3-live-qwen-corrected.jsonl`.
Its SHA-256 is
`9935238c0e6f0fbc6c450dc30c26c02506e54c9d76913b063a5d5082ce2439ae`.
The committed aggregate is `CM-56R3-live-summary.json`.

The 30 rows classified as follows:

| Classification | Count |
|---|---:|
| `PLANNED_AND_ENRICHED` | 26 |
| `PLANNER_FAILURE` | 3 |
| `ENRICHMENT_FAILURE` | 1 |

All three planner failures were `reverse_scale`: two provider
`invalid_response` outcomes and one `missing_section_capability` semantic
failure after the bounded correction. The one enrichment failure was
`source_ambiguous` for `source_selection`, where the provider returned two
section tasks with no source hints despite multiple explicit candidates. No
`source_missing` outcome occurred. Singleton-source tasks reached enrichment
with one selected source per section. The typed worker and semantic compiler
were not invoked.

The completed raw run predates the one-line `26086cd` bookkeeping correction;
its sole enrichment-failure row omits `planner_calls`, but retains the complete
plan, classification, error code, and redacted evidence used by the gate. This
does not affect the decision precedence or the source-selection result.

## Decision Gate

The completed 30-row matrix is evaluated in this order:

1. Any terminal planner failure yields `STOP_PLANNER_RELIABILITY`.
2. Otherwise, source selection failures yield `STOP_INPUT_CONTRACT` unless a
   multiple-source ambiguity is genuinely unresolved.
3. Only after planner and enrichment gates pass may the unchanged typed-worker
   matrix be rerun.

No CM-57 work, typed-worker fix, repair, fallback, provider change, or public
routing change is included in CM-56R3.

## Hard Stop

After the live aggregate is recorded, stop at CM-56R3. Do not start the typed
worker matrix or CM-57 in this slice. Preserve the raw JSONL outside Git unless
an audit decision requires a committed artifact.

## Decision

**STOP_PLANNER_RELIABILITY**

The fixed planner temperature and separate source context improved the host
source boundary: singleton candidates were selected deterministically and no
source-missing failures remained. However, three terminal planner failures
remain in the 30-row stage-1 matrix. The authorized precedence therefore stops
before the typed-worker matrix. CM-57 and CM-58 remain blocked.
