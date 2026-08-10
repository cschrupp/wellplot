# MCP Implementation Plan

Last updated: 2026-08-09

## Purpose

This document translates the MCP authoring mission and object-model direction
into an implementation sequence.

It is intentionally conservative:

- keep what is already working
- avoid broad refactors for their own sake
- move the MCP back toward a user-first authoring surface
- remove hidden authority gradually instead of destabilizing the whole system

## Mission Reminder

The final user should be able to create and refine plots with little or no
knowledge of `wellplot` internals.

The MCP and agent should therefore expose:

- stable authoring objects
- deterministic edit operations
- predictable precedence
- fallback defaults instead of hidden packet-specific overrides

## Current Findings

### 1. The current model is not one inheritance ladder

The system should not be treated as one linear inheritance chain such as:

- `report -> section -> track -> depth track -> curve -> array`

That mixes:

- containment
- form objects
- content objects
- data objects

These are separate concerns and should remain separate.

### 2. The data-object hierarchy is already in good shape

The dataset/channel layer is already well ordered and should not be reformatted
just for architectural neatness.

Current structure:

- `BaseChannel`
- `ScalarChannel`
- `ArrayChannel`
- `RasterChannel`

This is a real inheritance hierarchy and is already aligned with the product
needs.

Implication:

- preserve this layer
- do not redesign channel inheritance as part of the MCP cleanup

### 3. The document/layout side is mostly composition plus explicit kinds

The render/document layer already has the right core idea:

- `TrackSpec` is one shared form object
- track behavior is controlled by explicit `kind`
- content compatibility is enforced by validation rules

This is not a bug by itself.

Implication:

- preserve the composition-based layout model
- do not force subclass-heavy refactors where `kind` plus validation already
  works well

### 4. Track/content compatibility is one of the stronger parts of the model

Current compatibility rules are already valuable:

- normal tracks reject raster elements
- reference tracks reject raster elements
- annotation tracks reject curve/raster elements
- array tracks can own raster elements

Implication:

- keep these compatibility rules
- expose them more clearly through MCP discovery and authoring vocabulary

### 5. The weak point is the user-facing authoring ontology

The core model ingredients exist, but the MCP/agent layer has not consistently
projected them as one clear user-facing object model.

Current weakness:

- sections are strong in logfile/builder workflows but not equally explicit as
  first-class render-layer objects
- form objects and content objects are not documented or exposed clearly enough
  as one canonical authoring ontology
- packet logic has started to blur object ownership and authority

Implication:

- the next work should focus on one strict authoring contract, complete object
  operations, and precedence, not on reformatting healthy lower layers

### 6. Packet blueprints exposed a real product-direction risk

The packet-blueprint experiment helped surface:

- phase planning needs
- verification gaps
- missing deterministic edit tools

But it also introduced a product risk:

- blueprint reconciliation can silently override explicit user instructions

This conflicts with the intended final-user mental model.

Implication:

- packet/example assets should be demoted to scaffolds, examples, or fixtures
- reusable defaults should replace hidden packet authority

### 7. Deterministic rules are duplicated across layers

The same contract is currently expressed in several places:

- render dataclasses and enums
- a hand-maintained JSON Schema
- manual logfile validation
- mapping-to-dataclass parsers
- Python builder dictionaries
- MCP patch-key allowlists and mutation code
- agent success checks and packet reconciliation

Each layer is deterministic in isolation, but there is no guarantee that all
layers accept the same fields, values, defaults, and relationships.

Implication:

- another manually maintained vocabulary is not the first solution
- one canonical typed authoring contract must generate or drive the derivative
  contracts

### 8. Tool breadth is not object-contract completeness

The MCP already has many add/update/remove tools. Coverage is uneven because
objects do not all have complete `list`, `get`, `create`, `update`, `remove`,
and ordering operations backed by one typed service.

Implication:

- earlier `0.4.0` and `0.5.0` work remains valuable as delivered capability
- those slices are not sufficient evidence that the deterministic authoring
  foundation is complete
- `0.6.0` must close contract and CRUD parity before agent behavior is treated
  as release-stable

## Canonical Authoring Structure To Preserve

The intended authoring structure is:

- `report`
  - owns report-level blocks such as heading, remarks, and tail
  - owns ordered sections
- `section`
  - owns ordered tracks
  - owns section-local data source routing
- `track`
  - is a form object with subtype `reference`, `normal`, `array`, or
    `annotation`
  - owns compatible content objects
- content objects
  - `curve binding`
  - `raster binding`
  - `fill`
  - `annotation object`

Separately, the dataset hierarchy remains:

- `BaseChannel`
  - `ScalarChannel`
  - `ArrayChannel`
  - `RasterChannel`

## Non-Goals For This Cleanup

- do not redesign working dataset/channel inheritance
- do not replace the composition-based layout model with subclass-heavy track
  classes unless there is a concrete product need
- do not refactor render-layer internals merely for elegance
- do not expand packet-specific blueprints
- do not make hidden defaults more authoritative

## Approved `0.6.0` Implementation Plan

The `0.6.0` release is now a deterministic authoring-contract program. Existing
agent work remains available for development, but it is not the architectural
foundation and is not release-stable until the following slices pass.

Current progress:

- architecture direction approved and documented
- initial object inventory and known-conflict register written
- direct Pydantic dependency and first canonical model foundation added
- representative contract tests pass
- canonical YAML compatibility and render adapters are implemented for the
  current section, track, binding, annotation, page, depth, and remarks
  surface
- deterministic canonical object service is implemented with typed atomic
  list/get/create/update/remove/move/validate operations
- MCP now exposes the generated canonical JSON Schema and typed object
  inspection through deterministic discovery tools
- MCP persistence rejects mappings that cannot be normalized to the canonical
  authoring contract
- section edits and the canonical track/curve fields are routed through the
  shared service before projection into the legacy render envelope
- page and depth-axis edits are typed service operations used by their MCP
  tools
- typed create/update/remove/move request schemas are published as generated
  MCP discovery data
- the remaining MCP mutation families and duplicated patch catalogs are still
  pending in slice `0.6-E`

### Slice 0.6-A. Contract Inventory And Ownership

Goal:

- identify every persisted authoring object and establish one owner for every
  field and constraint

Work:

- complete [docs/authoring-contract-inventory.md](authoring-contract-inventory.md)
- map each existing schema field, dataclass field, parser rule, builder option,
  MCP patch key, and agent check to a target canonical object
- classify values as finite, constrained, contextual, relational, or explicitly
  extensible
- record compatibility and deprecation decisions before changing behavior

Acceptance:

- no persisted authoring field is unowned
- every object has a documented identity, parent, child compatibility, and
  required deterministic operations
- conflicts between current layers are listed explicitly

### Slice 0.6-B. Canonical Typed Authoring Models

Goal:

- establish one machine-readable source of truth

Work:

- add Pydantic v2 as a direct dependency
- create strict authoring models for logfile/report, output/page/depth, sections,
  track discriminated unions, bindings, fills, annotations, and report content
- use `extra="forbid"` for standard objects
- add an explicit `extensions` field only where open metadata is a real product
  requirement
- generate JSON Schema from these models
- represent finite values with enums and contextual values with documented
  lookup requirements

Acceptance:

- generated schema covers the full inventory
- create and update semantics distinguish omitted values from explicit `null`
- model and schema validation report the same field paths and constraints

### Slice 0.6-C. Compatibility And Render Adapters

Goal:

- adopt the canonical contract without rewriting healthy renderer/data layers

Work:

- parse existing supported YAML through compatibility adapters into canonical
  authoring models
- serialize canonical models back to normalized version-1 YAML
- convert canonical authoring models into existing render dataclasses
- resolve template inheritance before final canonical validation
- replace permissive unknown-key handling with explicit migration errors or an
  approved extension mapping

Acceptance:

- current production examples load, normalize, save, reload, and render without
  semantic regressions
- compatibility behavior is covered by golden fixtures
- no agent or MCP-specific normalization is required to make a document valid

Implementation checkpoint:

- `wellplot.authoring` provides canonical/legacy mapping, YAML, loading,
  template-resolution, and render conversion entry points
- legacy render-only fields are retained under explicit
  `extensions.compatibility` until their first-class canonical objects are
  implemented
- the existing renderer and logfile loader remain unchanged

### Slice 0.6-D. Deterministic Object Service

Goal:

- provide complete typed getters and setters for persisted authoring objects

Work:

- introduce a shared authoring service/repository over canonical models
- implement `list`, `get`, `create`, `update`, `remove`, `move`, and `validate`
  where each object family requires them
- use typed create and patch models rather than arbitrary dictionaries
- make mutations atomic: validate the resulting document before persistence
- define stable identities for bindings, annotations, remarks, and other
  ordered child objects
- define removal/cascade behavior explicitly

Acceptance:

- every inventory row has deterministic read and write coverage
- direct Python use can inspect and revise an existing report without YAML-shaped
  dictionaries
- failed updates leave the persisted document unchanged

Implementation checkpoint:

- `wellplot.authoring_service.AuthoringService` owns defensive canonical
  snapshots and validates every candidate before publishing it
- typed request and patch models cover sections, tracks, curve/raster
  bindings, annotations, fills, remarks, and ordered moves
- MCP now has a canonical validation gate; full mutation parity is completed
  incrementally in slice `0.6-E` without changing the legacy render envelope

### Slice 0.6-E. MCP Contract Parity

Goal:

- make MCP a thin deterministic projection of the same object service

Work:

- route existing MCP mutations through the shared service
- add missing object getters and operations only where required by the inventory
- derive MCP input schemas, patch fields, enums, and discovery resources from
  canonical models
- retire duplicated patch-key allowlists and manually repeated value sets
- keep fixed-root file safety and explicit persistence behavior unchanged

Acceptance:

- Python API, YAML schema, MCP schemas, and authoring discovery expose the same
  fields and values
- contract-parity tests fail if those surfaces drift
- existing narrow tools remain compatible or have documented migrations

Implementation checkpoint:

- `wellplot://authoring/schema/canonical.json` is generated directly from the
  Pydantic authoring models
- `wellplot://authoring/schema/operations.json` is generated from the typed
  authoring service request models
- `inspect_authoring_objects(...)` returns typed, parent-scoped object payloads
  for MCP clients
- `update_section(...)` and the canonical fields of `update_track(...)` and
  `update_curve_binding(...)` execute through `AuthoringService`
- `set_page_layout(...)`, `set_depth_axis(...)`, and the corresponding parts
  of `set_section_view(...)` execute through `AuthoringService`
- annotation create/update/remove, fill create/remove, core raster-binding
  create/update, and typed remarks replacement execute through
  `AuthoringService` when their fields are representable by the canonical
  contract
- legacy binding-level fills are normalized into track-level canonical fill
  relations and projected back without losing renderer-specific fill fields
- the legacy logfile mapping remains the persistence/render boundary, with a
  canonical validation gate on every persisted MCP mutation
- annotation geometry, label placement, typography, fill, border, marker, and
  arrow styling now have typed canonical object fields; legacy arrow `top` /
  `base` aliases normalize to canonical start/end geometry
- `inspect_authoring_vocab` and the patch-schema resource expose generated
  `canonical_patch_keys` from the typed service models; legacy patch-key lists
  remain as compatibility catalogs while renderer-only fields are migrated
- track grid properties now have typed canonical validation and partial-update
  merge semantics, with legacy nested grid aliases normalized at the adapter
  boundary and projected back for rendering
- track-header row reservations now have typed canonical validation and
  deterministic replacement semantics; renderer-only header styling remains
  outside this object contract
- reference-curve overlay properties now have typed canonical validation and
  binding-level update projection; value-label, callout, and raster display
  controls remain separate typed binding fields
- curve render mode, value-label formatting, wrapping, and header visibility
  now have typed canonical binding fields with nested partial-update merging
- raster normalization, clipping, interpolation, visibility, color limits,
  colorbars, sample axes, and waveform overlays now have typed canonical
  binding fields with nested partial-update merging
- reference-track axis/layout settings, major/minor spacing, secondary-grid
  visibility, header visibility, value formatting, orientation, and event
  markers now have typed canonical fields with nested partial-update merging;
  the adapter projects them back into the renderer's legacy reference envelope

### Slice 0.6-F. Defaults And Precedence

Goal:

- provide domain convenience without introducing hidden authority

Work:

- add asset-backed defaults catalogs for track, curve, raster, and header
  families
- apply defaults only to omitted fields
- enforce the precedence rule:
  1. explicit user instruction
  2. preserved existing state
  3. defaults catalogs
  4. starter/example scaffold
- demote packet blueprints to examples, starter scaffolds, or regression fixtures
- remove packet-specific reconciliation from general authoring paths

Implementation checkpoint:

- reusable track archetypes and style-family presets now load from the
  asset-backed `defaults/authoring_defaults.yaml` catalog rather than a
  hard-coded service tuple; the existing MCP inspection and preset APIs remain
  compatible
- default reconciliation fills only fields omitted by the persisted object;
  nested explicit values such as curve colors, scales, labels, and raster
  display settings are never overwritten by packet or family defaults
- packet blueprints are no longer inferred from freeform authoring text;
  `AuthoringSession.plan(..., blueprint_id=...)` exposes them only as explicit
  scaffold plans, while ordinary `run()` and `revise()` requests use the
  generic authoring path

Acceptance:

- explicit width, scale, color, line style, label, and raster settings survive
  defaults and scaffolds
- the same defaults mechanism works for CBL, caliper, porosity, resistivity, and
  other curve/raster families

### Slice 0.6-G. Agent Rebase And Release Acceptance

Goal:

- make generated intelligence a consumer of complete deterministic capability
- assemble broad user requests through typed desired state and dependency-ordered
  reconciliation

The current generic phase executor is necessary but not sufficient. It can
restrict tool families and verify persisted mutations, but it still allows a
provider to improvise the order of low-level edits. The missing product layer
is a generic assembly planner that works for CBL/VDL, open-hole, porosity,
resistivity, caliper, array, and custom multi-section reports.

Work:

- restrict the agent to intent classification, planning, tool selection, and
  reporting
- prohibit agent-side raw document repair and packet-specific hidden state
- verify each requested object outcome through canonical getters after writes
- preserve phase progress and blocked-phase reporting
- surface deterministic inconsistencies such as missing channels or invalid
  object references
- update canonical and stress-test notebooks

Implementation checkpoint:

- ordinary `run()` and `revise()` requests now produce generic phases for
  structure, bindings, content, styling, and final verification without
  selecting a packet blueprint
- each mutating generic phase requires a persisted diff from
  `summarize_logfile_changes`; an empty diff blocks the phase instead of
  silently consuming more provider rounds
- binding and fill outcomes are checked against persisted track bindings and
  `check_channel_availability`; missing or ambiguous source channels block the
  phase with a deterministic reason
- section, depth, page, annotation, and remark mutations are checked through
  `inspect_authoring_objects`; an empty or unrecognized mutation trace cannot
  satisfy the generic phase outcome check
- the shared phase executor is provider- and packet-neutral; packet assets are
  retained only for explicit scaffold plans and transitional regression tests

Acceptance:

- generic requests complete without a packet blueprint
- blocked requests identify the exact unsupported object, field, value, or
  contextual dependency
- phase reports correspond to persisted object state
- canonical LAS notebook and CBL stress-test notebook pass end to end
- full unit, MCP, agent, docs, and notebook smoke gates pass

### 0.6-G Completion Program: Desired-State Assembly

#### 0.6-G0. Contract And Domain Research

Research must produce reusable object rules, aliases, constraints, and test
fixtures rather than packet-specific templates.

The research output is recorded in the [cross-domain authoring contract
matrix](site/reference/domain-contract-matrix.md). It is the handoff contract
for `0.6-G1` and later slices, not a new packet blueprint.

- review representative open-hole, cased-hole, porosity, resistivity, caliper,
  image/array, and annotation logs
- identify universal header fields, units, aliases, track families, curve
  header conventions, scale semantics, raster semantics, and compatibility rules
- document which values are finite, constrained, contextual, relational, or
  explicitly extensible
- define the dependency graph between report, header, sections, tracks,
  bindings, fills, annotations, styles, and output settings
- use external domain or implementation research only to validate these
  reusable rules; do not encode each packet family as an authoritative blueprint

Acceptance:

- the rules apply to multiple log families without CBL-specific identifiers
- the research output is represented as canonical constraints, aliases, defaults,
  or fixtures

#### 0.6-G1. Complete The Canonical Report Contract

Status: the first-class report-contract foundation is implemented. The typed
authoring model now owns output settings, header slots, service titles, detail
rows/cells, provenance/availability metadata, and tail enablement; the
deterministic service exposes document-level getters and typed replacements.
Legacy YAML remains an adapter boundary and renderer behavior is covered by
round-trip tests.

Finish the persisted objects that are still only compatibility mappings or
renderer structures:

- first-class header structure and stable header-slot identities
- header labels, values, units, source keys, service titles, detail rows, and
  optional provenance
- tail/report blocks and remaining output settings that represent user intent
- deterministic getters and typed updates for header and report content

Existing header archetype assets remain layout scaffolds. They define available
slots and structure; they do not override explicit user values.

#### 0.6-G2. Typed Desired-State Models

Status: implemented as a provider-neutral Pydantic intent layer in
`wellplot.model.intent`. The layer composes the existing canonical authoring
models instead of defining a second vocabulary for scales, styles, bindings,
annotations, or raster profiles.

The intent layer covers partial changes for the report, header, page, depth,
output, tail, section, track, curve binding, raster binding, fill, annotation,
remark, and style/grid objects. Stable object identities and optional parent
scope are carried in the intent so later context resolution can report an
ambiguous target instead of guessing.

The models must distinguish:

- omitted values, which preserve existing state or permit defaults
- explicit values, which must be applied exactly
- explicit clear operations
- explicit object removal

The implementation uses the following rules:

- omitted fields remain absent in `model_fields_set` and therefore preserve
  existing state or permit a later default
- typed field values are explicit sets, including user-supplied colors, line
  styles, scales, and header values
- `{"operation": "clear"}` is the only explicit clear marker; raw `null` is
  rejected to prevent accidental data loss
- `{"operation": "remove", ...}` carries stable object identity and optional
  section/track scope for deletion
- curve and raster binding intents are explicitly discriminated by `kind`, so
  source-channel names cannot cause a raster binding to be treated as a curve

`AuthoringDocumentIntent` can be serialized through the generated
`authoring_intent_json_schema()` contract. The provider should return this
validated desired state instead of directly improvising a long sequence of MCP
mutations. G2 intentionally does not resolve aliases, apply defaults, compare
against a draft, or execute operations; those responsibilities begin in G3.

Acceptance completed:

- omitted, explicit, clear, and remove states are covered by focused tests
- raw null is rejected in favor of an explicit clear marker
- nested curve/raster binding intent is unambiguous and strictly validated
- the intent schema is generated from the Pydantic models

#### 0.6-G3. Context Resolution And Precedence

Status: implemented in `wellplot.authoring_context` as a provider-neutral
resolver. It accepts the current canonical document, optional scaffold,
selected defaults, inspected source-channel candidates, and alias catalogs as
explicit inputs. It returns a typed `AuthoringContextResolution`; it does not
load files, call MCP, or persist mutations.

Resolve contextual references before mutation planning:

- header field aliases and archetype slots
- source channels and channel aliases
- track/content compatibility
- stable binding identities, including duplicate same-channel bindings
- units, scales, styles, and raster presentation values

Use the precedence order: explicit user instruction, preserved existing state,
defaults catalog, starter scaffold.

The resolver records one decision per resolved field with its source and path,
so a future reconciler can apply only the selected values. It also returns
blocking issues rather than guessing when:

- a header alias matches no slot or more than one slot
- a requested source channel is unavailable or ambiguous
- a curve/raster binding does not match the inspected channel kind
- a binding identity is duplicated
- content is attached to an incompatible track kind

Header slots are normalized to stable canonical `slot_id` values. Channel
aliases are normalized to one inspected source mnemonic only when exactly one
candidate matches. Duplicate source channels remain valid when their binding
IDs are distinct. The resolver also preserves explicit nested styles, scales,
units, labels, and raster settings through the same precedence decisions.

Acceptance completed:

- explicit values override existing values, defaults, and scaffolds
- existing values override defaults, and defaults override scaffolds
- header and channel aliases resolve without inventing slots or channels
- missing/ambiguous channels and incompatible content produce blocking issues
- duplicate same-channel bindings are accepted when their identities differ
- defaulted track kinds participate in compatibility checks

G3 intentionally does not compare a complete document against desired state or
produce executable operations; those responsibilities begin in G4.

#### 0.6-G4. Generic Desired-State Reconciler

Status: implemented in `wellplot.authoring_reconciler` as a provider-neutral,
execution-free desired-state reconciler. It accepts either a raw
`AuthoringDocumentIntent` plus explicit context or an already-resolved
`AuthoringContextResolution`, and returns an `AuthoringReconciliationPlan`.

The plan contains typed operations with stable identities, object scope,
payloads, dependencies, and one of the ordered phases `report`, `sections`,
`tracks`, `bindings`, `content`, `presentation`, or `finalize`. It compares
only requested or non-preserved resolved values, so replaying the same intent
does not emit redundant mutations.

The reconciler covers:

- report title/subtitle, output, page, depth, tail, and header metadata
- stable general/service/detail header slots
- arbitrary section IDs and arbitrary numbers of sections
- track creation/update, widths, ordering, scales, grids, and headers
- duplicate same-channel curve instances using distinct binding IDs
- scalar and raster binding creation plus presentation updates
- fills, typed annotations, remarks, ordering, and explicit removals

It intentionally reports blocking issues instead of guessing when an existing
track kind or binding source channel would need to change in place. Those
objects have immutable identity/compatibility boundaries in the current
deterministic service; replacement or an explicit follow-up operation is safer
than silently removing and recreating user content.

The plan must establish dependencies in this order:

1. report/header/output objects
2. sections and section data sources
3. tracks, kinds, widths, and ordering
4. curve and raster bindings
5. fills and annotations
6. scales, labels, colors, line styles, and other presentation fields
7. final ordering, explicit removals, validation, and preview

The operation plan must be idempotent. Main/repeat replication may be an
optimization, but arbitrary section IDs and arbitrary numbers of sections must
remain valid.

Acceptance completed:

- matching explicit values produce no operations
- structural track operations precede binding operations
- content operations follow binding creation
- presentation operations follow structure/content phases
- ordering and explicit removals are final-phase operations
- duplicate same-channel bindings remain distinct by binding ID
- unsupported track-kind and binding-channel changes produce exact blocking
  issues rather than improvised compensating mutations

G4 intentionally does not execute operations or render previews; those
responsibilities begin in G5.

#### 0.6-G5. Deterministic Executor And Checkpoints

Status: implemented in `wellplot.authoring_executor` as a deterministic
executor bound to one `AuthoringService` instance. The service now also owns a
typed report title/subtitle patch so report-level G4 operations do not bypass
the canonical mutation boundary.

The executor:

- check preconditions
- apply atomically
- read the canonical object back
- verify the exact postcondition
- stop on failure without improvising compensating removals
- expose phase summaries and previews from persisted state

`AuthoringExecutionResult` records each operation outcome, the first blocking
error, the final canonical document, and `AuthoringPhaseCheckpoint` snapshots.
Callers may provide a preview callback receiving the persisted document and
phase; its returned PNG is stored on that checkpoint. Preview failures are
reported as warnings and never masquerade as a successful mutation.

Creation, updates, replacements, moves, and explicit removals are translated
to the existing typed `AuthoringService` requests. Partial output, tail,
header, fill, and annotation operations are merged into validated canonical
objects before service execution. Service validation remains the atomic
rollback boundary for each operation.

Acceptance completed:

- valid plans execute in dependency order and capture read-after-write success
- unknown or later dependencies fail before any mutation
- failed typed mutations stop later phases and preserve the last valid service
  snapshot
- arbitrary new sections can be created with their tracks before bindings
- duplicate same-channel bindings execute as distinct binding IDs
- phase checkpoints expose persisted canonical snapshots and optional previews

Track creation must complete before bindings; bindings must exist before fills;
move operations must happen after all required siblings exist; removal must be
explicit and last.

#### 0.6-G6. Agent Integration

Status: deterministic foundation implemented; live natural-language integration
remains incomplete. `AuthoringSession.plan()` now accepts an
`AuthoringDocumentIntent`, resolves it against an existing canonical document,
and exposes the resulting `AuthoringReconciliationPlan` as a dry run.

OpenAI and OpenAI-compatible backends now advertise typed-state support. Their
normal authoring path submits exactly one validated `AuthoringDocumentIntent`
through a provider-local contract; the provider does not receive mutation tools
in this stage. The agent then uses the same flow:

1. inspect the current document and sources
2. extract typed desired state
3. validate and resolve references/defaults
4. generate a dry-run operation plan
5. execute and verify the plan
6. report completed, blocked, unsupported, and inconsistent requests

The canonical document is persisted only after deterministic execution succeeds,
through the validated MCP `save_authoring_document` adapter. Failed resolution, execution, or
persistence leaves the draft unchanged and is surfaced in the structured user
report. Phase summaries are derived from executor checkpoints rather than from
provider claims.

Narrow deterministic shortcuts for header-only and style-only requests remain
available and retain their existing verification path; migrating those shortcuts
to typed intents is a follow-up hardening task before the final release gate.

Backends without typed-state support retain the legacy provider loop for
compatibility during the transition. They are not the release-default path.

Foundation acceptance completed:

- typed `plan()` returns ordered desired-state phases and deterministic operations
- caller-supplied typed state bypasses provider mutation loops
- capable providers receive only the intent-submission contract
- canonical resolution, reconciliation, execution, read-back verification, and
  persistence are ordered and fail-stop
- typed phase summaries and deterministic next-help reporting are exposed through
  the existing `AuthoringResult`

The live integration gate is reopened because the agent currently supplies the
reconciler with only existing-section channel names. It does not yet build a
complete context snapshot for newly referenced sources and sections, does not
wire the asset-backed generic defaults into desired-state planning, and asks the
provider for one large intent without a bounded correction pass. These gaps can
make an explicit request fail before deterministic assembly starts.

#### 0.6-G7. Cross-Domain Acceptance

Status: canonical deterministic acceptance implemented; provider-to-intent and
live notebook acceptance remain incomplete. The current provider-free matrix in
`tests/test_cross_domain_acceptance.py`. The fixtures compose the canonical
objects directly rather than using a packet blueprint, so the CBL/VDL case is
only one domain in the test surface.

The acceptance matrix covers:

- open-hole quicklook headers
- resistivity with logarithmic tracks
- porosity overlays and crossover fills
- mirrored caliper curves using one source channel twice
- CBL/VDL scalar and raster tracks
- annotation and mixed interpretation tracks
- one-section, main/repeat, and arbitrary multi-section reports
- missing channels, partial header data, and unsupported request fields
- explicit colors, line styles, labels, and scales overriding defaults

The canonical LAS notebook and experimental CBL notebook also have a
credential-free structural gate. The gate verifies that the notebooks remain
discoverable and use the public agent/session reporting flow; live provider
execution remains a manual acceptance step because it requires credentials and
source files.

The acceptance pass also closed a generic canonical-to-render adapter defect:
unset optional depth steps are now omitted before the legacy renderer schema is
called, rather than serialized as `null` and passed to `float()`.

The CBL notebook remains a stress test and regression fixture, not the source of
implementation rules. Its live run must still prove that the generic agent can
compile a request into the same canonical objects covered by this matrix.

### Corrective Integration Slices

These slices complete the reopened G6/G7 integration gate. They are intentionally
generic and apply to CBL/VDL, open-hole, porosity, resistivity, caliper, array,
annotation, and custom multi-section reports.

#### 0.6-G6R. Reopen Integration Acceptance

Record the distinction between the completed deterministic foundation and the
unfinished live-agent path. Keep packet blueprints out of ordinary planning and
define the natural-language notebook gates as release requirements.

#### 0.6-G6.1. Deterministic Context Snapshot

Build a typed, read-only context snapshot before intent extraction. It must include
the current canonical object inventory, header slots and aliases, every source
referenced by the request, source format, and channel candidates with mnemonic,
kind, unit, and source path. Missing or ambiguous context must be reported before
mutation.

#### 0.6-G6.2. Typed Request Compilation

Compile the request into a compact manifest and then a typed desired state using
the context snapshot. Return request-item coverage so every explicit instruction
maps to an intent path or an explicit unsupported/inconsistent result. Permit one
bounded correction pass for missing intent fields; do not expose mutation tools to
the provider.

#### 0.6-G6.3. Generic Defaults Resolution

Validate the asset-backed defaults catalog against canonical property names and
resolve defaults by object kind and channel family. Apply the precedence rule
`explicit request > preserved existing value > unambiguous generic default >
starter scaffold`. Packet blueprints remain opt-in scaffolds or fixtures and never
become implicit runtime authority.

#### 0.6-G6.4. Dependency-Ordered Assembly

Generate the deterministic assembly sequence:
`report/header -> sections and sources -> tracks -> curve/raster bindings ->
fills/annotations -> presentation/order -> validation`.

Support arbitrary sections, duplicate same-channel bindings, array tracks, and
custom combinations without packet-specific reconciliation rules.

#### 0.6-G6.5. Checkpoints and Persistence

Verify every phase against canonical getters, expose phase previews before the
final preview, and persist only after all phases pass. Convert transport failures
into structured blocked results and allow one safe idempotent save retry after
local serialization and validation.

#### 0.6-G7.1. Real Agent Acceptance

Status: recorded provider-to-intent acceptance implemented; live-provider execution
remains an optional credentialed gate.

`tests/test_cross_domain_acceptance.py` now replays provider submissions through
the real `submit_authoring_intent` contract and then runs the submitted state
through context resolution, planning, dependency-ordered reconciliation, and
read-after-write execution. The acceptance cases cover CBL/VDL, mirrored
caliper, porosity, logarithmic resistivity, open-hole header slots, annotations,
arrays, and arbitrary multi-section reports. They verify that explicit widths,
scales, colors, line styles, labels, raster settings, page layout, and header
values survive the provider boundary and override existing/default values.

Credentialed live-provider runs remain a manual release-gate activity; they must
exercise the same cases without granting the provider mutation tools.

#### 0.6-G7.2. Notebook and Release Gate

Update the notebooks to show context resolution, request coverage, defaults
provenance, operation plans, phase verification, and blocked reasons. A blocked
assembly must stop before rendering a partial draft. Release requires the unit,
MCP, agent, documentation, and notebook gates to pass.

Status: complete. The public notebook display helper now exposes these fields
from `AuthoringResult`, both user notebooks request phase previews, and the
structural acceptance test keeps the examples credential-free in CI.

## Release Gate

Do not publish `0.6.0` until the repository release gates below pass. Slices
`0.6-A` through `0.6-G7.2` are now the completed contract baseline.

Release-gate checklist:

- unit, MCP, agent, and cross-domain acceptance tests pass
- strict documentation build passes
- package and installed-wheel smoke checks pass
- canonical LAS notebook and experimental CBL notebook remain structurally
  discoverable and request per-phase previews
- credentialed live-provider acceptance is recorded manually when available

Provider expansion, remote MCP transport, persistent/vector memory, and new
packet-specific blueprints remain deferred. They do not block this contract
program.

## Test Strategy

Required new test groups:

- generated-schema snapshots and validation parity
- legacy YAML compatibility and canonical round trips
- object CRUD matrix and atomic rollback
- parent/child compatibility and contextual reference failures
- Python API/MCP schema parity
- defaults precedence and explicit-value preservation
- generic agent scenarios not backed by packet-specific assets
- installed-wheel and MCP stdio integration

The current behavioral tests remain regression protection. They do not replace
the new cross-layer parity tests.

## Expected Code Surface

Likely new or changed areas:

- new canonical authoring models under `src/wellplot/model/` or a dedicated
  `src/wellplot/authoring/` package
- `src/wellplot/logfile_schema.py`
- `src/wellplot/logfile.py`
- `src/wellplot/templates.py`
- `src/wellplot/api/builder.py`
- `src/wellplot/mcp/service.py`
- `src/wellplot/mcp/server.py`
- `src/wellplot/agent/core.py`
- packet/default assets and their loaders
- model, schema, API, MCP, agent, and compatibility tests

The exact package location for canonical models should be chosen in Slice
`0.6-A`; the architectural ownership and acceptance criteria are fixed here.
