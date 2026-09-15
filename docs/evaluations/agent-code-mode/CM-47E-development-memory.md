# CM-47E Development Memory

## Scope

CM-47E closes the evidence gap identified after the CM-47 implementation. It
adds deterministic graph-level revision fixtures only. The fixtures exercise
the v2 facade in `revise` mode and compare each supported shape at the correct
legacy boundary without changing production code, SDK semantics, graph
topology, or routing.

- **Evidence base SHA:** `cd52f46`
- **Evidence commit:** `22c8aad` (`Add CM-47 revision parity fixtures`)
- **Production LOC delta:** `0`
- **Runtime behavior delta:** `0`; test evidence only.

## Revision Parity Fixtures

The v2 facade now has deterministic fixtures for:

```text
report-only revision
    v2 report worker path ↔ unchanged legacy report-worker boundary

existing-section revision
    v2 revise facade ↔ unchanged legacy revise graph

mixed report + existing-section revision
    v2 revise facade ↔ unchanged legacy revise graph
```

The report-only case does not manufacture a dummy legacy section. The existing
and mixed cases use the legacy `compile_document_revision()` graph with the
same canonical report/section intent shape and compare exact serialized
`AuthoringDocumentIntent` output.

The mixed failure fixture proves that a successful report worker cannot publish
a partial merged intent when the existing-section worker fails. The successful
revision fixtures also assert that the input document remains unchanged and
that omitted section fields such as subtitle and tracks remain absent from the
emitted sparse intent.

## Validation

- CM-47 facade revision parity tests: `15 passed`.
- Code Mode and architecture tests: `72 passed`.
- Unchanged legacy revision tests: `5 passed`.
- Ruff check over the changed test file: passed.
- Ruff format check over the changed test file: passed.
- `git diff --check`: passed.
- Evidence commit was pushed to `origin/eval/mcp-stabilization`.

## Boundaries And Deferrals

CM-47E does not add existing-child-object selection or update semantics,
visual correction, public routing, engine switching, MCP, persistence,
rendering, production apply, legacy graph changes, or legacy deletion. It does
not weaken the unchanged acceptance or parity contracts.

**PROCEED / STOP:** CM-47 and CM-47E are now implemented and evidenced.
CM-47 is closed. Stop before CM-48 implementation until bounded visual
correction is separately authorized.
