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
- advanced grid/header/overlay fields and renderer-only annotation/raster
  fields remain compatibility-path fields until their canonical models and
  service operations are added
- `inspect_authoring_vocab` and the patch-schema resource expose generated
  `canonical_patch_keys` from the typed service models; legacy patch-key lists
  remain as compatibility catalogs while renderer-only fields are migrated
- track grid properties now have typed canonical validation and partial-update
  merge semantics, with legacy nested grid aliases normalized at the adapter
  boundary and projected back for rendering

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

Acceptance:

- explicit width, scale, color, line style, label, and raster settings survive
  defaults and scaffolds
- the same defaults mechanism works for CBL, caliper, porosity, resistivity, and
  other curve/raster families

### Slice 0.6-G. Agent Rebase And Release Acceptance

Goal:

- make generated intelligence a consumer of complete deterministic capability

Work:

- restrict the agent to intent classification, planning, tool selection, and
  reporting
- prohibit agent-side raw document repair and packet-specific hidden state
- verify each requested object outcome through canonical getters after writes
- preserve phase progress and blocked-phase reporting
- surface deterministic inconsistencies such as missing channels or invalid
  object references
- update canonical and stress-test notebooks

Acceptance:

- generic requests complete without a packet blueprint
- blocked requests identify the exact unsupported object, field, value, or
  contextual dependency
- phase reports correspond to persisted object state
- canonical LAS notebook and CBL stress-test notebook pass end to end
- full unit, MCP, agent, docs, and notebook smoke gates pass

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
