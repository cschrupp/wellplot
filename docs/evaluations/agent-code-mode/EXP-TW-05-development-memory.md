# EXP-TW-05 Development Memory

## Baseline and question

- Baseline: `91c4151` (final EXP-TW-04 evidence correction).
- Question: which structural schema feature first breaks the local
  llama.cpp/Qwen structured-output path between historical `SectionDraft` and
  strengthened `SectionDraftS`?
- Status: experimental harness implemented; live characterization pending.
- Production delta: zero.

This is a compatibility bisect, not a model-quality benchmark. The provider,
model, typed input, prompt semantics, request settings, Gate-A implementation,
and provider adapter remain fixed. Only the requested response model changes.

```text
known-good schema
        ↓
change one structural feature
        ↓
measure compatibility
        ↓
only then decide remediation
```

## Schema ladder

The ladder is defined in `scripts/exp_tw05_schema_bisect.py` and uses the
historical leaf models and role domain without adding role-to-kind semantics.

| Variant | Feature introduced | Response model |
| --- | --- | --- |
| S0 | Historical control | `SectionDraft` unchanged |
| S1 | Track discriminator on `kind` | `SectionDraftS1` |
| S2 | Normal/reference curve-only bindings | `SectionDraftS2` |
| S3 | Array raster-only bindings | `SectionDraftS3` |
| S4 | Required array `x_scale` | `SectionDraftS4` |
| S5 | Exact strengthened control | Existing `SectionDraftS` |

Every variant preserves `TrackRole = Literal["combo", "depth", "cbl", "vdl"]`
and reuses `ScaleDraft`, `CurveBindingDraft`, `RasterBindingDraft`, and
`SampleAxisDraft`. No variant encodes `vdl → array`, `cbl → normal`, or any
other task-specific role/kind rule.

## Provider and input control

The primary live target is the local llama.cpp OpenAI-compatible endpoint using
Qwen `qwen3.6-35b-a3b`, with the same endpoint/backend settings used by the
TW-03 and TW-04 local evidence: JSON Schema mode, `max_tokens`, timeout 900,
and `chat_template_kwargs.enable_thinking=false`. Each attempt uses the exact
deterministic `serialize_provider_input(TypedWorkerInputBundle)` payload and
the exact historical TW-03 system instruction:

```text
Return exactly one SectionDraft that matches the typed input bundle. Use no fields outside the SectionDraft schema.
```

That instruction is shared across all variants and contains no
schema-specific hints.

There is exactly one structured generation call per attempt. Provider and
structured-output failures are terminal. No repair, retry, fallback, raw
response parsing, custom grammar, provider switching, or orchestration is
present.

The staged runner executes 10 independent `main_pass` and 10 independent
`repeat_pass` attempts per variant. It flushes each completed attempt to the
redacted JSONL before starting the next request and persists each section
aggregate before advancing. If S0 does not produce structurally valid outputs
for all attempts in both sections, the ladder stops and the result is
classified as a control failure rather than interpreted causally. The CLI can
also stop explicitly after `S0`, which is required before spending calls on
downstream variants.

## Evidence contract

Each redacted attempt records the variant and schema hash, section role,
attempt index, provider/model identity, exact provider-input hash, request
settings, typed outcome, safe provider metadata, metrics when available, the
validated output projection when available, and optional secondary Gate-A
evidence. Credentials, raw SDK objects, hidden reasoning, filesystem paths,
and unrelated environment data are not retained.

The runner also produces deterministic JSON Schema projections and adjacent
structural diff summaries for `S0 → S1 → S2 → S3 → S4 → S5`. These are review
artifacts only; no custom JSON-Schema interpreter is used.

## Deterministic validation

Focused tests cover:

- historical and strengthened controls;
- unchanged golden semantics for both sections;
- deterministic schema hashes and adjacent diff projections;
- S1 permissiveness for normal/raster and array/curve shapes;
- S2 normal/reference curve-only restrictions;
- S3 array raster-only restriction with optional `x_scale`;
- S4 required array `x_scale`;
- historical role-domain preservation;
- identical provider payloads across all variants;
- one-call terminal provider failures;
- S0 control-failure stop behavior.

## Live results

Live results are not yet recorded. The initial control run was interrupted
before any attempt record was produced and is inconclusive; it is not a
control failure. After the corrected S0 control run succeeds, record the per
variant/section funnel here and in a compact JSON aggregate:

```text
attempts
provider-call successes
structurally valid outputs
structured-output failures
provider failures
secondary Gate-A successes
available token/latency metrics
```

The interpretation must identify the first observed compatibility collapse,
if any, without claiming a specific llama.cpp, Qwen, Pydantic, or discriminator
bug beyond the measured transition. If S0 fails, stop and preserve that as a
control failure.

## Hard stop

No files under `src/wellplot` changed. TW-05 does not modify historical or
strengthened production/experimental contracts, provider adapters, prompts,
Gate A, repair behavior, retries, planner/enricher logic, compiler behavior,
LangGraph, rendering, or production integration.

Stop after compatibility characterization. Do not implement remediation in
TW-05; any workaround or follow-up schema/provider design requires a separate
authorization.
