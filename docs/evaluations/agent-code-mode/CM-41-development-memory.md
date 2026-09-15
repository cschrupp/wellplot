# CM-41 Development Memory

## Scope

CM-41 adds deterministic, host-owned enrichment for the Code Mode v2 semantic
plan without changing provider calls, graph routing, or document mutation.

- **Slice base SHA:** `8fb81e5`
- **Implementation commit:** `58b9d01`
- **Implementation scope:** explicit source candidates under explicit allowed
  roots; injected bounded source loading; per-call canonical-path caching;
  lexical existing-section resolution; inspection-facade projections; and an
  immutable transient `EnrichedSemanticContext`.

## Contract

```text
SemanticPlan + AuthoringDocumentSpec + host source candidates
    -> SemanticEnricher
    -> EnrichedSemanticContext
```

Source selection is strictly host-bounded. Candidates are normalized, symlink
resolved, required to be readable regular files, and rejected when they are
missing, outside their declared root, unsupported, or in trusted-format
conflict. Unknown suffixes are accepted only with explicit trusted format
metadata. The loader is an injected protocol and receives only the canonical
path and normalized `las`/`dlis` format.

The enrichment boundary exposes only bounded dataset metadata and channel
facts. It does not retain arrays, parser objects, renderer state, or raw
loader exceptions. Equivalent canonical candidates are loaded at most once per
enrichment call; no process-global cache was added.

Existing section hints resolve deterministically against title and subtitle in
the canonical inspection facade: exact matches take precedence, followed by
unique phrase containment. Unresolved and ambiguous hints are typed failures;
new sections retain `section_id=None`, with no host identity allocation.

The original `SemanticPlan` is preserved in the frozen context. Header slots,
sections, and section-scoped channels are read through
`AuthoringInspectionFacade`. No provider/planner request, graph/workflow node,
MCP call, persistence operation, reconciliation, or document mutation occurs.

## Validation

- CM-41-focused enrichment/planner/inspection tests: `27 passed`.
- Adjacent Code Mode/provider/capability/source-context regression selection:
  `76 passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.

## Boundaries and Risks

- No live provider request was made; source loading was tested with an injected
  fake loader.
- CM-41 does not implement LAS/DLIS parsing, source discovery, program
  workers, semantic capability execution, LangGraph routing, MCP integration,
  persistence, or legacy deletion.
- Source candidates and allowed roots remain explicit host inputs. A later
  worker slice owns how the bounded context is consumed; it must not expand
  this boundary into filesystem discovery.

## Decision

**PROCEED / STOP:** CM-41 is implemented and evidenced in separate commits.
Stop before CM-42 program-worker integration until separately authorized.
