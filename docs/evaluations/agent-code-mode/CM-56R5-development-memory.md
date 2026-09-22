# CM-56R5 Development Memory

## Status

- Slice: typed-input representation forensics
- Baseline: `aa0195f`
- Implementation: pre-live checkpoint
- Production changes: none
- Live inference: not authorized before checkpoint review
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

## Hard Stop

This slice adds evaluation-only scripts, tests, and evidence documentation.
No `src/wellplot` file, production prompt, schema, compiler, planner, enricher,
routing, retry, repair, fallback, or acceptance contract may change. Commit and
push the pre-live checkpoint, then stop for review before any live provider
calls. CM-57 remains blocked regardless of the R5 result.
