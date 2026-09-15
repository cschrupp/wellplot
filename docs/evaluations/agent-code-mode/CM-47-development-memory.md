# CM-47 Development Memory

## Scope

CM-47 adds the internal Code Mode revision boundary for report-wide sparse
updates and host-resolved existing sections. The host selects the canonical
section target during enrichment; generated programs can request only the
opaque target handle and cannot provide or discover its identity.

- **Slice base SHA:** `7d16fd5`
- **Implementation commit:** `21cf21b` (`Add host-bound section revision worker`)
- **Production LOC delta:** `+132/-23` in the implementation commit
- **Runtime behavior delta:** internal v2 revision compilation is now available;
  public routing, persistence, rendering, apply, MCP, and legacy behavior are
  unchanged.

## Host-Owned Revision Authority

Section target resolution remains a deterministic enrichment responsibility:

```text
SectionTask.existing_section_hint
    -> exact title/subtitle or unique containment match
    -> canonical host section_id
    -> opaque worker target
```

Every section hint is resolved once per enrichment call. If two section tasks
resolve to the same canonical section, enrichment fails with the stable
`section_target_duplicate` category before source loading or worker/provider
execution. Existing unresolved and ambiguous hint errors remain unchanged.

`IntentBuilder.register_section_target()` binds one host-selected identity to
one worker attempt. The executable program surface adds only:

```python
section = wp.target_section(report)
wp.update_section(section, title="Updated title")
```

`wp.target_section()` accepts no section ID. The canonical ID is adopted by
the host-owned builder and appears only in the resulting intent fragment. The
section worker does not publish selectors or update operations for existing
tracks, curve/raster bindings, fills, or annotations.

## Sparse Section and Report Semantics

New-section compilation retains the CM-42/CM-43R path and allocator behavior.
For an existing target, the section validator requires exactly one section
fragment whose identity equals the host-selected target and whose supplied
fields contain a mutation beyond `section_id`. Identity-only target adoption,
new sibling sections, and provider-supplied target IDs are rejected.

The existing section update path remains sparse. Omitted title, subtitle,
depth, data-source, and child fields are not copied into generated intent.
Private `ProgramRuntime` reconciliation therefore changes the requested target
fields while retaining omitted section fields, existing child tracks, and
sibling sections. The caller's document remains unchanged.

Report revision continues to use the CM-44 report root and sparse report
primitives; no report target selector or report ID was added. This preserves
the appropriate parity boundaries: report-only revision compares the report
worker path, while existing-section and mixed revision compare the v2 facade
against the unchanged legacy revision behavior where a comparable legacy shape
exists. No dummy legacy section is introduced for report-only work.

## Validation

- Code Mode and architecture tests: `68 passed`.
- Authoring-program builder/interpreter/runtime regression selection: `42 passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.
- Implementation commit was pushed to `origin/eval/mcp-stabilization`.

Focused coverage includes exact opaque-target revision, canonical-ID absence
from initial and repair prompts, rejection of selector arguments, identity-only
revisions, sibling creation, duplicate resolved targets, sparse private
application, omitted-field preservation, sibling preservation, and unchanged
new-section behavior.

## Boundaries And Deferrals

CM-47 does not add existing-child-object selection or update semantics, delete,
rename, move, public routing, engine switching, MCP, persistence, rendering,
production apply, legacy graph changes, or legacy deletion. The graph remains
an internal async host facade and no public v2 route is introduced.

**PROCEED / STOP:** CM-47 is implemented and evidenced in separate commits.
Stop before CM-48 implementation until bounded visual correction is separately
authorized.
