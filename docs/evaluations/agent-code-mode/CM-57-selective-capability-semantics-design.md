# CM-57 Selective Capability Semantics Design

## 1. Status And Authority

- Project: WellPlot
- Branch: `eval/mcp-stabilization`
- Design baseline: `3eec5173bb08ba7a6de9e417d71819247e2dc699`
- Correction baseline: `f6ae1f12e0cbda4cfcaa4ff8125201c72cf6623b`
- Scope: production design only
- Provider calls: `0`
- Production changes: `0`
- Implementation: not started

CM-56R8R-S1 demonstrated that a small capability-specific semantic contract can
recover WellPlot-specific raster semantics without disturbing generic scale
semantics. This document defines the smallest production architecture that can
carry that contract. It does not change the capability registry, typed worker,
schema, prompt, planner, enricher, compiler, allocator, routing, or evidence.

The hard stop for this slice is this document, one evidence-only commit, and
the independent design review that follows it.

## 2. Evidence Baseline

The accepted S1 result is recorded in
`docs/evaluations/agent-code-mode/CM-56R8R-S1-live-summary.json`:

```text
                         A       S
full semantic acceptance 3/15    12/15
track scale              36/36   36/36
binding scale            24/24   24/24
raster profile           0/9     9/9
sample axis              9/18    12/12
scale regressions        0
target recoveries        12
unrequested extras       0
decision                 SELECTIVE_CONTRACT_FULL_RECOVERY
```

The raw S1 evidence remains outside the repository at
`/tmp/cm56r8r-s1-live-qwen.jsonl` with SHA-256
`43345200d356677a9c88ac77997c14c5d16c6d973711e38d17a1dea6ea86ae1c`.
The three repetitions per case are reproducibility evidence, not fifteen
statistically independent semantic observations.

The validated causal finding is narrow:

- Generic track and binding scale mappings already work without extra guidance.
- Full semantic guidance recovered raster/sample-axis fields but caused the
  `MINMAX_NAME_CONFLICT_SIGNATURE` reverse-scale regression.
- Selective guidance for raster profile, sample-axis fields, and the
  `track.x_scale` versus `binding.sample_axis` distinction recovered the target
  fields with no scale regression.

The production design therefore must not document generic mappings for
`linear`, `log`, `tangential`, `minimum`, `maximum`, `reverse`, or numeric
track x-scale language unless later evidence requires it.

## 3. Problem Statement

The current production capability declarations already provide one authoritative
registry and worker-facing descriptors. The typed worker currently receives
selected task fields, capability descriptors, and bounded source/channel
context, then generates a `SectionSemanticDraft` before deterministic context
validation and compilation.

S1 shows that one capability needs a small amount of additional application
meaning that ordinary schema knowledge and natural language do not reliably
provide:

```text
binding.raster:
    raster profile
    sample-axis unit, origin, step, and tick count
    distinction between track x-scale and raster sample-axis coordinates
```

That meaning must be capability-local, deterministic, bounded, provider-safe,
and independent of canonical runtime identity or rendering policy. It must not
become a second capability registry, a parser, a repair engine, or a global
prompt of accumulated benchmark rules.

## 4. Goals

CM-57 design should enable a future implementation to:

1. Attach optional semantic metadata to the existing `CapabilitySpec`.
2. Select metadata deterministically from `SectionTask.capability_ids`.
3. Serialize only selected, provider-safe metadata into the typed worker input.
4. Express the validated raster profile and sample-axis semantics generically.
5. Keep generic scale mappings outside capability metadata.
6. Preserve `SectionSemanticDraft` as the machine-enforced response authority.
7. Preserve deterministic context validation and semantic compilation.
8. Allow future capabilities to attach their own semantics without central
   worker switches.
9. Keep the initial rollout shadow-only and independently measurable.

## 5. Non-Goals

CM-57 does not include:

- changes under `src/wellplot/**`;
- provider calls or live inference;
- response-schema changes;
- planner or enrichment changes;
- compiler semantic-policy changes;
- semantic-ID normalization or allocator changes;
- title-fidelity changes;
- program-worker fallback, repair, or routing changes;
- persistence, rendering, MCP, notebook, or public cutover;
- moving evaluation JSON into runtime dependencies;
- a semantic rule engine, ontology, parser, DSL, or specialist-worker system.

## 6. Current Production Architecture

The active LangGraph section route is still the program worker:

```text
CodeModeGraphDependencies
    section_compiler = ProgramSectionCompiler
        ↓
build_compile_graph()
        ↓
compile_worker node
        ↓
ProgramSectionCompiler.compile(...)
        ↓
AuthoringDocumentIntent
```

The exact active wiring is in
`src/wellplot/agent/code_mode/workflow.py`: `CodeModeGraphDependencies` types
`section_compiler` as `ProgramSectionCompiler`, `build_compile_graph()` invokes
`dependencies.section_compiler.compile()` for section sends, and the graph
construction is used by `CodeModeCompileFacade` in `facade.py`.

The typed semantic path is a separate shadow/component path, not the active
graph compiler:

```text
TypedSectionCompiler
        ↓
TypedSectionWorkerInput
        ↓
SectionSemanticDraft
        ↓
validate_section_semantics()
        ↓
compile_section_semantics()
        ↓
AuthoringDocumentIntent
```

CM-56 and S1 validated this typed component, but it is not currently injected
into `CodeModeGraphDependencies` and does not replace `ProgramSectionCompiler`.
The truthful migration sequence is therefore:

```text
Today:
    LangGraph → ProgramSectionCompiler

Validated experimental typed path:
    original request + typed context + selective metadata
        → TypedSectionCompiler

Future:
    freeze the production typed input contract
        → shadow-test that exact contract
        → separately decide graph activation
```

The authoritative locations are:

- `src/wellplot/capabilities/base.py`: `CapabilitySpec` and capability
  descriptor projection.
- `src/wellplot/capabilities/registry.py`: `CapabilityRegistry`, registration,
  alias resolution, and deterministic catalogs.
- `src/wellplot/capabilities/builtins.py`: `builtin_capabilities()` and the
  built-in capability declarations, including `binding.raster`.
- `src/wellplot/agent/code_mode/planner.py`: `SectionTask`, `SemanticPlanner`,
  planner capability validation, and the compact planning catalog.
- `src/wellplot/agent/code_mode/workflow.py`: active graph dependencies,
  `ProgramSectionCompiler` injection, dynamic worker dispatch, and graph merge.
- `src/wellplot/agent/code_mode/enrichment.py`: `SourceContext`,
  `ResolvedSectionContext`, deterministic source/channel resolution, and host
  source ownership.
- `src/wellplot/agent/code_mode/typed_section_worker.py`:
  `TypedSectionWorkerInput`, `build_typed_section_input()`,
  `serialize_typed_section_input()`, `TYPED_SECTION_SYSTEM_PROMPT`, and
  `TypedSectionCompiler.compile()`.
- `src/wellplot/agent/code_mode/section_semantics.py`:
  `SectionSemanticDraft`, the required discriminated track schema, and
  `validate_section_semantics()`.
- `src/wellplot/agent/code_mode/semantic_section_compiler.py`:
  `compile_section_semantics()` and the sparse canonical intent projection.
- `src/wellplot/authoring_program/ids.py`: `IdAllocator`, reservation, and
  deterministic canonical identity allocation.

The existing architecture already keeps provider mechanics and orchestration
outside the capability declarations. CM-57 should extend that seam rather than
introduce another one.

## 7. Current Capability Registry Model

`CapabilitySpec` in `src/wellplot/capabilities/base.py` is a frozen slotted
dataclass with the capability ID, category, descriptions, aliases, parent/source
constraints, planning hints, artifact model, compiler, optional v2 arguments
model/handler, worker hints, and examples.

`CapabilityRegistry` in `src/wellplot/capabilities/registry.py` owns startup
registration and alias uniqueness. Its catalogs are deterministic:

- `planning_catalog()` sorts by canonical capability ID.
- `worker_catalog()` resolves selected IDs and sorts canonical IDs.
- iteration sorts canonical IDs.

`builtin_capabilities()` in `src/wellplot/capabilities/builtins.py` is the
authoritative built-in declaration source. `binding.raster` already owns the
array/raster binding capability and already advertises `profile` and
`sample_axis` as optional binding-local concepts in its worker hints.

The current `metadata: dict[str, str]` field is too loose for provider-facing
semantic contracts and is mutable despite the frozen dataclass. It should not
be overloaded with the S1 contract. The future implementation should add one
typed immutable optional field to `CapabilitySpec` while retaining the existing
metadata field for its current compatibility role.

## 8. Current Typed-Worker Input Contract

`TypedSectionWorkerInput` in
`src/wellplot/agent/code_mode/typed_section_worker.py` contains:

- `section_task: TypedSectionTaskInput`;
- `capabilities: tuple[TypedSectionCapabilityInput, ...]`;
- `sources: tuple[TypedSectionSourceInput, ...]`.

`build_typed_section_input()` projects `SectionTask` and
`ResolvedSectionContext` into this path-redacted provider payload. It resolves
canonical capability identifiers through the registry, preserves source and
channel order from the host context, and exposes exact channel mnemonics plus
recognition aliases. `serialize_typed_section_input()` uses deterministic JSON
ordering and compact separators.

The accepted S1 experiment did not use this payload alone. Its A and S arms
used:

```text
current typed task/context input
    + authoritative original request
    + selective metadata for S
```

The current production `TypedSectionWorkerInput` has no
`authoritative_request` field. Therefore S1 proves the selective intervention
only in combination with an authoritative request, not on the current
production payload by itself. CM-57 must not claim otherwise.

The current payload deliberately excludes canonical source paths, document
internals, runtime IDs, renderer settings, provider responses, and evaluation
gold. The semantic metadata addition must preserve this boundary.

`SectionSemanticDraft` in
`src/wellplot/agent/code_mode/section_semantics.py` remains unchanged. Its
required `kind` discriminator, ordered tracks/bindings, local semantic IDs,
scale fields, raster profile, and sample-axis fields are the response contract.

## 9. Proposed Semantic-Metadata Model

Use one optional field on the existing `CapabilitySpec`, conceptually in
`src/wellplot/capabilities/base.py`:

```python
@dataclass(frozen=True, slots=True)
class CapabilitySemanticMapping:
    concept: str
    language_patterns: tuple[str, ...]
    targets: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class CapabilitySemanticMetadata:
    purpose: str
    mappings: tuple[CapabilitySemanticMapping, ...] = ()
    distinctions: tuple[str, ...] = ()


class CapabilitySpec:
    ...
    semantic_metadata: CapabilitySemanticMetadata | None = None
```

The exact class names may follow repository naming conventions during CM-57A,
but the shape is intentionally small:

- `purpose` explains the capability-specific semantic domain.
- `concept` gives a stable review label.
- `language_patterns` gives bounded recognition phrases, not a parser grammar.
- `targets` identifies provider-facing typed fields and a human-readable value
  cue; it is guidance, not executable transformation logic.
- `distinctions` expresses cross-field meaning that should not be inferred by
  copying one field into another.

The `targets` representation should remain immutable tuples rather than a
mutable dictionary. Mapping order is then explicit and stable. There is no
callable, regular expression, parser, provider instruction, runtime ID, or
canonical path in this model.

The initial `binding.raster` metadata would express only:

```text
generic raster / waveform raster / VDL raster → binding.profile
sample unit U → binding.sample_axis.unit
source origin X → binding.sample_axis.source_origin
source step X → binding.sample_axis.source_step
N ticks → binding.sample_axis.tick_count
```

It would also state that `track.x_scale` is the array-track horizontal domain
and `binding.sample_axis` is the raster-internal sample coordinate system. It
would explicitly say not to populate sample-axis bounds by copying track
x-scale bounds without an independent request.

It would not contain mappings for `binding.scale.*` or
`track.x_scale.*` numeric fields.

## 10. Semantic Metadata Authority

The single production authority should be:

```text
CapabilitySpec.semantic_metadata
```

The built-in declaration for `binding.raster` would own its metadata alongside
its description, source kinds, worker hints, and argument model. A future
capability module would attach its own metadata when it constructs its
`CapabilitySpec`.

The following are derived representations, not authorities:

- deterministic worker-input `semantic_contracts` payload;
- prompt text that explains how to read that payload;
- tests asserting the declaration is serialized correctly;
- documentation describing the contract.

The historical JSON under `docs/evaluations/**` remains evidence only. Runtime
code must not import it.

## 11. Capability Selection And Ordering

The selector belongs at the existing registry/typed-worker boundary, not in the
planner and not in a second registry. Conceptually:

```text
SectionTask.capability_ids
        ↓
CapabilityRegistry.get()
        ↓
canonical CapabilitySpec.semantic_metadata
        ↓
omit capabilities with None metadata
        ↓
TypedSectionWorkerInput.semantic_contracts
```

Selection is deterministic and uses the order in `SectionTask.capability_ids`.
That order is already the planner's semantic task order and avoids turning an
unordered set into provider input. Duplicate IDs in one task do not duplicate
metadata: the selector keeps the first occurrence in task order while leaving
the original task unchanged. Unknown or non-canonical IDs continue to fail at
the existing typed-worker representability boundary.

The selector must not fuzzy-match, infer, search, or ask the provider which
metadata to use. A capability with no metadata is omitted. An empty contract
object should not be emitted merely to make the payload shape uniform.

### 11.1 Authoritative Request Decision

The future production typed worker should include the host-provided original
request. This is the selected decision:

```text
INCLUDE_AUTHORITATIVE_REQUEST_IN_FUTURE_TYPED_WORKER
```

S1 used the authoritative original request in both A and S. The current
production `TypedSectionWorkerInput` does not, so S1 does not validate the
proposed production payload yet. Before CM-57B production integration, a
separate input-boundary experiment must compare:

```text
P:   current TypedSectionWorkerInput
P+S: current TypedSectionWorkerInput + selective metadata
```

with no authoritative request, and separately compare the selected future
contract. That experiment must use the same response schema, evaluator,
context, compiler, and no-repair policy. Its purpose is to determine whether
the request is necessary rather than to silently attribute S1's result to a
payload it did not test.

The reason to prefer the request in the future contract is evidence-based: S1
validated it, it preserves user-authored semantics that the planner may
compress, and it keeps planner task decomposition separate from worker semantic
interpretation. The request is not planner output, expected semantics, or
evaluation provenance.

The future host flow is:

```text
CodeModeGraphState.request
        ↓
isolated section worker payload
        ↓
TypedSectionCompiler.compile(..., authoritative_request=...)
        ↓
TypedSectionWorkerInput.authoritative_request
```

The value remains user-authored natural language. It must be copied from host
graph state, not reconstructed from `SectionTask`, and must not be synthesized
from evaluator or canonical document data.

Section isolation remains mandatory. A typed worker may receive only the
original request, its single `SectionTask`, its single `ResolvedSectionContext`,
and selected capability metadata. It must not receive sibling contexts, sibling
outputs, graph-wide evaluation data, or unrelated canonical source data.

## 12. Worker Serialization

The future provider-safe payload should extend the existing typed input with
the selected request and metadata, without altering the existing `section_task`,
`capabilities`, or `sources` objects:

```json
{
  "authoritative_request": "...",
  "section_task": {},
  "capabilities": [],
  "sources": [],
  "semantic_contracts": [
    {
      "capability_id": "binding.raster",
      "purpose": "...",
      "mappings": [],
      "distinctions": []
    }
  ]
}
```

`semantic_contracts` is omitted when no selected capability has metadata. This
keeps the no-contract payload as close as possible to the current worker input
and makes absence meaningful. When present, contracts are serialized in task
capability order, mapping order is declaration order, and JSON serialization
remains sorted/compact through the existing serializer.

The serialized field may contain only bounded descriptions, language patterns,
typed semantic target paths, and value cues. It must not contain:

- canonical source paths or source filenames;
- canonical section, track, or binding IDs;
- document contents or sibling task context;
- expected outputs, evaluation metadata, or benchmark identifiers;
- renderer classes, layout values, styles, colors, or program commands;
- provider settings, retry instructions, or repair instructions.

The provider boundary remains:

```text
authoritative original request
SectionTask
bounded generic capability descriptors
selected capability-local semantic metadata
bounded opaque source/channel context
        ↓
structured SectionSemanticDraft
```

`authoritative_request` is host-provided user intent. It is not capability
metadata, planner output, evaluation provenance, or a substitute for the
typed task/context contracts. No canonical path or runtime identity is added
by carrying it.

## 13. Prompt Integration

The existing `TYPED_SECTION_SYSTEM_PROMPT` in
`src/wellplot/agent/code_mode/typed_section_worker.py` already tells the worker
to use the schema, exact source/channel context, ordered semantics, and local
semantic IDs. The future additive prompt text should be one bounded paragraph:

```text
semantic_contracts contains capability-specific Wellplot meanings that need
explicit clarification. Use those mappings where applicable. For semantics not
documented there, interpret the authoritative request normally using the
SectionSemanticDraft schema. Do not infer additional semantics or copy example
values.
```

This text must not mention S1, R8R, reverse-scale failures, benchmark values,
preserving an A output, or generic scale-field mappings. It should not repeat
the full response schema or become a global list of capability behavior.

The prompt change is provider-facing but remains data-driven. It does not add a
capability switch or a second prompt for raster workers.

## 14. Validation And Boundedness

Validation is split by ownership:

### Registry/declaration validation

`CapabilitySpec` construction should fail fast for empty metadata text,
duplicate concepts, duplicate mapping phrases, duplicate target paths within a
mapping, empty target paths, and mutable metadata containers. Target paths must
be bounded dotted identifiers. A capability cannot declare duplicate semantic
metadata objects.

### Typed-worker boundary validation

The typed worker should validate target paths against the small set of
`SectionSemanticDraft` fields that are intentionally exposable. Initially the
allowlist is:

```text
binding.profile
binding.sample_axis.unit
binding.sample_axis.source_origin
binding.sample_axis.source_step
binding.sample_axis.tick_count
```

No target beginning with `binding.scale` or any numeric
`track.x_scale` target is allowed by the initial contract. This is a small
explicit allowlist, not reflection infrastructure or a semantic rule engine.

### Boundedness

The implementation should use named engineering limits rather than unbounded
provider input. A reasonable initial guard is at most eight mappings per
capability, eight language patterns per mapping, four distinctions per
capability, and an eight-kilobyte serialized semantic-contract budget per
worker request. These are transport/safety bounds, not experiment-derived
semantic thresholds; they can be revised by a later design review if the
capability catalog grows.

Text values should be non-empty and length-bounded. Metadata must be immutable
after registry construction. Serialization must fail before provider
construction if validation or the aggregate size bound fails.

The model should not attempt to validate natural-language truth. It validates
shape, boundedness, target ownership, and provider safety; the typed response,
context validator, and compiler remain the semantic authorities.

## 15. Failure Behavior

- Capability has no semantic metadata: omit `semantic_contracts`; proceed with
  the normal typed worker input.
- Selected capability has metadata: include its validated contract.
- Duplicate capability IDs: retain only the first metadata instance in task
  order; do not mutate the task or invent a new capability.
- Unknown/non-canonical capability ID: preserve the existing typed-worker
  representability failure before provider generation.
- Invalid metadata at registry construction: fail fast as a developer error.
- Invalid metadata discovered during worker projection: fail before provider
  generation with a bounded host validation error.
- Provider ignores metadata: do not repair or synthesize fields; normal
  response-schema validation, contextual validation, and compiler behavior
  determine the result.
- Semantic generation failure: preserve the failure. There is no metadata-driven
  fallback to `ProgramSectionCompiler`.

No failure path should expose canonical source paths, provider raw responses, or
arbitrary exception text in the provider-safe diagnostic.

## 16. Planner, Enricher, And Compiler Impact

### Planner: `PLANNER_CHANGE_NOT_REQUIRED`

`SemanticPlanner._planning_catalog()` in
`src/wellplot/agent/code_mode/planner.py` intentionally exposes a compact
planning descriptor. The planner already selects canonical capability IDs in
`SectionTask.capability_ids`; it does not need to decide capability-specific
worker wording. Adding semantic contracts to the planner would expand the
planner contract and duplicate the later deterministic lookup.

### Enricher: `NO`

`SemanticEnricher` and `ResolvedSectionContext` in
`src/wellplot/agent/code_mode/enrichment.py` own explicit source candidates,
canonical source paths, channels, units, aliases, and section target
resolution. Capability semantic metadata does not select files or channels and
must not be mixed into source discovery or source validation.

### Compiler semantic policy: `NO`

`validate_section_semantics()` remains the context validator, and
`compile_section_semantics()` remains a deterministic translation from a
validated draft to sparse `AuthoringDocumentIntent`. The compiler must not infer
raster profiles, sample axes, scale orientation, titles, or semantic repairs
from capability metadata. It consumes the typed result; metadata ends at the
provider input boundary.

### Routing and fallback: `NO`

No route changes and no automatic fallback between typed and program workers are
part of CM-57.

## 17. Identity Boundary Analysis

The current identity flow is:

```text
SectionSemanticDraft.title/source_candidate/tracks
        ↓
validate_section_semantics()
        ↓
compile_section_semantics()
        ↓
IdAllocator seeded from AuthoringDocumentSpec
        ↓
canonical section/track/binding IDs
        ↓
AuthoringDocumentIntent
```

More precisely:

- `section_id_hint` is host-supplied to `compile_section_semantics()` and is
  allocated by `IdAllocator.allocate_section()`.
- Each track `semantic_id` is validated for uniqueness, then used as the
  advisory `track-{semantic_id}` hint to `allocate_track()`.
- Each binding `semantic_id` is validated for uniqueness within its track, then
  used as the advisory `binding-{semantic_id}` hint to `allocate_binding()`.
- The current compiler passes `id_hint` rather than `channel` to
  `IdAllocator.allocate_binding()`, so binding identity is coupled to the
  model's local label even though the allocator can also seed from a channel.
- `source_candidate` is selected by the model from opaque host-provided IDs,
  validated against `ResolvedSectionContext`, and then resolved by the host to
  `AuthoringDataSource(source_path, source_format)`.
- `channel` is selected by the model from exact host-provided mnemonics and is
  validated for source membership and scalar/array kind before compilation.

This preserves repeated-channel semantics because bindings remain ordered
objects and semantic IDs must be unique. Two bindings may use the same physical
channel without being deduplicated. The current allocator still means that
equivalent models using different local labels may receive different canonical
IDs.

### Current identity-flow diagram

```text
LLM track.semantic_id / binding.semantic_id
                 │
                 ▼
       allocator id_hint strings
                 │
                 ▼
             IdAllocator
                 │
                 ▼
 canonical AuthoringTrack/Binding IDs
```

The preferred long-term principle is that semantic IDs are model-local
correspondence labels and canonical runtime identity is host-owned. The current
repository has not yet fully implemented that separation, so CM-57 must not
silently claim that it has.

## 18. Identity Ownership Table

| Identity | Proposed by | Validated by | Final owner | May model wording change final value? |
| --- | --- | --- | --- | --- |
| Section ID | Host `section_id_hint` / target context | Compiler and `IdAllocator` | Host allocator | No |
| Track `semantic_id` | `SectionSemanticDraft` | Pydantic and semantic validator uniqueness check | Worker-local draft | Yes, currently indirectly |
| Binding `semantic_id` | `SectionSemanticDraft` | Pydantic and per-track uniqueness check | Worker-local draft | Yes, currently indirectly |
| Canonical track ID | `IdAllocator.allocate_track()` | Allocator reservations | Host/compiler | No, but current hint changes it indirectly |
| Canonical binding ID | `IdAllocator.allocate_binding()` | Allocator reservations | Host/compiler | No, but current hint changes it indirectly |
| Source candidate ID | Host `SourceCandidate` inventory, selected by worker | `validate_section_semantics()` | Host context | Worker may select only a supplied ID |
| Channel mnemonic | Host loader/context, selected by worker | Source membership and kind validation | Host source contract | Worker may select only an exact supplied mnemonic |

## 19. Title-Fidelity Classification

The S1 residual `Gamma Ray` versus `Gamma Ray Section` behavior is not a raster
semantic. It belongs to:

```text
SEPARATE_FIDELITY_SLICE
```

The title path is request/task text to worker-generated
`SectionSemanticDraft.title`, then compiler projection to
`AuthoringSectionIntent.title`. CM-57 must not add a “preserve titles
literally” instruction to raster metadata. A future fidelity slice should define
whether exact title preservation is required, how revisions treat omitted
titles, and how title acceptance is measured.

## 20. Extensibility Analysis

The proposed extension is capability-local:

```text
new CapabilitySpec
        + optional CapabilitySemanticMetadata
        ↓
existing registry lookup
        ↓
existing typed-worker serialization
```

A future borehole-image capability could attach orientation, azimuth-reference,
and depth/sample semantics. A well-diagram capability could attach its own
domain vocabulary. A future typed annotation capability could document
annotation-specific meaning. None requires editing a central
`if capability_id == ...` block in the worker.

Cross-capability distinctions are initially attached to `binding.raster`, because
S1 proved that capability's sample-axis meaning and the distinction is only
needed when a raster binding is present. `track.array` supplies the parent
track context through the existing capability selection. If future capabilities
create many independent cross-capability invariants, that is a later design
question; CM-57 should not create a generic invariant engine for this one case.

## 21. Alternatives Considered

### Alternative 1: Global worker-prompt expansion

This is easy to implement but grows one prompt with every capability and
repeats guidance for tasks that do not use it. R8R demonstrated that broad
guidance can interfere with already-correct generic scale behavior. Rejected.

### Alternative 2: Capability-local structured semantic metadata

This reuses the existing registry, selects only relevant metadata, is
auditable, and supports future capabilities without central switches. It is
the minimum sufficient architecture. Recommended.

### Alternative 3: Specialist worker per capability

Current evidence concerns one small semantic gap, not a need for separate
orchestration or model roles. Specialist workers would add routing, failure,
and parity complexity without evidence. Deferred.

### Alternative 4: Deterministic parser or rule engine

A parser would duplicate natural-language-to-semantic interpretation, create a
second semantic authority, and invite benchmark-specific rules. It would also
blur provider failure versus host repair. Rejected for CM-57.

### Alternative 5: Keep the experimental JSON externally

This avoids production model work but leaves runtime behavior dependent on an
evaluation artifact and creates duplicate authority between source-code
capabilities and docs. Rejected. The experiment remains historical evidence;
production metadata should be declared beside its capability.

## 22. Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Prompt/input growth as capabilities expand | Select only task capabilities, omit empty metadata, enforce serialized size bounds. |
| Conflicting metadata from multiple capabilities | Keep metadata capability-local; reject duplicate target paths within one contract and document cross-capability ownership. |
| Over-documenting obvious semantics | Require evidence for each mapping and explicitly exclude generic scale mappings. |
| Metadata drift from `SectionSemanticDraft` | Maintain a small typed-worker target allowlist and run schema/serialization tests before provider use. |
| Cross-capability invariant ownership becoming unclear | Attach the current distinction to `binding.raster`; open a separate design slice if composition grows. |
| Provider sensitivity to wording | Keep prompts additive and bounded; evaluate with paired shadow cases and frozen payload hashes. |
| Semantic-ID/canonical-ID instability | Do not expand CM-57 to refactor identity; record the separate identity slice and compare canonical projections in shadow validation. |
| Benchmark overfitting | Build a new production-semantic corpus with new values, layouts, paraphrases, and negative cases. |
| Future capability composition | Resolve metadata by registered capability ID and preserve task order; avoid global capability branches. |

## 23. Broader Shadow-Validation Plan

Before any production route activation, build a new shadow corpus from
production semantics rather than copying S1 expected outputs. It should use new
values, channels, track arrangements, and phrasing. It should include:

- paraphrased generic raster, waveform, and VDL requests;
- different sample units;
- origin-only and step-only cases where the schema permits them, plus invalid
  combinations where it does not;
- alternate wording for tick counts;
- array x-scale without a sample-axis request;
- independent x-scale and sample-axis requests;
- multiple raster bindings and multiple array tracks;
- raster bindings with explicit, implied, and absent profile language;
- composition with normal/reference tracks and repeated physical channels;
- negative source, channel-kind, duplicate-ID, and unsupported-capability cases.

The corpus authoring rule is that cases come from production semantic
requirements, not from copying golden output fields. Expected values may be
written by a separate deterministic evaluator, but they must not be serialized
into provider input. Each future shadow row should retain input hashes,
metadata hashes, schema hash, evaluator hash, model controls, structured
validity, context validity, compiler validity, and leaf-level semantic status.

The shadow harness must evaluate the complete future typed input boundary. Once
the authoritative-request decision is implemented, every row must record the
request-bearing payload hash and prove that the worker received only its own
request, task, context, and selected metadata. The current S1 summary cannot be
reused as proof of that production-native boundary without this input-contract
check.

## 24. Implementation Slices

The minimum future decomposition is:

### CM-57A — Capability metadata model and registry authority

Implement the immutable metadata dataclasses, optional `CapabilitySpec` field,
declaration-time validation, deterministic registry projection, and unit tests.
Attach only the initial `binding.raster` metadata. Do not change provider
serialization or routing in this slice if the registry API can be tested in
isolation.

### CM-57B — Typed worker serialization and bounded prompt integration

Add the provider-safe `semantic_contracts` projection to
`TypedSectionWorkerInput`, select contracts from task capability IDs, add the
small prompt paragraph, and test omission, ordering, redaction, size bounds,
target allowlisting, and A/S-equivalent payload isolation. Add the selected
`authoritative_request` only after the separate input-boundary experiment has
frozen that contract. Keep the active `ProgramSectionCompiler` route unchanged
and do not add repair or fallback. CM-57B is blocked until the request-bearing
future payload is independently justified.

### CM-57C — Broader typed-worker shadow evaluation

Run the new unseen corpus through the real planner/enricher boundary and the
typed worker in shadow mode using the exact request-bearing future payload.
Compare scientific leaves, source/channel validity, repeated-channel
preservation, title behavior, and canonical projection stability. Keep provider
controls and evidence handling explicit.

### CM-57D — Production activation decision

Only after CM-57C is independently accepted should a separate authorization
define graph/routing integration. CM-57D owns the explicit decision between
`ProgramSectionCompiler` and `TypedSectionCompiler` in
`CodeModeGraphDependencies`; it is not authorized by this design checkpoint.

### Separate identity slice

The semantic-ID coupling should be handled separately, tentatively as
`CM-58 — Host-Owned Canonical Identity`. It should define structural host
identity for tracks/bindings, preserve repeated-channel multiplicity, and prove
revision/reconstruction parity. It must not be folded into CM-57A or CM-57B.

### Separate title-fidelity slice

The title issue should receive a separate bounded fidelity slice after its
acceptance requirement is defined. It must not be solved by raster metadata.

## 25. Acceptance Criteria

Future implementation review should require:

- one authoritative production metadata field on `CapabilitySpec`;
- no parallel capability registry;
- immutable, bounded, deterministic metadata;
- initial raster profile and sample-axis semantics expressible;
- no generic binding-scale or numeric track-x-scale mappings;
- deterministic task-order selection and omission for capabilities without metadata;
- exact provider-safe serialization insertion point in `typed_section_worker.py`;
- no source paths, runtime IDs, renderer policy, or evaluation gold in metadata;
- no planner or enricher change without new evidence;
- no compiler semantic-policy change;
- no fallback, repair, or routing change;
- explicit target-path validation and pre-provider failure behavior;
- repeated physical-channel bindings remain distinct;
- identity coupling remains outside the metadata implementation;
- title fidelity remains outside CM-57;
- broader unseen shadow corpus before activation;
- no production activation until shadow evidence is independently accepted.

## 26. Open Questions

These do not block the design recommendation but must be resolved in the
implementation slices:

1. Whether the metadata field should be named `semantic_metadata` or
   `worker_semantic_metadata` to distinguish it from the existing loose
   `metadata` field.
2. Whether provider-facing value cues should use one target/value tuple shape or
   a small typed target object. The implementation should choose the simpler
   immutable representation and reject executable-looking instructions.
3. Whether the initial serialized size guard should be eight kilobytes or an
   existing repository-wide context limit if one is found during CM-57A.
4. Whether duplicate capability IDs should eventually be rejected by
   `SectionTask`; CM-57 should only deduplicate the metadata projection and not
   silently alter planner semantics.
5. Whether canonical identity should use channel-aware allocation or a fully
   structural host allocator; this belongs to the separate identity slice.

## 27. Final Recommendation

The minimum sufficient architecture is:

```text
CapabilityRegistry
        │
        ├── CapabilitySpec
        │       └── optional CapabilitySemanticMetadata
        │
        └── deterministic lookup from SectionTask.capability_ids
                        │
                        ▼
              TypedSectionWorkerInput
             ┌──────────┼───────────┬──────────────┐
             │          │           │              │
 authoritative  task/context  semantic_contracts  sources
 request
             │          │           │              │
             └──────────┴───────────┴──────────────┘
                        ▼
              structured generation
                        ▼
              SectionSemanticDraft
                        ▼
              context validation
                        ▼
              deterministic compiler
                        ▼
              AuthoringDocumentIntent
```

The authority table is:

| Concern | Authority |
| --- | --- |
| Capability existence | `CapabilityRegistry` |
| Capability-specific semantic meaning | `CapabilitySpec.semantic_metadata` |
| Task scope | `SectionTask` |
| Source/channel inventory | `ResolvedSectionContext` |
| Natural language to semantic IR | Typed worker/provider |
| Semantic structure | `SectionSemanticDraft` |
| Contextual validity | `validate_section_semantics()` |
| Canonical identity | Host/compiler `IdAllocator` |
| Canonical intent | `compile_section_semantics()` |
| Presentation defaults | Existing defaults/renderer layer |
| Provider mechanics | Provider adapter |

Final architecture decision:

```text
PROCEED_WITH_CAPABILITY_LOCAL_SEMANTIC_METADATA
```

Identity decision:

```text
DEFER_IDENTITY_CHANGE_TO_SEPARATE_SLICE
```

The identity issue is `NON_BLOCKING_ARCHITECTURAL_DEBT` for the metadata
implementation because the metadata path does not need to alter allocation,
and changing it now would confound the capability-semantics experiment.

Title decision:

```text
SEPARATE_FIDELITY_SLICE
```

Current route status:

```text
Active section route: PROGRAM_SECTION_COMPILER
Typed semantic route: NOT YET ACTIVE
```

Input-boundary status:

```text
Authoritative-request production decision:
INCLUDE_AUTHORITATIVE_REQUEST_IN_FUTURE_TYPED_WORKER

CM-57A blocked by request decision: NO
CM-57B blocked by request decision: YES
```

CM-57A can be implemented independently as metadata model/registry work after
separate authorization. CM-57B must wait until the request-bearing production
input contract is frozen and the no-request P/P+S boundary experiment has been
reviewed. CM-57 implementation is otherwise not started.
