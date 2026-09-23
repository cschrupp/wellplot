# CM-56R6 Development Memory

## Status

- Slice: authoritative-original-request worker diagnostic and repeated-channel planner forensics
- Baseline: `2db8d9f`
- Production changes: none
- CM-57: blocked
- Live inference: complete; diagnostic only

## Purpose

CM-56R5 showed that the current typed schema and deterministic compiler were
mostly healthy, while semantic acceptance remained zero. It also showed that
planner output can lose scientific details before the worker sees them. CM-56R6
tests whether preserving the original request directly at the worker boundary
improves semantic generation, without changing production contracts.

## Arm A/C: Request Preservation

The six frozen CM-56 cases are evaluated only when planning reaches a section
task: `scalar_linear`, `reverse_scale`, `generic_raster`, `waveform`,
`cbl_continuity`, and `vdl_sample_axis`. Each attempt runs the planner and
enricher once. The resulting task and resolved context are shared by two worker
calls:

```text
A = current production typed input
C = exact A input + path-redacted authoritative_original_request
```

Both calls use the same `SectionSemanticDraft`, context validator, deterministic
compiler, evaluator, provider, and worker temperature (`0.0`). The C system
prompt explicitly defines the original request as authoritative, the section
task as routing/scope, and resolved context as the available source/channel
boundary. C does not receive generated output or failure feedback from A.

The original request is path-redacted before provider exposure. Evidence stores
only hashes, sizes, classifications, and bounded semantic findings; it does not
store raw provider responses or request prose.

## Arm B: Repeated-Channel Planner Forensics

The `repeated_channel` case runs ten independent planner-only attempts at
temperature `0.0`. The unchanged production planner and OpenAI-compatible
adapter are wrapped by an evaluation-only response capture. Each provider
response is classified using safe metadata only:

```text
provider exception
provider shape/refusal/tool failure
incomplete response
JSON parse failure
schema validation failure
semantic plan failure
successful plan
```

The capture records response hashes, lengths, finish/shape flags, sanitized
validation locations/types, and a bounded plan projection. It never stores raw
provider content.

## Frozen Controls

- Corpus SHA-256: `4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e`.
- Response schema SHA-256: `93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4`.
- Planner temperature: `0.0`.
- Worker temperature: `0.0` for both A and C.
- Maximum output tokens: `16384`.
- Timeout: `900` seconds.

## Interpretation

```text
C materially improves semantics over A -> authoritative request is a useful worker input boundary
A and C fail identically                 -> request preservation is insufficient or another worker issue remains
A and C both succeed                      -> current worker boundary is adequate for these cases
mixed/nonrepeatable                      -> inconclusive diagnostic
```

The repeated-channel arm is separate evidence. It does not override the A/C
verdict. Its response-shape/schema classification determines whether a narrow
planner forensic follow-up is justified.

## Hard Stop

This slice is evaluation-only. It does not change `src/wellplot`, prompts,
schemas, compilers, planner behavior, enricher behavior, routing, retries,
repair, fallback, persistence, or production acceptance. No CM-57 work starts
from this checkpoint. Live evidence, if authorized and run, must be recorded
separately and reviewed before any production contract change.

## Live Evidence

The authorized local Qwen run used the frozen controls above. The A/C
representation arm completed 18 paired rows (36 worker calls):

- Variant A: 18/18 provider calls completed, 18/18 structured, 15/18 context/compiler-valid, 0/18 semantic acceptance.
- Variant C: 18/18 provider calls completed, 18/18 structured, 15/18 context/compiler-valid, 0/18 semantic acceptance.
- Both arms had the same three `channel_missing` CBL outcomes.
- Fifteen rows passed context/compiler validation, but every row had semantic omissions or other evaluator failures.
- The VDL control retained insufficient planner input for three rows; no hidden axis facts were restored.
- The A/C payload relation was exact: C added only `authoritative_original_request`, with the path-redacted request and the explicit authority prompt.

The representation verdict is therefore `TYPED_WORKER_SEMANTICS_REMAINS`, not
`REPRESENTATION_INSUFFICIENT`: request preservation did not improve semantic
acceptance under the same typed schema/compiler/evaluator path.

The separate repeated-channel arm completed ten planner-only attempts. All ten
were `PLAN_SUCCESS` with one provider call, valid JSON, valid `SemanticPlan`,
and valid semantic-plan validation. The earlier 10/10 `invalid_response`
finding did not reproduce under these frozen local controls; it is retained as
historical evidence, not erased or reclassified.

Raw artifacts:

- A/C JSONL: `/tmp/cm56r6-authoritative-qwen-rerun.jsonl`, SHA-256 `bf59a618dbff03b4a529e0f3d484e22c04c74a6eb7203ac3410142c30d50a8ff`.
- Repeated-channel JSONL: `/tmp/cm56r6-repeated-channel-qwen.jsonl`, SHA-256 `ac761b98b387f1cb25f4abc42c11939e2f6d61a4c6f1d812fa4573116ed3904f`.
- Both raw artifacts passed the bounded redaction scan. Raw provider content was not committed.

## Final Stop

CM-56R6 does not authorize a production semantic-worker redesign, prompt
change, planner change, schema change, repair behavior, or CM-57. The next
decision requires separate review of the remaining worker-semantic failure
and the non-reproduced repeated-channel result.
