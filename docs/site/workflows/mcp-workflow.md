# MCP Workflow

`wellplot` includes an experimental stdio MCP server for local logfile
workflows.

Use it when you want an MCP-aware client to validate, inspect, preview, and
author normalized logfile YAML without adding new Python import surfaces to your
own code.

If you want hosted-model natural-language authoring from Python, use the public
`wellplot.agent` layer on top of this server instead of re-implementing the
provider + MCP tool loop yourself.

## Install

```bash
python -m pip install "wellplot[mcp]"
python -m pip install "wellplot[agent]"
```

Current `wellplot.agent` provider support:

- OpenAI
- OpenAI-compatible endpoints through `provider="openai_compat"` plus
  `base_url=...`

## Agent Credentials

Preferred OpenAI setup:

```bash
export OPENAI_API_KEY="your-key-here"
```

Equivalent ignored local-file sources supported by `wellplot.agent`:

```text
.env.local
.env
OPENAI_API_KEY.txt
openai_api_key.txt
```

Guidance:

- do not hard-code provider keys in notebooks, YAML, or committed example files
- use `.env.local` or `OPENAI_API_KEY.txt` under the job or repository root
  when you want one local persistent secret that stays out of version control
- for `provider="openai_compat"`, loopback endpoints such as
  `http://localhost:11434/v1` receive an automatic placeholder token when no
  key is configured
- non-loopback OpenAI-compatible endpoints still require a real key through
  `api_key=...`, `OPENAI_COMPAT_API_KEY`, `OPENAI_API_KEY`, or `.env.local`

## Launch Model

`wellplot-mcp` is a stdio server. In normal use, an MCP client launches it for
you and keeps the process attached to the session.

Typical client registration:

```json
{
  "mcpServers": {
    "wellplot": {
      "command": "wellplot-mcp",
      "cwd": "/absolute/path/to/job-root"
    }
  }
}
```

## Server-Root Policy

The server root is the current working directory when `wellplot-mcp` starts.

That policy applies to:

- `logfile_path`
- referenced template paths
- referenced section or top-level data sources
- `output_path`
- `output_dir`
- `base_dir`

If any of those resolve outside the server root, the call fails with a clear
path-access error.

## Recommended Review Flow

Use the narrow tools in this order:

1. `validate_logfile(logfile_path)`
2. `inspect_logfile(logfile_path)`
3. one of:
   - `preview_section_png(...)`
   - `preview_track_png(...)`
   - `preview_window_png(...)`
   - `preview_logfile_png(...)` when you really need the generic superset

Why this order:

- validation confirms the logfile and its referenced data are renderable
- inspection gives you valid section ids, track ids, and resolved source paths
- the explicit preview tools are easier for MCP clients than the generic
  preview contract

## Preview Tools

Preferred read-only preview tools:

- `preview_section_png(logfile_path, section_id, page_index=0, dpi=144)`
- `preview_track_png(logfile_path, section_id, track_ids, page_index=0, dpi=144, depth_range=None, depth_range_unit=None)`
- `preview_window_png(logfile_path, depth_range, depth_range_unit=None, page_index=0, dpi=144, section_ids=None)`

All preview tools:

- return in-memory PNG content only
- force the Matplotlib preview path even if the logfile config uses another
  backend
- never write files

Use `render_logfile_to_file(...)` only when you want an explicit on-disk
artifact such as a PDF.

## Data Inspection Flow

When a request starts from raw LAS/DLIS data instead of an existing draft,
inspect the source before you start binding curves.

Main tools:

- `inspect_data_source(source_path, source_format="auto")`
- `check_channel_availability(requested_channels, source_path=None, logfile_path=None, section_id=None, source_format="auto")`

Recommended split:

- use `inspect_data_source(...)` first to discover the source format, shared
  index range, available channels, and basic well metadata
- use `check_channel_availability(...)` before authoring when the user names
  channels or domains such as gamma ray, porosity, resistivity, CBL, or VDL
- use `logfile_path` + `section_id` when you want to confirm availability
  against one draft section rather than the raw source directly

## Authoring Flow

The experimental authoring flow is intentionally conservative:

1. inspect the raw source when the workflow starts from LAS/DLIS data
2. create a normalized draft from an example or existing logfile
3. summarize the draft before issuing authoring edits
4. preview the affected section, track, or window
5. validate or normalize text only when you are operating on unsaved YAML
6. save or render only to explicit output paths

Main tools:

- `inspect_data_source(source_path, source_format="auto")`
- `check_channel_availability(requested_channels, source_path=None, logfile_path=None, section_id=None, source_format="auto")`
- `create_logfile_draft(output_path, example_id=None, source_logfile_path=None, overwrite=False)`
- `summarize_logfile_draft(logfile_path)`
- `set_section_data_source(logfile_path, section_id, source_path, source_format="auto", title=None, subtitle=None)`
- `parse_key_value_text(source_text, format_hint=None)`
- `inspect_heading_slots(logfile_path=None, template_path=None)`
- `preview_header_mapping(logfile_path, values, overwrite_policy="fill_empty")`
- `apply_header_values(logfile_path, values, overwrite_policy="fill_empty")`
- `inspect_style_presets(preset_family=None)`
- `inspect_authoring_vocab(logfile_path=None, template_path=None)`
- `add_track(logfile_path, section_id, id, title, kind, width_mm, x_scale=None, grid=None, track_header=None, reference=None, annotations=None)`
- `update_track(logfile_path, section_id, track_id, patch)`
- `remove_track(logfile_path, section_id, track_id, remove_bindings=True)`
- `bind_curve(logfile_path, section_id, track_id, channel, label=None, style=None, scale=None, header_display=None)`
- `bind_raster(logfile_path, section_id, track_id, channel, ...)`
- `update_curve_binding(logfile_path, section_id, track_id, channel, patch)`
- `update_raster_binding(logfile_path, section_id, track_id, channel, patch)`
- `remove_curve_binding(logfile_path, section_id, track_id, channel)`
- `remove_raster_binding(logfile_path, section_id, track_id, channel)`
- `move_track(logfile_path, section_id, track_id, before_track_id=None, after_track_id=None, position=None)`
- `set_heading_content(logfile_path, patch)`
- `set_remarks_content(logfile_path, remarks)`
- `summarize_logfile_changes(logfile_path, previous_text=None)`
- `export_example_bundle(example_id, output_dir, overwrite=False)`
- `validate_logfile_text(yaml_text, base_dir=None)`
- `format_logfile_text(yaml_text, base_dir=None)`
- `save_logfile_text(yaml_text, output_path, overwrite=False, base_dir=None)`

Recommended split:

- use `inspect_data_source(...)` and `check_channel_availability(...)` before
  draft creation when the request starts from one raw LAS/DLIS source
- use `create_logfile_draft(...)` + `summarize_logfile_draft(...)` when you
  want a file-backed authoring target that an MCP client can revise in steps
- use `set_section_data_source(...)` when a starter draft should be switched to
  one user LAS/DLIS file before you start adding tracks and bindings
- use `parse_key_value_text(...)` when the source material is a copied header
  packet, tabular note block, or other simple key-value text
- use `inspect_heading_slots(...)` when the next task is filling provider
  fields, general report fields, service titles, detail-table cells, or
  remarks content from external text
- use `preview_header_mapping(...)` after you extract header values but before
  you write anything into the draft; it will surface ambiguous keys,
  overwrite-policy conflicts, and the exact heading patch it would apply
- use `apply_header_values(...)` only after the preview looks right; it writes
  the same deterministic mapping result back into the draft and returns the
  saved heading summary
- use `inspect_style_presets(...)` when the request is mostly about visual
  conventions such as color, fill, contrast, scale defaults, or common
  CBL/VDL, porosity, gamma-ray, and resistivity layouts
- use `inspect_authoring_vocab(...)` before major edits so the client sees the
  valid track kinds, fill kinds, heading fields, and any available channels in
  the current draft
- use `add_track(...)`, `update_track(...)`, `remove_track(...)`,
  `bind_curve(...)`, `bind_raster(...)`, `update_curve_binding(...)`,
  `update_raster_binding(...)`, `remove_curve_binding(...)`,
  `remove_raster_binding(...)`, and `move_track(...)` for the deterministic
  track/layout edit loop
- use `set_heading_content(...)` and `set_remarks_content(...)` for first-page
  report text and summary-block edits
- use `summarize_logfile_changes(...)` when the client kept the prior YAML text
  and needs a structural review summary before render or save
- use `validate_logfile_text(...)`, `format_logfile_text(...)`, and
  `save_logfile_text(...)` when the client is still working with unsaved YAML
  text in memory

## Iterative Agent Pattern

For hosted-model authoring from Python, the public `wellplot.agent` layer is
meant to be iterative rather than one giant prompt.

Recommended split:

- use `await session.run(...)` once to seed the first draft from either
  `example_id` or `source_logfile_path`
- use `await session.revise(...)` for later notebook cells and user feedback
- use `await session.render_logfile_to_file(...)` for the final MCP-backed PDF
  render once the previews look correct

This is the pattern used by the step-by-step user notebook:

- `examples/notebooks/user/agent_las_step_by_step.ipynb`

## `base_dir` Semantics

`base_dir` is used only for unsaved text workflows.

When provided, `validate_logfile_text(...)`, `format_logfile_text(...)`, and
`save_logfile_text(...)` resolve relative paths from that directory under the
server root. This matters for:

- `template.path`
- top-level `data.source_path`
- section-level `data.source_path`

When `save_logfile_text(...)` writes the normalized YAML, relative paths are
rebased so they still resolve correctly from the saved file location.

## Normalization Boundary

`format_logfile_text(...)` and `save_logfile_text(...)` operate on the
normalized report representation.

That means:

- comments are not preserved
- YAML anchors are not preserved
- original formatting is not preserved
- template indirection is materialized into canonical YAML

Use the authoring tools when you want a clean, validated logfile artifact, not
when you need a comment-preserving editor.

## Packaged Resources And Prompts

The server also exposes:

- schema and example resources for discovery and example adaptation
- authoring catalog resources for deterministic edit planning
- prompts for logfile review, preview, example-driven starts, and
  natural-language-to-tool authoring flows
- `ingest_header_text(...)` for copied header packets that should move through
  parse -> preview mapping -> apply mapping instead of ad hoc edits

See [MCP API](../reference/mcp-api.md) for the exact tool, resource, and prompt
names.
