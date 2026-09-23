# CM-56R8 Development Memory

## Status

- Slice: capability-local semantic contract diagnostic
- Baseline: `a8acbf1`
- Implementation checkpoint: `aefd7aa`
- Provider calls: `0`
- Live inference: not started
- Production changes: `0`
- CM-57: blocked

## Rationale

CM-56R7 showed that schema validity, source grounding, and topology were strong,
while scientific field mapping failed systematically. The current evidence does
not establish that the model lacks well-log terminology. It establishes a
narrower boundary: natural-language scientific meaning is not reliably mapped to
the exact WellPlot semantic IR field.

Structured-generation and semantic-parsing systems distinguish legal schema
shape from semantic descriptions and schema linking. CM-56R8 tests that
distinction without introducing a production semantic-documentation subsystem.

## Frozen A/B Boundary

The five primary cases are `scalar_linear`, `reverse_scale`, `generic_raster`,
`waveform`, and `vdl_sample_axis`, with three paired attempts each. The CBL
context-invalid case and repeated-channel planner case are excluded.

Both variants share one planner/enrichment result, authoritative original
request, selected capabilities, resolved source/channel context, response
schema, model settings, compiler, validator, and evaluator.

```text
A = current R6 authoritative-request worker boundary
B = exact A payload + selected capability-local semantic_contracts
```

B adds only a concise instruction that the contracts define domain-to-IR field
meaning and that examples are mappings, not defaults. No generated A output,
failure feedback, repair, or deterministic semantic filling is used.

## Contract Artifact

The frozen evaluation-only contracts are in
`CM-56R8-semantic-contracts.json`. They cover only the selected capabilities:

- `track.normal`: normal track container, title, ordered curve bindings.
- `track.array`: array container and horizontal `track.x_scale` semantics.
- `binding.curve`: exact scalar channel and individual `binding.scale` semantics.
- `binding.raster`: exact array channel, raster profile, and sample-axis semantics.

The contracts explicitly distinguish curve-specific `binding.scale` from array
track `track.x_scale`, document linear/log/tangential/reverse mappings, explain
generic/waveform/vdl profiles, and define sample unit, origin, step, and tick
meaning. Examples use synthetic names and values that are not frozen benchmark
answers. No expected sections, Gate-A outputs, case IDs, source candidate IDs,
canonical IDs, paths, or provider fields are used to construct them.

## Hard Stop Before Live Inference

The harness and contract artifact must be reviewed and pushed before any model
call. The live plan is 15 paired attempts and 30 worker calls at planner and
worker temperature `0.0`, maximum output tokens `16384`, and timeout `900`
seconds. This checkpoint intentionally does not run that matrix.

R8 will use the existing `SectionSemanticDraft`, deterministic compiler,
context validator, and evaluator unchanged. It will report scientific-only
pass, full semantic acceptance, per-family pass rates, pairwise recoveries and
regressions, and the exact capability-contract hash.

## Hard Boundaries

No production planner, enricher, workflow, schema, compiler, typed worker,
provider adapter, routing, retry, fallback, evaluator, or acceptance change is
authorized. No raw provider output or live evidence is committed. CM-57 remains
blocked pending separate review of the pre-live checkpoint.
