# CM-56 Development Memory

## Status

- Slice: CM-56 real planner/enricher to typed-section shadow validation
- Baseline: `6984b36` (CM-55R baseline-comparison evidence)
- Implementation checkpoint: `018c882`
- State: deterministic checkpoint complete; live evidence not started
- Production routing: unchanged; `ProgramSectionCompiler` remains active

## Question

CM-56 measures whether the existing production semantic boundary can provide
enough information for a typed section worker:

```text
natural-language request
    -> SemanticPlanner
    -> SemanticEnricher
    -> SectionTask + ResolvedSectionContext
    -> path-free typed input
    -> SectionSemanticDraft
    -> CM-55 validation/compiler
```

The typed worker is shadow-only. It does not register with the graph, facade,
session, MCP server, notebook adapter, routing selector, or public helpers.

## Implementation

- Added `typed_section_worker.py` under `wellplot.agent.code_mode`.
- Added the sequential `cm56_typed_section_shadow.py` harness.
- Reused the existing `SemanticPlanner`, `SemanticEnricher`,
  `SectionSemanticDraft`, CM-55 validation/compiler, provider protocol, and
  capability registry.
- Added a deterministic provider-input contract artifact with pinned schema,
  prompt, and case-corpus hashes.
- Added ten cases: CBL main/repeat continuity, scalar linear, reverse scale,
  repeated channel, source selection, VDL/sample axis, logarithmic scale,
  tangential scale, generic raster, and waveform.
- Added physical fixture files so source containment and loader behavior are
  exercised rather than replaced by directory discovery or an in-memory path
  shortcut.

## Boundary Invariants

- One typed structured generation call per section worker attempt.
- Reconstruction only; revision is rejected before provider dispatch.
- Unsupported capabilities fail as a representability gap before generation.
- No retry, repair, fallback, critic, orchestration, or routing behavior.
- Provider payloads contain task semantics, selected capability descriptors,
  opaque candidate IDs, and bounded channel metadata only.
- Canonical paths and source formats remain host-side; path-shaped text is
  redacted before serialization.
- Generated drafts are revalidated against the exact enriched context and are
  compiled only after structural and context validation.
- Canonical IDs and source paths may appear only in the host-side intent
  fragment, never in the provider payload.
- Input sufficiency is audited before typed output evaluation; missing required
  facts take precedence over semantic model failure.
- Existing `ProgramSectionCompiler` is not invoked by the shadow worker and
  production routing remains unchanged.

## Deterministic Evidence

Validation at the implementation checkpoint:

- `11 passed` focused CM-56 worker/shadow tests
- `78 passed` planner, enrichment, semantic compiler, and architecture tests
- Ruff check passed for all changed Python files
- Ruff format check passed for all changed Python files
- JSON validation passed for the case corpus and input-contract artifact
- `git diff --check` passed
- Zero changes under the pre-existing CM-55 files or public routing paths

The current full repository suite was not used as a CM-56 gate. Existing
unrelated worktree changes remain untouched and the prior CM-55R baseline
comparison remains the authoritative full-suite qualification.

## Live Controls

The pinned local live configuration is recorded in
`CM-56-input-contract.json`:

- OpenAI-compatible JSON Schema backend
- Qwen3.6-35B-A3B-MTP-GGUF through the controlled llama.cpp endpoint
- temperature `1.0`
- maximum output tokens `16384`
- timeout `900` seconds
- thinking disabled
- sequential attempts

No live rows are included in this checkpoint. After review of this commit,
the live stage must use the unchanged code, prompt, schema, corpus, and
controls. Any live summary belongs in a later evidence-only commit.

## Deferred Work

CM-56 does not implement provider generation outside the shadow harness,
repair, typed-worker routing, public cutover, revision support, capability
extensions, source discovery, persistence, rendering, MCP changes, or legacy
deletion. If the live matrix shows missing planner/enricher semantics, the
next slice is CM-56R rather than a prompt-only workaround.

## Decision

**PROCEED to the controlled CM-56 local live stage after the implementation
checkpoint is pushed. Do not begin CM-57.**
