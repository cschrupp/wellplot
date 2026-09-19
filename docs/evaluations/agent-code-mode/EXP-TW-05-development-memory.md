# EXP-TW-05 Development Memory

## Baseline and question

- Baseline: `91c4151` (final EXP-TW-04 evidence correction).
- Question: which structural schema feature first breaks the local
  llama.cpp/Qwen structured-output path between historical `SectionDraft` and
  strengthened `SectionDraftS`?
- Status: live characterization complete through the first observed schema
  transition; remediation not started.
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
downstream variants, and can resume at `S1` while appending to the existing
redacted evidence file after a successful control.

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

The first two local Python runs were inconclusive because the sandbox blocked
the Python client before it could connect to llama.cpp. The approved network
run used the verified local configuration and the exact historical TW-03
prompt. Its S0 control reproduced structured validity across both sections:

| Variant | Feature | Main structured | Repeat structured | Total structured | Gate-A successes |
| --- | --- | ---: | ---: | ---: | ---: |
| S0 | historical control | 10/10 | 10/10 | 20/20 | 8/20 |
| S1 | track discriminator | 0/10 | 0/10 | 0/20 | 0/20 |

S0 recorded 34,157 total tokens and 1,125,062.28 ms across metric-bearing
calls. S1 made 20 provider calls, all of which ended at
`structured_output_failure / invalid_response`; no provider transport failures
were observed and no structured-output metrics were retained for those
failures.

The first observed compatibility collapse is therefore `S0 → S1`, the
introduction of the discriminated track union on `kind`. This localizes the
collapse at the first measured transition, but does not establish a specific
llama.cpp, Qwen, Pydantic, or discriminator implementation bug. S2 through S5
were not included in the completed compatibility matrix after the transition
was localized; their schema definitions, hashes, and adjacent diff
projections remain available for review, but they have no completed live
result rows.

The retained raw workspace evidence also contains an incomplete S2
`main_pass` sequence: attempts 1 through 6 all ended in
`structured_output_failure / invalid_response`, after which the run was
aborted before an S2 section aggregate was written. These six observations
are preserved for auditability but are excluded from the TW-05 matrix and do
not change the `S0 → S1` inference. S2 was not completed, and S3 through S5
were not attempted.

The compact live aggregate is committed as
`EXP-TW-05-live-summary.json`, and the deterministic schema review artifact is
committed as `EXP-TW-05-schema-artifact.json`. The raw redacted JSONL remains
under `/tmp` and is not committed.

The live aggregate records the per-variant/section funnel:

```text
attempts
provider-call successes
structurally valid outputs
structured-output failures
provider failures
secondary Gate-A successes
available token/latency metrics
```

The interpretation does not claim a provider implementation defect beyond the
measured transition. S0 did not fail, so the control was valid and the ladder
was stopped only after S1 localized the first observed collapse.

## Hard stop

No files under `src/wellplot` changed. TW-05 does not modify historical or
strengthened production/experimental contracts, provider adapters, prompts,
Gate A, repair behavior, retries, planner/enricher logic, compiler behavior,
LangGraph, rendering, or production integration.

Stop after compatibility characterization. Do not implement remediation in
TW-05; any workaround or follow-up schema/provider design requires a separate
authorization.
