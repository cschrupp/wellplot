# CM-56R7 Development Memory

## Status

- Slice: offline semantic failure decomposition
- Baseline: `3ea8484`
- Implementation checkpoint: `a839493`
- Evidence checkpoint: pending
- Provider calls: `0`
- Production changes: `0`
- CM-57: not started; remains blocked

## Evidence Integrity

R7 analyzed only the frozen CM-56R6 A/C evidence. The raw R6 JSONL was not
modified, rerun, or reconstructed.

- Path: `/tmp/cm56r6-authoritative-qwen-rerun.jsonl`
- SHA-256: `bf59a618dbff03b4a529e0f3d484e22c04c74a6eb7203ac3410142c30d50a8ff`
- Rows: `18`
- Case distribution: six cases, three rows each
- Corpus SHA-256: `4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e`

The analyzer failed closed on missing files, SHA mismatches, wrong row counts,
wrong case distributions, incomplete A/C pairs, and corpus mismatches before
doing semantic analysis.

## Eligibility

An output was evaluation-eligible only when `structured_valid`, `context_valid`,
and `compiler_valid` were all true. Context-invalid rows were retained as
separate evidence and excluded from field-level semantic denominators.

| Variant | Rows | Eligible | Context-invalid | Full acceptance |
| --- | ---: | ---: | ---: | ---: |
| A | 18 | 15 | 3 (`channel_missing`) | 0/15 |
| C | 18 | 15 | 3 (`channel_missing`) | 0/15 |

The three CBL context-invalid rows per variant were not converted into semantic
omissions.

## Semantic Failure Topology

R7 reconstructed the exact applicable check paths emitted by
`evaluate_semantic_draft()` from the frozen expected sections. It treated a path
listed in `omissions` as failed and an applicable path absent from `omissions`
as passed. `unrequested_semantics` remained a separate rejection dimension.

| Family | A pass / applicable | C pass / applicable |
| --- | ---: | ---: |
| Labels | 24/30 | 27/30 |
| Source grounding | 15/15 | 15/15 |
| Track topology | 30/30 | 30/30 |
| Binding topology | 60/60 | 60/60 |
| Track scale | 0/9 | 0/9 |
| Binding scale | 0/6 | 0/6 |
| Raster profile | 3/9 | 0/9 |
| Sample axis | 0/3 | 0/3 |

All `15/15` eligible A rows and `15/15` eligible C rows failed at least one
scientific-semantic family. No eligible row passed every scientific-semantic
check. There were no label-only rejections and no unrequested-only rejections.

The scientific-only diagnostic projection was therefore `0/15` for A and
`0/15` for C. The topology projection was `15/15` for both variants. This
replaces the coarse `0/18` full-acceptance impression with a precise result:
source/channel grounding and topology were stable, while scientific semantic
fields failed systematically.

Family-specific zero-pass findings were:

- A: track scale `0/9`, binding scale `0/6`, sample axis `0/3`.
- C: track scale `0/9`, binding scale `0/6`, raster profile `0/9`, sample axis `0/3`.

The exact per-check statistics, per-case matrix, row profiles, and pairwise
tables are in `CM-56R7-semantic-failure-summary.json`.

## Per-Case Findings

- `cbl_continuity`: `0/3` eligible for both variants because all rows failed context validation with `channel_missing`.
- `scalar_linear`: A and C were eligible `3/3`; both failed all binding-scale checks.
- `reverse_scale`: A and C were eligible `3/3`; both failed all binding-scale checks.
- `generic_raster`: A and C were eligible `3/3`; A failed track-scale checks and C failed track-scale plus raster-profile checks.
- `waveform`: A and C were eligible `3/3`; both failed track-scale and raster-profile checks, with additional label/unrequested differences recorded in the detailed matrix.
- `vdl_sample_axis`: A and C were eligible `3/3`; both failed track-scale, raster-profile, and sample-axis checks. A also had label failures; C did not.

## Pairwise A/C Evidence

Pairwise comparison was computed only for paired rows where both variants were
evaluation-eligible. Across applicable check instances:

- Both pass: `129`
- A fail / C pass: `3`
- A pass / C fail: `3`
- Both fail: `27`

The only C recoveries were three label checks. C had three raster-profile
regressions. Net family deltas were neutral for the overall semantic question:

- Labels: `+3` checks recovered, `0` regressions.
- Raster profile: `0` recoveries, `3` regressions.
- Source, topology, track scale, binding scale, and sample axis: `0` recoveries, `0` regressions.

The original request therefore did not improve any scientific-semantic family.

## VDL Attribution

The VDL policy remained variant-specific:

- A: `3/3` sample-axis failures are attributed to `UPSTREAM_FACT_NOT_PRESERVED`, because the planner task lacked the unit/tick-count facts.
- C: `3/3` sample-axis failures are attributed to the worker semantic boundary, because C received the authoritative original request containing those facts.

These are not merged into one worker-failure count.

## Decision

Top-level decision: **`SCIENTIFIC_SEMANTICS_SYSTEMIC`**.

This is a diagnostic finding, not a replacement acceptance rule. It means every
eligible semantic-rejected output contained at least one scientific-semantic
failure; it does not authorize changing the evaluator, schema, prompt, planner,
compiler, or production route. The evidence supports investigating the typed
worker's scientific semantic synthesis boundary rather than treating labels or
topology as the dominant cause.

The separate CM-56R6 repeated-channel planner arm remains historical context
only: it completed `10/10 PLAN_SUCCESS` and is not part of this semantic
decomposition.

## Hard Stop

CM-56R7 changed no production files and made no provider calls. It does not
authorize a typed-worker redesign, deterministic semantic extraction, prompt or
schema changes, repair/retry behavior, planner/enricher changes, routing, or
CM-57. Further architecture work requires review of this decomposition.
