# CM-42 Development Memory

## Scope

CM-42 adds a bounded new-section scalar reconstruction worker without routing
the v2 path into production or changing the v1 graph worker.

- **Slice base SHA:** `6163edb`
- **Implementation commit:** `392778c`
- **Implementation scope:** `ProgramSectionCompiler`, scoped worker prompts,
  fresh host-seeded identity allocators, restricted-program interpretation,
  section-only intent gating, private canonical dry runs, and one bounded repair
  sequence.

## Contract

```text
task_index + EnrichedSemanticContext + AuthoringDocumentSpec
    -> ProgramSectionCompiler
    -> one generate_program()
    -> AuthoringProgram
    -> interpret_authoring_program()
    -> one section-only AuthoringDocumentIntent
    -> private ProgramRuntime dry run
    -> ProgramExecutionResult
```

This slice proves only new scalar-section reconstruction. A resolved existing
section is rejected before provider generation because the restricted runtime
currently exposes create-oriented calls, not deterministic select/update
operations. The worker never repurposes an existing section ID as an `id_hint`.

Every candidate attempt creates a fresh `IdAllocator` seeded with current
section IDs, section-local track IDs, global binding IDs, and fill/annotation
IDs. Repaired candidates receive a fresh builder and allocator, so failed
attempt reservations cannot change the repaired identity sequence. The section
gate requires exactly one section fragment and rejects report-wide fields,
global child lists, and removals.

The worker sends only the indexed task, selected v2 capability descriptors,
bounded source/channel metadata, and executable SDK reference. Capability
examples are not copied into the prompt because their current declarative
forms are not necessarily executable runtime syntax. Initial provider failures
propagate without fabricating an `AuthoringProgram`; after source exists,
`ProgramRepairCoordinator` is invoked at most once, and the repaired candidate
is run through the full interpreter and private dry run exactly once.

## Validation

- CM-42-focused tests: `8 passed`.
- Adjacent Code Mode/provider/capability/source-context regression selection:
  `105 passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.

## Boundaries and Risks

- No live provider request was made; the pilot uses a deterministic fake backend.
- No report worker, revision worker, CBL A/B comparison, LangGraph routing, MCP
  integration, persistence, rendering, or legacy deletion is included.
- The worker currently proves one scalar normal track with scalar curve binding.
  Broader section capability coverage requires a later slice and must not be
  added through worker-specific routing branches.

## Decision

**PROCEED / STOP:** CM-42 is implemented and evidenced in separate commits.
Stop before CM-43, the CBL section A/B experiment, until separately authorized.
