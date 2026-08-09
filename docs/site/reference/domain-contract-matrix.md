# Domain Contract Matrix

This document is the `0.6-G0` contract-research output for the authoring
surface. It defines reusable object rules for well-log reports without making
any packet family, service company, or channel list authoritative.

## Mission And Scope

The user should be able to create and refine a scientifically useful well-log
plot without knowing the internal YAML or MCP vocabulary. The deterministic
authoring contract must therefore understand the relationships between report
forms, supplied data, and visual content before an agent or UI chooses any
mutation.

This matrix is a design contract, not a packet template. It does not prescribe
that a report contains a particular service, track, or channel. It defines the
objects that can be composed, the content each object can own, and the checks
required before content is persisted.

## Object Families

The authoring model has four distinct families. They should not be collapsed
into one inheritance ladder.

### Form Objects

Form objects define report structure and available places for content:

- `Report`: owns output intent, report blocks, and ordered sections.
- `Page`: owns physical page and continuous-layout settings.
- `Header`: owns stable slots, labels, service titles, detail rows, and values.
- `Section`: owns one data context and an ordered track layout.
- `Track`: owns a visual lane and declares compatible content.
- `TrackHeader`: owns the title, scale, legend, and division presentation.

### Content Objects

Content objects populate form objects:

- header values and service titles
- curve bindings and their labels, scales, colors, and line styles
- raster bindings and their profile, colorbar, sample-axis, and waveform options
- fills between compatible curve instances or limits
- reference events and overlays
- annotation objects
- remarks, tail blocks, and report notes

Content identity must be stable independently of its source channel. This is
what permits the same channel to appear more than once with different scales or
styles.

### Data Objects

Data objects describe what can be read from a source:

```text
BaseChannel
├── ScalarChannel       one value per reference sample
└── ArrayChannel        multiple sample values per reference sample
    └── RasterChannel   array data intended for raster presentation
```

The data hierarchy is not the layout hierarchy. An array-shaped source may be
rendered by an array track, while the binding still owns display choices such
as colormap and normalization.

### Presentation And Output Objects

Styles, grids, scales, page settings, and renderer settings are value objects
attached to the form or content that they describe. They do not own channels,
tracks, or sections. Output settings must remain explicit authoring objects so
page size, orientation, continuous layout, and output defaults are not inferred
from a packet family.

## Dependency Graph

The minimum valid assembly sequence is:

```text
Report
├── output/page/depth settings
├── header slots and report blocks
├── section
│   ├── data source and source-channel availability
│   └── ordered tracks
│       ├── track form and compatibility kind
│       ├── curve/raster bindings
│       │   └── scale, labels, style, and display metadata
│       ├── fills and overlays
│       └── annotations or reference events
└── remarks/tail blocks
```

The deterministic executor must create or resolve parents before children:

1. resolve report, page, depth, and output context
2. resolve the header archetype and stable header slots
3. create or resolve sections and their data sources
4. inspect source channels and normalize aliases
5. create tracks, validate their kinds, widths, and order
6. create bindings with stable `binding_id` values
7. apply binding scales, labels, styles, and raster display settings
8. create fills, overlays, reference events, and annotations
9. apply final ordering, explicit clears/removals, validation, and rendering

An operation that cannot satisfy its parent or compatibility precondition must
be blocked with an exact reason. It must not be replaced by an inferred track,
an invented channel, or a compensating deletion.

## Compatibility Matrix

| Content | Normal track | Reference track | Array track | Annotation track |
| --- | --- | --- | --- | --- |
| Scalar curve binding | yes | yes | overlay only when explicitly supported | no |
| Raster binding | no | no | yes | no |
| Curve fill | yes | only for compatible curve semantics | only for supported curve overlays | no |
| Reference event | no | yes | no | no |
| Annotation object | no | no | no | yes |

`ArrayChannel` describes source shape; it does not by itself authorize a
raster binding. `RasterBinding` expresses the intended raster presentation and
must be attached to an `ArrayTrack` unless an explicit future compatibility
rule says otherwise.

## Value Constraint Categories

Every public field must declare which kind of constraint applies. This keeps
agent selection and deterministic validation from treating every string as an
enum.

| Category | Meaning | Examples |
| --- | --- | --- |
| finite | Closed set in the contract | track kind, scale kind, annotation kind |
| constrained | Typed value with range or grammar | width, opacity, color, line width |
| contextual | Valid after inspecting the current document or source | section id, track id, channel mnemonic |
| relational | Valid only with another object or field | fill target, raster/track compatibility |
| extensible | Explicit vendor or plugin data | `extensions` mapping only |

The MCP vocabulary should expose this category for each field. For example,
`scale.kind` is finite, `scale.min` is constrained and relational to
`scale.max`, and `channel` is contextual.

## Header Contract

Header archetypes are structural scaffolds. They define available fields and
their layout, but they do not override explicit user values or turn unrelated
input into new fields.

Each header slot needs a stable identity and these properties:

| Property | Purpose |
| --- | --- |
| `slot_id` | Stable target for deterministic updates |
| `label` | Rendered human-facing label |
| `value` | Current displayed value, including an explicit blank |
| `unit` | Unit displayed with or beside the value |
| `source_key` | Optional source metadata key |
| `aliases` | User and source-language names that resolve to the slot |
| `provenance` | Source, user, default, or preserved value origin |
| `availability` | Whether a matching value was found or remains unknown |
| `layout_path` | Location in the header block/detail structure |

Header filling must distinguish:

- omitted: preserve the current value
- explicit value: set the matching slot exactly
- explicit blank/clear: clear that slot intentionally
- unmatched input: report it as unused or inconsistent; do not add a new slot

The same rules apply to general fields, service titles, detail rows, units, and
the open-hole/cased-hole variants. A header fill is successful only when every
requested matching value has a persisted slot-level postcondition.

## Scale, Grid, And Raster Semantics

Scale is part of a binding and may also be part of the containing track. These
are related but distinct values:

- a track scale defines the visual coordinate system and grid divisions
- a binding scale defines how one curve maps into that coordinate system
- a mirrored duplicate curve may use an intentionally different binding scale
- a log track must derive major and minor divisions from the final logarithmic
  bounds, not retain divisions from an earlier range

When a track scale changes, the executor must verify the track bounds, scale
kind, and grid configuration together. Changing only curve labels or binding
limits is not enough.

Raster bindings additionally require explicit semantics for:

- profile (`generic`, `vdl`, or `waveform`)
- normalization
- colormap and color limits
- sample axis and units
- optional colorbar
- optional waveform overlay

Defaults may suggest these values, but explicit user styles and display values
always win and must be visible in the persisted canonical object.

## Defaults And Blueprints

Defaults are fallback values for reusable object families. They may provide a
recommended width, conventional scale, or print-safe style when the user and
existing document do not specify one.

The precedence order is:

1. explicit user instruction
2. preserved existing value
3. selected defaults entry
4. starter scaffold value

Packet blueprints are optional scaffolds or test fixtures. They must not be the
source of truth for the canonical object model, channel availability, styling,
or verification. No packet-specific blueprint should be required to create a
normal, reference, array, or annotation report.

The current defaults and archetype assets are therefore audit inputs for the
next slices. Any family-specific entries must be explainable as optional
defaults, not hidden mutations or authoritative packet geometry.

## Domain And Fixture Matrix

These families are acceptance domains, not hard-coded build recipes.

| Domain | Typical forms | Content to exercise | Special semantics | Initial fixture |
| --- | --- | --- | --- | --- |
| open-hole quicklook | report, header, reference depth, normal tracks | metadata fields, scalar curves, fills, remarks | open-hole header slots and partial values | open-hole starter and LAS notebook |
| cased-hole service | report, cased-hole header, reference depth, normal and array tracks | scalar service curves, duplicate bindings, raster data, notes | service titles, array sample axis, mixed source availability | CBL/VDL production example |
| porosity | report, reference depth, normal overlay tracks | density/neutron curves, mirrored scale, crossover fills | reversed or mirrored binding scales | Forge16B porosity example |
| resistivity | report, reference depth, normal track | shallow/medium/deep curves, explicit styles | logarithmic track/grid divisions and shared bounds | resistivity notebook fixture |
| caliper and QC | report, reference depth, normal tracks | same-channel duplicates, line styles, fills, annotations | repeated source channel with independent binding ids | QC/caliper fixture to add |
| image and array | report, reference depth, array tracks | raster bindings, colorbars, sample axes, waveform overlays | two-dimensional data and display normalization | VDL/raster fixture plus generic array fixture |
| interpretation and mixed | report, sections, annotation tracks, normal/reference tracks | intervals, markers, text, arrows, events | stable annotation ids and lane constraints | annotation fixture to add |

The matrix deliberately names the behavior to test rather than prescribing a
fixed list of mnemonics or track positions.

## Required Research Artifacts

`0.6-G0` is complete when the following artifacts are available:

- this object/dependency and compatibility matrix
- a finite-value register and compatibility alias register
- a header-slot fixture for each supported header detail family
- representative canonical fixtures for scalar, duplicate, fill, raster, and
  annotation content
- explicit unresolved-contract decisions recorded before `0.6-G1`

Targeted external domain research may validate conventions such as header
terminology, unit aliases, and resistivity grid behavior. It must produce
reusable rules or test data, not another authoritative packet template.

## Handoff To `0.6-G1` Through `0.6-G7`

| Slice | Contract output from this matrix |
| --- | --- |
| `0.6-G1` | first-class report, header, tail, and output objects with slot identity |
| `0.6-G2` | typed desired-state models with omitted, explicit, clear, and remove semantics |
| `0.6-G3` | contextual alias/source resolution and explicit precedence |
| `0.6-G4` | generic idempotent reconciliation over the dependency graph |
| `0.6-G5` | read-after-write checkpoints and phase-level postconditions |
| `0.6-G6` | agent planning that emits desired state before deterministic mutation |
| `0.6-G7` | cross-domain fixtures, notebook acceptance, and unsupported-request reports |

## Open Contract Risks

The next implementation slices must resolve these known issues without
introducing packet-specific branches:

- header and tail structures are still partly compatibility/render objects
- report, section, and render-document representations are not fully unified
- scalar `log` and grid `logarithmic` names need an explicit compatibility rule
- legacy track-kind aliases must be accepted only at compatibility boundaries
- defaults are currently distributed across assets, schema/parser behavior,
  dataclasses, and renderer fallbacks
- header aliases, source aliases, and binding identity need one resolution path
- phase verification must inspect the canonical persisted object, not merely a
  successful tool response
