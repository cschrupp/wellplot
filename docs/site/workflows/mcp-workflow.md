# MCP Workflow

`wellplot` includes an experimental stdio MCP server for local logfile
workflows.

Use it when you want an MCP-aware client to validate, inspect, preview, and
author normalized logfile YAML without adding new Python import surfaces to your
own code.

## Install

```bash
python -m pip install "wellplot[mcp]"
```

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

## Authoring Flow

The experimental authoring flow is intentionally conservative:

1. create a normalized draft from an example or existing logfile
2. summarize the draft before issuing authoring edits
3. preview the affected section, track, or window
4. validate or normalize text only when you are operating on unsaved YAML
5. save or render only to explicit output paths

Main tools:

- `create_logfile_draft(output_path, example_id=None, source_logfile_path=None, overwrite=False)`
- `summarize_logfile_draft(logfile_path)`
- `inspect_authoring_vocab(logfile_path=None, template_path=None)`
- `add_track(logfile_path, section_id, id, title, kind, width_mm, x_scale=None, grid=None, track_header=None, reference=None, annotations=None)`
- `bind_curve(logfile_path, section_id, track_id, channel, label=None, style=None, scale=None, header_display=None)`
- `update_curve_binding(logfile_path, section_id, track_id, channel, patch)`
- `move_track(logfile_path, section_id, track_id, before_track_id=None, after_track_id=None, position=None)`
- `set_heading_content(logfile_path, patch)`
- `set_remarks_content(logfile_path, remarks)`
- `summarize_logfile_changes(logfile_path, previous_text=None)`
- `export_example_bundle(example_id, output_dir, overwrite=False)`
- `validate_logfile_text(yaml_text, base_dir=None)`
- `format_logfile_text(yaml_text, base_dir=None)`
- `save_logfile_text(yaml_text, output_path, overwrite=False, base_dir=None)`

Recommended split:

- use `create_logfile_draft(...)` + `summarize_logfile_draft(...)` when you
  want a file-backed authoring target that an MCP client can revise in steps
- use `inspect_authoring_vocab(...)` before major edits so the client sees the
  valid track kinds, fill kinds, heading fields, and any available channels in
  the current draft
- use `add_track(...)`, `bind_curve(...)`, `update_curve_binding(...)`, and
  `move_track(...)` for the deterministic track/layout edit loop
- use `set_heading_content(...)` and `set_remarks_content(...)` for first-page
  report text and summary-block edits
- use `summarize_logfile_changes(...)` when the client kept the prior YAML text
  and needs a structural review summary before render or save
- use `validate_logfile_text(...)`, `format_logfile_text(...)`, and
  `save_logfile_text(...)` when the client is still working with unsaved YAML
  text in memory

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

See [MCP API](../reference/mcp-api.md) for the exact tool, resource, and prompt
names.
