# Authoring Contract Inventory

Last updated: 2026-08-06

## Purpose

This document is the implementation inventory for the deterministic `wellplot`
authoring contract. It defines the object families that must be represented by
one canonical typed model before the `0.6.0` release is considered complete.

The inventory is intentionally broader than the MCP tool list. The Python API,
YAML serialization, MCP tools, agent verification, and public documentation
must all describe the same objects and constraints.

## Implementation Checkpoint

The first implementation slice now includes:

- direct `pydantic>=2.7` package dependency
- `wellplot.model.authoring` with strict document, section, track, binding,
  fill, annotation, page, depth, style, and remarks models
- generated-schema coverage for the canonical document boundary
- representative tests for discriminators, duplicate binding instances,
  compatibility constraints, strict fields, and logarithmic scales
- `wellplot.authoring` compatibility adapters for legacy logfile mappings,
  normalized canonical YAML, template loading, and render conversion

Header fields and service titles now carry stable canonical slot identities.
The deterministic service and MCP expose bounded updates for those child
objects, so filling one header value does not require replacing the complete
header mapping.

The canonical models are now wired to the YAML compatibility boundary and the
existing render dataclasses. The deterministic object service now provides
typed atomic operations over those models. The Python builder and MCP
mutations remain separate implementation slices.

## Contract Rule

Every standard authoring property must have one canonical definition covering:

- serialized name
- Python type
- required, optional, and nullable behavior
- default value or default factory
- finite values, range, format, or contextual lookup rule
- parent object and allowed child objects
- create/update mutability
- cross-field and cross-object constraints
- YAML and API compatibility behavior
- deterministic read and write operations

Unknown standard properties must be rejected. If extension data is needed, it
must live in an explicit `extensions` mapping rather than relying on arbitrary
extra keys.

## Sources Being Consolidated

The current contract is distributed across:

- `src/wellplot/model/document.py`
- `src/wellplot/model/channels.py`
- `src/wellplot/model/dataset.py`
- `src/wellplot/logfile_schema.py`
- `src/wellplot/logfile.py`
- `src/wellplot/templates.py`
- `src/wellplot/api/builder.py`
- `src/wellplot/mcp/service.py`
- `src/wellplot/mcp/server.py`
- `src/wellplot/agent/`

Implementation must consolidate these sources without weakening current
validation or changing rendering semantics unintentionally.

## Canonical Layers

### Data Contract

The existing data hierarchy remains authoritative for loaded and computed data:

- `BaseChannel`
- `ScalarChannel`
- `ArrayChannel`
- `RasterChannel`
- `WellDataset`

This layer is already typed and should not be redesigned as part of the
authoring-contract work.

### Authoring Contract

The new canonical authoring layer owns persisted report intent. It should use
strict Pydantic v2 models and generate the JSON Schema consumed by YAML and MCP
discovery.

This layer owns:

- report composition
- section and source routing
- track structure
- bindings and annotations
- page/output/depth configuration
- heading, remarks, and tail content
- reusable visual value objects

### Render Contract

The existing render dataclasses remain the renderer-facing representation.
Explicit adapters convert validated authoring models into render objects.

Render dataclasses must not become a second public authoring contract.

### Service Contract

A deterministic object service owns reads and mutations. Python API and MCP
entry points call this same service rather than editing normalized dictionaries
independently.

## Value Categories

Possible values are not always finite enums. Every field must be assigned one
of these constraint categories:

| Category | Meaning | Examples |
| --- | --- | --- |
| finite | Closed enum known from the contract | track kind, scale kind, annotation kind |
| constrained | Open value with a type, range, or grammar | positive width, opacity, color, line width |
| contextual | Closed only after inspecting the current document or dataset | section id, track id, channel mnemonic, binding id |
| relational | Validity depends on another object or field | fill target exists, raster belongs to a compatible track |
| extensible | Deliberately open plugin/vendor data | explicit `extensions` mapping only |

MCP discovery must identify the category so an agent can distinguish an enum
from a value that requires document or data-source inspection.

## Object Inventory

Status meanings:

- `preserve`: current typed model is suitable and needs only contract linkage
- `consolidate`: behavior exists but definitions are duplicated
- `add`: no complete first-class authoring object exists yet

### Envelope And Output Objects

| Target object | Identity / parent | Current representation | Status |
| --- | --- | --- | --- |
| `LogfileSpec` | root | logfile schema and normalized mapping | consolidate |
| `DataSourceSpec` | logfile or section | schema mapping and loader arguments | consolidate |
| `RenderSpec` | logfile | schema mapping | consolidate |
| `MatplotlibRenderSpec` | render | nested schema mappings | consolidate |
| `MatplotlibStyleSpec` | matplotlib render | nested schema mappings and renderer defaults | consolidate |
| `SectionTitleStyleSpec` | matplotlib style | schema mapping and renderer defaults | consolidate |
| `HeaderStyleSpec` | matplotlib style | schema mapping and renderer defaults | consolidate |
| `FooterStyleSpec` | matplotlib style | schema mapping and renderer defaults | consolidate |
| `ReportStyleSpec` | matplotlib style | schema mapping and renderer defaults | consolidate |
| `TrackHeaderStyleSpec` | matplotlib style | schema mapping and renderer defaults | consolidate |
| `TrackBodyStyleSpec` | matplotlib style | schema mapping and renderer defaults | consolidate |
| `CurveCalloutStyleSpec` | matplotlib style | schema mapping and renderer defaults | consolidate |
| `GridStyleSpec` | matplotlib style | schema mapping and renderer defaults | consolidate |
| `MarkerStyleSpec` | matplotlib style | schema mapping and renderer defaults | consolidate |
| `RasterStyleSpec` | matplotlib style | schema mapping and renderer defaults | consolidate |
| `PageSpec` | report | schema mapping plus render dataclass | consolidate |
| `DepthAxisSpec` | report | schema mapping plus render dataclass | consolidate |

### Report And Section Objects

| Target object | Identity / parent | Current representation | Status |
| --- | --- | --- | --- |
| `ReportSpec` | logfile document | normalized logfile mapping | add |
| `SectionSpec` | `id`, report | layout mapping and builder section | add |
| `HeaderSpec` | report | render dataclass and logfile mapping | consolidate |
| `ReportBlockSpec` | header or tail | render dataclass and schema object | consolidate |
| `ReportValueSpec` | report field/cell | render dataclass and schema object | consolidate |
| `ReportFieldSpec` | report block | render dataclass and schema object | consolidate |
| `ReportServiceTitleSpec` | report block | render dataclass and schema object | consolidate |
| `ReportDetailSpec` | report block | render dataclass and schema object | consolidate |
| `ReportDetailRowSpec` | report detail | render dataclass and schema object | consolidate |
| `ReportDetailColumnSpec` | report detail | render dataclass and schema object | consolidate |
| `ReportDetailCellSpec` | report detail row/column | render dataclass and schema object | consolidate |
| `RemarksSpec` | report | logfile `layout.remarks` sequence | add |
| `RemarkBlockSpec` | remarks | schema mapping | add |
| `TailSpec` | report | logfile mapping reusing report content | add |
| `FooterSpec` | report/section render | render dataclass and schema mapping | consolidate |
| `HeaderFieldSpec` | simple header | render dataclass and schema mapping | consolidate |
| `MarkerSpec` | report or section | render dataclass and schema mapping | consolidate |
| `ZoneSpec` | report or section | render dataclass and schema mapping | consolidate |

### Track Form Objects

The canonical contract should use a discriminated union keyed by `kind`. The
renderer may continue using one composition-based `TrackSpec`.

| Target object | Allowed content | Status |
| --- | --- | --- |
| `NormalTrackSpec` | curve bindings and curve fills | consolidate |
| `ReferenceTrackSpec` | compatible curve bindings, overlays, and reference events | consolidate |
| `ArrayTrackSpec` | raster bindings and supported curve overlays | consolidate |
| `AnnotationTrackSpec` | annotation objects only | consolidate |

Shared track value objects:

| Target object | Parent | Status |
| --- | --- | --- |
| `TrackHeaderSpec` | track | consolidate |
| `TrackHeaderObjectSpec` | track header | consolidate |
| `ReferenceAxisSpec` | reference track | consolidate |
| `ReferenceSecondaryGridSpec` | reference track | consolidate |
| `NumberFormatSpec` | reference track/header | consolidate |
| `ReferenceEventSpec` | reference track | consolidate |
| `GridSpec` | track | consolidate |
| `HorizontalGridSpec` | grid | consolidate |
| `VerticalGridSpec` | grid | consolidate |
| `GridLineSpec` | horizontal or vertical grid | consolidate |
| `ScaleSpec` | track or binding | consolidate |

### Binding And Display Objects

Bindings must have stable identity independent of channel mnemonic so the same
channel can be bound more than once.

| Target object | Identity / parent | Status |
| --- | --- | --- |
| `CurveBindingSpec` | `binding_id`, section/track | consolidate |
| `RasterBindingSpec` | `binding_id`, section/track | consolidate |
| `StyleSpec` | binding or nested display object | consolidate |
| `CurveHeaderDisplaySpec` | curve binding | consolidate |
| `CurveValueLabelsSpec` | curve binding | consolidate |
| `CurveWrapSpec` | curve binding | consolidate |
| `CurveCalloutSpec` | curve binding | consolidate |
| `ReferenceCurveOverlaySpec` | curve binding | consolidate |
| `CurveFillSpec` | curve binding or track-level relation | consolidate |
| `CurveFillCrossoverSpec` | curve fill | consolidate |
| `CurveFillBaselineSpec` | curve fill | consolidate |
| `RasterColorbarSpec` | raster binding | consolidate |
| `RasterSampleAxisSpec` | raster binding | consolidate |
| `RasterWaveformSpec` | raster binding | consolidate |

### Annotation Objects

The canonical contract should use a discriminated union keyed by annotation
kind.

| Target object | Parent | Status |
| --- | --- | --- |
| `IntervalAnnotationSpec` | annotation track | consolidate |
| `TextAnnotationSpec` | annotation track | consolidate |
| `MarkerAnnotationSpec` | annotation track | consolidate |
| `ArrowAnnotationSpec` | annotation track | consolidate |
| `GlyphAnnotationSpec` | annotation track | consolidate |

## Initial Finite Value Register

These values are already present in current models or validation and must be
reconciled into canonical enums. Slice `0.6-A` must identify any additional
finite set before implementation starts.

| Value family | Canonical values | Compatibility note |
| --- | --- | --- |
| track kind | `reference`, `normal`, `array`, `annotation` | legacy `depth`, `curve`, `image` map through compatibility adapters |
| binding kind | `curve`, `raster` | no implicit inference after canonical parsing |
| scalar scale | `linear`, `log`, `tangential` | `auto` is a request/default state, not a resolved render transform |
| grid scale | `linear`, `logarithmic`, `tangential` | normalize naming separately from scalar scale compatibility |
| grid display | `below`, `above`, `none` | closed enum |
| grid spacing | `count`, `scale` | closed enum |
| track-header object | `title`, `scale`, `legend`, `divisions` | closed enum |
| reference axis | `depth`, `time` | closed enum |
| number format | `automatic`, `fixed`, `scientific`, `concise` | closed enum |
| raster profile | `generic`, `vdl`, `waveform` | defaults may suggest but not force a profile |
| raster normalization | `auto`, `none`, `trace_maxabs`, `global_maxabs` | applies independently where waveform/raster fields differ |
| raster colorbar position | `right`, `header` | closed enum |
| curve fill | `between_curves`, `between_instances`, `to_lower_limit`, `to_upper_limit`, `baseline_split` | target requirements vary by kind |
| reference overlay mode | `curve`, `indicator`, `ticks` | closed enum |
| reference tick side | `left`, `right`, `both` | closed enum |
| annotation kind | `interval`, `text`, `marker`, `arrow`, `glyph` | discriminated union |
| annotation label mode | `none`, `free`, `dedicated_lane` | closed enum |
| report detail | `open_hole`, `cased_hole` | header archetypes provide values, not alternate models |
| source format | `auto`, `las`, `dlis` | `auto` resolves before data use |
| render backend | `matplotlib`, `plotly` | backend capability validation remains explicit |
| page orientation | `portrait`, `landscape` | closed enum |
| alignment | `left`, `center`, `right` | apply only to fields supporting alignment |
| missing-channel policy | `skip`, `error` | no silent third behavior |

## Known Contract Conflicts To Resolve In `0.6-A`

| Conflict | Required decision |
| --- | --- |
| scalar scale uses `log` while grid scale uses `logarithmic` | keep separate canonical enums or normalize serialization with an explicit adapter |
| legacy track kinds `depth`, `curve`, and `image` alias canonical kinds | accept only through version-1 compatibility parsing; emit canonical kinds |
| a channel mnemonic is sometimes used as binding identity | require stable `binding_id`; channel remains a contextual source reference |
| annotations are updated by list index | add stable annotation identity and preserve list order separately |
| fills are represented as curve-owned nested data but may relate two bindings | define ownership, target identity, update, and removal semantics once |
| sections are first-class in logfile/builder mappings but not in the flat render document | make `SectionSpec` canonical and adapt each section to render documents |
| page, depth, header, footer, and document mappings accept unknown keys | forbid standard extras and define explicit compatibility/extensions behavior |
| MCP patches use `null` as removal while omitted fields mean no change | preserve this distinction with typed patch models and field-set inspection |
| defaults exist in dataclasses, schema/parser behavior, assets, and renderer fallbacks | choose one authoring default owner and expose applied-default provenance |
| nested styles are accepted as loose mappings in builders and MCP tools | define typed style objects and compatibility overloads |
| template inheritance and normalized logfile validation happen at different stages | define resolution order and validate canonical models after inheritance |
| packet blueprints contain expected geometry and styling | retain only scaffold/fixture data; remove authority from general mutation and verification |

## Compatibility Matrix

| Content | Normal | Reference | Array | Annotation |
| --- | --- | --- | --- | --- |
| curve binding | yes | yes | supported overlay only | no |
| raster binding | no | no | yes | no |
| curve fill | yes | only when curve semantics support it | only for supported curve overlays | no |
| reference event | no | yes | no | no |
| annotation object | no | no | no | yes |

Any exception to this table must be represented explicitly in the canonical
model and covered by a compatibility test.

## Required Deterministic Operations

Every persisted object family must declare which operations it supports:

| Operation | Requirement |
| --- | --- |
| `list` | Return stable ids, kinds, parent ids, and order |
| `get` | Return the complete canonical object, including resolved defaults when requested |
| `create` | Accept a typed create model and return the persisted object |
| `update` | Accept a typed patch model; distinguish omitted values from explicit `null` |
| `remove` | Define child/cascade behavior explicitly |
| `move` | Required for ordered report, section, track, binding, and annotation collections |
| `validate` | Return object-local and document-level errors without writing |

Not every nested value object needs a standalone MCP tool. It must still be
readable and writable through its owning object's typed operation.

## Current CRUD Coverage Assessment

| Object family | Read coverage | Write coverage | Gap |
| --- | --- | --- | --- |
| report/page/depth | summary-level | partial setters | no complete canonical getter or typed patch model |
| section | summary-level | source/update/replicate | no complete section object CRUD |
| track | binding-focused inspection | add/update/remove/move | patch contract duplicated manually |
| curve binding | track inspection | bind/update/remove | no direct canonical getter; identity paths vary |
| raster binding | track inspection | bind/update/remove | no direct canonical getter; nested options remain loose |
| fill | indirect through curve | add/remove | no complete first-class get/update contract |
| annotation | indirect through track | add/update/remove by index | needs stable annotation identity and canonical getter |
| heading/report values | slot inspection | replace/apply values | needs typed report-block CRUD and preservation rules |
| remarks/tail/footer | summary-level | partial replacement | incomplete object-level editing |

## Pydantic Model Rules

The authoring models should use these defaults unless a documented compatibility
case requires otherwise:

- Pydantic v2 `BaseModel`
- strict validation where YAML coercion is not intentionally supported
- `extra="forbid"`
- discriminated unions for track, binding, annotation, and fill kinds
- enums for finite values
- constrained numeric and string fields for open values
- immutable identifiers after creation
- separate create and update models where mutability differs
- explicit serializers for normalized YAML compatibility
- field descriptions suitable for generated schema and public reference docs

Pydantic becomes a direct package dependency when this slice is implemented.
Its current transitive presence through optional MCP/agent dependencies is not a
stable package contract.

## Migration And Compatibility Rules

- Existing supported logfile YAML must remain readable during `0.6.0`.
- Normalized output may change only when documented and covered by fixtures.
- Current template inheritance must resolve before final canonical validation.
- Unknown legacy keys must produce an actionable migration error or be moved
  through an explicit compatibility adapter; they must not be silently dropped.
- Defaults must not overwrite explicit serialized or user-provided values.
- Existing render dataclasses and channel classes stay in place until adapters
  prove equivalent behavior.
- Agent code must not construct or repair raw authoring dictionaries after the
  deterministic service exists.

## Contract Test Matrix

Implementation is incomplete until tests prove:

- every canonical model generates a closed JSON Schema
- every enum and constrained value has positive and negative tests
- existing example YAML loads through compatibility adapters
- load, normalize, save, and reload preserve canonical meaning
- model fields, generated schema, Python API, MCP input schemas, and discovery
  resources expose the same property names and value constraints
- every persisted object has the required deterministic operations
- invalid parent/child combinations fail before persistence
- explicit `null`, omitted values, and defaults remain distinct
- user-provided values survive defaults, starter scaffolds, planning, and
  verification
- generic caliper, porosity, resistivity, annotation, and raster scenarios pass
  without packet-specific authority

## Completion Gate

This inventory is complete when every row has:

- a canonical model owner
- a field-level contract
- a compatibility decision
- deterministic read/write coverage
- generated schema coverage
- tests proving API/MCP/schema parity

The inventory should then become generated reference material where practical,
not another manually duplicated contract.
