# MCP API

This page documents the experimental MCP server surface exposed by
`wellplot[mcp]`.

## Status And Boundary

- status: experimental
- transport: stdio
- entry point: `wellplot-mcp`
- import boundary:
  - no new public `wellplot` or `wellplot.api` imports were added for this
    feature
  - the public surface is the MCP server contract itself

## Root Policy

The server root is the current working directory when `wellplot-mcp` starts.

These inputs must resolve inside that root:

- logfile paths
- template references
- data source paths
- `base_dir`
- output directories
- output file paths

Preview tools are always read-only. Write-capable tools require explicit output
paths or directories.

## Tools

### `validate_logfile(logfile_path)`

Purpose: validate one saved logfile path and its referenced inputs.

Returns:

- `valid`
- `message`
- `name`
- `render_backend`
- `section_ids`

### `inspect_logfile(logfile_path)`

Purpose: inspect one saved logfile path and discover valid preview ids.

Returns:

- `name`
- `render_backend`
- `configured_output_path`
- `page_settings`
- `depth_settings`
- `has_heading`
- `has_remarks`
- `has_tail`
- `section_ids`
- `sections`

Each section record contains:

- `id`
- `title`
- `source_path`
- `source_format`
- `depth_range`
- `track_ids`
- `track_kinds`

### `preview_logfile_png(logfile_path, page_index=0, dpi=144, section_id=None, track_ids=None, depth_range=None, depth_range_unit=None, include_report_pages=True)`

Purpose: generic superset preview tool for whole-report or filtered PNG output.

Behavior:

- returns one MCP image payload
- forces the Matplotlib preview path
- supports report pages, scoped sections, scoped tracks, and depth windows

### `preview_section_png(logfile_path, section_id, page_index=0, dpi=144)`

Purpose: preview one section without using the generic preview contract.

Behavior:

- returns one MCP image payload
- validates that `section_id` exists

### `preview_track_png(logfile_path, section_id, track_ids, page_index=0, dpi=144, depth_range=None, depth_range_unit=None)`

Purpose: preview one or more tracks inside one section.

Behavior:

- returns one MCP image payload
- validates `section_id`
- validates that each requested track id exists inside that section
- rejects an empty `track_ids` selection

### `preview_window_png(logfile_path, depth_range, depth_range_unit=None, page_index=0, dpi=144, section_ids=None)`

Purpose: preview a bounded depth window, optionally filtered to selected
sections.

Behavior:

- returns one MCP image payload
- validates that the depth range has positive height
- validates requested section ids when provided

### `render_logfile_to_file(logfile_path, output_path, overwrite=False)`

Purpose: render the full report to an explicit file path.

Returns:

- `backend`
- `page_count`
- `output_path`

Behavior:

- uses the configured render backend
- writes only when `output_path` is explicit
- rejects existing targets unless `overwrite=True`

### `export_example_bundle(example_id, output_dir, overwrite=False)`

Purpose: export one packaged production example into a writable directory under
the server root.

Returns:

- `example_id`
- `output_dir`
- `written_files`

Exported files:

- `README.md`
- `base.template.yaml`
- `full_reconstruction.log.yaml`
- `data-notes.md`

### `create_logfile_draft(output_path, example_id=None, source_logfile_path=None, overwrite=False)`

Purpose: create one normalized draft logfile from either a packaged example or
an existing logfile.

Returns:

- `output_path`
- `name`
- `section_ids`
- `seed_kind`
- `seed_value`

Behavior:

- requires exactly one seed source:
  - `example_id`, or
  - `source_logfile_path`
- writes only to an explicit `output_path`
- rejects existing targets unless `overwrite=True`
- normalizes the draft through the canonical serializer path
- rebases relative render and data paths so the cloned draft resolves from its
  new location

### `summarize_logfile_draft(logfile_path)`

Purpose: inspect one draft logfile for deterministic authoring workflows.

Returns:

- `name`
- `render_backend`
- `configured_output_path`
- `has_heading`
- `has_remarks`
- `has_tail`
- `section_count`
- `section_ids`
- `sections`

Each section record contains:

- `id`
- `title`
- `source_path`
- `source_format`
- `depth_range`
- `track_ids`
- `track_kinds`
- `curve_binding_count`
- `raster_binding_count`
- `available_channels`
- `dataset_loaded`
- `dataset_message`

Notes:

- this is the preferred inspect-first tool for draft authoring flows
- channel discovery is best-effort and depends on the referenced data source
  and optional format dependencies being available

### `add_track(logfile_path, section_id, id, title, kind, width_mm, x_scale=None, grid=None, track_header=None, reference=None, annotations=None)`

Purpose: append one track to a draft logfile and persist the validated result.

Returns:

- `logfile_path`
- `section_id`
- `track_id`
- `track_ids`
- `track_count`

Behavior:

- appends the new track at the end of the target section
- writes back to the explicit `logfile_path`
- rejects duplicate track ids within the target section
- validates the mutated draft through the normal renderable logfile path before
  saving

### `bind_curve(logfile_path, section_id, track_id, channel, label=None, style=None, scale=None, header_display=None)`

Purpose: add one scalar curve binding to an existing draft track.

Returns:

- `logfile_path`
- `section_id`
- `track_id`
- `channel`
- `binding_kind`
- `binding_count`

Behavior:

- resolves the requested channel against the target section dataset
- rejects duplicate curve bindings for the same section, track, and channel
- writes back to the explicit `logfile_path`
- validates the mutated draft before saving

### `update_curve_binding(logfile_path, section_id, track_id, channel, patch)`

Purpose: patch one existing curve binding inside a draft logfile.

Returns:

- `logfile_path`
- `section_id`
- `track_id`
- `channel`
- `binding`

Supported patch keys:

- `label`
- `style`
- `scale`
- `header_display`
- `fill`
- `reference_overlay`
- `value_labels`
- `wrap`
- `render_mode`

Behavior:

- deep-merges nested mapping updates
- removes optional properties when their patch value is `null`
- rejects unsupported patch keys
- writes back to the explicit `logfile_path`
- validates the mutated draft before saving

### `move_track(logfile_path, section_id, track_id, before_track_id=None, after_track_id=None, position=None)`

Purpose: reorder one track inside a draft logfile.

Returns:

- `logfile_path`
- `section_id`
- `track_id`
- `track_ids`
- `track_count`

Behavior:

- requires exactly one target selector:
  - `before_track_id`, or
  - `after_track_id`, or
  - `position`
- renumbers the full section track order before saving
- writes back to the explicit `logfile_path`
- validates the mutated draft before saving

### `set_heading_content(logfile_path, patch)`

Purpose: patch the report heading block inside a draft logfile.

Returns:

- `logfile_path`
- `has_heading`
- `has_tail`
- `heading`

Supported patch keys:

- `enabled`
- `provider_name`
- `general_fields`
- `service_titles`
- `detail`
- `tail_enabled`

Behavior:

- deep-merges nested heading mapping updates
- removes optional properties when their patch value is `null`
- defaults `heading.enabled` to `true` when omitted
- accepts `tail_enabled` on the heading patch and materializes
  `layout.tail.enabled` in the normalized YAML
- rejects unsupported patch keys
- writes back to the explicit `logfile_path`
- validates the mutated draft before saving

### `set_remarks_content(logfile_path, remarks)`

Purpose: replace the first-page remarks block inside a draft logfile.

Returns:

- `logfile_path`
- `remarks_count`
- `remarks`

Behavior:

- replaces the full remarks list rather than appending to it
- writes back to the explicit `logfile_path`
- validates the mutated draft before saving

### `inspect_authoring_vocab(logfile_path=None, template_path=None)`

Purpose: expose deterministic authoring vocabularies plus optional draft or
template context.

Returns:

- `track_kinds`
- `scale_kinds`
- `curve_fill_kinds`
- `report_detail_kinds`
- `track_header_object_kinds`
- `heading_patch_keys`
- `curve_binding_patch_keys`
- `move_track_selectors`
- `heading_field_catalog`
- `track_archetypes`
- `resource_uris`
- `target_summary`

Behavior:

- accepts at most one target:
  - `logfile_path`, or
  - `template_path`
- without a target, still returns the static authoring catalogs
- with `logfile_path`, includes section ids, track ids, available channels, and
  heading/remarks state from the current draft
- with `template_path`, includes heading-field and section/track context from
  the referenced template mapping

### `summarize_logfile_changes(logfile_path, previous_text=None)`

Purpose: summarize structural draft changes relative to an optional earlier YAML
snapshot.

Returns:

- `logfile_path`
- `changed`
- `message`
- `section_ids`
- `added_tracks_by_section`
- `removed_tracks_by_section`
- `reordered_tracks_by_section`
- `added_curve_bindings`
- `removed_curve_bindings`
- `updated_curve_bindings`
- `heading_changed`
- `remarks_changed`
- `render_output_changed`
- `summary_lines`

Behavior:

- when `previous_text` is omitted, returns a usage hint instead of inventing a
  diff baseline
- compares normalized report structures, not raw YAML formatting
- focuses on structural changes relevant to the current deterministic authoring
  surface

### `validate_logfile_text(yaml_text, base_dir=None)`

Purpose: validate unsaved full logfile YAML text.

Returns the same structured fields as `validate_logfile(...)`:

- `valid`
- `message`
- `name`
- `render_backend`
- `section_ids`

Notes:

- `base_dir` is optional
- when provided, relative template and data paths are resolved from that
  directory under the server root

### `format_logfile_text(yaml_text, base_dir=None)`

Purpose: validate and normalize full logfile YAML text through the canonical
serializer path.

Returns:

- `name`
- `render_backend`
- `section_ids`
- `yaml_text`

Normalization boundary:

- comments are not preserved
- YAML anchors are not preserved
- original formatting is not preserved
- template indirection is flattened into canonical YAML

### `save_logfile_text(yaml_text, output_path, overwrite=False, base_dir=None)`

Purpose: validate, normalize, and write full logfile YAML text to an explicit
path.

Returns:

- `name`
- `render_backend`
- `section_ids`
- `output_path`

Behavior:

- rejects existing targets unless `overwrite=True`
- rebases relative template and data paths so the saved normalized YAML still
  resolves correctly from the output location

## Resources

Static resources:

- `wellplot://schema/logfile.json`
- `wellplot://examples/production/index.json`
- `wellplot://authoring/schema/patch.json`
- `wellplot://authoring/catalog/track-kinds.json`
- `wellplot://authoring/catalog/fill-kinds.json`
- `wellplot://authoring/catalog/track-archetypes.json`
- `wellplot://authoring/catalog/header-fields.json`

Resource templates:

- `wellplot://examples/production/{example_id}/README.md`
- `wellplot://examples/production/{example_id}/base.template.yaml`
- `wellplot://examples/production/{example_id}/full_reconstruction.log.yaml`
- `wellplot://examples/production/{example_id}/data-notes.md`

Supported packaged example ids:

- `cbl_log_example`
- `forge16b_porosity_example`

## Prompts

Prompt names:

- `review_logfile(logfile_path)`
- `preview_logfile(logfile_path, focus=None)`
- `start_from_example(example_id, goal)`
- `author_plot_from_request(goal, logfile_path=None, example_id=None)`
- `revise_plot_from_feedback(logfile_path, feedback)`

Intent:

- `review_logfile` guides the validate -> inspect -> summarize path
- `preview_logfile` guides the validate -> inspect -> preview path
- `start_from_example` embeds example resources and asks the client to adapt
  them to a stated goal
- `author_plot_from_request` guides a host model toward deterministic authoring
  edits instead of full YAML rewrites
- `revise_plot_from_feedback` guides iterative draft revision plus preview and
  structural change review

## Suggested Client Order

For existing files:

1. `validate_logfile(...)`
2. `inspect_logfile(...)`
3. a narrow preview tool
4. `render_logfile_to_file(...)` only when you want an artifact on disk

For new YAML authoring:

1. `export_example_bundle(...)` when you want a starter packet
2. `validate_logfile_text(...)`
3. `format_logfile_text(...)`
4. `save_logfile_text(...)`

For draft authoring:

1. `create_logfile_draft(...)`
2. `summarize_logfile_draft(...)`
3. `inspect_authoring_vocab(...)`
4. apply `add_track(...)`, `bind_curve(...)`, `update_curve_binding(...)`,
   `move_track(...)`, `set_heading_content(...)`, and
   `set_remarks_content(...)`
5. `summarize_logfile_changes(...)` when the client retained a previous YAML
   snapshot
6. preview with a narrow PNG tool
7. render or save only after review
