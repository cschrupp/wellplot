# CM-55 Development Memory

## Slice

- Baseline: `25df6d7`
- Implementation: `a818676`
- Slice: CM-55 deterministic typed section models and compiler
- Initial evidence: `25df6d7`
- CM-55R correction commit: `c2173f7`
- Final frozen/evidence baseline: `34c6491`
- Status: complete; production routing remains unchanged
- Next boundary: CM-56 real planner/enricher shadow or A/B validation

CM-55 promotes the CM-54 contract into production code without adding
provider generation, prompts, repair, graph nodes, routing, or persistence.
The implementation stops at static semantic validation and sparse canonical
intent construction.

## Implemented Boundary

The production flow is:

```text
SectionSemanticDraft
    -> static structural validation
    -> ResolvedSectionContext validation
    -> host IdAllocator reservations
    -> sparse AuthoringDocumentIntent
```

The models are strict, immutable, whitespace-stripping Pydantic models with
`extra="forbid"`. Track discriminator fields are required and have no schema
defaults:

```text
normal     -> curve bindings only
reference  -> curve bindings only
array      -> raster bindings only and requires x_scale
```

Binding kind fields retain defaults because they are not used to select a
track union branch; this is an explicit CM-55 design choice and is not claimed
as a TW-08 discriminator result.

The production contract uses generic worker-local `semantic_id` values. The
experimental CBL role vocabulary is not part of the production model. Source
selection remains an opaque candidate ID, and canonical paths enter only the
host-side `AuthoringDataSource` intent after source validation.

## Compiler Invariants

- Existing-section revision is rejected explicitly; CM-55 implements the
  validated new-section reconstruction boundary only.
- Selected sources and exact source-scoped channels are required.
- Curve channels must be scalar and raster channels must be array-valued.
- Track and per-track binding semantic IDs must be unique.
- Track, binding, and channel order are preserved.
- Repeated same-channel bindings remain separate canonical binding instances.
- Canonical section, track, and binding IDs are allocated by the host
  `IdAllocator`; semantic IDs are only allocation hints/correlation handles.
- Omitted semantic scales and presentation fields remain omitted from sparse
  intent so downstream defaults are not converted into explicit user intent.
- No styles, widths, grids, labels, fills, annotations, or renderer policy are
  invented by the compiler.

The compiler does not reconcile, execute, render, persist, call providers, or
repair invalid output.

## CM-55R Correction

CM-55R closed the deterministic contract gaps found after the initial CM-55
evidence commit. The compiler now requires a trimmed host-owned
`section_id_hint`, accepts an optional host `IdAllocator`, and never derives
canonical section identity from the semantic title. Source candidate and
channel selection are exact and reject duplicate identities with stable
`source_candidate_ambiguous` and `channel_ambiguous` errors. Empty sample-axis
objects are rejected while valid partial axis pairs remain supported.

Identity-allocation substrate failures are wrapped as the dedicated
`SectionSemanticCompilationError` with stable `identity_allocation_failed`
classification; raw allocator details do not cross the semantic boundary.
The downstream proof now passes sparse intent through ordinary canonical
defaults, reconciliation, service execution, and completion without moving
presentation policy into the compiler.

The native schema summary is committed at
`CM-55-schema-summary.json`:

```text
response model: wellplot.agent.code_mode.section_semantics.SectionSemanticDraft
schema SHA-256: 93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4
canonical schema characters: 5388
track discriminator: kind (required, no defaults)
binding defaults: curve / raster tags only
request-specific literals: false
```

## Evidence

The focused CM-55 suite covers:

- required track discriminator schema behavior;
- strict extra-field and branch-shape rejection;
- array scale requirements and identity validation;
- unchanged TW-02R golden semantic replay for `main_pass` and `repeat_pass`;
- deterministic output and host-owned identity allocation;
- ordering and repeated-channel preservation;
- linear, log, and tangential scales;
- generic, VDL, and waveform raster profiles;
- sample-axis propagation;
- source, channel, scalar/array, duplicate-identity, and revision validation;
- path-free worker models and sparse omission behavior.

Validation:

```text
30 focused CM-55R compiler tests passed
91 focused architecture/Code Mode regression tests passed
Ruff check passed
Ruff format --check passed
git diff --check passed
```

The required full-suite run at the finalized CM-55R head completed as:

```text
34c6491: 1531 passed, 10 failed, 2 skipped, 11 subtests passed
```

The pre-CM-55R A/B run used the `25df6d7` source archive with the same local
data and untracked graph-report test artifacts needed to execute the same test
set:

```text
25df6d7: 1517 passed, 10 failed, 2 skipped, 11 subtests passed
```

The clean archive without those local artifacts produced `1489 passed, 14
failed`; the additional failures were missing-file/fixture errors caused by
the clean extraction, so that result was not used for node-by-node comparison.

The ten failing node IDs were identical at both compared heads, with
equivalent failure semantics:

```text
tests/test_agent.py::AgentTests::test_server_command_prefers_sibling_entry_point
tests/test_agent.py::AgentTests::test_server_env_propagates_current_pythonpath
tests/test_agent_tool_contract.py::test_profile_budget_is_bounded_and_smaller_than_diagnostic_contract
tests/test_graph_report_worker.py::test_live_report_failure_is_corrected_without_mutating_the_scaffold
tests/test_graph_report_worker.py::test_canonical_report_error_is_returned_for_bounded_correction[reconstruct]
tests/test_graph_report_worker.py::test_canonical_report_error_is_returned_for_bounded_correction[revise]
tests/test_graph_report_worker.py::test_rejected_report_never_becomes_an_accepted_artifact
tests/test_graph_report_worker.py::test_explicit_report_layout_changes_and_revision_clears_remain_supported
tests/test_graph_section_submission.py::test_section_instructions_require_native_submission[reconstruct]
tests/test_graph_section_submission.py::test_section_instructions_require_native_submission[revise]
```

The repository-wide suite is not globally green at either baseline. CM-55R
introduces no additional full-suite failures relative to the pre-CM-55R
baseline; no CM-55R test failed.

## Deferred Work

CM-55 does not claim typed support for annotations, fills, curve overlays on
array tracks, complete style/grid/label semantics, all subtitle/depth-window
requests, or existing-section revision. These remain visible in the CM-54
representability matrix. CM-56 must measure real planner/enricher input
sufficiency before any expansion or section-worker cutover.

No provider calls, prompts, retries, repair, planner changes, enrichment
changes, graph changes, routing changes, MCP changes, notebook changes, or
legacy deletions occurred.

Production routing still uses the existing program section worker. CM-57
remains the cutover gate, and CM-58 remains the unchanged public/default-route
acceptance gate.
