# Typed Section-Worker Contract

- **Status:** Implemented deterministic substrate; CM-56 validation pending
- **Implementation:** CM-55/CM-55R complete (`34c6491`; implementation `c2173f7`); routing remains unchanged
- **Design baseline:** `5c98ad1`
- **Architecture authority:** [Code Mode architecture contract](agent-code-mode-architecture.md)
- **Evidence authority:** [consolidated typed-worker memory](evaluations/agent-code-mode/EXP-TW-consolidated-development-memory.md)

## Purpose

This document freezes the production design boundary for a future typed
semantic section worker. It converts the EXP-TW-00 through EXP-TW-08 evidence
into a general Wellplot contract without copying the CBL benchmark taxonomy or
implementing the worker.

CM-54 is design-only. CM-55/CM-55R implement the production models and
deterministic compiler. No routing, graph, provider, planner, enrichment,
repair, MCP, notebook, renderer, persistence, or test behavior changes are
part of this contract slice.

## Production Flow

The promoted section boundary is:

```text
SectionTask + ResolvedSectionContext
        |
        v
provider-safe typed worker input
        |
        v
backend.generate_structured(..., response_model=static model)
        |
        v
static semantic section draft
        |
        v
structural validation
        |
        v
context and semantic validation
        |
        v
deterministic semantic compiler
        |
        v
section-local AuthoringDocumentIntent
```

The compiler translates intent. It does not repair provider output, invent
scientific semantics, rewrite channel selections, reorder tracks or bindings,
deduplicate repeated views, call another model, persist, render, or call MCP.
Host completion may supply deterministic mechanics and defaults that are not
worker-owned.

## Static Schema Rules

The production response model is static and request-independent. It must not
use request-driven `create_model(...)`, runtime-generated `Literal` values,
request-specific unions, document IDs, channel IDs, or provider-specific
schema rewriting. The model itself remains the JSON Schema authority through
`response_model.model_json_schema()`.

The model should use the production equivalent of:

```python
ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
)
```

Unknown fields fail. Ordered tracks, bindings, and other ordered semantic
collections remain ordered tuples or equivalent immutable ordered values.

Track discriminators are explicit required fields:

```python
class NormalTrackSemanticDraft:
    kind: Literal["normal"]

class ReferenceTrackSemanticDraft:
    kind: Literal["reference"]

class ArrayTrackSemanticDraft:
    kind: Literal["array"]
```

This is a narrow compatibility rule for track discriminators. It does not
forbid Pydantic defaults globally. TW-08 retained defaults elsewhere and CM-55
must not remove defaults merely for stylistic consistency.

## Proposed Production Names

The production names should make the semantic/canonical distinction visible
and must not inherit experimental `TW`, `S`, or CBL-specific suffixes:

```text
SectionSemanticDraft
NormalTrackSemanticDraft
ReferenceTrackSemanticDraft
ArrayTrackSemanticDraft
CurveBindingSemanticDraft
RasterBindingSemanticDraft
SemanticScale
SemanticSampleAxis
```

CM-55 may adjust names only for an existing repository naming convention. It
must preserve the semantic distinction and not expose canonical IDs as worker
identity fields.

## Initial Semantic Shape

The initial promoted contract is intentionally smaller than the canonical
authoring schema. This is a non-executable design sketch, not production code:

```python
class SectionSemanticDraft:
    title: str
    source_candidate: str
    tracks: tuple[TrackSemanticDraft, ...]


class NormalTrackSemanticDraft:
    semantic_id: str
    kind: Literal["normal"]              # required
    title: str
    x_scale: SemanticScale | None
    bindings: tuple[CurveBindingSemanticDraft, ...]


class ReferenceTrackSemanticDraft:
    semantic_id: str
    kind: Literal["reference"]           # required
    title: str
    x_scale: SemanticScale | None
    bindings: tuple[CurveBindingSemanticDraft, ...]


class ArrayTrackSemanticDraft:
    semantic_id: str
    kind: Literal["array"]               # required
    title: str
    x_scale: SemanticScale
    bindings: tuple[RasterBindingSemanticDraft, ...]


TrackSemanticDraft = Annotated[
    NormalTrackSemanticDraft
    | ReferenceTrackSemanticDraft
    | ArrayTrackSemanticDraft,
    Field(discriminator="kind"),
]


class CurveBindingSemanticDraft:
    semantic_id: str
    kind: Literal["curve"]
    channel: str
    scale: SemanticScale | None


class RasterBindingSemanticDraft:
    semantic_id: str
    kind: Literal["raster"]
    channel: str
    profile: RasterProfile | None
    sample_axis: SemanticSampleAxis | None
```

Binding kinds are fixed semantic branch kinds. The requiredness behavior of
binding tags must remain compatible with the selected provider path and is not
silently expanded from the TW-08 result; CM-55 must validate any change
separately. Only required track tags are frozen by this slice.

All semantic IDs are non-empty worker-local identities. Track IDs are unique
within one section draft. Binding IDs are unique within their parent track.
Neither becomes a canonical Wellplot ID.

## Ownership Boundary

### Worker-owned semantics

The worker may own values that express the requested scientific section:

- section title;
- opaque source candidate selection;
- ordered track semantic identity, kind, and title;
- explicit track or binding scale semantics;
- explicit reversal and scale unit;
- ordered channel selection;
- repeated-view semantic identity;
- explicit raster profile and sample-axis semantics.

### Host-owned mechanics

The worker must not receive or emit these as identity or implementation
mechanics:

- canonical section, track, or binding IDs;
- canonical source paths or parser objects;
- filesystem paths or dataset objects;
- renderer objects or matplotlib coordinates;
- LangGraph state;
- reconciliation operations, persistence flags, or provider internals.

The host resolves `source_candidate` through the task-local
`ResolvedSectionContext`, allocates canonical identities, and builds the
`AuthoringDocumentIntent` fragment. Explicit user instructions still override
defaults. If the initial contract cannot express an explicit request, that is
a representability gap, not permission to silently apply a default.

## Source and Repeated-View Identity

`source_candidate` is an opaque host-issued candidate ID. The worker may select
only provider-visible candidates and must never manufacture a path, parser
object, dataset object, section ID, or internal source UUID.

Channel mnemonic is not binding identity. Two bindings may intentionally use
the same channel:

```text
channel = CBL, semantic_id = cbl_0_100
channel = CBL, semantic_id = cbl_0_10
```

The compiler preserves both ordered bindings and does not deduplicate them.

## Generalized Semantic Vocabulary

### Scales

Canonical Wellplot scales support:

```text
linear
log
tangential
```

`SemanticScale` should cover `kind`, `minimum`, `maximum`, `reverse`, and an
optional `unit`, with canonical validation for bounds and logarithmic values.
Minimum/maximum are worker-owned when an explicit scale is requested. Kind and
reverse are worker-owned when explicitly requested; otherwise host/default
policy may apply. Unit is worker-owned when explicitly requested or
scientifically necessary.

TW-08 directly validated only the CBL linear representation. Log and
tangential scales are production generalizations that CM-56 must exercise.
The worker must not repeat canonical presentation defaults merely because the
canonical model has defaults.

### Raster profiles

Canonical raster profiles include:

```text
generic
vdl
waveform
```

The production contract must not promote the experimental `vdl` literal as
the complete profile domain. Profile, normalization, sample axis, and
waveform semantics must be classified individually as worker-owned,
host/default, or deferred. Renderer-only configuration should not be copied
into the worker schema.

### Sample axes

An explicit `SemanticSampleAxis` may express the canonical concepts:

```text
unit
source_origin
source_step
minimum
maximum
tick_count
```

An absent sample axis means the worker made no explicit request and host,
default, or source metadata may resolve it. A present sample axis is explicit
scientific intent; the compiler preserves its values and does not silently
replace them with defaults. Not every raster requires one.

## Validated Core and Product Gaps

TW-03S and TW-08 validated this typed-worker core:

```text
normal    -> curve bindings only
reference -> curve bindings only
array     -> raster bindings only
array     -> x_scale required
```

This is not a permanent statement that the full Wellplot domain is
array-to-raster-only. The canonical `ArrayTrackSpec` permits curve overlays on
array/image tracks. That capability is an explicit representability gap for
the initial typed core. CM-57 may not remove or bypass the existing section
path for that capability until the typed contract adds and validates it.

## Representability Matrix

The matrix compares the proposed typed contract with the TW R1 result, the
current `ProgramSectionCompiler`, and the canonical Wellplot model/capability
surface. `validated-core` means directly supported by TW-08. `production-
generalization` requires CM-56 evidence. `host-owned` is deterministic
completion or presentation policy. `deferred` is not currently represented by
the initial typed contract. `program-partial` means the current program worker
can express some but not all of the row.

| Semantic capability | EXP-TW R1 | Current ProgramSectionCompiler | Canonical Wellplot capability | CM-54 disposition |
| --- | --- | --- | --- | --- |
| New section title | yes | yes | yes | validated-core |
| Subtitle | no | yes | yes | deferred |
| Section depth/window semantics | no | yes | yes | deferred |
| Opaque source selection | yes | yes | yes | validated-core |
| Normal track | yes | yes | yes | validated-core |
| Reference track | yes | yes | yes | validated-core |
| Array track | yes | yes | yes | validated-core |
| Annotation track | no | no | yes | deferred representability gap |
| Track semantic identity/title | semantic identity and title | id hint and title | canonical id/title | validated-core; host owns canonical ID |
| Track width | no | yes | yes | host-owned default; explicit request deferred |
| Track scale | linear x-scale only | linear/log SDK options | linear/log/tangential | production-generalization |
| Track reverse | yes through scale | yes | yes | validated-core for explicit value |
| Track grid | no | no | yes | host-owned/deferred |
| Curve channel | yes | yes | yes | validated-core |
| Repeated same-channel curves | yes with semantic IDs | multiple calls can repeat channel | unique canonical binding IDs | validated-core |
| Curve label | no | yes | yes | deferred; explicit user request remains a gap |
| Curve scale | linear only | linear/log program options | linear/log/tangential | production-generalization |
| Curve style | no | basic color/line options | full style | deferred |
| Reference overlay | no | no exposed SDK option | yes | deferred representability gap |
| Raster channel | yes | yes | yes | validated-core |
| Raster profile | `vdl` only | generic/vdl/waveform options | generic/vdl/waveform | production-generalization |
| Raster sample axis | required in R1 | not exposed in SDK reference | supported with optional fields | production-generalization |
| Raster normalization | no | basic normalization option | supported | deferred |
| Raster color limits | no | basic color limits option | supported | deferred |
| Raster colormap | no | basic colormap option | supported | deferred |
| Raster alpha | no | basic alpha option | supported | deferred |
| Waveform options | no | no exposed SDK option | supported | deferred |
| Curve overlay on array track | no | not supported by selected capability parents | supported | explicit gap; cannot regress |
| Fills | no | no exposed SDK operation | supported | deferred |
| Annotations | no | no exposed SDK operation | supported | deferred |
| Log scales | no | partial | supported | production-generalization |
| Tangential scales | no | not represented by track SDK | supported by canonical scale | production-generalization |
| New-section reconstruction | yes | yes | yes | validated reconstruction boundary |
| Existing-section revision | no | section-sparse/partial only | supported by canonical intent/service | deferred; requires production evidence |

The matrix is a scope control, not a claim that every canonical capability
must be added to the first typed worker. A missing row remains visible and
must be handled before complete removal of the current section path.

## Planner and Enricher Input Sufficiency

Production currently supplies a `SectionTask` containing `goal`,
`capability_ids`, `existing_section_hint`, `source_hints`, `requirements`,
and `constraints`, plus a `ResolvedSectionContext`. CM-54 does not modify
`SectionTask`. CM-56 must measure whether this input is sufficient rather than
assuming free text is equivalent to typed evidence.

| Proposed worker output | Current production input | Sufficiency status |
| --- | --- | --- |
| Section title | `goal`; possibly free-text `requirements` | representable only in free text; not guaranteed |
| Semantic track identity | `requirements`, `constraints` | representable only in free text; not guaranteed |
| Track kind | selected track capability IDs and registry metadata | explicitly represented when selected; verify task completeness |
| Channel | `ResolvedSectionContext` inventories plus free-text requirements | available for grounding; selected channel not guaranteed |
| Repeated-view identity | free-text requirements/constraints | not currently guaranteed |
| Scale values | free-text requirements/constraints | not currently guaranteed |
| Scale type | free-text requirements/constraints | not currently guaranteed |
| Reverse | free-text requirements/constraints | not currently guaranteed |
| Raster profile | capability hints plus free-text requirements | partially represented; not semantically guaranteed |
| Sample axis | source/channel metadata is bounded but not a typed production task field | not currently guaranteed |
| Source selection | `source_hints` and resolved source candidates | candidates are available; selected source is not guaranteed |

The future serializer must remain path-free, host-bounded, task-local, and
sibling-section isolated. CM-56 owns the real planner/enricher measurement.
CM-56R is permitted only if that evidence demonstrates an input-sufficiency
defect; it must remain generic and not encode CBL-specific rules.

## Validation Layers

Structural validation owns request-independent facts:

- unknown fields fail;
- required track discriminator is valid;
- normal/reference binding shape is curve-only in the validated core;
- array binding shape is raster-only in the validated core;
- array x-scale is present in the validated core;
- semantic IDs are non-empty and unique in their local scope;
- numeric fields satisfy scale and sample-axis constraints.

Context/semantic validation owns task- and source-dependent facts:

- selected source candidate exists;
- selected channel exists on the selected source;
- curves use scalar channels;
- rasters use array channels;
- explicit semantics are representable by the selected capability set.

Gate A remains experiment-specific. Production code must not know `Main Pass`,
`Repeat Pass`, the CBL range values, `source-1` as an expected answer, or VDL
benchmark constants except when supplied by a real user task.

## Reconstruction and Revision

TW-00 through TW-08 validated new-section reconstruction only. They do not
prove typed existing-section revision parity.

The initial promoted contract is therefore a validated reconstruction boundary.
Revision requires separate production evidence for:

- host-resolved existing target identity;
- sparse updates that preserve omitted fields;
- adding a child versus replacing a child;
- removals and their ownership rules.

The CM-47 host-bound revision behavior remains the canonical reference. CM-54
does not define a complete typed revision schema, and CM-57 remains conditional
on CM-56 evidence and revision coverage.

## Graph and Result Integration

The current graph result model contains `ProgramExecutionResult`,
`ProgramDiagnostic`, and `ProgramMetrics` because the current section worker is
program-based. A typed section worker must not fabricate an `AuthoringProgram`,
fake AST metrics, fake program source, or fake repair counts merely to fit that
result type.

CM-55/57 must define a genuine typed-section result boundary carrying the
equivalent of success, an intent fragment, diagnostics, provider evidence, and
structural validation evidence. Any graph evidence unification must preserve
the distinction between genuine program metrics and typed structured generation
evidence. No new state class is introduced in CM-54.

## Provider and Repair Boundary

The future worker uses the existing provider-v2 abstraction:

```python
backend.generate_structured(
    request,
    response_model=SectionSemanticDraft,
)
```

No provider adapter change is planned. Provider input remains path-free,
host-bounded, source/channel grounded, task-local, and sibling-section
isolated.

Initial typed production validation is first-attempt only. The typed worker
does not automatically port `ProgramRepairCoordinator`, add retries, or fall
back from typed structured generation to program synthesis. Repair requires a
separate evidence-driven authorization after first-attempt production
measurements.

## Relationship to Report Worker and Capabilities

`ReportProgramCompiler` remains unchanged. The transitional graph may be
heterogeneous:

```text
report task   -> ReportProgramCompiler
section task  -> future TypedSectionCompiler
```

Both produce section/report-local `AuthoringDocumentIntent` fragments for the
existing deterministic merge path.

The capability registry tells the planner and worker which installed
capabilities exist. The semantic draft describes a generic composition of
those capabilities. The contract must not add `if cbl`, `if vdl`, or other
scientific-use-case branches to the worker schema, compiler, or graph topology.

## CM-55 Boundary

CM-55/CM-55R implement the static production models and deterministic semantic
compiler defined here. The finalized evidence baseline `34c6491` preserves the matrix
as an explicit gate, validates against the actual canonical models, and leaves
production routing unchanged. CM-55 does not inherit permission for planner
changes, real-provider cutover, repair, fallback, or graph integration beyond
the contract boundary. CM-56 owns real planner/enricher sufficiency evidence.
