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

Intent:

- `review_logfile` guides the validate -> inspect -> summarize path
- `preview_logfile` guides the validate -> inspect -> preview path
- `start_from_example` embeds example resources and asks the client to adapt
  them to a stated goal

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
3. preview with a narrow PNG tool
4. apply future explicit edit tools
5. render or save only after review
