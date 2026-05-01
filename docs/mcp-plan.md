# MCP Rollout Status

Last updated: 2026-04-29

## Purpose

This document is the live repo-local status document for the experimental
`wellplot` MCP surface.

The original extracted v1 plan has now been implemented and extended. This file
tracks what is actually in the repository, what release it is being prepared
for, and what still requires maintainer action outside the repo.

## Release Status

- Repo target version: `0.3.0`
- Public status: experimental
- Transport: stdio-first through `wellplot-mcp`
- Packaging:
  - optional extra: `wellplot[mcp]`
  - console entry point: `wellplot-mcp`
- Release note boundary:
  - the originally planned scoped-preview slice and writable-authoring slice
    landed together in the current tree and are being released together as
    `0.3.0`

## Implemented Surface

### Tools

- `validate_logfile(logfile_path)`
- `inspect_logfile(logfile_path)`
- `preview_logfile_png(...)`
- `preview_section_png(logfile_path, section_id, page_index=0, dpi=144)`
- `preview_track_png(logfile_path, section_id, track_ids, page_index=0, dpi=144, depth_range=None, depth_range_unit=None)`
- `preview_window_png(logfile_path, depth_range, depth_range_unit=None, page_index=0, dpi=144, section_ids=None)`
- `render_logfile_to_file(logfile_path, output_path, overwrite=False)`
- `export_example_bundle(example_id, output_dir, overwrite=False)`
- `create_logfile_draft(output_path, example_id=None, source_logfile_path=None, overwrite=False)`
- `summarize_logfile_draft(logfile_path)`
- `add_track(logfile_path, section_id, id, title, kind, width_mm, x_scale=None, grid=None, track_header=None, reference=None, annotations=None)`
- `bind_curve(logfile_path, section_id, track_id, channel, label=None, style=None, scale=None, header_display=None)`
- `update_curve_binding(logfile_path, section_id, track_id, channel, patch)`
- `validate_logfile_text(yaml_text, base_dir=None)`
- `format_logfile_text(yaml_text, base_dir=None)`
- `save_logfile_text(yaml_text, output_path, overwrite=False, base_dir=None)`

### Resources

- `wellplot://schema/logfile.json`
- `wellplot://examples/production/index.json`
- `wellplot://examples/production/{example_id}/README.md`
- `wellplot://examples/production/{example_id}/base.template.yaml`
- `wellplot://examples/production/{example_id}/full_reconstruction.log.yaml`
- `wellplot://examples/production/{example_id}/data-notes.md`

Packaged example ids:

- `cbl_log_example`
- `forge16b_porosity_example`

### Prompts

- `review_logfile(logfile_path)`
- `preview_logfile(logfile_path, focus=None)`
- `start_from_example(example_id, goal)`

## Behavior and Safety Notes

- The server root is the current working directory when `wellplot-mcp` starts.
- File-based tools may only read from and write to paths that resolve inside
  that root.
- Preview tools are read-only and always return in-memory PNG content rendered
  through Matplotlib.
- Explicit writes only happen through:
  - `render_logfile_to_file(...)`
  - `export_example_bundle(...)`
  - `create_logfile_draft(...)`
  - `add_track(...)`
  - `bind_curve(...)`
  - `update_curve_binding(...)`
  - `save_logfile_text(...)`
- `validate_logfile_text(...)`, `format_logfile_text(...)`, and
  `save_logfile_text(...)` accept unsaved full logfile YAML text. When
  `base_dir` is provided, relative template and data references are resolved
  from that directory under the server root.
- `format_logfile_text(...)` and `save_logfile_text(...)` normalize the logfile
  through the canonical serializer path. They do not preserve comments,
  anchors, original formatting, or template indirection.

## Implementation Notes

- `wellplot` and `wellplot.api` import surfaces remain unchanged.
- The implementation lives in:
  - `src/wellplot/mcp/server.py`
  - `src/wellplot/mcp/service.py`
  - packaged example assets under `src/wellplot/mcp/assets/`
- Release verification now includes:
  - base installed-wheel smoke coverage
  - a second clean-environment smoke path with the optional MCP dependency
    enabled
- Scoped preview filtering now preserves implicit bindings for single-section
  savefiles, which was necessary for reliable section/track MCP previews.

## Verification In Repo

Primary coverage now includes:

- service-layer tests in `tests/test_mcp_service.py`
- stdio integration and registration tests in `tests/test_mcp_server.py`
- installed-wheel smoke coverage in `scripts/smoke_installed_wheel.py`
- release workflow MCP verification in `.github/workflows/release.yml`
- public documentation pages under `docs/site/`

## Remaining Maintainer Actions

The following actions are intentionally outside this repo-local implementation
document and still need to happen through the normal release flow:

1. Run the GitHub `Release` workflow with `publish_target=verify-only`.
2. Run a TestPyPI rehearsal for `0.3.0`.
3. Publish `0.3.0` to PyPI.
4. Let the merged documentation changes publish through the normal docs path to
   Read the Docs and the GitHub Pages mirror.

## Next Planned Slice

After the `0.3.0` experimental release is out, the next MCP milestone should be
natural-language-driven authoring.

Key direction:

- keep freeform language understanding in the MCP client or host LLM
- expand `wellplot-mcp` with deterministic authoring tools, vocabularies,
  prompts, and draft workflows
- avoid server-side opaque YAML rewrites from raw freeform text

Detailed plan:

- [docs/mcp-authoring-plan.md](mcp-authoring-plan.md)

Concrete `0.4.0` foundation tools:

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

The full `0.4.0` deterministic authoring foundation now exists in the
repository, including:

- draft lifecycle tools
- deterministic track/curve/heading/remarks edit tools
- authoring vocabulary inspection plus catalog resources
- structural change summaries
- LLM-facing prompts for freeform authoring and revision

The next MCP-focused implementation slice should now move to the richer
`0.5.0` ingestion and workflow ergonomics work described in
[docs/mcp-authoring-plan.md](mcp-authoring-plan.md).

Planned `0.5.0` focus:

- `inspect_data_source(...)`
- `check_channel_availability(...)`
- `inspect_heading_slots(...)`
- `preview_header_mapping(...)`
- `apply_header_values(...)`
- `parse_key_value_text(...)`
- `inspect_style_presets(...)`
- header/style catalog resources
- `ingest_header_text(...)` prompt

Scope note:

- standalone source inspection in this phase is for LAS and DLIS only; LIS
  support is not planned in this slice.

Implemented so far in `0.5.0`:

- `inspect_data_source(...)`
- `check_channel_availability(...)`
- `inspect_heading_slots(...)`
- `preview_header_mapping(...)`
- `apply_header_values(...)`
- `parse_key_value_text(...)`
- `inspect_style_presets(...)`
- `ingest_header_text(...)` prompt
- `wellplot://authoring/catalog/header-key-aliases.json`
- `wellplot://authoring/catalog/style-presets.json`

Next up:

- release/docs closure for the completed `0.5.0` MCP workflow slice
