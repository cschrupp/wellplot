# MCP Implementation Plan

Last updated: 2026-08-10

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
- open-world object construction that does not require a catalogued scientific
  family or internal schema knowledge

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
- generic track-form defaults are asset-backed and can complete uncatalogued
  normal, reference, array, and annotation tracks
- optional family matching uses partial evidence and reports unmatched channel
  mnemonics without blocking generic construction
- defaulted fields expose source-level provenance and specific style presets
  override broader family archetypes
- blocked typed plans expose exact missing properties, defaults warnings, and
  domain-language next help
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
the compact inventory and scoped typed-intent contracts, merges the validated
fragments, and then runs the canonical submitted state through context
resolution, planning, dependency-ordered reconciliation, and read-after-write
execution. The acceptance cases cover CBL/VDL, mirrored
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

## Reopened 0.6-H: User-Facing Header Resolution

The canonical header keys introduced by the deterministic contract are internal
identities. They must not become a prerequisite for scientists using the agent.
Users should be able to write `Rm measured`, `RM at bottom temperature`, or the
visible field label and receive deterministic placement or a human-readable
clarification when the request is ambiguous.

The header workflow is:

1. inspect the current heading and its available semantic fields
2. resolve the user phrase against visible labels, asset-backed aliases, and
   qualifiers
3. apply a value only when the resolver has one valid target
4. ask for clarification when multiple targets remain
5. report unmatched values in domain language, without requiring internal keys

Canonical keys remain accepted for programmatic API callers and diagnostics.
They are not the primary agent prompt contract.

### 0.6-H1. Asset-Backed Header Language Metadata

Status: complete.

- retain stable canonical keys for persistence and object identity
- add optional user-facing aliases to header archetype detail fields
- carry aliases through schema validation, typed authoring models, legacy
  adapters, and canonical YAML serialization
- remove string-derived semantic aliases from the service; domain wording must
  come from data assets or stable visible labels
- preserve label-based fallback for older third-party templates without aliases

Acceptance:

- `Rm measured` resolves to the field labeled `RM @ Measured Temp`
- `Rm bottom` resolves to `RM @ Bottom Temp`
- the same mechanism is available to other header fields without RM-specific
  service code

### 0.6-H2. Generic Deterministic Field Resolver

Status: complete.

- rank exact labels, configured aliases, normalized wording, and qualifiers
- resolve only against fields present in the current heading
- never guess when two candidates remain equally valid
- keep explicit canonical-key matching available only as an advanced path

Implementation checkpoint:

- header targets retain their canonical key, visible label, and asset-backed
  aliases as separate match metadata
- exact configured aliases and labels are ranked before conservative
  qualifier-aware phrase matching
- natural phrases such as `RM measured temperature` resolve without exposing
  internal keys, while unqualified `RM` remains blocked when both RM slots
  are present
- intentionally mirrored general/detail mappings, such as `Date`, retain
  their existing multi-target behavior

Acceptance completed:

- qualified user phrases resolve to one current heading slot
- duplicate labels and unqualified qualifiers remain conflicts
- canonical and `detail.<key>` paths continue to work for advanced callers
- older templates without canonical keys retain label-based matching

### 0.6-H3. Human-Readable Ambiguity Contract

Status: complete.

- return candidate display labels with mapping conflicts
- replace generic instructions to provide prefixed keys with a clarification
  question containing the actual header labels
- allow unambiguous values in the same request to be applied while one value is
  held for clarification

Implementation checkpoint:

- ambiguous mappings include `candidate_labels`, `clarification_question`, and
  candidate target metadata with each visible `display_label`
- duplicate visible labels receive deterministic scope qualifiers such as
  `(general field)` and `(detail field)` in the clarification choices
- `apply_header_values(...)` persists unambiguous assignments from the same
  request and reports the ambiguous values as skipped conflicts

Acceptance completed:

- ambiguous RM/service-company phrases ask a human-readable question
- visible candidate labels distinguish duplicate labels where possible
- a conflict does not discard unrelated successful assignments

### 0.6-H4. Agent Reporting and Clarification

Status: complete.

- report completed fields using visible labels, not canonical IDs
- add structured `needs_clarification` data to the authoring result
- show the original value and the human-readable candidate choices

Implementation checkpoint:

- `AuthoringResult.needs_clarification` preserves the original input key and
  value, clarification question, candidate labels, and target metadata
- `AuthoringUserReport` renders a concise `Needs clarification` section while
  retaining the structured entries for notebook and UI integrations
- deterministic header assignments prefer `display_label` over canonical
  `target_key` in user-facing completion and skip messages

Acceptance completed:

- completed header fields are reported with visible labels
- ambiguous values are exposed as structured clarification entries
- notebook display includes the clarification question without requiring users
  to inspect canonical keys

### 0.6-H5. Clarification Continuation

Status: complete.

- keep pending clarification state in the agent/session run state only
- accept follow-ups such as `the measured one` or `use bottom temperature`
- revalidate the selected field against the current draft before applying it

Implementation checkpoint:

- `AuthoringSession` stores pending header choices only for the lifetime of the
  in-memory session and clears them when a new run overwrites the draft
- a revision follow-up is resolved against visible candidate labels and
  qualifiers, then converted to a scoped canonical mapping key internally
- the selected key is previewed against the current heading before the original
  value is applied; stale or unavailable targets fail closed
- a focused agent regression test verifies that the follow-up bypasses the
  provider loop and persists the selected value

Acceptance completed:

- `Use the measured one.` applies the pending `RM` value to `RM @ Measured Temp`
- a pending choice is not persisted in the MCP server or across authoring
  sessions
- the final report clears `needs_clarification` after successful continuation

### 0.6-H6. Notebook and Documentation Acceptance

Status: complete.

- update the notebook to use natural header language
- verify unique phrases, ambiguous phrases, and follow-up clarification
- keep canonical keys in advanced API documentation only
- run MCP, agent, model, notebook, and documentation gates before closing H

Implementation checkpoint:

- the canonical LAS walkthrough uses qualified phrases such as `Rmf measured`
  and `Rmc measured` without exposing internal mapping keys
- the walkthrough includes an intentionally ambiguous `RM` request and displays
  the structured clarification result before replying with `Use the measured
  one.` when clarification is requested
- the structural notebook gate checks the natural-language examples and rejects
  internal `detail.*` keys in the user notebook source
- the API reference retains canonical keys only for programmatic callers and
  diagnostics

Acceptance completed:

- notebook source remains credential-free and JSON-valid
- unique, ambiguous, and follow-up clarification paths are represented in the
  canonical notebook
- agent, MCP, cross-domain, and documentation validation gates pass

## Reopened 0.6-I: Open-World Object Construction

The desired-state workflow can now normalize equivalent nested and root-level
binding references, but notebook testing exposed a deeper defaults boundary.
A natural request for a resistivity track produced one track operation and
three valid binding operations, then blocked because the new track lacked
required form fields. The defaults catalog already contained a resistivity
title, normal-track kind, width, logarithmic scale, and presentation styles,
but the family matcher rejected the whole family because `MSFL` was not listed
as a shallow-resistivity mnemonic.

That behavior is not only a missing alias. It makes structural object creation
depend on complete scientific-family recognition, which is incompatible with
the product mission. Users must be able to create custom tracks and bind
inspected source channels even when no packaged family knows their terminology.

The governing invariant for this program is:

> Generic canonical object construction must succeed independently of optional
> scientific-family defaults. Family recognition may enrich presentation, but
> it must not define which valid objects users are allowed to create.

Track form and scale vocabularies must also remain distinct:

- track form kinds: `normal`, `reference`, `array`, `annotation`
- scale kinds: `linear`, `log`, `tangential`

A resistivity track is ordinarily a `normal` track with a `log` X-scale. The
same normal-track form must remain available to arbitrary scalar channels that
have no scientific-family entry.

Implementation policy:

- complete and commit each slice separately
- keep packet blueprints out of normal request resolution
- keep scientific mnemonic additions asset-backed
- do not add request-specific branches to the agent or reconciler
- preserve explicit user values ahead of every default source

### 0.6-I1. Generic Form Completion

Status: implemented in the current development branch.

Goal:

- make every supported track form constructible without selecting a scientific
  family

Work:

- add asset-backed generic form defaults for `normal`, `reference`, `array`, and
  `annotation` tracks
- derive a user-facing title from the requested object name or humanized stable
  track id when title is omitted from the typed provider submission
- resolve form kind from explicit wording and compatible child content:
  - explicit depth/reference intent selects `reference`
  - raster content selects `array`
  - annotation content selects `annotation`
  - otherwise requested scalar-curve content selects `normal`
- supply a conservative width default by form kind when neither the user nor
  existing state supplies one
- carry explicit X-scale, grid, style, label, and ordering instructions through
  generic completion without requiring a family match

Acceptance:

- a custom scalar track with an arbitrary inspected channel can be created with
  no family catalog entry
- a custom raster track and annotation track receive compatible form defaults
- omitted structural fields are completed without exposing internal property
  names to the user
- explicit form kind, width, title, and presentation fields are never replaced

Implementation checkpoint:

- generic form defaults are stored in `authoring_defaults.yaml`
- form inference covers explicit kind, raster children, annotation children,
  depth/reference naming, and scalar fallback
- nested and scoped root-level child declarations are considered during form
  inference
- focused defaults, context, and reconciler tests pass

### 0.6-I2. Optional Family Matching And Catalog Corrections

Status: implemented in the current development branch.

Goal:

- make scientific-family defaults an optional evidence-based overlay

Work:

- add `MSFL` to the asset-backed shallow-resistivity channel family as a domain
  catalog correction
- replace the all-channels-must-be-known family gate with deterministic evidence
  scoring
- treat unknown channel mnemonics as neutral when object identity and known
  channels strongly identify one family
- reject a family when inspected channels provide known contradictory evidence
- keep equal-scoring or otherwise ambiguous family matches unresolved
- allow generic construction to continue when no family is selected
- report unmatched channel mnemonics in defaults provenance instead of dropping
  every structural default

Acceptance:

- `ILD`, `ILM`, and `MSFL` select the resistivity conventions
- a resistivity-like track containing one new vendor mnemonic retains generic
  construction and reports the unmatched mnemonic
- recognized porosity channels do not silently receive resistivity conventions
- a track with no family match remains valid when its canonical form and content
  are compatible

Implementation checkpoint:

- `MSFL` is included in the asset-backed shallow-resistivity catalog
- family candidates use known channel overlap, track identity, and form kind
  evidence instead of an all-channels-known gate
- known channel evidence that belongs to another family rejects the conflicting
  candidate, while unknown mnemonics remain neutral
- unmatched channel mnemonics are retained in defaults provenance
- scoped root-level bindings participate in family selection
- focused defaults, context, and reconciler tests pass

### 0.6-I3. Defaults Precedence And Provenance

Status: implemented in the current development branch.

Goal:

- make every completed value explainable and preserve the most specific valid
  authority

Work:

- enforce the refined precedence order:
  1. explicit user instruction
  2. explicit preservation of existing state
  3. selected specific family or style preset
  4. selected family archetype
  5. generic form defaults
  6. starter scaffolds and examples
- correct internal family-patch ordering so a specific preset cannot be
  overwritten by its more general archetype
- record field-level provenance for inferred title, form kind, width, scale,
  grid, binding style, and family classification
- keep packet assets outside the defaults authority chain unless the caller
  explicitly selects one as a starter scaffold

Acceptance:

- an explicit width, color, line style, label, or scale survives every selected
  default family
- specific triple-combo presentation values win over generic normal-track
  values when both are applicable
- generic form provenance remains visible when no family is selected
- repeated reconciliation is idempotent

Implementation checkpoint:

- generic form, family archetype, style preset, and binding-template defaults
  record field-level provenance
- style preset patches are applied after archetype patches so specific values
  such as width, scale, grid, and binding style are retained
- the existing family/provenance metadata remains compatible, while agent plan
  results also expose field-level default sources
- explicit typed values continue to win through contextual resolution
- focused defaults, context, reconciler, and full-suite tests pass

### 0.6-I4. Actionable Creation Diagnostics

Status: implemented in the current development branch.

Goal:

- report the actual resolution failure instead of only the final schema symptom

Work:

- calculate the exact required fields still unresolved after generic and family
  defaults have run
- replace `Creating a track requires title, kind, and width_mm` with a message
  that names only the fields actually missing for the identified track
- include defaults-selection diagnostics such as unmatched channels,
  contradictory evidence, or an ambiguous family tie
- distinguish track form kind from X-scale kind in user-facing reports
- recommend user clarification only when the missing information cannot be
  resolved from the request, inspected source, existing state, or generic form
  defaults
- never ask a notebook user to provide canonical keys solely to compensate for
  an internal resolution failure

Acceptance:

- a blocked report identifies the exact object, missing field, and failed
  resolution source
- an unknown family convention is reported as a warning when generic
  construction can continue
- genuine ambiguity produces concrete choices in domain language
- the final `Next help` recommendation describes a user decision rather than an
  internal schema repair

Implementation checkpoint:

- track creation blockers identify only the unresolved display title, track form,
  or track width
- plan warnings are exposed separately from blocking reasons and flow into
  typed user reports
- unmatched-channel and ambiguous-default diagnostics are retained in the
  report path
- next-help text distinguishes track form (`normal`, `reference`, `array`, or
  `annotation`) from X-scale (`linear`, `log`, or `tangential`)
- notebook display shows plan warnings without labeling them as blockers
- focused diagnostic, agent, and full-suite tests pass

### 0.6-I5. Cross-Domain Open-World Acceptance

Status: implemented in the current development branch.

Goal:

- prove that the workflow is not fitted to the current resistivity notebook

Required scenarios:

- the existing LAS request creates a resistivity track after depth, binds
  `ILD`, `ILM`, and `MSFL`, applies logarithmic `0.2` to `2000` scales, and keeps
  the deepest curve visually strongest
- an uncatalogued custom scalar track is created from arbitrary available
  channels
- a porosity overlay uses explicit user scales and optional family conventions
- a CBL scalar track and VDL raster track are constructed from canonical
  objects without selecting a packet blueprint
- an array track and annotation track receive compatible generic form defaults
- duplicate same-channel bindings remain supported only through distinct stable
  binding ids
- known incompatible content, unavailable source channels, and genuinely
  ambiguous family matches still fail closed

Acceptance:

- all scenarios compile to the same provider-neutral intent and canonical
  reconciliation path
- no scenario requires a request-specific branch or authoritative packet asset
- explicit user presentation values remain unchanged
- deterministic read-back verifies the created object graph and phase outcomes

Implementation checkpoint:

- a minimal depth-only report can receive a new resistivity track with generic
  form completion, `ILD`/`ILM`/`MSFL` bindings, log scale `0.2` to `2000`, and
  strongest styling on the deepest curve
- uncatalogued scalar, array/raster, annotation, and CBL duplicate-binding
  objects execute through the same typed plan and read back successfully
- CBL/VDL construction does not select a packet blueprint; ambiguous CBL style
  conventions remain warnings or blockers unless the user supplies the intended
  presentation
- missing source channels, incompatible binding content, and unresolved track
  forms fail closed with the corresponding user-facing issue
- compatibility validation defers when the parent form is unresolved, allowing
  reconciliation to report missing track form fields instead of a misleading
  child-content incompatibility
- focused open-world, context, defaults, cross-domain, and agent tests pass

### 0.6-I6. Notebook, Documentation, And Release Acceptance

Status: reopened; provider-boundary acceptance is still required.

Work:

- rerun the canonical LAS notebook from a clean draft using the existing
  natural-language resistivity request unchanged
- document generic form completion, optional family overlays, provenance, and
  form-kind versus scale-kind vocabulary
- update troubleshooting guidance with actionable defaults diagnostics
- add structural notebook checks that reject internal-field requirements in
  user prompts
- run targeted defaults, resolver, reconciler, agent, MCP, and notebook tests
- run the full test suite, Ruff, strict documentation build, and installed-wheel
  smoke checks
- record the provider-submitted typed intent, contextual resolution decisions,
  applied defaults, and final operation payloads for the exact notebook request

Acceptance:

- the user does not need to provide `kind`, `width_mm`, stable ids, or other
  internal fields for an ordinary track-creation request
- the unchanged resistivity notebook request completes and reports selected
  generic/family provenance
- the unchanged resistivity notebook request is submitted by the provider,
  resolved, reconciled, executed, and read back with the expected track width,
  form, scale, ordering, bindings, and style strengths
- an uncatalogued custom-track acceptance case also completes
- documentation presents family defaults as optional enrichment rather than an
  object-construction authority

Implementation checkpoint:

- canonical and experimental notebook prompt blocks are structurally checked
  for user-facing language and reject internal desired-state field names
- the canonical LAS guide explains generic form completion, optional family
  enrichment, field-level provenance, and form-kind versus X-scale vocabulary
- MCP workflow troubleshooting explains unmatched-channel warnings,
  fail-closed incompatibilities, ambiguous conventions, and phase checkpoints
- package version, changelog, full test suite, strict docs build, and installed
  wheel smoke checks pass
- provider extraction and deterministic reconciliation are covered together;
  static prompt inspection alone is not a release acceptance test

## Reopened 0.6-J: Provider Compiler Stabilization

Live execution of the canonical LAS notebook confirmed that the deterministic
object service, defaults resolver, reconciler, and executor are not the current
blocking layer. The source contains `SP`, `ILD`, `ILM`, and `MSFL`; the generic
defaults and deterministic acceptance tests can construct the requested
objects. The live provider nevertheless returned without submitting a valid
typed intent, so neither request reached reconciliation or MCP mutation.

The current extraction boundary presents only one tool, but that tool contains
the complete authoring intent graph. Its generated schema has 58 definitions
and is also repeated as pretty-printed text in the provider message. This makes
a narrow track or binding request carry the report, page, header, annotation,
raster, fill, and every other authoring contract at once. The resulting failure
is currently collapsed into a generic instruction to provide more internal
fields, even when the user's request is already sufficient.

This is provider-compiler complexity, not evidence that more MCP mutation tools
are needed. The governing invariants for this program are:

> Natural language is compiled through small typed contracts, while the full
> canonical document remains the deterministic validation and persistence
> authority.

> A provider failure must be observable before it is interpreted as a missing
> user instruction or unsupported MCP capability.

Implementation policy:

- do not add MCP verbs, packet blueprints, or scientific-family branches to
  make the SP or resistivity examples pass
- keep the canonical Pydantic models and deterministic execution pipeline as
  the final authority
- reduce only the provider-facing compilation surface; do not weaken canonical
  validation or permit arbitrary provider dictionaries
- preserve one bounded correction attempt for invalid typed submissions
- treat SP and resistivity as representative acceptance fixtures alongside
  uncatalogued and non-curve objects
- complete and commit each slice separately

### 0.6-J1. Extraction Observability And Failure Contract

Status: implemented in the current development branch.

Goal:

- expose what happened at the provider boundary without leaking credentials or
  requiring debug logging

Work:

- retain provider finish reason, whether a tool call was emitted, submitted
  tool name, argument-decoding failures, Pydantic validation failures, coverage
  failures, and the bounded correction outcome
- preserve a short sanitized provider text response when no tool call is made
- distinguish `no_tool_call`, `invalid_json`, `schema_validation_failed`,
  `coverage_failed`, `round_budget_exhausted`, and transport failures
- stop replacing these diagnostics with the generic recommendation to provide
  canonical object fields
- expose the diagnostics through structured `AuthoringResult` report facts and
  concise notebook output

Acceptance:

- a no-tool response reports that exact condition and a provider-facing next
  action
- an invalid submission reports stable canonical validation paths without
  exposing request credentials or entire prompts
- a valid submission retains the existing concise user report
- extraction failure never claims that MCP mutation failed when MCP was not
  called

Implementation checkpoint:

- provider adapters expose normalized response metadata for finish/status,
  round count, and emitted tool calls
- desired-state extraction records submission status, validation failures,
  coverage failures, sanitized provider text, and provider exceptions
- round exhaustion, malformed JSON, transport failure, prose-only responses,
  and rejected typed submissions produce distinct report facts
- the final user report preserves extraction diagnostics and no longer asks the
  user to provide internal object fields when MCP was never called
- focused compilation, adapter, and full-suite tests pass

### 0.6-J2. Compact Request Inventory And Contract Budget

Status: implemented in the current development branch; scoped typed-intent
routing remains the follow-up `0.6-J3` slice.

Goal:

- establish a small, measurable first compilation stage

Work:

- replace the full-intent first submission with a compact request inventory
  containing requested action, object family, target identity or description,
  parent scope, explicit values, and coverage status
- support the canonical object families: report/header, section, track, curve
  binding, raster binding, fill, annotation, page/output/depth, and remarks
- keep natural user descriptions when stable ids are not known; contextual
  resolution remains deterministic
- remove the pretty-printed full JSON Schema from the provider message because
  the tool schema already carries its contract
- record provider-message and tool-schema size budgets in tests so accidental
  growth is visible

Acceptance:

- the first-stage tool schema does not depend on the full canonical document
  schema
- every request manifest item is mapped, preserved, unsupported, or
  inconsistent exactly once
- compound requests can inventory multiple object families without choosing
  mutation order
- the unchanged SP and resistivity requests produce complete compact
  inventories without internal keys in the notebook prompt

Implementation checkpoint:

- compact `AuthoringRequestInventory` models describe actions, canonical
  object families, human target/parent descriptions, explicit values, and
  coverage status
- inventory validation rejects duplicate, unknown, missing, unsupported, and
  unexplained request items deterministically
- the full typed-intent schema is supplied only through the provider function
  definition and is no longer duplicated in the prompt text
- provider contract metrics record message size, tool-schema size, and compact
  inventory-schema size for budget tests and diagnostics
- focused compilation and adapter tests pass

### 0.6-J3. Scoped Typed Intent Compilation And Merge

Status: implemented in the current development branch.

Goal:

- compile each inventoried request group through the smallest applicable typed
  intent contract

Work:

- define generated provider submission contracts for related canonical
  families instead of one monolithic `AuthoringDocumentIntent` submission
- group dependent objects where required, such as track plus child bindings,
  while keeping unrelated report/header and annotation schemas out of that
  submission
- compile inventory groups independently with one bounded correction attempt
- merge validated partial intents deterministically by canonical identity and
  parent scope
- reject conflicting partial intents, duplicate identities, incomplete request
  coverage, and incompatible parent/child combinations before planning
- validate the merged result as `AuthoringDocumentIntent` before defaults,
  reconciliation, or persistence

Acceptance:

- a scalar-track request compiles only track, curve-binding, scale/grid, style,
  ordering, and coverage fields
- a header-only request does not receive section, raster, fill, or annotation
  schemas
- mixed requests merge into one canonical partial intent without losing
  explicit values
- explicit scale, color, line style, width, label, and ordering survive the
  staged compiler unchanged
- no scoped compiler contains SP-, resistivity-, CBL-, porosity-, or
  packet-specific control flow

Implementation checkpoint:

- the compact request inventory routes canonical object families into report,
  structure, scalar-content, raster-content, and annotation scopes
- each scope receives a generated Pydantic view projected from the canonical
  intent models rather than a separately maintained provider schema
- structural track declarations and child content declarations compile through
  bounded independent submissions; accepted section and track identities are
  forwarded to child scopes before the fragments rejoin
- each scoped submission permits one correction, validates only its request
  subset, and contributes to final whole-request coverage
- unsupported and inconsistent inventory items remain explicit coverage entries
  instead of being converted into guessed authoring objects
- deterministic merge rejects conflicting fields and duplicate section, track,
  binding, fill, annotation, and remark identities before validating the result
  as `AuthoringDocumentIntent`
- scoped provider context excludes unrelated current-document object families;
  defaults, channel resolution, reconciliation, execution, and verification are
  unchanged downstream
- focused tests cover contract-size bounds, header/report isolation, mixed
  structure and content compilation, explicit presentation preservation,
  duplicate rejection, and absence of scientific-family compiler branches

### 0.6-J4. Provider Adapter Conformance

Status: implemented in the current development branch.

Goal:

- make typed compilation behavior consistent across supported provider APIs

Work:

- require the designated submission function when a compilation stage permits
  exactly one function and prose is not a valid outcome
- preserve automatic tool selection only in workflows where a prose-only
  response is valid
- verify streamed tool-call id, name, and argument fragment assembly
- normalize finish reasons and malformed/empty response diagnostics across the
  Responses and OpenAI-compatible Chat Completions adapters
- keep provider-specific request options inside adapters rather than the
  deterministic compiler
- add recorded adapter fixtures for no-tool, one-tool, corrected-tool,
  malformed-arguments, and truncated responses

Acceptance:

- the same compact submission contract behaves consistently through the
  supported OpenAI and OpenAI-compatible adapters
- a required submission cannot silently finish as prose
- correction responses preserve the prior assistant tool call and tool result
  in provider-compatible message order
- adapter tests do not call MCP and compiler tests do not depend on a live
  provider

Implementation checkpoint:

- desired-state inventory and scoped-intent calls pass one explicit required
  submission function to provider adapters; broad MCP authoring loops retain
  automatic tool selection
- the Responses adapter sends the required function choice on the initial
  request and continues correction exchanges from the returned response id
- the Chat Completions adapter sends the required function choice initially and
  again after an explicit tool validation error, while preserving assistant
  tool-call and tool-result message order for corrections
- an explicitly accepted typed submission ends its compiler stage immediately;
  the adapter does not request a redundant prose summary, while explicit tool
  validation errors keep the required submission function enforced for the one
  permitted correction
- both adapters classify required-tool omissions, malformed non-object JSON
  arguments, incomplete streamed calls, empty responses, and truncated
  responses through stable `ProviderAdapterError` statuses
- both adapters report normalized response facts: adapter name, round count,
  emitted-tool flag, finish reasons, response statuses, and required tool name
- recorded adapter tests cover required one-call submission, correction,
  prose-when-optional, no-tool, empty, malformed, and truncated responses
  without MCP or provider credentials

### 0.6-J5. End-To-End Compiler Acceptance Matrix

Goal:

- prove meaningful natural-language success across object families rather than
  only validating caller-supplied typed intents

Required scenarios:

- add `SP` to an existing GR/SP track with an explicit `-80` to `20` scale
- create a resistivity track after depth, bind `ILD`, `ILM`, and `MSFL`, apply
  logarithmic `0.2` to `2000` scales and grid behavior, and make the deepest
  curve visually strongest
- create an uncatalogued normal track from an inspected scalar channel
- create an array/raster track and bind an available array channel
- apply an explicit curve color and line style that overrides family defaults
- revise header content through the deterministic header-language path
- report an unavailable channel and an ambiguous target without mutation

Work:

- run each request through provider submission, typed validation, deterministic
  context resolution, defaults, reconciliation, execution, persistence, and
  canonical read-back
- use recorded provider submissions in CI and a credentialed live-provider
  matrix as a manual release gate
- assert final object values and ordering, not only tool calls or non-empty
  output
- record which layer blocked and verify that no later layer ran after a block

Acceptance:

- every successful scenario produces the expected persisted canonical object
  graph and renderable draft
- every blocked scenario identifies the exact compiler, context, defaults,
  reconciliation, execution, transport, or render layer
- tests fail if a provider emits no submission, if a request item disappears,
  or if execution reports success without canonical read-back evidence
- no acceptance scenario selects a packet blueprint unless the caller
  explicitly requested a starter scaffold

Implementation checkpoint:

- recorded provider fixtures now exercise the real `run_request` desired-state
  workflow for scalar, logarithmic multi-curve, uncatalogued scalar, raster,
  explicit-style, header-language, missing-channel, and ambiguous-channel
  requests
- the matrix asserts canonical YAML read-back and render-model conversion for
  successful requests; unresolved channel cases must stop after provider
  submission and before any canonical save
- a credentialed live-provider matrix remains a manual release gate because
  its provider output is non-deterministic and must not make CI flaky

### 0.6-J6. Notebook, Documentation, And Release Closure

Goal:

- close the live authoring promise with reproducible evidence

Work:

- rerun `agent_las_step_by_step.ipynb` from a clean project directory without
  changing the SP or resistivity prompts
- retain phase previews and show compact compiler diagnostics only when a stage
  blocks
- update user documentation to explain intent compilation without exposing
  canonical keys as required user vocabulary
- document provider capability requirements and the difference between a
  provider compilation failure and an MCP mutation failure
- run full tests, Ruff, strict documentation build, notebook structural checks,
  package build, and installed-wheel MCP smoke checks

Acceptance:

- the SP and resistivity notebook cells complete and read back the requested
  persisted state
- the same workflow succeeds for at least one uncatalogued scalar track
- notebook users are not instructed to supply `track_id`, `kind`, `width_mm`,
  `binding_id`, or JSON paths for ordinary requests
- the release record names the live providers/models tested and separates
  optional provider limitations from deterministic product limitations
- no further MCP surface expansion is accepted until this release gate passes

## Reopened 0.6-K: Hierarchical Object-Operation Compilation

Live notebook testing after the scoped compiler work exposed a remaining
architectural mismatch. The provider no longer receives the full canonical
document schema at once, but the current scopes still combine unrelated levels
of the authoring hierarchy. In particular, the `report` scope combines document
settings, header content, remarks, and tail content, while the `structure`
scope asks the provider to describe sections and tracks as a partial desired
state before child content can be assembled.

This remains too close to asking the provider to solve a YAML puzzle. The MCP
already has a canonical object service and typed operation models, but its
discovery and the agent compiler do not yet present those operations as one
natural parent/child hierarchy.

The governing invariants for this program are:

> MCP mutation tools expose deterministic canonical object operations. They do
> not expose raw YAML paths or require a provider to construct a document
> graph.

> A provider sees only the object branch and parent context needed for the
> current user clause. Header work, report settings, sections, tracks, and
> track content are separate compilation contexts.

> The deterministic host resolves identity, defaults, dependencies,
> compatibility, persistence, and verification. Generated intelligence
> interprets the user's language and supplies explicit requested values.

The canonical hierarchy for this program is:

```text
document
|-- settings: output, page, depth
|-- report content: title/subtitle, header, remarks, tail
`-- sections[]
    `-- section
        `-- tracks[]
            `-- track
                |-- curve bindings -> fills
                |-- raster bindings -> raster display objects
                `-- annotations
```

Data-source inspection is contextual input. Validate, preview, render, and save
are lifecycle operations. Neither belongs in the provider-facing mutation
hierarchy.

Implementation policy:

- do not add packet-, CBL-, resistivity-, porosity-, or vendor-specific
  compiler branches
- do not expose raw JSONPath/YAML setters as the public authoring model
- generate hierarchy and operation discovery from the canonical Pydantic
  models and `AuthoringService` request models
- keep object mutation tools bounded by one object and its parent scope
- use defaults only after preserving explicit user values and existing-state
  instructions
- replace the scoped desired-state compiler after operation parity; do not keep
  two permanent authoring workflows
- complete and commit each slice separately

### 0.6-K1. Generated Hierarchy And Operation Catalog

Status: implemented in the current development branch.

Goal:

- make the canonical object tree, legal children, operations, fields, and
  constraints discoverable without reading YAML or provider prompt text

Work:

- define generated hierarchy metadata for document settings, report content,
  sections, tracks, bindings, fills, annotations, and nested header/raster
  objects
- generate each node's identity, parent requirements, legal children,
  supported operations, create schema, update schema, movable status, and
  verification getter from existing canonical models
- expose the catalog through MCP discovery, including a hierarchy resource and
  a focused inspection tool that accepts one object kind
- classify each property as finite, constrained, contextual, or relational and
  expose applicable generic defaults separately from allowed values
- audit `inspect_authoring_objects(...)` parity: report, output, header, tail,
  and all other service-owned object kinds must be inspectable through the same
  canonical service

Acceptance:

- discovery for `header` contains no section, track, binding, raster, or
  annotation schemas
- discovery for `track` names its legal child kinds and immutable form-kind
  rule
- every `AuthoringService` object kind has a generated getter/operation entry
- schema parity tests fail when service models and MCP discovery diverge

### 0.6-K2. Complete Bounded Object Mutation Parity

Status: implemented in the current development branch.

Goal:

- make every supported persisted mutation expressible as one typed operation
  over one canonical object

Work:

- audit create/update/remove/move/validate coverage against the hierarchy
  catalog
- add only missing object-level operations, favoring typed patches over
  replacement of whole parent branches
- add first-class header-slot and service-title updates so filling one header
  value does not replace the complete header object
- keep remark, section, track, curve, raster, fill, and annotation operations
  parent-scoped and stable-id based
- return the canonical object reference and post-write object from each
  mutation for immediate verification
- preserve atomic validation and reject incompatible child operations before
  persistence

Acceptance:

- changing one header slot cannot clear unrelated header values or structure
- changing one binding style cannot replace sibling bindings or track form
- create/update/remove/move operations round-trip through canonical YAML and
  read back through the matching getter
- no mutation requires a caller to patch an arbitrary YAML mapping

Implementation note:

- `AuthoringService` now exposes stable `header_slot` and `service_title`
  identities with typed partial updates.
- MCP exposes `update_header_slot(...)` and `update_service_title(...)`; both
  persist through the canonical-to-legacy adapter and return the updated
  canonical object for read-back verification.
- Nested report-value mappings are normalized without stringifying their
  structured value during a subsequent load.

### 0.6-K3. Hierarchical Request Router

Goal:

- split natural language into small hierarchy work units without asking the
  provider to assemble authoring state

Work:

- replace the current object-family inventory with a compact clause inventory
  containing action, top-level branch, natural target, natural parent, explicit
  values, preserve constraints, and dependencies
- use branch values for document settings, title/subtitle, header, remarks,
  tail, section, track, curve, raster, fill, and annotation
- preserve the user's original clause text for the downstream branch compiler
- classify negative instructions such as "do not add remarks" as assertions,
  not update operations
- reject or clarify genuinely cross-parent ambiguity before any mutation

Acceptance:

- a remarks-only request creates one remarks work unit
- a header-fill request creates one header work unit and receives only header
  discovery/context
- a request containing header edits and new log tracks becomes two independent
  work units rather than one mixed contract
- every user clause is mapped, preserved, unsupported, inconsistent, or needs
  clarification exactly once

### 0.6-K4. Parent-First Object Operation Compiler

Goal:

- compile each work unit into the smallest applicable canonical operation

Work:

- generate branch-specific provider submission contracts from the create and
  update request models rather than from `AuthoringDocumentIntent`
- compile report settings, header slots, remarks/tail, sections, tracks, curve
  bindings/fills, raster bindings, and annotations independently
- provide only the selected parent snapshot, relevant source-channel facts,
  allowed values, and defaults metadata to each compiler call
- allow human targets and descriptions in provider output; resolve stable ids
  and aliases deterministically after submission
- carry explicit values unchanged into operation requests and record defaults
  provenance only for omitted values
- permit one bounded correction for invalid operation submissions

Acceptance:

- a header compiler cannot emit a track operation and a track compiler cannot
  emit a header mutation
- a new track operation is compiled before any child binding operation
- explicit scale, width, color, line style, label, and ordering survive without
  reinterpretation by later stages
- provider schemas contain no unrelated object definitions or full-document
  desired-state graph

### 0.6-K5. Deterministic Dependency Plan And Transaction

Goal:

- assemble valid multi-object edits through deterministic hierarchy ordering

Work:

- build an operation dependency graph from canonical parent identities and
  relational references
- order document/report operations independently, sections before tracks,
  tracks before bindings/annotations, bindings before fills, and validation
  before preview/save
- resolve default values and generated stable ids once, then pass those resolved
  identities to child operations
- evaluate preserve assertions before and after execution
- execute against a defensive canonical snapshot and persist only after all
  required operations and assertions pass
- stop at the first blocked dependency and do not run descendant operations

Acceptance:

- mixed header and section requests do not leak state between branches
- child operations never run against a missing parent
- retries are idempotent and do not duplicate sections, tracks, bindings,
  fills, annotations, or remarks
- a failed operation leaves the persisted draft unchanged while retaining
  precise operation diagnostics

### 0.6-K6. Hierarchical Verification And Progress Reporting

Goal:

- prove progress at the object level instead of inferring success from provider
  submissions or whole-document diffs

Work:

- read every changed object through its generated canonical getter
- compare only the requested fields, relationships, order, and assertions for
  that operation
- record clause id, branch, parent, operation, defaults provenance, before/after
  evidence, and verification status
- generate phase previews only after a hierarchy branch has persisted a
  verified visual change
- report no-op preservation separately from completed mutation
- prevent a provider's prose response or accepted tool payload from being
  described as a completed authoring change

Acceptance:

- "Done" contains only canonically persisted, read-back-verified outcomes
- a remarks request cannot report unrelated GR or header mutations
- a failed header, track, or binding check names the exact object and property
- token/round use is associated with work units so repeated no-progress stages
  are visible and bounded

### 0.6-K7. Migration, Cross-Domain Acceptance, And Release Closure

Goal:

- replace the scoped desired-state path and prove that hierarchical operations
  generalize beyond the example notebooks

Work:

- migrate `run()`, `revise()`, and `plan()` to the hierarchy router, object
  operation compiler, deterministic dependency planner, and verifier
- route deterministic header-language and narrow remarks handling through the
  same canonical object operations
- remove the broad scoped-fragment merge path after behavior and diagnostic
  parity; do not retain it as an automatic fallback
- add recorded-provider acceptance for open-hole, porosity, caliper,
  resistivity, CBL/VDL, array, annotation, page/output, and mixed report/section
  requests
- rerun the canonical LAS notebook and CBL stress-test notebook from clean
  drafts with unchanged user-facing prompts
- update MCP and user documentation from the generated hierarchy and operation
  catalog

Acceptance:

- the canonical LAS notebook completes initial draft, remarks, SP, and
  resistivity requests with exact canonical read-back
- mixed header plus multi-section construction compiles and executes as
  separate hierarchy branches
- an uncatalogued scalar track and a custom annotation workflow use the same
  object-operation path as catalogued examples
- no acceptance request depends on a packet blueprint or request-specific code
- `AuthoringDocumentIntent` scoped compilation is absent from the normal agent
  path before `0.6.0` release
- unit, MCP, agent, cross-domain, docs, notebook, package, and installed-wheel
  release gates pass

## Release Gate

Do not publish `0.6.0` until the repository release gates below pass. Slices
`0.6-A` through `0.6-G7.2`, plus the reopened `0.6-H1` through `0.6-H6`
header-language slices, are the completed contract baseline. Reopened slices
`0.6-I1` through `0.6-I6`, compiler slices `0.6-J1` through `0.6-J6`, and
hierarchy slices `0.6-K1` through `0.6-K7` are release blockers because
open-world construction, provider compilation, and deterministic hierarchical
object operations are all required for the user-facing authoring promise.

Release-gate checklist:

- unit, MCP, agent, and cross-domain acceptance tests pass
- strict documentation build passes
- package and installed-wheel smoke checks pass
- canonical LAS notebook and experimental CBL notebook remain structurally
  discoverable and request per-phase previews
- catalogued and uncatalogued track requests both complete through generic
  canonical construction without packet-specific authority
- provider compilation uses bounded scoped contracts and reports exact
  extraction failures before any deterministic authoring stage runs
- unchanged SP and resistivity notebook requests persist and read back the
  requested objects and values
- provider compilation follows the natural authoring hierarchy and submits
  bounded canonical object operations rather than partial document graphs
- header, report-content, section, track, and track-content work is compiled in
  separate parent-scoped contexts and verified through canonical getters
- the scoped `AuthoringDocumentIntent` fragment compiler is no longer used by
  the normal agent path
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
