# CM-48 Development Memory

## Scope

CM-48 adds the first bounded visual-correction boundary for Code Mode v2. It
is deliberately narrower than the full section worker: visual review can
request only one root-level correction on one host-selected existing section.
Existing track, binding, fill, annotation, source, report, and cross-section
selectors remain outside this slice.

- **Evidence base SHA:** `9997c02`
- **Implementation commits:** `e6f725c` and `a0c0a25`
- **Production LOC delta:** `633`
- **Test LOC delta:** `403`
- **Runtime behavior delta:** one new private v2 visual-correction boundary;
  no public routing, persistence, MCP, or renderer-backend behavior changed.

## Bounded Flow

The coordinator in
`src/wellplot/agent/code_mode/visual_correction.py` performs:

```text
original intent verification
    -> host section render
    -> one structured visual review
    -> one validated section correction
    -> existing ProgramSectionCompiler
    -> neutral private canonical apply
    -> original/correction intent verification
    -> preservation checks
    -> one final private render
```

The visual evaluator receives only the user request, an in-memory render
artifact, the `selected_section` scope marker, and the allowlisted semantic
capability. It receives no document, intent, section ID, track/binding ID,
source path, output path, provider object, or graph state.

The correction is transformed deterministically into one existing-section
`SectionTask`; the semantic planner is not invoked. The host supplies the
opaque section target through `ResolvedSectionContext`, and the existing
worker retains its restricted interpreter, private dry run, and CM-34 repair
boundary.

The returned worker intent is accepted only when it contains exactly one
host-selected section and only `title`, `subtitle`, or `depth_range` changes.
Private application uses `AuthoringService`, `reconcile_authoring`, and
`execute_authoring_plan` on a deep copy. The caller document and original
intent remain unchanged.

## Terminal And Boundedness Contracts

Stable terminal reasons include semantic verification, initial render, review,
correction rejection, worker, private-apply, preservation, postcondition, and
final-render failures. `no_correction` and `corrected` are the only successful
terminal states.

```text
render_count       0..2
review_count       0..1
correction_count   0..1
repair_count       0..2 (CM-34 format-only repair remains the provider bound)
```

There is no second visual review, no recursive correction loop, and no partial
corrected document on failure. After correction, the original intent and the
correction intent must both remain satisfied. Report-wide fields, non-target
sections, target identity, target tracks, target data source, and extensions
must remain identical.

## Validation

- CM-48 visual-correction and architecture tests: `16 passed`.
- Full Code Mode and architecture regression selection: `79 passed`.
- Ruff check: passed.
- Ruff format check: passed.
- `git diff --check`: passed.
- Implementation commits were pushed to `origin/eval/mcp-stabilization`.

## Boundaries And Deferrals

CM-48 does not import or modify `wellplot.agent.graph.finalization`,
`wellplot.agent.graph.verifier`, or `wellplot.agent.graph.models`. It adds no
vision-provider adapter, semantic planner call, public Python/notebook route,
MCP tool, persistence, rendering backend, graph cutover, child-object target
selection, or legacy deletion. The existing legacy finalization layer remains
outside the v2 boundary.

**PROCEED / STOP:** CM-48 is implemented and evidenced. Stop before CM-50
public cutover planning/implementation until separately authorized.
