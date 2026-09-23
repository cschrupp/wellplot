# CM-56R8R-S1 Development Memory

## Status

- Slice: selective semantic-contract live evaluation
- Baseline: `7e0233421f8c9c6142d35eaeb29f533a0604667b`
- Experiment version: `CM-56R8R-S1`
- Authorized checkpoint: `7f3d33802cb3025cab05b4c84c9188a3e1b5c0e6`
- Worker calls: `30` (`15` A, `15` S)
- Planner calls: `15`
- Total backend requests: `45`
- Provider failures: `0`
- Production changes: `0`
- Live inference: **COMPLETE**
- Decision: `SELECTIVE_CONTRACT_FULL_RECOVERY`
- CM-57: blocked

## Governing Hypothesis

CM-56R8R-F1 found that the full semantic contract recovered raster-profile and
sample-axis semantics but regressed the already-correct reverse binding-scale
mapping. The three regressions all emitted the exact endpoint swap
`200 -> 0` to `0 -> 200` while preserving `kind=linear` and `reverse=true`.
F1 classified that relationship as
`MINMAX_NAME_CONFLICT_SIGNATURE`, without claiming access to model reasoning.

S1 therefore tests the minimum intervention: retain the authoritative worker's
generic scale behavior and add only the WellPlot-specific raster/sample-axis
guidance that R8R demonstrated was useful.

## Experimental Boundary

Variant A is unchanged from the accepted R8R control:

```text
typed worker input
    + authoritative original request
    + AUTHORITATIVE_REQUEST_SYSTEM_PROMPT
```

Variant S is exactly A plus one `selective_semantic_contracts` JSON field and a
bounded contract-use instruction. It receives no A output, evaluator result,
expected projection, or repair information. Both arms share one planner and
enrichment result, the same response schema, context validator, compiler,
evaluator, provider, and future execution controls.

## Selective Contract

Artifact:
`CM-56R8R-S1-selective-semantic-contracts.json`

- Version: `cm56r8r-s1.selective-semantic-contracts.v1`
- SHA-256: `c6dd637e3b9f287f796a76cf147acd29fbacaa9c350f6d9ab4ae8c0e5360a02f`
- Capability contract included: `binding.raster` only.
- Included mappings: `binding.profile`, `binding.sample_axis.unit`,
  `binding.sample_axis.source_origin`, `binding.sample_axis.source_step`, and
  `binding.sample_axis.tick_count`.
- Included distinction: `track.x_scale` is the array-track horizontal domain;
  `binding.sample_axis` is the raster-internal sample coordinate system, and
  track bounds must not be copied into sample-axis bounds without an independent
  request.
- Scale mappings present: none.
- Binding-scale targets present: none.
- Track-x-scale numeric mapping targets present: none.
- Concrete numeric scale examples: none.

The artifact contains no case IDs, frozen source IDs, expected titles,
benchmark endpoint tuples, expected projections, or R8R failure values. Its
machine-checkable mapping targets are structurally tested rather than checked
only by substring.

## Frozen Provenance And Controls

- Corpus SHA-256: `4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e`
- Response schema SHA-256: `93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4`
- Evaluation contract SHA-256: `3e6c3c36d967acb60e6bb7cda13db95d76ed7a754eb92c4bcf5688d76b0da4da`
- Evaluator version: `cm56r8r.corrected-evaluator.v1`
- Evaluator source SHA-256: `4bddc22e5a8267cd36e96624884eba8c8578fdd229c7d71c0bd7986bcab12e49`
- Future model: `Qwen3.6-35B-A3B-MTP-GGUF`
- Planner and worker temperature: `0.0`
- Maximum output tokens: `16384` using `max_tokens`
- Timeout: `900` seconds
- Attempts per case: `3`
- Future population: five cases, 15 paired rows, 30 worker calls
- Future output: `/tmp/cm56r8r-s1-live-qwen.jsonl`

The new runner has no mutable CLI options for temperatures, token limits,
timeout, or attempts. It rejects injected control mismatches and refuses to
append to a non-empty evidence file. Its default CLI path performs only
pre-live validation; provider execution requires a separate explicit live flag.

## Pre-Live Review Rework

The rework baseline was `5ff18b6584064d54a14df852510aab4e0e55f7c5`. The
selective contract artifact was not modified. The harness now records the
exact source-byte SHA-256 through a local `harness_source_sha256()` helper and
keeps the design baseline separate from live authorization provenance:

```text
design_baseline_sha = 7e0233421f8c9c6142d35eaeb29f533a0604667b
authorized_checkpoint = explicit 40-character lowercase SHA supplied only for live execution
```

The live runner rejects a missing, short, non-hex, uppercase, or otherwise
invalid checkpoint before provider construction. It also validates selective
contract, evaluator, evaluation-contract, corpus, and response-schema hashes
before provider construction. The future evidence-row builder is exercised by
a provider-free synthetic A/S row test and includes the complete provenance
fields required for a successful paired attempt.

## Pre-Live Evaluation Inventory

The harness derives applicable scientific leaves from the frozen corpus and
corrected evaluation contract without sending this inventory to a provider:

```text
scalar_linear:
    binding scale
reverse_scale:
    binding scale
generic_raster:
    track scale, raster profile
waveform:
    track scale, raster profile, no unrequested sample-axis bounds
vdl_sample_axis:
    track scale, raster profile, sample unit/origin/step/tick_count
```

The future decision is exact and regression-dominant: incomplete populations
are inconclusive; any A-pass/S-fail scale leaf produces
`SELECTIVE_CONTRACT_REGRESSION`; otherwise complete profile/sample-axis
recovery with no scientific extras is full recovery, partial target recovery
is partial recovery, and no target recovery is no benefit.

## Live Inference

The authorized run used the local llama.cpp OpenAI-compatible endpoint with
model `Qwen3.6-35B-A3B-MTP-GGUF`, planner and worker temperature `0.0`,
`16384` maximum output tokens using `max_tokens`, a `900` second timeout, and
three attempts for each of the five frozen cases. The run used checkpoint
`7f3d33802cb3025cab05b4c84c9188a3e1b5c0e6` and wrote the raw evidence to
`/tmp/cm56r8r-s1-live-qwen.jsonl`.

The raw evidence SHA-256 is
`43345200d356677a9c88ac77997c14c5d16c6d973711e38d17a1dea6ea86ae1c` and the
raw file remains outside the repository. The bounded committed aggregate is
`CM-56R8R-S1-live-summary.json`.

Population integrity passed:

```text
rows                         15/15
cases                        5 × 3
input sufficiency            15/15
selective-contract-only diff 15/15
A evaluation eligible        15/15
S evaluation eligible        15/15
provider failures            0
scale regressions            0
unrequested scientific extras 0
```

The paired scientific results were:

```text
                         A       S
full semantic acceptance 3/15    12/15
track scale              36/36   36/36
binding scale            24/24   24/24
raster profile           0/9     9/9
sample axis              9/18    12/12
```

S recovered twelve targeted scientific leaves without regressing any scale
leaf. The frozen decision logic therefore returns
`SELECTIVE_CONTRACT_FULL_RECOVERY`. Against the accepted R8R full-contract B
result, S retains profile and sample-axis recovery while avoiding the six
reverse-scale endpoint regressions identified by F1.

## Validation

The pre-live command path produced metadata only and made no network request.
Before live execution, the focused S1 tests and adjacent R8R/R8R-F1 tests
passed: `60 passed`. The live JSONL passed the frozen aggregation and
population-integrity checks described above.
Ruff, formatting, Python compilation, JSON validation, redaction scanning, and
`git diff --check` pass. No production files or historical R8R/F1 artifacts
were modified.

## Hard Stop

The live evidence authorizes no prompt redesign, schema change, production
integration, routing change, repair, fallback, or CM-57 work. CM-56R8R-S1 is
complete as an evaluation slice; the next decision requires independent review
of the bounded summary and raw evidence hash.
