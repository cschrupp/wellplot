# CM-56R8R Development Memory

## Status

- Slice: corrected semantic evaluation contract
- Baseline: `17da03e`
- Implementation checkpoint: `3f8c0d9`
- Provider calls: `0`
- Live inference: not started
- Production changes: `0`
- CM-57: blocked

Artifact hashes:

- Corrected evaluator: `c64e96239e1fea142b4b178cb5f7442389e8bb563d10f576fac1dd48de91ca94`
- Semantic contracts: `1f1ec51c7122b28a87e707051ee7c9203cb13e5b4c0aadf773228fdbfad61eb0`
- Evaluation contract: `3e6c3c36d967acb60e6bb7cda13db95d76ed7a754eb92c4bcf5688d76b0da4da`

## Why CM-56R8R Exists

CM-56R8 produced valid 15-pair evidence, but its scale-family measurements used
the historical evaluator's asymmetric nested-object comparison. Generated
`SemanticScale` values materialized intrinsic defaults such as `kind=linear` and
`reverse=false`, while expected fixture dictionaries omitted those defaults.
The resulting scale failures are historical observations, not reliable evidence
of scale-generation failure.

The R8 `binding.raster` contract also contained the typo
`source_axis.source_origin` instead of `sample_axis.source_origin`, and its
curve-scale mapping did not explicitly map range endpoints to
`binding.scale.minimum` and `binding.scale.maximum`.

R8R corrects measurement before any architecture decision. It does not rewrite
R7 or R8 history, change production code, or assume that contracts will recover
scale semantics. The prior R8 raster-profile result remains valid evidence:
R8 A `0/9`, B `9/9`, with 9 recoveries and 0 regressions.

## VDL Semantic Audit

The production definitions establish that track x-scale and raster sample-axis
bounds are independent semantic fields:

- `src/wellplot/agent/code_mode/section_semantics.py:40-67` defines
  `SemanticScale` separately from `SemanticSampleAxis`; sample-axis minimum and
  maximum are optional fields, not derived values.
- `src/wellplot/agent/code_mode/semantic_section_compiler.py:170-172` compiles
  `ArrayTrackSemanticDraft.x_scale` independently.
- `src/wellplot/agent/code_mode/semantic_section_compiler.py:194-226` compiles
  raster `sample_axis` independently and does not copy track x-scale values.
- `src/wellplot/model/document.py:1101-1150` stores raster sample-axis
  minimum/maximum separately from the track x-scale.
- `src/wellplot/renderers/plotly.py:303-311` may use track x-scale as a
  downstream rendering fallback when explicit sample-axis bounds are absent;
  that is presentation behavior, not a worker semantic implication.

Therefore R8R uses the declarative VDL policy `explicit_request_only`: retain
the explicit unit, source origin, source step, and tick count, retain the
track x-scale bounds, and remove only the historical sample-axis minimum and
maximum from the R8R expected overlay. The frozen corpus is unchanged.

## Corrected Contracts

`CM-56R8R-semantic-contracts.json` is versioned independently from R8 and uses
machine-checkable mappings. It explicitly maps:

- curve linear/log/tangential ranges to `binding.scale.kind`, `minimum`, and
  `maximum`;
- reverse/reversed language to `binding.scale.reverse`;
- array x-scale language to `track.x_scale.minimum` and `maximum`;
- generic/waveform/vdl language to `binding.profile`;
- sample unit, origin, step, and ticks to the exact `binding.sample_axis.*`
  paths.

No frozen case IDs, source IDs, expected titles, benchmark numeric tuples,
paths, canonical IDs, or provider content appear in the provider contract.

`CM-56R8R-evaluation-contract.json` is separate from the provider contract. It
declares symmetric model normalization, leaf status values, scientific families,
and the transparent VDL expected-semantic overlay with provenance.

## Corrected Evaluator

The corrected evaluator version is `cm56r8r.corrected-evaluator.v1`. It uses the
same `SemanticScale` model for expected and generated
values, preserving explicit units and rejecting wrong bounds, transforms, and
reverse flags. It uses the same symmetric treatment for `SemanticSampleAxis`
without injecting compiler presentation defaults such as tick count 5.

Scientific results are exposed at leaf resolution with `PASS`, `MISSING`,
`WRONG_VALUE`, and `UNREQUESTED_EXTRA`, then aggregated by field, family, case,
variant, and pair. Generated and expected semantic projections are bounded
post-generation evidence; raw provider prose and reasoning are not retained.

The A/B boundary remains unchanged:

```text
A = authoritative original request + current typed worker input
B = exact A + corrected capability-local semantic contracts
```

Both arms retain the same planner result, enriched context, response schema,
compiler, and provider settings. Expected overlays and evaluation data are
never included in either provider payload.

## Hard Stop Before Live Inference

The R8R evaluator, contracts, VDL audit, tests, and evidence policy must be
reviewed and pushed before any model call. The future run is exactly 15 paired
rows and 30 worker calls across the five frozen R8 cases, using the unchanged
local Qwen controls. This implementation slice makes zero provider calls.

Historical artifacts remain untouched:

- `CM-56R7-development-memory.md`
- `CM-56R7-semantic-failure-summary.json`
- `CM-56R8-development-memory.md`
- `CM-56R8-live-summary.json`
- `CM-56R8-semantic-contracts.json`
- `scripts/cm56r8_semantic_contract_diagnostic.py`
- `tests/test_cm56r8_semantic_contract_diagnostic.py`

No production planner, enricher, workflow, schema, compiler, typed worker,
provider adapter, routing, retry, fallback, evaluator, or acceptance change is
authorized. CM-57 remains blocked pending independent review and separate live
authorization.
