# EXP-TW-04 Development Memory

## Baseline and question

- Baseline: `21bd657` (final EXP-TW-03S structural schema experiment).
- Question: when a provider returns a structurally valid `SectionDraftS` that
  is semantically wrong for the typed task, can one targeted repair call
  recover it using only worker-boundary information?
- Status: harness implemented and validated; live provider evaluation pending.

TW-04 is a semantic-repair experiment, not a general retry or resilience
experiment. Provider transport/authentication/rate-limit/timeout failures and
structured-output failures are terminal. Unexpected programming exceptions
remain exceptions.

## Bounded protocol

```text
TypedWorkerInputBundle
        |
        v
one structured generation call, response_model=SectionDraftS
        |
        +--> provider/structured failure: terminal
        |
        v
corrected Gate A
        |
        +--> success: terminal
        |
        v
deterministic semantic diff from typed task + previous SectionDraftS
        |
        v
exactly one repair generation call, response_model=SectionDraftS
        |
        v
final Gate-A result, terminal
```

Each logical attempt therefore has at most two provider calls. There is no
recursive repair, critic, reflection, automatic patching, fallback, provider
switch, planner change, graph/orchestration change, or production integration.

## Repair contract

`SemanticMismatch` records an output path, its corresponding typed-input path,
one of `missing`, `unexpected`, `value_mismatch`, or `order_mismatch`, and the
observed/expected semantic values. Expected values come only from
`TypedWorkerInputBundle.task`; they are not read from the golden fixture,
canonical intent, Gate-A constants, or downstream artifacts.

`RepairTask` contains only the original path-free typed input bundle, the
previous `SectionDraftS`, and the deterministic mismatch tuple. Both initial
and repair calls use `SectionDraftS`, so the TW-03S structural invariants are
enforced before either Gate-A evaluation.

The diagnostic function has no corpus, golden, Gate-A, provider, or renderer
dependency. Mutating the typed task changes the mismatch expectation directly,
which makes the task rather than the benchmark the repair authority.

## Evidence contract

`LogicalAttemptEvidence` preserves the first draft and metrics independently
from the optional repair attempt. `RepairExperimentSummary` separates:

- first provider-call success, structural validity, and Gate-A success;
- repair eligibility and call count;
- repair provider-call success, structural validity, and Gate-A success;
- repair conversion and final success;
- first, repair, and combined token/latency totals.

No raw provider responses, credentials, hidden reasoning, filesystem paths, or
canonical artifacts are retained by this experiment harness.

## Validation and live protocol

The focused harness tests cover first success, provider/structured terminal
failures, one semantic repair, failed repair with no third call, typed-input-only
diagnostics, changed typed-task expectations, path-free repair serialization,
unexpected exception propagation, and aggregate metrics.

The authorized live protocol is 10 `main_pass` plus 10 `repeat_pass` logical
attempts per provider, analyzed within each provider:

```text
first-attempt success -> final success after one repair
```

The local Qwen and OpenRouter/Nemotron runs are separate exploratory provider
evidence sets. They must not overwrite TW-03 evidence or be ranked as a formal
cross-provider benchmark.

## Hard stop

Production delta remains zero. No files under `src/wellplot` are changed.
TW-04 does not start planner changes, compiler changes, LangGraph, retries,
repair loops, or production integration.

After the harness and authorized live evidence are recorded, stop before any
future repair/orchestration slice.
