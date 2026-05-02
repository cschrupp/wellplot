# MCP Rollout Status

Last updated: 2026-05-01

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
- the `0.6.0` host-side agent layer that removes provider/session glue from
  end-user notebooks

Planned `0.6.0` focus:

- add `wellplot.agent` as a public host-side orchestration layer
- keep `wellplot-mcp` deterministic and provider-agnostic
- add a provider-neutral core plus thin adapters:
  - OpenAI
  - OpenAI-compatible providers
  - Anthropic
- refactor the natural-language notebook to use the public agent API instead of
  embedded MCP/provider glue

Scope note:

- this is a host-side integration layer, not a redesign of the MCP server
- provider-neutral does not mean provider-identical; adapter differences should
  stay explicit

## Pause Checkpoint (2026-05-01)

This section records the exact repo-local pause point after the first
natural-language notebook prototype and before the `wellplot.agent`
implementation starts.

### Latest Committed Planning Boundary

- branch in use during this checkpoint: `codex/release-mcp-launcher-fix`
- latest planning commit: `8f1823a`
- commit message: `Plan MCP 0.6 provider-neutral agent layer`

### In-Progress Worktree Prototype

The following work exists in the local worktree but is not yet captured in the
committed plan history:

- `.gitignore`
  - ignores local OpenAI token files:
    - `.env`
    - `.env.local`
    - `OPENAI_API_KEY.txt`
    - `openai_api_key.txt`
- `src/wellplot/mcp/service.py`
  - fixes `create_logfile_draft(example_id=...)` so packaged example rebasing
    uses `examples/production/{example_id}` semantics under the current server
    root instead of the installed asset-package path
- `tests/test_mcp_service.py`
  - adds coverage for packaged-example draft rebasing
- `scripts/generate_example_notebooks.py`
  - adds the self-contained natural-language MCP notebook generator
  - contains the current OpenAI-specific orchestration prototype
- `examples/notebooks/developer/mcp_natural_language_demo.ipynb`
  - generated and executed notebook artifact for the OpenAI + local MCP proof
- docs/runtime references:
  - `README.md`
  - `docs/site/guides/examples.md`
  - `examples/notebooks/developer/README.md`

### Notebook Prototype Status

Current prototype notebook:

- `examples/notebooks/developer/mcp_natural_language_demo.ipynb`

What it currently demonstrates:

- local API-key loading from ignored files or environment variables
- OpenAI Responses API driving local stdio `wellplot-mcp`
- deterministic MCP tool execution against the LAS-backed
  `forge16b_porosity_example`
- executed artifact checked in locally with outputs

Current practical outcome:

- the notebook successfully creates and validates a draft at
  `workspace/mcp_demo/openai_forge16b_recreated.log.yaml`
- the recorded run currently applies heading and remarks mutations reliably
- the prototype is useful as a workflow proof, but it is still too provider-
  specific and too glue-heavy for the final user-facing API

Why this matters:

- this prototype confirms that the missing product layer is host-side
  orchestration, not more MCP server functionality
- this is the main justification for the planned `0.6.0` `wellplot.agent`
  layer

### Verified Commands At This Pause Point

The following commands passed against the prototype state:

- `uv run ruff check src/wellplot/mcp/service.py tests/test_mcp_service.py scripts/generate_example_notebooks.py`
- `uv run ruff format --check src/wellplot/mcp/service.py tests/test_mcp_service.py scripts/generate_example_notebooks.py`
- `uv run python -m unittest tests.test_mcp_service tests.test_mcp_server -v`
- `uv run --group docs mkdocs build --strict`
- notebook execution:
  - `uv run python - <<'PY' ... NotebookClient(...).execute() ... PY`

### Runtime Requirements For The Prototype Notebook

- repository checkout is required
- install extras and dependencies in the active environment:
  - `wellplot[mcp,notebook,las]`
  - `openai`
- provide `OPENAI_API_KEY` through one of:
  - environment variable
  - `.env.local`
  - `.env`
  - `OPENAI_API_KEY.txt`
  - `openai_api_key.txt`

Notes:

- those token-file paths are intentionally git-ignored
- the live-model notebook should remain manual or opt-in; it should not become
  a required CI gate

### Recommended Restart Order

When work resumes:

1. review the uncommitted natural-language notebook prototype diff
2. decide whether to commit the prototype state as one checkpoint or split it
   into:
   - MCP packaged-example rebasing fix
   - notebook/generator/docs prototype
3. start the `0.6.0` extraction by moving the orchestration glue from the
   notebook into a host-side internal prototype module
4. define the public `wellplot.agent` request/result/event model
5. implement the OpenAI adapter first
6. then shrink the notebook so it imports the new public API instead of
   embedding the orchestration logic
