# EXP-TW-03 Development Memory

## Baseline and decision

- Baseline: `ad7a0ad` (EXP-TW-02I).
- Purpose: measure first-attempt provider generation of corrected `SectionDraft`
  values from the typed, path-free worker input.
- Scope: experimental files only; no production-package delta.
- Decision: one structured generation call per independent attempt, followed by
  unchanged structural validation and corrected Gate A scoring.

## Boundary

```text
TypedWorkerInputBundle
        |
        v
one StructuredGenerationRequest
        |
        v
generate_structured(..., response_model=SectionDraft)
        |
        v
SectionDraft or typed provider failure
        |
        v
corrected Gate A
        |
        v
immutable redacted first-attempt evidence
```

The user payload is exactly the deterministic TW-02I bundle serialization. The
system instruction only requests one `SectionDraft`; it does not add semantic
values. The corrected TW-02R `SectionDraft` is reused as the response model.

## Outcome contract

Each attempt has exactly one outcome:

- `provider_failure`: configuration, authentication, timeout, rate limit,
  transport, or provider rejection.
- `structured_output_failure`: invalid-response or validation failures, or a
  backend result that is not a validated `SectionDraft`.
- `gate_a_failure`: a structurally valid draft that fails corrected Gate A.
- `success`: a structurally valid draft that passes corrected Gate A.

There is no retry, repair, provider fallback, output normalization, field
completion, reordering, critic, planner, graph, or orchestration behavior.
Unexpected programming exceptions are not converted into experiment outcomes.

## Evidence

`FirstAttemptEvidence` records the experiment version/baseline, section role,
attempt index, provider/model identifiers, SHA-256 hashes of the exact provider
input and response schema, request settings, outcome, safe provider metadata,
provider metrics, the typed `SectionDraft` when available, corrected Gate A
booleans, and a deterministic path-free review projection.

Evidence does not retain provider request bodies, raw provider text, SDK
objects, credentials, authorization headers, filesystem paths, provenance
records, canonical intents, or hidden reasoning. `ExperimentSummary` provides
per-section counts for repeated independent attempts and sums available token
and latency metrics. A provider call counts as successful when it does not end
in `provider_failure`, so completed calls with malformed structured output stay
distinct from both provider failure and structurally valid output.

## Validation

Focused tests use fake asynchronous backends and prove:

- exactly one call for success, provider failure, structured failure, and Gate-A
  failure;
- `SectionDraft` is the response model;
- the user payload equals TW-02I serialization;
- Gate A sees the exact provider-returned draft object;
- prior attempt outputs and failure feedback do not enter later attempts;
- evidence serialization is deterministic, path-free, and credential-free;
- provider failure categories remain distinguishable.
- completed structured-output failures remain separate from provider-call
  failures;
- unexpected backend exceptions propagate instead of becoming evidence rows.

No live credentials or provider calls are required by the unit suite. The
ten-attempt section runner is available for a separately configured live run.

## Hard stop

Production delta remains zero. TW-04 is not started: retries, repair, critics,
reflection, orchestration, provider fallback, and production integration remain
outside this slice.

PROCEED: review and commit EXP-TW-03 only, then stop.
