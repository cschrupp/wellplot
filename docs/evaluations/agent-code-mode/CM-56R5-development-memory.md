# CM-56R5 Development Memory

## Status

- Slice: typed-input representation forensics
- Baseline: `aa0195f`
- Implementation checkpoint: `f3ed28a`
- Evidence correction: `00d055f`
- Live extraction correction: `227f248`
- Production changes: none
- Live inference: complete; diagnostic only
- CM-57: blocked
- Repeated-channel arm: implemented as a separate ten-attempt planner-only run

## Purpose

CM-56 post-R4 completed with `STOP_PLANNER_RELIABILITY`, but its dominant
worker result was zero accepted typed outputs among twenty-seven sections that
reached the typed worker. CM-56R5 isolates whether the current prose-heavy
worker input is weaker than an explicit semantic representation.

## Frozen A/B Boundary

For every case and attempt, the current production planner and enricher run
exactly once. The resulting `SectionTask` and `ResolvedSectionContext` are
frozen and feed both provider calls.

Variant A is exactly the current production projection:

```text
build_typed_section_input(task, section_context, registry)
    -> serialize_typed_section_input(...)
```

Variant B is byte-for-byte Variant A plus an evaluation-only
`explicit_semantics` object. B is built only from task prose and resolved
source/channel context. It does not read expected sections, canonical intent,
compile contracts, Gate-A gold, or any other expected artifact.

Both variants use the unchanged typed system prompt, `SectionSemanticDraft`
response schema, context validator, deterministic compiler, semantic evaluator,
provider, and worker settings. B never receives A's generated output or failure
feedback.

## Explicit Provenance

Every B field has an executable provenance record classified as `task`,
`context`, or `diagnostic_local_identity`. B construction fails before provider
generation if any emitted field cannot be verified against its declared source.
Evidence rows retain only a safe locator and SHA-256 evidence digest; they do
not retain flattened task prose or source/context text. Synthetic POSIX and
Windows path-shaped task text is covered by serialized-row redaction tests.
Missing VDL axis facts remain missing; R5 does not restore them from the
original request for the primary representation verdict.

The VDL case is therefore reported as a preservation control. A later optional
request-complete diagnostic may test downstream handling of explicit axis facts,
but it cannot be counted as evidence that the current planner preserved them.

## Cases and Matrix

Primary representation cases:

- `scalar_linear`
- `reverse_scale`
- `generic_raster`
- `waveform`
- `cbl_continuity` main section only

Preservation/control case:

- `vdl_sample_axis`

Each arm uses three independent attempts per case. The A/B result records
structured validity, context validity, compiler validity, semantic acceptance,
omissions, unrequested semantics, input hashes/chars, and provider metrics.

The harness flushes every completed row immediately. A structured response
validation failure is recorded as a completed provider call with invalid typed
output; a typed provider-boundary failure remains a provider failure. An
unexpected implementation exception is not converted into experiment evidence.
Explicit-input provenance failures are recorded as pre-generation diagnostic
rows and do not abort the remaining matrix. Scale kinds are emitted only when
the task explicitly states a `<kind> scale`; generic "log plot" wording is not
treated as scientific scale evidence.

Repeated-channel planner reliability is a separate ten-attempt planner-only
arm using the current production source-summary boundary. Its results are not
merged into the worker A/B matrix.

## Frozen Controls

- Corpus SHA-256: `4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e`.
- Typed prompt SHA-256: `19b0e289d2fa8ea362840aa94d90ad43cdea5b2ebdc866363df1ef28a38f2d49`.
- Response schema SHA-256: `93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4`.
- Planner temperature: `0.0`.
- Worker temperature: `1.0`.
- Maximum output tokens: `16384`.
- Timeout: `900` seconds.

The pre-live harness also verifies that the paired input-sufficiency audit is
serialized from its explicit fields rather than from implementation details of
the slots-based audit object. The repeated-channel arm uses the same production
planner source-summary boundary and never invokes typed generation.

## Interpretation

```text
A fails, B succeeds consistently -> REPRESENTATION_INSUFFICIENT
A and B fail with the same pattern -> TYPED_BOUNDARY_FAILURE
A and B both succeed             -> ORCHESTRATION_INTEGRATION_SUSPECT
Mixed or nonrepeatable           -> INCONCLUSIVE_REPRESENTATION
```

Planner reliability and VDL semantic-preservation findings remain separate
from this decision.

## Live Evidence

The authorized local Qwen run used the frozen controls above. The first
escalated attempt was interrupted before any row after the sandboxed network
path exceeded its wait; it is not part of the evidence. A fresh run with the
`227f248` extraction correction completed all eighteen paired representation
rows, and a separate run completed all ten repeated-channel planner rows.

Representation evidence:

- Raw JSONL: `/tmp/cm56r5-representation-qwen-rerun.jsonl`.
- SHA-256: `65389bc1c02fef2163acf7f770da01e4774f7d03d7ec9e1b64da5ce794ad43f`.
- Six cases, three paired attempts each; 18 planner/enrichment boundary
  invocations and 36 typed-worker calls.
- Variant A: 18/18 structured, 14/18 context-valid, 14/18 compiler-valid,
  0/18 semantic acceptance.
- Variant B: 18/18 structured, 15/18 context-valid, 15/18 compiler-valid,
  0/18 semantic acceptance.
- Primary verdict: `INCONCLUSIVE_REPRESENTATION`. No B arm produced
  consistent semantic acceptance. Scalar and generic raster showed improved
  context validity, reverse and waveform remained typed semantic failures, and
  CBL produced a distinct context-failure pattern.

The VDL preservation control is separate: its planner input was insufficient in
all three rows. `source_origin` and `source_step` survived into task prose;
`unit` and `tick_count` did not. Neither A nor B achieved semantic acceptance.
No request-complete axis facts were restored.

Repeated-channel evidence:

- Raw JSONL: `/tmp/cm56r5-repeated-channel-qwen.jsonl`.
- SHA-256: `41f0189cd826bd235b00b37dd617ceb35d40664dd1cca0500d84ccc0e76668c8`.
- Ten planner-only attempts; typed-worker calls: zero. Each terminal
  `invalid_response` is retained as an attempt-level result, not conflated with
  a successful planner response.
- All ten ended as `PLANNER_FAILURE` with provider category
  `invalid_response`.
- This finding is separate from and does not override the representation
  verdict.

Raw provider content was not committed. Both raw artifacts passed the bounded
redaction scan. The aggregate is recorded in
`CM-56R5-live-summary.json`.

## Hard Stop

This slice adds evaluation-only scripts, tests, and evidence documentation.
No `src/wellplot` file, production prompt, schema, compiler, planner, enricher,
routing, retry, repair, fallback, or acceptance contract changed. The live
evidence is complete; stop here for review. No CM-57, production contract
redesign, prompt modification, repair, or routing change follows from this
slice. CM-57 remains blocked.
