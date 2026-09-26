# CM-57C-R3 Planner Contract Remediation Design

## Status And Authority

- Project: WellPlot
- Branch: `eval/mcp-stabilization`
- Frozen evidence checkpoint: `5356bcfcb61607831aaf25837dbd830e978d7ff4`
- Accepted CM-57C result: `GENERALIZATION_PIPELINE_FAILURE`
- Scope: production planner design only
- Provider calls: `0`
- Production changes: `0`
- Implementation: not started
- CM-57D: blocked

This document defines the smallest production planner change justified by the
CM-57C evidence. It is a design artifact, not an implementation authorization.
The accepted typed-worker findings remain separate and are not remediated here.

## Evidence Basis

The CM-57C population was complete at 32 rows. Twenty-one rows failed before
typed-worker execution because the planner/enrichment contract did not produce
the expected section capability decomposition:

```text
capability-closure omissions       6 / 32
duplicate capability type          2 / 32
exact unique expected sets rejected
by another strict planner gate    13 / 32
wrong capability substitutions     0 / 32
```

The 13-row category is intentionally not split further. The frozen evidence
does not distinguish an unexpected `report_task` from a non-empty
`unresolved_requirements` condition, so this design does not invent that
diagnosis.

The independently observed typed-worker gaps are deferred:

```text
reverse semantics                  repeated 2 / 2
explicit sample-axis min/max       repeated 2 / 2
unrequested semantic defaults      observed 1 / 2
```

Those findings must not be used to broaden planner remediation.

## Existing Authority And Gap

`CapabilitySpec.allowed_parents` is already the authoritative production
relationship field. Built-in declarations use it for structural relationships
such as:

```text
binding.curve  -> track.normal | track.reference
binding.raster -> track.array
track.normal   -> section.log_plot
track.reference -> section.log_plot
track.array    -> section.log_plot
```

The current `CapabilitySpec.planning_descriptor()` includes
`allowed_parents`, but the Code Mode `_planning_catalog()` projection removes
that field before the planner sees the catalog. The implementation slice must
therefore expose the existing field through the planner-safe projection; it
must not add a second dependency table or change individual capability
declarations unless a declaration is demonstrably incorrect.

The planner currently validates canonical IDs, categories, and the presence of
a section capability, but it does not reject duplicate capability IDs or check
selected-capability parent closure. The planner prompt also does not explicitly
define capability IDs as unique capability types or require complete structural
closure.

## Frozen Planner Contract

`SectionTask.capability_ids` is an ordered, deterministic sequence containing a
unique set of canonical capability **types** required for one work unit. It is
not an object-instance list.

Therefore multiple requested curve bindings still select one
`binding.curve` capability ID. Binding multiplicity, repeated channels, and
other object-level semantics remain in `requirements`, the authoritative
request, and the downstream typed worker output.

For a selected capability with registered `allowed_parents`, at least one
allowed parent must be selected in the same task. Closure is structural
validation, not semantic intent inference:

```text
section.log_plot + track.normal + binding.curve  -> valid
section.log_plot + binding.raster                -> invalid
section.log_plot + binding.curve                 -> invalid
section.log_plot + track.array + binding.raster  -> valid
```

The last invalid example remains invalid because `binding.curve` has more than
one possible parent and the planner has not selected the semantic parent.
The host must not choose `track.normal` or `track.reference` arbitrarily.

The validator must continue to accept a basic section task containing only
`section.log_plot`. A parent graph constrains selected capabilities; it does
not infer unselected children from a parent or infer semantic leaf intent from
the request.

## Selected Architecture

The preferred production design is:

```text
CapabilitySpec.allowed_parents
        |
        v
planner-safe capability catalog
        +
generic capability-selection instruction
        |
        v
SemanticPlanner
        |
        v
deterministic semantic-plan validation
        |
        v
existing one-call semantic correction
```

The planner-safe catalog should add only the existing structural
`allowed_parents` values to the projection. It must continue to omit worker
semantic metadata, argument schemas, runtime handlers, compiler metadata,
filesystem paths, canonical object IDs, and provider-specific details.

The generic planner instruction should communicate four rules:

1. Select the complete set of capability types needed for each work unit.
2. Emit each canonical capability ID at most once.
3. When a selected capability declares allowed parents, select an appropriate
   parent capability and continue through the registered structural closure.
4. Do not add capabilities for semantics that were not requested.

The wording must remain generic. It must not name CBL, VDL, benchmark cases,
current expected requests, or hardcoded track/binding choices.

## Deterministic Validation

The implementation slice should add generic validation to the existing
`validate_semantic_plan()` path:

```text
duplicate_capability
missing_capability_parent
```

`duplicate_capability` is emitted before any host normalization. The host must
not silently deduplicate the list because the duplicate is planner evidence and
must enter the existing correction path.

`missing_capability_parent` includes the selected capability ID and its
registered allowed-parent IDs in bounded diagnostic data. Those IDs are
registry structure, not a semantic answer. The model must still choose among
multiple valid parents from the request.

Parent validation should operate over the registry graph rather than special
cases such as `if capability_id == "binding.raster"`. Traversal must be bounded
and cycle-safe. Production registration cycle rejection may be handled by a
separate registry slice; CM-57C-R3 only requires that validation cannot recurse
indefinitely.

Capability order remains deterministic for serialization and provider input,
but semantic validity must not depend on section-before-track ordering. Existing
canonical ID, category, section-capability, unknown-capability, and alias rules
remain unchanged.

The validator must not enforce that `report_task` and `section_tasks` are
mutually exclusive. Mixed report-plus-section work is legitimate. It must also
not require `unresolved_requirements` to be empty: that field continues to mean
requirements unavailable to the current capability set, not planner uncertainty.

## Correction Interaction

The existing bounded planner correction remains the only correction:

```text
initial structured planner call
        |
        +-- valid plan -> return
        |
        +-- semantic error -> one correction call
                              |
                              +-- valid -> return
                              +-- invalid -> typed PlannerSemanticFailure
```

The correction receives the original path-redacted request, the previous plan,
the bounded diagnostic, and the same planner-safe catalog. No host-generated
capability is inserted before correction. No additional retry, post-correction
repair, fallback, or deterministic semantic completion is introduced.

The correction diagnostic may say that a selected capability requires one of
its registered parent types and list those parent IDs. It must not tell the
planner which parent to choose when multiple parents are valid.

## Alternatives Considered

### Prompt Only

Rejected as the sole architecture. It is small but duplicates registry facts in
prose and requires prompt edits when plugin capabilities change.

### `allowed_parents` Without Prompt Clarification

Insufficient alone. The model still needs the generic distinction between
capability types and requested instances, and it must be told to produce a
complete unique set.

### Prompt Plus Registry Metadata

Selected. It is the minimum registry-driven design that addresses both observed
failure classes and remains extensible to future capabilities.

### Deterministic Host Closure

Rejected. Adding missing parents or deduplicating IDs would hide planner
failures, could choose the wrong parent when several are valid, and would blur
planner responsibility with semantic intent inference.

## Explicit Non-Goals

CM-57C-R3 does not include:

- changes to typed worker models, semantic metadata, reverse handling, or
  sample-axis semantics;
- changes to `SectionTask` or `SemanticPlan` schemas;
- capability declaration rewrites or a second dependency table;
- deterministic capability injection, deduplication, or child inference;
- changes to `report_task` or `unresolved_requirements` meaning;
- provider calls, live inference, or a planner comparison harness;
- routing, LangGraph topology, enrichment, compilation, persistence, MCP,
  notebook, or public API changes;
- CM-57D or any route activation.

## Future Implementation Boundary

After independent design acceptance, the implementation should be a separate
`CM-57P1` slice limited to the existing planner-safe projection, generic prompt
clarification, duplicate validation, parent-closure validation, bounded
diagnostics, and deterministic tests. It should not modify the typed worker,
enricher, compiler, workflow, or built-in capability declarations unless an
unavoidable contract defect is found and separately authorized.

The next evaluation should be planner-only (`CM-57P2`), using the frozen CM-57C
request corpus and the same provider controls. It should measure plan validity,
capability completeness/uniqueness, parent closure, report-task presence, and
unresolved requirements without invoking typed workers. A full end-to-end
CM-57C rerun should wait for that planner result and for separate decisions on
the deferred typed-worker gaps.

The planner target for the frozen 32-row evidence population is complete
planner validity, not an arbitrary percentage threshold.

## Plugin Extensibility And Dependency Direction

The dependency direction remains:

```text
CapabilitySpec
    -> planner-safe projection
    -> SemanticPlanner
    -> validated SemanticPlan
```

A plugin capability declaring `allowed_parents` automatically participates in
the same generic planner contract. The planner must not import built-in IDs or
contain per-capability switches. Worker semantic metadata remains outside the
planner catalog because it belongs to the downstream language-to-semantic-IR
boundary.

## Deferred Typed Findings

The CM-57C typed executions leave three separate future questions:

- reverse-direction semantic interpretation;
- explicit sample-axis minimum/maximum mapping;
- unstable unrequested raster defaults.

These are not planner-contract fixes and must remain separate from CM-57P1 and
CM-57P2. CM-57D remains blocked until the planner and typed-worker boundaries
are independently validated.

## Design Decision

```text
PROPOSED

Expose existing capability structural parent relationships through the
planner-safe catalog, define capability_ids as a complete unique set of
capability types, and validate uniqueness/selected-parent closure without
deterministically repairing semantic omissions.
```

Independent design review is required before implementation.
