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

1. start from a packaged example bundle when useful
2. generate or edit full logfile YAML text
3. validate the text before writing
4. normalize it through the canonical serializer path
5. save only to an explicit output path

Main tools:

- `export_example_bundle(example_id, output_dir, overwrite=False)`
- `validate_logfile_text(yaml_text, base_dir=None)`
- `format_logfile_text(yaml_text, base_dir=None)`
- `save_logfile_text(yaml_text, output_path, overwrite=False, base_dir=None)`

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
- prompts for logfile review, preview, and example-driven starts

See [MCP API](../reference/mcp-api.md) for the exact tool, resource, and prompt
names.
