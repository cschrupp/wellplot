# MCP Natural-Language Authoring Plan

Last updated: 2026-05-01

## Summary

Goal for the next version:

- let MCP clients turn natural-language plotting requests into valid wellplot
  savefiles and previews
- keep the actual plot edits deterministic, schema-backed, and reviewable
- support both greenfield authoring and iterative edit flows

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

## API Readiness Assessment

The current core is already strong enough to support this direction.

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

What is still missing is not a new rendering core. It is a deterministic
mutation layer for draft authoring.

## Non-Goals For This Phase

- no server-side dependency on a specific LLM vendor or API
- no direct freeform text tool that silently rewrites a logfile on disk
- no hidden long-lived server state that cannot be serialized or inspected
- no attempt to preserve YAML comments, anchors, or original formatting during
  normalized save flows

## Current Gaps

The current MCP surface is strong for review, preview, export, validation, and
normalized save. It is still weak for iterative authoring because it lacks:

- a first-class draft lifecycle for new plots
- structured edit operations for tracks, bindings, fills, headings, and remarks
- schema-backed authoring vocabularies for clients to discover
- deterministic helpers for mapping extracted header values into the right
  report fields
- a patch/diff workflow that lets the user inspect what changed before saving

## Required Building Blocks

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

- `add_track(...)`
- `update_track(...)`
- `remove_track(...)`
- `bind_curve(...)`
- `update_curve_binding(...)`
- `remove_curve_binding(...)`
- `add_curve_fill(...)`
- `set_depth_axis(...)`
- `set_heading_content(...)`
- `set_remarks_content(...)`
- `set_section_data_source(...)`

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

- complete in the repository-local MCP implementation
- remaining work for that release is release/docs closure, not missing authoring
  primitives

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

## Release 0.6.0: Provider-Neutral Agent Layer

### Goal

Move the natural-language orchestration glue out of notebooks and into a
public, host-side `wellplot` API while keeping `wellplot-mcp` deterministic and
provider-agnostic.

### Status (2026-05-06)

Current branch status:

- branch in use: `codex/release-mcp-launcher-fix`
- public host-side API is implemented under `wellplot.agent`
- the shared core now owns request/result models, local stdio MCP runtime
  access, tool replay, previews, validation capture, and change summaries
- the natural-language notebook and companion example now import the public API
  instead of embedding provider + MCP orchestration glue
- OpenAI support is implemented as the reference adapter
- one OpenAI-compatible adapter path is implemented through
  `provider="openai_compat"` plus `base_url=...`
- loopback-compatible endpoints such as `http://localhost:11434/v1` now receive
  an automatic placeholder token when no real key is configured
- docs now recommend `OPENAI_API_KEY` or notebook `getpass()` as the primary
  credential flows, with `.env.local` as the local persistent fallback

Anthropic status:

- explicitly deferred from this branch
- the adapter contract remains separate by design
- deferral is intentional, not an untracked gap in the shared-core work

### Problem Statement

The current natural-language notebook proves the workflow, but it exposes too
much infrastructure code to the user:

- MCP stdio session setup
- tool filtering and schema translation
- provider-specific tool-loop control
- API-key loading and environment setup
- result aggregation for previews, validation, and change summaries

That notebook is acceptable as an integration proof, but it is too complex as a
real end-user surface.

### Product Decision

The agent layer should be provider-neutral at the core, but not provider-
identical.

The right boundary is:

- `wellplot.mcp`: deterministic tools, prompts, resources, safety, validation
- `wellplot.agent`: provider-neutral orchestration core
- provider adapters:
  - OpenAI
  - OpenAI-compatible providers
  - Anthropic

This logic should not move into `wellplot-mcp`.

### Keep In The MCP Server

- deterministic tool implementations
- deterministic prompts
- deterministic resources
- server-root/path safety
- validation, preview, and normalized-save semantics

### Keep Out Of The MCP Server

- provider SDK clients
- API-key loading as a server concern
- provider-specific tool-loop behavior
- notebook display code

## Release 0.6.0 Architecture

### Module Shape

Recommended layout:

- `wellplot.agent`
- `wellplot.agent.core`
- `wellplot.agent.mcp`
- `wellplot.agent.providers.openai`
- `wellplot.agent.providers.openai_compat`
- `wellplot.agent.providers.anthropic`

Exact names can change, but the split should remain.

### Core Concepts

#### 1. MCP Session Layer

Responsibilities:

- launch local `wellplot-mcp`
- open and close stdio sessions
- normalize MCP tools/prompts/resources for the agent core
- later support remote MCP as a separate transport mode if needed

Candidate types:

- `LocalStdioMcpSession`
- `McpToolRegistry`
- `McpPromptRegistry`

#### 2. Provider-Neutral Agent Core

Responsibilities:

- accept a natural-language authoring request
- accept a deterministic MCP tool surface
- run a provider adapter until completion or failure
- collect tool trace, final text, previews, validation, and change summary in
  one notebook-friendly result object

Candidate types:

- `AuthoringRequest`
- `AuthoringResult`
- `ToolCallEvent`
- `ToolResultEvent`
- `AgentBackend`

#### 3. Provider Adapters

Adapters translate provider APIs into the shared core contract.

Planned first adapters:

- `OpenAIResponsesBackend`
- `OpenAICompatBackend`
- `AnthropicMessagesBackend`

Notes:

- OpenAI-compatible providers can share a large part of the implementation
- Anthropic should be separate from the beginning
- Ollama should initially be supported only where the OpenAI-compatible path is
  sufficient

#### 4. Execution Modes

Make these explicit:

- local stdio MCP + provider tool loop
- remote MCP + provider-native connector path later, where useful

Do not force them into one fake abstraction too early.

## Release 0.6.0 Provider Strategy

### OpenAI

- first-class
- primary reference implementation

### Hugging Face

- second-wave support through the OpenAI-compatible adapter where practical

### Ollama

- OpenAI-compatible fallback path only
- expect a more manual loop because stateful Responses semantics are weaker

### Anthropic

- separate adapter
- do not hide its API shape behind an OpenAI-specific abstraction

## Release 0.6.0 Public API Shape

The notebook should eventually shrink to something like:

```python
from wellplot.agent import run_authoring_request

result = await run_authoring_request(
    goal="Recreate the porosity example with a simpler header.",
    example_id="forge16b_porosity_example",
    output_logfile="workspace/mcp_demo/openai_forge16b_recreated.log.yaml",
    provider="openai",
    model="gpt-5.4-mini",
)
```

Or an explicit session:

```python
from wellplot.agent import AuthoringSession

session = AuthoringSession.from_local_mcp(provider="openai", model="gpt-5.4-mini")
result = await session.run(
    goal="Add a porosity overlay track and shorten the remarks.",
    example_id="forge16b_porosity_example",
    output_logfile="workspace/mcp_demo/porosity_variant.log.yaml",
)
```

The notebook should consume public `wellplot` interfaces, not embed provider
tool-loop internals.

## Release 0.6.0 Concrete Scope

### In Scope

- public host-side agent API for local stdio `wellplot-mcp`
- provider-neutral orchestration core
- OpenAI adapter
- one OpenAI-compatible adapter path
- notebook refactor to use the new public API
- tests around deterministic orchestration glue where possible
- docs for credentials, optional installs, and supported providers

### Out Of Scope

- moving provider logic into `wellplot-mcp`
- promising perfect feature parity across all providers
- mandatory CI execution of live hosted-model notebooks
- remote MCP transport in the same slice unless it becomes necessary for one
  chosen adapter

## Release 0.6.0 Implementation Order

1. extract the current notebook glue into a private internal prototype module
2. define the provider-neutral result and event model
3. implement local stdio MCP session helpers
4. implement the OpenAI adapter
5. refactor the notebook to use the public agent API
6. add the OpenAI-compatible adapter
7. add the Anthropic adapter
8. document provider capabilities and limitations explicitly

Implementation snapshot:

- steps 1 through 6 are complete on `codex/release-mcp-launcher-fix`
- step 7 is explicitly deferred
- step 8 is complete for the currently supported providers

## Release 0.6.0 Acceptance

`0.6.0` is complete when:

- the natural-language notebook no longer embeds large MCP/provider helper
  cells
- the notebook imports public `wellplot` APIs and remains runnable
- OpenAI works through the shared agent core
- at least one OpenAI-compatible backend also works through the same core
- Anthropic support is either implemented or explicitly deferred with a
  documented adapter contract
- the MCP server itself remains deterministic and unchanged in role

Acceptance snapshot (2026-05-06):

- satisfied: the notebook no longer embeds large MCP/provider helper cells
- satisfied: the notebook imports public `wellplot` APIs
- satisfied: OpenAI works through the shared core
- satisfied: an OpenAI-compatible path works through the same core
- satisfied: Anthropic is now explicitly deferred in this plan
- satisfied: `wellplot-mcp` remains deterministic and unchanged in role

## First Five Operations

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

The current codebase does not need a new public core API, but it does need a
small internal authoring layer.

Recommended additions:

1. Mutable logfile-mapping helpers
   - load one logfile into a normalized mapping
   - locate sections, tracks, and bindings by stable identifiers
   - write the mapping back through the existing canonical serializer
2. Draft mutation service helpers
   - implement edit operations in one internal module that MCP tools call
   - keep all mutations path-based and stateless
3. Shared post-mutation validation
   - every write path should run:
     - schema validation
     - dataset resolution
     - renderable document construction
4. Shared authoring summaries
   - draft summary and change summary should be built from one canonical
     inspector shape
5. Static authoring vocabulary resources
   - keep the first pass hand-authored and explicit
   - derive richer generated catalogs only after the authoring surface settles

## Implementation Order

Recommended build order for `0.4.0`:

1. internal mutable draft mapping helpers
2. `create_logfile_draft(...)`
3. `summarize_logfile_draft(...)`
4. `add_track(...)`
5. `bind_curve(...)`
6. `update_curve_binding(...)`
7. `move_track(...)`
8. `set_heading_content(...)`
9. `set_remarks_content(...)`
10. `inspect_authoring_vocab(...)`
11. `summarize_logfile_changes(...)`
12. prompts, notebook demo, docs, and release hardening

This is enough for a first natural-language-driven workflow where the MCP host
LLM can reliably satisfy requests like:

- add a porosity track
- bind RHOB and NPHI
- set RHOB to red and NPHI to blue
- fill neutron-density crossover in yellow
- add a first-page remark block
- set scales and colors
- add a crossover fill
- apply remarks
- preview the section
- save the draft

## Data Model Work Required

Before the edit surface is ergonomic, we likely need some internal cleanup:

- stable patchable identifiers for:
  - sections
  - tracks
  - bindings
  - heading blocks
  - remark blocks
- helper functions that mutate `LogFileSpec` / normalized mappings without
  duplicating ad hoc YAML surgery across MCP tools
- reusable validation paths for partial edit operations
- explicit header-field key conventions so value mapping is deterministic

## Testing And Evaluation

We need deterministic tests for authoring behavior even though the user-facing
workflow starts from natural language.

Required coverage:

- unit tests for each new authoring tool
- service-layer golden tests for:
  - add track
  - bind curves
  - set scales/styles/fills
  - set headings/remarks
  - save and reload
- stdio integration tests for the main authoring flow
- installed-wheel smoke extension once authoring tools are public

Suggested golden scenarios:

- "add porosity track with RHOB and NPHI"
- "move GR to the right and recolor it"
- "add neutron-density crossover fill"
- "apply these header values"
- "insert this remark block"

## Documentation Work

When this slice lands, docs must explain the boundary clearly:

- the user speaks in natural language to an MCP client
- the client turns that request into `wellplot-mcp` tool calls
- the server applies deterministic edits and returns previews/results

Docs to add or update:

- `README.md`
- `docs/mcp-plan.md`
- `docs/site/workflows/mcp-workflow.md`
- `docs/site/reference/mcp-api.md`
- new authoring examples or notebooks

## Immediate Next Step

The next step is no longer core extraction.

The immediate follow-up is release/documentation closure for the implemented
agent slice:

1. keep the branch docs aligned with the shipped `wellplot.agent` surface
2. merge or rebase the branch back onto `main`
3. decide whether to add one explicit `openai_compat` example before the next
   release cut
4. revisit Anthropic only as a separate follow-on adapter task
