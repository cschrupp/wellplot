# CM-56 Development Memory

## Status

- Slice: CM-56 real planner/enricher to typed-section shadow validation
- Baseline: `6984b36` (CM-55R baseline-comparison evidence)
- Implementation checkpoint: `018c882`
- State: deterministic checkpoint and local live matrix complete
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

The full repository suite completed with `1542 passed, 10 failed, 2 skipped,
11 subtests passed`. The ten failures are confined to the previously unrelated
agent/tool-contract and graph report/section tests; no CM-56 change touched
those files. Existing unrelated worktree changes remain untouched. The exact
failure nodes and qualification are recorded in `CM-56-live-summary.json`.

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

The implementation checkpoint contained no live rows. The completed live
matrix is recorded separately in `CM-56-live-qwen.jsonl`; its code, prompt,
schema, corpus, and controls were unchanged from the checkpoint.

## Local Live Result

The unchanged matrix was run against the verified local llama.cpp endpoint
advertising model `qwen3.6-35b-a3b`:

- 10 frozen cases
- 3 sequential attempts per case
- 30 case-level rows and 33 section outcomes
- evidence: `CM-56-live-qwen.jsonl`
- aggregate summary: `CM-56-live-summary.json`
- evidence SHA-256: `e383983a6fa84b629d994b9adea4019c70e326bec91f4e4fb8bb9a69c9161137`
- provider payload/path redaction scan: passed

Section-outcome classification counts were:

```text
INPUT_INSUFFICIENT                  21
PLANNER_FAILURE                      6
DETERMINISTIC_COMPILER_FAILURE      4
SCHEMA_COMPATIBILITY_FAILURE        1
TYPED_WORKER_SEMANTIC_FAILURE       1
```

The dominant and gate-determining result is `INPUT_INSUFFICIENT`: the real
planner output did not consistently preserve the source and scientific facts
declared by the held-out cases. This is an input-contract result, not a reason
to add prompt examples, worker repair, or source inference. The run also
contains four rows whose bounded error type is
`SectionSemanticValidationError` and one typed semantic failure; those are
retained as observed downstream evidence and do not override the earlier
input-sufficiency stop condition.

The four rows classified by the unchanged harness as
`DETERMINISTIC_COMPILER_FAILURE` have raw error type
`SectionSemanticValidationError`; they failed during typed context validation
before deterministic compilation. The program-worker comparator was not run
after the decisive input-contract stop, so no additional inference or provider
comparison is implied by CM-56.

CM-56 therefore stops at `STOP_INPUT_CONTRACT`. No CM-57 scope is authorized
by this evidence, and no production routing or provider code was changed.

## Deferred Work

CM-56 does not implement provider generation outside the shadow harness,
repair, typed-worker routing, public cutover, revision support, capability
extensions, source discovery, persistence, rendering, MCP changes, or legacy
deletion. The next separately authorized slice is CM-56R for planner-to-worker
source and explicit scientific-requirement preservation; it must rerun this
unchanged typed worker before any prompt or worker changes are considered.

## Decision

**STOP at CM-56 input-contract evidence. Plan CM-56R separately; do not begin
CM-57.**
