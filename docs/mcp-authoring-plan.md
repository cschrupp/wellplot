# MCP Natural-Language Authoring Plan

Last updated: 2026-08-13

## Summary

Goal for the next version:

- let MCP clients turn natural-language plotting requests into valid wellplot
  savefiles and previews
- keep the actual plot edits deterministic, schema-backed, and reviewable
- support both greenfield authoring and iterative edit flows

Mission reminder:

- the final user should be able to plot and refine data with little or no
  knowledge of internal `wellplot` structures
- MCP should therefore expose stable authoring objects and deterministic edit
  operations rather than hidden packet-specific orchestration rules

The canonical direction is documented in
[docs/mcp-authoring-model.md](mcp-authoring-model.md).

Representative user requests:

- "Add a porosity track with NPHI and RHOB."
- "Put GR on the left at 0-150 gAPI in green."
- "Fill neutron-density crossover in yellow."
- "This text file has the header values; map them into the report header."
- "Use this remark block on the first page."
- "Move caliper next to depth and make it narrower."

## Core Product Decision

`wellplot` should not embed a model-specific natural-language parser in the MCP
server.

Instead:

- the MCP client or host LLM interprets the user's freeform request
- `wellplot-mcp` exposes deterministic authoring tools, resources, prompts, and
  patch formats that the client can call
- every mutation remains explicit, validatable, previewable, and safe to save

This keeps the server portable across MCP hosts while still enabling
natural-language workflows.

## Authoring Model Direction

The MCP/agent surface should align with one canonical object model:

- form objects such as `report`, `section`, `track`, `heading`, `remarks`, and
  `tail`
- content objects such as `curve binding`, `raster binding`, `fill`, and
  `annotation object`

Track kinds remain form subtypes:

- `reference`
- `normal`
- `array`
- `annotation`

This distinction matters because the natural-language layer should speak in
user-meaningful objects:

- add a track
- bind a curve
- set a scale
- style a curve
- fill header values

rather than relying on hidden packet-specific reconstruction logic.

### Precedence Rule

The intended precedence order is:

1. explicit user instruction
2. explicit preservation of existing draft state
3. defaults catalogs
4. starter scaffolds and examples

Defaults are fallback guidance. They must not silently override explicit user
intent.

### Defaults Instead Of Hidden Packet Authority

Reusable guidance should increasingly live in defaults catalogs such as:

- track-family defaults
- curve-family defaults
- raster-family defaults
- header archetypes
- starter scaffolds

Examples and packet assets may remain useful as:

- examples
- starter scaffolds
- regression fixtures

But they should not become a second authoritative template system.

### Open-World Object Construction

Scientific-family recognition must not be required to construct a valid
authoring object. A user may request a familiar family such as resistivity,
porosity, caliper, or CBL, but they may also request a project-specific track
whose channels and terminology do not exist in the packaged defaults catalog.

The agent and deterministic resolver should therefore separate two concerns:

1. generic object construction
2. optional scientific-family presentation conventions

Generic construction is responsible for completing required form properties
from the request and object relationships. For a new track this includes:

- deriving a user-facing title from the requested name when the provider omits
  an explicit title field
- selecting a form kind from explicit wording and compatible child content
- supplying an asset-backed width default for that form kind
- preserving explicit scale, grid, style, and layout instructions exactly

Family defaults may then enrich the object with conventional labels, scales,
colors, line weights, or raster presentation. Failure to recognize a family or
one channel mnemonic must not discard the generic structural defaults or block
an otherwise valid object.

The vocabulary must keep form and presentation kinds distinct:

- track form kinds are `normal`, `reference`, `array`, and `annotation`
- scale kinds are `linear`, `log`, and `tangential`

A resistivity track is normally a `normal` form track with a `log` X-scale. A
custom scalar track can use the same form without being classified as a
resistivity family.

The refined precedence order is:

1. explicit user instruction
2. explicit preservation of existing state
3. selected specific family or style preset
4. selected family archetype
5. generic form defaults
6. starter scaffolds and examples

Unknown channel mnemonics are open-world inputs. When the source inspection
confirms that a channel exists and its data kind is compatible with the target
object, an unknown family classification should produce provenance or a
warning, not a structural failure. Known contradictory evidence and genuinely
ambiguous family matches must still fail closed.

## API Readiness Assessment

The current data and render cores are strong enough to preserve. The public
authoring boundary is not yet complete enough to support reliable generated
authoring.

What is already in place:

- the report model already represents the needed authoring targets:
  - sections
  - tracks
  - curve and raster bindings
  - headings
  - remarks
  - render/page/depth settings
- the programmatic builder already mirrors much of that structure in explicit
  Python calls
- logfile parsing and template inheritance already normalize and validate full
  savefiles
- the serializer already gives us a canonical YAML output path
- the current MCP surface already provides safe validate, inspect, preview,
  format, and save loops under a fixed server root

What is still missing is not a new rendering core. It is:

- one strict typed authoring contract shared by Python, YAML, MCP, and agent
  verification
- generated schema and discovery instead of duplicated field/value lists
- complete deterministic object inspection and mutation
- explicit compatibility adapters into the existing renderer
- contract-parity tests that detect cross-layer drift

## Non-Goals For This Phase

- no server-side dependency on a specific LLM vendor or API
- no direct freeform text tool that silently rewrites a logfile on disk
- no hidden long-lived server state that cannot be serialized or inspected
- no attempt to preserve YAML comments, anchors, or original formatting during
  normalized save flows
- no rewrite of the working dataset/channel or renderer layers without a
  demonstrated compatibility requirement
- no new packet-specific blueprint authority
- no provider or remote-transport expansion before deterministic contract parity

## Current Gaps

The current MCP surface has broad review and mutation capability. The remaining
gaps are structural:

- standard fields, values, defaults, and relationships are duplicated across
  dataclasses, JSON Schema, parsers, builders, MCP allowlists, and agent checks
- page, depth, header, footer, and the document mapping still permit arbitrary
  extra properties in the hand-maintained schema
- the Python builder accepts many loose nested mappings
- object getter coverage is uneven, and several child objects lack stable ids
  or complete CRUD
- MCP tools mutate normalized dictionaries directly instead of calling one
  canonical typed object service
- packet-specific agent logic can compensate for missing semantics and override
  explicit user values

Live provider testing has also exposed a separate compilation-boundary gap:

- the provider currently receives one monolithic typed-intent tool containing
  the complete report, header, section, track, curve, raster, fill, annotation,
  page, output, and remarks graph even for a narrow edit
- that schema is duplicated as text in the provider message despite already
  being supplied as the function schema
- a provider that returns prose instead of the required typed submission causes
  no MCP call, but the current user report hides the provider response and can
  incorrectly suggest that the request needs internal object fields
- deterministic tests using caller-supplied intents prove the execution path,
  not the natural-language compilation path

The `0.6-J` compiler work reduced the original monolithic submission, but live
notebook acceptance proved that its scoped partial-document compiler remains in
the normal natural-language path. It redundantly asks providers for object
family, hierarchy branch, and arbitrary intent paths, then merges partial
`AuthoringDocumentIntent` fragments before bridging the result back into typed
service operations.

The active correction is `0.6-K7.4` through `0.6-K7.8` in
[docs/mcp-implementation-plan.md](mcp-implementation-plan.md). It derives branch
ownership deterministically, tracks coverage by work-unit id, compiles directly
into generated canonical service-operation contracts, removes the superseded
provider fragment path, and closes with cross-domain notebook acceptance. This
work must reduce permanent compiler complexity and must not add MCP mutation
tools, provider-specific prompt branches, packet authority, or
scientific-family special cases.

The detailed inventory is
[docs/authoring-contract-inventory.md](authoring-contract-inventory.md).

## Implemented Capability Building Blocks (Historical)

The following sections record how the current MCP roster was built. They are
retained for tool history; the `0.6.0` contract program supersedes them as the
active implementation order.

### 1. Draft Lifecycle

Clients need a clear way to create and evolve an authoring target without
writing directly to the final savefile path.

Needed behavior:

- start from an example bundle, template, or blank draft
- keep all writes under the configured server root
- allow preview and validation of unsaved or draft content before promotion to
  a final file

Candidate tools:

- `create_logfile_draft(example_id=None, template_path=None, output_path, overwrite=False)`
- `summarize_logfile_draft(logfile_path)`
- `promote_logfile_draft(logfile_path, output_path, overwrite=False)`

### 2. Structured Edit Surface

Natural-language authoring only becomes reliable if the MCP client can apply
small, explicit operations instead of regenerating entire YAML files.

High-value edit domains:

- sections
- tracks
- curve bindings
- scales
- curve styles
- fills
- page/depth settings
- headings
- remarks
- output settings

Preferred v1 shape:

- explicit high-value edit tools first
- generic patch schema only after the domain model stabilizes

Candidate tools:

- `update_section(...)`
- `add_track(...)`
- `update_track(...)`
- `add_annotation_object(...)`
- `update_annotation_object(...)`
- `remove_annotation_object(...)`
- `remove_track(...)`
- `bind_curve(...)`
- `update_curve_binding(...)`
- `remove_curve_binding(...)`
- `add_curve_fill(...)`
- `set_depth_axis(...)`
- `set_page_layout(...)`
- `set_section_view(...)`
- `set_heading_content(...)`
- `set_remarks_content(...)`
- `set_section_data_source(...)`
- `remove_curve_fill(...)`
- `clear_track_bindings(...)`

Remaining broader authoring surface after the current foundation:

- possible grouped removal helpers for repeated notebook workflows beyond the
  now-implemented per-track binding clear operation

### 3. Authoring Vocabulary And Discovery

The MCP client needs to know what is legal before it plans edits.

Needed discovery surface:

- valid track kinds
- valid fill kinds
- scale kinds and required fields
- common authoring archetypes:
  - porosity
  - resistivity
  - CBL/VDL
  - caliper/reference
- required/optional heading fields for a given template or draft

Candidate resources:

- `wellplot://authoring/schema/patch.json`
- `wellplot://authoring/catalog/track-kinds.json`
- `wellplot://authoring/catalog/fill-kinds.json`
- `wellplot://authoring/catalog/track-archetypes.json`
- `wellplot://authoring/catalog/header-fields.json`

Candidate tools:

- `inspect_authoring_vocab(logfile_path=None, template_path=None)`
- `inspect_heading_slots(logfile_path)`

### 4. Deterministic Header And Remark Ingestion

For requests like "this text file has the header data", the model should
extract values, but the server should still own the mapping and validation.

Needed behavior:

- expose which header fields exist and which keys are expected
- let the client submit normalized key-value data
- validate that the target fields exist and reject ambiguous mappings
- provide remark-block helpers rather than forcing raw YAML surgery

Candidate tools:

- `apply_header_values(logfile_path, values, section_id=None)`
- `preview_header_mapping(logfile_path, values)`
- `set_remark_blocks(logfile_path, remarks)`

Optional later helper:

- deterministic key-value parser for plain text or CSV-like blocks when the
  source format is simple enough to parse without an LLM

## Next Authoring Broadening Slice

After the current track, binding, header, depth-axis, and style-editing
foundation, the next highest-value additions are:

1. additional notebook-facing ergonomics where repeated project/setup patterns remain
2. preset-oriented section/page helpers only where repetitive edits still appear
3. any remaining agent-facing cleanup exposed by iterative notebook usage

These additions matter because iterative user workflows are now blocked less by
curve/track creation and more by the remaining layout and cleanup operations
that still require broad patching or manual YAML edits.

### 5. Review Loop For Safe Authoring

Every nontrivial authoring flow should support a standard loop:

1. inspect current draft
2. apply one or more explicit edits
3. validate
4. preview section/track/window or full-page output
5. save or promote only after review

Needed supporting tools:

- `validate_logfile_text(...)`
- `format_logfile_text(...)`
- draft summarization/diff helpers
- the existing preview tools

Missing addition:

- `diff_logfile_text(before_text, after_text)` or
- `summarize_logfile_changes(logfile_path, previous_text=None)`

### 6. LLM-Facing Prompt Contracts

The MCP prompts should explicitly teach clients how to convert freeform plot
requests into deterministic tool calls.

Needed prompts:

- `author_plot_from_request(goal, logfile_path=None, example_id=None)`
- `revise_plot_from_feedback(logfile_path, feedback)`
- `ingest_header_text(logfile_path, source_text, source_description=None)`

Prompt responsibilities:

- force inspect-first behavior
- prefer explicit small edits over full rewrites
- require validation before save
- require previews before final render or promotion

## Proposed Release Slices

### Release 0.4.0: Deterministic Authoring Foundation

Historical interpretation: the planned deterministic tool roster was
implemented. This slice did not establish one canonical field-level contract,
so "foundation" here refers to capability breadth rather than final
architecture.

Deliver:

- draft lifecycle tools
- high-value edit tools for tracks, curve bindings, heading content, and
  remarks
- authoring vocabulary resources
- prompts for LLM-guided authoring flows
- change summarization helpers for edit review

Acceptance:

- a client can start from an example or blank draft and iteratively author a
  valid plot without hand-editing YAML
- a client can add a porosity track, bind curves, set scales/styles/fills, add
  remarks, and save the result through MCP

### Release 0.5.0: Rich Ingestion And Workflow Ergonomics

Historical interpretation: the planned ingestion and header workflow roster was
implemented. Its request/result models still need consolidation under the
`0.6.0` canonical contract.

Deliver:

- standalone LAS/DLIS data-source inspection and channel availability checks
- header-slot inspection and mapping helpers
- deterministic import helpers for simple structured text sources
- stronger archetype catalogs, alias catalogs, and style presets
- richer authoring notebook/demo flows

Acceptance:

- a client can inspect a raw LAS/DLIS source, confirm the channels needed for a
  requested plot are actually present, then move into deterministic draft
  authoring
- a client can ingest header values from provided text, map them into the
  report structure, preview the result, and save confidently

Concrete focus:

- make raw data inspection explicit instead of requiring a pre-existing draft
- let MCP clients answer "do we have GR/RHOB/NPHI/CBL/VDL in this source?"
  before they start creating bindings
- make header and cover-page value mapping deterministic instead of ad hoc
- reduce prompt verbosity by exposing reusable style and archetype presets
- keep freeform language in the MCP client while giving it better structured
  targets for ingestion and revision

### Release 0.6.0: Canonical Deterministic Authoring Contract

Deliver:

- complete authoring object/field/constraint inventory
- strict Pydantic v2 authoring models and generated JSON Schema
- compatibility and render adapters
- complete typed object inspection and mutation service
- MCP/schema/API contract parity
- defaults catalogs with explicit precedence
- agent rebase onto deterministic object outcomes

Acceptance:

- every persisted authoring object and standard property has one canonical
  owner
- Python, YAML, MCP, and agent verification expose the same constraints
- explicit user values survive defaults and scaffolds
- generic workflows succeed without packet-specific authority
- all release, docs, notebook, and installed-wheel gates pass

## Release 0.4.0 Concrete Tool Set

This is the concrete authoring roster that fits the current API base without
forcing a model or renderer rewrite:

1. `create_logfile_draft(...)`
2. `summarize_logfile_draft(...)`
3. `add_track(...)`
4. `bind_curve(...)`
5. `update_curve_binding(...)`
6. `move_track(...)`
7. `set_heading_content(...)`
8. `set_remarks_content(...)`
9. `inspect_authoring_vocab(...)`
10. `summarize_logfile_changes(...)`
11. `author_plot_from_request(...)` prompt
12. `revise_plot_from_feedback(...)` prompt

Notes:

- `fill` is not a separate first-pass tool. It is part of
  `update_curve_binding(...)`.
- `move_track(...)` is included because natural-language requests will often
  care about adjacency and order, and the current YAML/list model already makes
  that possible.
- header text ingestion from raw source files remains a `0.5.0` item. The
  `0.4.0` goal is to make the target heading structure editable first.

Implemented so far:

- `create_logfile_draft(...)`
- `summarize_logfile_draft(...)`
- `add_track(...)`
- `bind_curve(...)`
- `update_curve_binding(...)`
- `move_track(...)`
- `set_heading_content(...)`
- `set_remarks_content(...)`
- `inspect_authoring_vocab(...)`
- `summarize_logfile_changes(...)`
- `author_plot_from_request(...)` prompt
- `revise_plot_from_feedback(...)` prompt

`0.4.0` status:

- planned tool roster complete in the repository-local MCP implementation
- superseded architectural interpretation: deterministic contract and object
  operation completeness are now `0.6.0` release work

## Release 0.5.0 Concrete Tool Set

This is the next concrete MCP slice after the deterministic authoring
foundation.

1. `inspect_data_source(source_path, source_format="auto")`
2. `check_channel_availability(requested_channels, source_path=None, logfile_path=None, section_id=None, source_format="auto")`
3. `inspect_heading_slots(logfile_path=None, template_path=None)`
4. `preview_header_mapping(logfile_path, values, overwrite_policy="fill_empty")`
5. `apply_header_values(logfile_path, values, overwrite_policy="fill_empty")`
6. `parse_key_value_text(source_text, format_hint=None)`
7. `inspect_style_presets(logfile_path=None)`
8. `ingest_header_text(logfile_path, source_text, source_description=None)` prompt

Supporting resources:

- `wellplot://authoring/catalog/header-key-aliases.json`
- `wellplot://authoring/catalog/channel-aliases.json`
- `wellplot://authoring/catalog/style-presets.json`
- `wellplot://authoring/catalog/overwrite-policies.json`

Notes:

- `0.5.0` is still not a server-side "understand any document" feature.
- standalone data inspection in this phase is file-based and limited to the
  formats the project already supports today: LAS and DLIS.
- actual LIS support remains out of scope for `0.5.0`.
- direct inspection of live pandas/numpy objects is also out of scope for MCP
  in this phase unless a client serializes them into an explicit payload.
- the parser should stay deterministic and limited to simple structured forms:
  - `Key: Value`
  - `KEY=VALUE`
  - two-column text blocks
- OCR, PDF table extraction, and ambiguous freeform interpretation remain the
  MCP client's responsibility.

## Release 0.5.0 Tool Contracts

### 1. `inspect_data_source(...)`

Purpose:

- inspect one raw LAS or DLIS source before any draft/logfile exists

Inputs:

- `source_path`
- `source_format`

Return shape:

- `source_path`
- `source_format_detected`
- `dataset_name`
- `index`
- `channels`
- `metadata_keys`
- `warnings`

Why it matters:

- authoring starts with "what data do I actually have?"
- this should be the first MCP-native step before creating bindings or
  explaining missing channels back to the user

### 2. `check_channel_availability(...)`

Purpose:

- compare requested channel names or aliases against one inspected source or one
  draft section dataset

Inputs:

- `requested_channels`
- `source_path` or `logfile_path`
- `section_id`
- `source_format`

Return shape:

- `requested_channels`
- `found_channels`
- `missing_channels`
- `alias_matches`
- `ambiguous_matches`
- `warnings`

Why it matters:

- natural-language authoring requests often start with domain names like
  "porosity", "deep resistivity", or "VDL"
- the MCP client needs one deterministic check before it starts binding curves

### 3. `inspect_heading_slots(...)`

Purpose:

- expose the exact heading/report slots available in a draft or template before
  applying imported values

Return shape:

- `provider_slots`
- `general_field_slots`
- `service_title_slots`
- `detail_slots`
- `remarks_capabilities`
- `current_values`
- `resource_uris`

Why it matters:

- `inspect_authoring_vocab(...)` gives broad editing vocabulary
- `inspect_heading_slots(...)` should become the precise contract for
  report-header ingestion and review

### 4. `preview_header_mapping(...)`

Purpose:

- dry-run header value application without mutating the draft

Inputs:

- `logfile_path`
- `values`
- `overwrite_policy`

Return shape:

- `resolved_assignments`
- `unmatched_values`
- `conflicting_values`
- `warnings`
- `predicted_heading_patch`

Ambiguous entries in `conflicting_values` include the visible
`candidate_labels`, a `clarification_question`, and candidate target metadata.
The predicted patch still contains any unambiguous assignments from the same
request; a client can apply those while retaining the conflicting value for a
follow-up clarification.

The agent-side continuation keeps that pending choice in the active
`AuthoringSession` only. A follow-up may refer to a visible candidate naturally
instead of repeating a canonical key; the agent re-previews the selected target
against the current heading before applying the original value. New runs and
new sessions do not inherit pending choices.

Why it matters:

- the MCP client needs one reviewable step between "I extracted these values"
  and "write them into the draft"

### 5. `apply_header_values(...)`

Purpose:

- apply normalized header values to a draft through the server-owned mapping
  rules

Inputs:

- `logfile_path`
- `values`
- `overwrite_policy`

Supported overwrite policies:

- `fill_empty`
- `replace`
- `merge_lists`

Return shape:

- `logfile_path`
- `applied_assignments`
- `skipped_assignments`
- `warnings`
- `heading_summary`

### 6. `parse_key_value_text(...)`

Purpose:

- deterministically parse simple structured text blocks into normalized
  key-value pairs

Inputs:

- `source_text`
- `format_hint`

Return shape:

- `pairs`
- `unparsed_lines`
- `format_detected`
- `warnings`

Deliberate first-pass limit:

- no OCR
- no PDF parsing
- no fuzzy multi-table inference
- no hidden value-to-slot mapping in this tool

### 7. `inspect_style_presets(...)`

Purpose:

- expose curated style presets and recommended patches for common authoring
  goals

Expected preset families:

- porosity overlays
- gamma ray defaults
- resistivity log conventions
- CBL/VDL high-contrast and print-safe variants
- first-page header/remarks presentation presets

Why it matters:

- many natural-language requests include color/scale/fill conventions that
  should map to reusable presets instead of one-off patches every time

## Release 0.5.0 Implementation Order

Recommended build order:

1. `inspect_data_source(...)`
2. `check_channel_availability(...)`
3. channel-alias resources
4. `inspect_heading_slots(...)`
5. header-key alias resources
6. `preview_header_mapping(...)`
7. `apply_header_values(...)`
8. `parse_key_value_text(...)`
9. style-preset resources + `inspect_style_presets(...)`
10. richer notebook/demo flow
11. `ingest_header_text(...)` prompt

## Release 0.5.0 Acceptance

`0.5.0` is complete when:

- a client can inspect one raw LAS/DLIS source and understand its available
  channels, index range, and basic metadata before drafting
- a client can deterministically check whether requested channels are present
  before creating bindings
- a client can inspect the exact heading/report slots in a target draft
- a client can parse simple structured header text into key-value pairs
- a client can preview how those values would map into the draft before saving
- a client can apply the mapping with an explicit overwrite policy
- a client can rely on preset catalogs for common style conventions instead of
  restating them in every prompt
- the MCP notebook/demo shows one end-to-end "header packet to rendered draft"
  workflow

## Release 0.6.0: Canonical Deterministic Authoring Contract

### Goal

Complete the deterministic authoring framework before treating generated
authoring as stable. Every persisted object, property, value constraint, and
relationship must have one canonical typed definition and complete required
read/write coverage.

### Current Status (2026-08-13)

Implemented capability:

- public host-side `wellplot.agent` API
- local stdio MCP runtime and provider-neutral result/event handling
- OpenAI and OpenAI-compatible provider paths
- phase planning, deterministic checks, previews, and concise reports
- broad MCP tools for draft, section, track, binding, report, and ingestion
  workflows

Release blockers:

- the normal provider route still compiles scoped partial document intents
  before bridging back into typed service operations
- redundant provider-authored hierarchy branches and arbitrary intent paths can
  contradict canonical object ownership
- extraction reports can retain corrected failures and lose the trace for the
  active failed stage
- unchanged canonical notebook prompts have not passed exact read-back through
  the direct hierarchy-operation route

### Architecture Boundary

- `wellplot` canonical authoring models: strict object/field/value contract
- `wellplot` authoring service: deterministic object inspection and mutation
- `wellplot.mcp`: thin provider-agnostic projection of that service
- `wellplot.agent`: intent interpretation, planning, tool selection, and
  read-after-write verification
- existing channel/data and render dataclasses: preserved behind adapters

Provider SDK clients, credentials, and provider-specific tool loops remain out
of the MCP server.

### Required Slices

1. `0.6-A`: contract inventory and ownership
2. `0.6-B`: canonical Pydantic authoring models and generated schema
3. `0.6-C`: compatibility and render adapters
4. `0.6-D`: deterministic object service and complete CRUD
5. `0.6-E`: MCP contract parity
6. `0.6-F`: defaults and precedence
7. `0.6-G`: agent rebase and release acceptance
8. `0.6-H` and `0.6-I`: user-language header resolution and open-world object
   construction
9. `0.6-J`: bounded provider compiler foundation
10. `0.6-K1` through `0.6-K7.3`: generated hierarchy, typed operations,
    transaction, verification, and closure of the broad provider-to-MCP loop
11. `0.6-K7.4` through `0.6-K7.8`: direct provider-to-service-operation
    compilation, dead-path removal, and final acceptance

Detailed contracts:

- [docs/authoring-contract-inventory.md](authoring-contract-inventory.md)
- [docs/mcp-implementation-plan.md](mcp-implementation-plan.md)

### In Scope

- Pydantic v2 as a direct dependency for authoring-boundary models
- strict standard fields and explicit extension points
- generated JSON Schema and MCP discovery
- typed create and patch models
- complete deterministic object reads and writes
- current YAML compatibility and renderer adapters
- defaults precedence and packet-blueprint demotion
- generic agent and notebook acceptance

### Out Of Scope

- renderer or channel-model rewrites without a demonstrated compatibility need
- new packet-specific blueprints
- additional hosted-model providers
- remote HTTP/SSE MCP transport
- persistent or vector memory
- mandatory live-provider CI

### Release Acceptance

`0.6.0` is complete when:

- every inventory object and property has one canonical owner
- generated schema replaces hand-maintained field/value duplication
- Python, YAML, MCP, and agent verification enforce the same contract
- all required deterministic object operations are implemented and atomic
- legacy supported YAML round-trips without semantic regression
- explicit user values override defaults and scaffolds
- generic CBL, caliper, porosity, resistivity, annotation, and raster workflows
  pass without packet-specific authority
- MCP stdio integration, unit, agent, docs, notebook, and installed-wheel tests
  all pass
- package version, changelog, release notes, and public documentation describe
  the shipped surface accurately

## First Five Operations (Historical `0.4.0` Design)

These are the first five authoring operations that should be defined and built
before anything else. Together they are enough to support a real "build a
porosity panel" workflow.

### 1. `create_logfile_draft(...)`

Proposed signature:

- `create_logfile_draft(output_path, example_id=None, source_logfile_path=None, overwrite=False)`

Behavior:

- requires exactly one seed source:
  - packaged `example_id`, or
  - existing `source_logfile_path`
- writes canonical logfile YAML to `output_path`
- rebases relative `render.output_path`, top-level `data.source_path`, and
  section-level `data.source_path` when cloning from an existing logfile
- enforces server-root restrictions and explicit output path writes

Return shape:

- `output_path`
- `name`
- `section_ids`
- `seed_kind`
- `seed_value`

Deliberate first-pass limit:

- no blank-draft creation in `0.4.0`
- no direct template-only draft creation in `0.4.0`

### 2. `summarize_logfile_draft(...)`

Proposed signature:

- `summarize_logfile_draft(logfile_path)`

Behavior:

- read-only
- resolves the draft, its sections, and its datasets
- returns a compact authoring summary suitable for LLM planning
- acts as the inspect-first tool for draft-edit workflows

Return shape:

- `name`
- `render_backend`
- `configured_output_path`
- `has_heading`
- `has_remarks`
- `section_count`
- `sections[*].id`
- `sections[*].title`
- `sections[*].track_ids`
- `sections[*].curve_binding_count`
- `sections[*].raster_binding_count`
- `sections[*].available_channels`

Why this is first-pass critical:

- the client needs one compact place to discover what can be edited before it
  starts issuing mutations

### 3. `add_track(...)`

Proposed signature:

- `add_track(logfile_path, section_id, id, title, kind, width_mm, x_scale=None, grid=None, track_header=None, reference=None, annotations=None)`

Behavior:

- mutates the explicit draft file at `logfile_path`
- appends a new track to `document.layout.log_sections[*].tracks`
- rejects duplicate `id` values within the target section
- validates the resulting draft through the normal logfile/schema/renderable
  path before saving

Return shape:

- `logfile_path`
- `section_id`
- `track_id`
- `track_ids`
- `track_count`

Deliberate first-pass limit:

- appends to the end of the section track list
- does not attempt list insertion or relative ordering
- reordering is handled by `move_track(...)`

### 4. `bind_curve(...)`

Proposed signature:

- `bind_curve(logfile_path, section_id, track_id, channel, label=None, style=None, scale=None, header_display=None)`

Behavior:

- adds one curve binding to `document.bindings.channels`
- requires:
  - target section exists
  - target track exists
  - target channel resolves in the section dataset
- rejects duplicate `(section_id, track_id, channel, kind="curve")` bindings
- saves the normalized draft only if the post-edit logfile still validates and
  builds

Return shape:

- `logfile_path`
- `section_id`
- `track_id`
- `channel`
- `binding_kind`
- `binding_count`

Why this is enough for v1:

- it supports the high-frequency authoring move of "put curve X on track Y"
- it keeps the initial add operation simple, while richer styling is handled by
  the next tool

### 5. `update_curve_binding(...)`

Proposed signature:

- `update_curve_binding(logfile_path, section_id, track_id, channel, patch)`

Behavior:

- finds an existing curve binding by `(section_id, track_id, channel)`
- applies a constrained patch over the binding
- allows only these mutable keys:
  - `label`
  - `style`
  - `scale`
  - `header_display`
  - `fill`
  - `reference_overlay`
  - `value_labels`
  - `wrap`
  - `render_mode`
- deep-merges nested mappings
- treats `null` values as "remove this optional property"
- validates and normalizes the draft before persisting

Return shape:

- `logfile_path`
- `section_id`
- `track_id`
- `channel`
- `binding`

Why this is the key natural-language bridge:

- requests like "make GR green", "set 0-150 gAPI", or "add yellow
  neutron-density crossover fill" all collapse into deterministic patches on an
  existing binding

## Internal Implementation Seams

Required internal split:

1. canonical Pydantic authoring models
2. YAML/template compatibility adapters
3. renderer adapters into existing document dataclasses
4. deterministic object service shared by Python and MCP
5. generated JSON Schema, MCP discovery, and reference artifacts
6. defaults resolver with explicit provenance and precedence
7. agent planner/verifier consuming only deterministic service outcomes

Raw mutable logfile mappings remain a compatibility implementation detail. They
must not remain the source of truth or the public mutation contract.

## Implementation Order

Follow slices `0.6-A` through `0.6-G` without overlap that creates a second
temporary contract. In particular:

- do not publish a new vocabulary before canonical models exist
- do not migrate MCP mutations before compatibility and atomic service behavior
  are tested
- do not implement defaults before omitted/explicit/existing value provenance
  is representable
- do not resume agent optimization before MCP contract parity is complete

## Data Model Work Required

Required work is tracked per object in
[docs/authoring-contract-inventory.md](authoring-contract-inventory.md).

Key model decisions:

- strict standard fields with explicit extension points
- discriminated unions for track, binding, annotation, and fill kinds
- stable ids for independently editable child objects
- typed create models and patch models
- contextual validation for channel and object references
- atomic document validation after every mutation
- explicit adapters that preserve current channel and render models

## Testing And Evaluation

We need deterministic tests for authoring behavior even though the user-facing
workflow starts from natural language.

Required coverage:

- generated-schema and model-validation parity
- current YAML compatibility, normalization, and round trips
- field, enum, default, and null/omitted behavior
- complete object CRUD matrix and atomic rollback
- parent/child compatibility and contextual-reference failures
- Python API/MCP input and result parity
- defaults precedence and explicit-value preservation
- stdio integration tests for the main authoring flow
- installed-wheel smoke coverage

Suggested golden scenarios:

- "add porosity track with RHOB and NPHI"
- "move GR to the right and recolor it"
- "add neutron-density crossover fill"
- "apply these header values"
- "insert this remark block"
- "bind one channel twice with different ids, scales, colors, and line styles"
- "create an array track and configure raster sample-axis presentation"
- "reject a raster binding on a normal track"
- "report a requested channel that is absent from the selected section source"

## Documentation Work

When these slices land, docs must explain the boundary clearly:

- the user speaks in natural language to an MCP client
- the client turns that request into `wellplot-mcp` tool calls
- the server applies canonical deterministic object operations and returns
  inspectable objects, previews, and results
- Python, YAML, and MCP share the same authoring contract
- defaults never override explicit user values

Docs to add or update:

- `README.md`
- `docs/mcp-plan.md`
- `docs/authoring-contract-inventory.md`
- `docs/programmatic-api-plan.md`
- `docs/site/workflows/mcp-workflow.md`
- `docs/site/reference/mcp-api.md`
- generated public authoring-object reference
- new authoring examples or notebooks

## Immediate Next Step

Start `0.6-A` only:

1. complete the field-level inventory from all current contract sources
2. record every conflict and compatibility decision
3. choose the canonical model package location
4. define the first implementation boundary for `0.6-B`

Do not add new agent behavior or MCP convenience verbs during this slice unless
they are required to represent a missing canonical object operation.
