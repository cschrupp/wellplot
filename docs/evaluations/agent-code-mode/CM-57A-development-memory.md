# CM-57A Development Memory

## Baseline

- Authorized baseline: `85cf2582dbb94c26bd55512dec0b5f1aaa5a4b46`
- Branch: `eval/mcp-stabilization`
- Slice: CM-57A

## Scope

CM-57A adds immutable, developer-authored semantic metadata to capability
declarations. `CapabilitySpec.semantic_metadata` is the sole production
authority. The metadata is validated when a capability is declared and remains
host-side data; it is not a planner or worker contract in this slice.

The initial owner is `binding.raster`, with seven mappings for raster profiles
and explicit sample-axis fields plus three distinctions separating track
horizontal-domain semantics from raster sample-axis semantics. The declaration
contains no benchmark values or scale mappings.

## Boundaries

- Provider calls: `0`
- Provider-facing changes: none
- Planner changes: none
- Typed-worker input and serialization changes: none
- Typed-worker prompt changes: none
- Enricher changes: none
- Semantic compiler changes: none
- Identity changes: none
- Title behavior changes: none
- Routing changes: none
- Registry storage: existing `CapabilityRegistry` only
- Registry selector/projection API: none

Existing planning, worker, and Code Mode worker descriptors remain unchanged.
No provider serialization, metadata hash/versioning, target allowlist, or
semantic execution was added. CM-57B owns the future provider projection.

## Validation

The focused tests cover immutable tuple-only declarations, blank values,
generic dotted target paths, duplicate concepts/patterns/targets, count bounds,
backward-compatible declarations, exact `binding.raster` ownership, registry
canonical/alias lookup, descriptor non-leakage, and benchmark anti-leakage.

The active production route remains `ProgramSectionCompiler`; the typed
semantic route remains inactive. CM-57B and the input-boundary experiment
remain blocked.

## Hard Stop

This slice stops after deterministic implementation and validation. It does not
add provider input, prompt integration, routing, identity work, title fidelity,
CM-57B, CM-57C, CM-57D, or CM-58.
