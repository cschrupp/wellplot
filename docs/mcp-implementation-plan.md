# MCP Implementation Plan

Last updated: 2026-08-06

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

Add provider-neutral partial intent models for report, header, section, track,
curve binding, raster binding, fill, annotation, and output changes.

The models must distinguish:

- omitted values, which preserve existing state or permit defaults
- explicit values, which must be applied exactly
- explicit clear operations
- explicit object removal

The provider should return this validated desired state instead of directly
improvising a long sequence of MCP mutations.

#### 0.6-G3. Context Resolution And Precedence

Resolve contextual references before mutation planning:

- header field aliases and archetype slots
- source channels and channel aliases
- track/content compatibility
- stable binding identities, including duplicate same-channel bindings
- units, scales, styles, and raster presentation values

Use the precedence order: explicit user instruction, preserved existing state,
defaults catalog, starter scaffold.

#### 0.6-G4. Generic Desired-State Reconciler

Implement a deterministic reconciler that compares the current canonical
document with the desired partial state and returns a typed operation plan.

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

#### 0.6-G5. Deterministic Executor And Checkpoints

Execute each typed operation through `AuthoringService`:

- check preconditions
- apply atomically
- read the canonical object back
- verify the exact postcondition
- stop on failure without improvising compensating removals
- expose phase summaries and previews from persisted state

Track creation must complete before bindings; bindings must exist before fills;
move operations must happen after all required siblings exist; removal must be
explicit and last.

#### 0.6-G6. Agent Integration

Update `AuthoringSession.plan()`, `run()`, and `revise()` to use the same flow:

1. inspect the current document and sources
2. extract typed desired state
3. validate and resolve references/defaults
4. generate a dry-run operation plan
5. execute and verify the plan
6. report completed, blocked, unsupported, and inconsistent requests

Keep narrow deterministic shortcuts for header-only and style-only requests,
but make them use the same canonical intent and verification contracts.

#### 0.6-G7. Cross-Domain Acceptance

Add acceptance fixtures for:

- open-hole quicklook headers
- resistivity with logarithmic tracks
- porosity overlays and crossover fills
- mirrored caliper curves using one source channel twice
- CBL/VDL scalar and raster tracks
- annotation and mixed interpretation tracks
- one-section, main/repeat, and arbitrary multi-section reports
- missing channels, partial header data, and unsupported request fields
- explicit colors, line styles, labels, and scales overriding defaults

The CBL notebook remains a stress test and regression fixture, not the source of
implementation rules.

## Release Gate

Do not publish `0.6.0` until slices `0.6-A` through `0.6-G` are complete.

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
