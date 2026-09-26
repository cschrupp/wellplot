# ADR-CM57: Planner Capability Contract

- **Status:** PROPOSED
- **Date:** 2026-09-25
- **Baseline:** `5356bcfcb61607831aaf25837dbd830e978d7ff4`
- **Scope:** semantic planner contract design only

## Context

The CM-57C unseen shadow population completed with
`GENERALIZATION_PIPELINE_FAILURE`. Twenty-one of 32 rows stopped before typed
execution because planner-produced section capability selections were
incomplete, duplicated, or rejected by another strict planner gate. The
existing capability registry already owns structural relationships through
`CapabilitySpec.allowed_parents`, but the Code Mode planner-safe projection
does not currently expose those relationships and the validator does not check
selected-capability uniqueness or parent closure.

The typed-worker reverse and sample-axis findings are separate semantic-worker
issues and are intentionally outside this decision.

## Decision

Expose the existing `CapabilitySpec.allowed_parents` values through the
planner-safe capability catalog. Define `SectionTask.capability_ids` as an
ordered unique set of canonical capability **types**, not requested object
instances. Add one generic planner instruction requiring complete structural
capability selection and unique IDs. Add deterministic validation for duplicate
IDs and missing selected-capability parent closure.

Use the existing bounded semantic correction for those validation diagnostics.
Do not inject missing capabilities, deduplicate planner output, infer child
capabilities, or choose among multiple allowed parents in host code.

The proposed dependency direction is:

```text
CapabilitySpec.allowed_parents
    -> planner-safe catalog
    -> SemanticPlanner
    -> deterministic validation
    -> existing bounded correction
```

## Structural Rules

- A selected capability with registered allowed parents requires at least one
  selected allowed parent in the same task.
- A capability with multiple valid parents requires the planner to select the
  semantic parent; the host must not choose one arbitrarily.
- Capability IDs are canonical and unique within a task.
- Capability order remains deterministic but does not determine semantic
  validity.
- A basic section task containing only its section capability remains legal.
- Mixed report and section work remains legal.
- `unresolved_requirements` retains its current meaning and is not globally
  rejected.

## Alternatives Rejected

- Prompt-only dependency prose, because it duplicates registry authority.
- Registry metadata without generic prompt clarification, because it does not
  define type uniqueness or complete closure clearly enough.
- Host-side closure repair, because it hides planner omissions and cannot
  resolve multiple valid parents safely.
- Per-capability planner switches, because they do not support plugins without
  central orchestration changes.

## Consequences

Positive consequences:

- Structural planner knowledge remains registry-authoritative and extensible.
- Planner omissions and duplicates remain observable semantic failures.
- Existing correction budgeting and provider-neutral error boundaries remain
  unchanged.
- Worker semantic metadata is not exposed to the planner.

Tradeoffs:

- Planner output may fail rather than being made executable by host repair.
- Multiple-parent capability choices remain model-owned.
- A planner-only validation experiment is required before end-to-end rerun.

## Non-Goals And Follow-Up

This ADR does not authorize production implementation, provider calls, live
inference, typed-worker changes, reverse/sample-axis remediation, routing, or
CM-57D. If accepted, implementation belongs to CM-57P1 and planner-only live
validation belongs to CM-57P2.
