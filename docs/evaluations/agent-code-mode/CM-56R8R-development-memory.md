# CM-56R8R Development Memory

## Status

- Slice: corrected semantic evaluation contract
- Baseline: `17da03e`
- Pre-live review baseline: `9988908`
- Implementation checkpoint: `d6e291c`
- Provider calls: `30`
- Live inference: complete
- Production changes: `0`
- CM-57: blocked

Artifact hashes:

- Corrected evaluator: `4bddc22e5a8267cd36e96624884eba8c8578fdd229c7d71c0bd7986bcab12e49`
- Evaluator version: `cm56r8r.corrected-evaluator.v1`
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

The pre-live review rework is bounded to the corrected evaluator and its
focused tests. Scientific extras are recorded as explicit `UNREQUESTED_EXTRA`
leaf statuses, including extra scale and sample-axis fields. Missing raster
profiles use the binding leaf path
`tracks[i].bindings[j].profile`. Population aggregation remains diagnostic for
partial rows but emits `INCONCLUSIVE_SEMANTIC_CONTRACT` unless all 15 exact
case/attempt pairs are present, input-sufficient, contract-only-different, and
evaluation-eligible in both arms.

Every future row and aggregate carries the evaluator version and exact source
digest of the evaluator executed. The live runner freezes the R8 controls at
execution time: model `Qwen3.6-35B-A3B-MTP-GGUF`, planner and worker temperature
`0.0`, maximum output tokens `16384`, `max_tokens`, timeout `900` seconds, and
three attempts per case. Control overrides are rejected, and the runner refuses
to append to a non-empty JSONL evidence path.

The R8R evaluator, contracts, VDL audit, tests, and evidence policy were
reviewed and pushed before the authorized model call. The matrix used exactly
15 paired rows and 30 worker calls across the five frozen R8 cases, using the
unchanged local Qwen controls. The pre-live rework itself made zero provider
calls.

## Live Evidence

The authorized matrix completed once through the local Qwen endpoint. The raw
JSONL remains outside the repository:

- Path: `/tmp/cm56r8r-live-qwen.jsonl`
- SHA-256: `bf1274b987c948e68c36f4f0de6a945860fce6baf97e32f335943bfbb3c16aca`
- Population: 15 paired rows, five cases, three attempts per case
- Worker calls: 30, provider failures: 0
- Input sufficiency: `15/15`
- A/B evaluation eligibility: `15/15` each
- Semantic-contract-only difference: `15/15`
- Evaluator version/source hash and all frozen artifact hashes: identical across rows

The bounded aggregate is in `CM-56R8R-live-summary.json`. Corrected R8R
results are:

```text
                              A          B
track scale                  36/36      36/36
binding scale                24/24      18/24
raster profile                0/9        9/9
sample axis                   9/18      12/12
scientific-only               6/15      12/15
full semantic acceptance      3/15      12/15
```

There were 12 scientific A-fail/B-pass recoveries and 6 A-pass/B-fail
regressions, producing the frozen decision
`SEMANTIC_CONTRACT_PARTIAL_RECOVERY`. The regressions are retained in the
leaf-level summary; no manual reinterpretation or threshold was applied.

Compared with the valid R8 observation, raster profile remains `A 0/9 -> B
9/9`. R8R is the first corrected symmetric `SemanticScale` measurement, and
the VDL result is the first measurement under the `explicit_request_only`
sample-axis policy. R8's historical scale-family rates are not reused as
corrected baselines.

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

Validation for the rework: 28 focused tests and 66 focused-plus-adjacent tests
pass; Ruff lint and formatting, Python compilation, JSON validation, and
`git diff --check` pass. R8R live inference remains **NOT STARTED**.
