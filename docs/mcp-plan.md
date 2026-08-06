# MCP Rollout Status

Last updated: 2026-08-06

## Purpose

This document is the live repo-local status document for the experimental
`wellplot` MCP surface.

The original extracted v1 plan has now been implemented and extended. This file
tracks what is actually in the repository, what release it is being prepared
for, and what still requires maintainer action outside the repo.

## Strategic Direction

The MCP surface is being corrected back toward the final-user product goal:

- scientists should be able to describe and iteratively refine plots without
  needing to know internal application mechanics
- MCP should expose deterministic authoring objects and tools
- defaults should fill missing details only
- explicit user instructions should override defaults and scaffolds

The canonical direction for this correction is documented in
[docs/mcp-authoring-model.md](mcp-authoring-model.md).

Implementation inventory and slice plan:

- [docs/authoring-contract-inventory.md](authoring-contract-inventory.md)
- [docs/mcp-implementation-plan.md](mcp-implementation-plan.md)

## Release Status

- Published package metadata: `0.3.0`
- Branch release target: `0.6.0`, not ready to publish
- Public status: experimental
- Transport: stdio-first through `wellplot-mcp`
- Packaging:
  - optional extra: `wellplot[mcp]`
  - console entry point: `wellplot-mcp`
- Release boundary:
  - post-`0.3.0` tool, ingestion, and agent capabilities are implemented in the
    current branch
  - `0.6.0` is blocked on canonical authoring contract, object CRUD, MCP parity,
    defaults precedence, agent revalidation, and release closure

## Implemented Surface

This section is a capability snapshot, not evidence that every object has a
complete canonical contract.

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
- `inspect_data_source(...)`
- `check_channel_availability(...)`
- `set_section_data_source(...)`
- `replicate_section_structure(...)`
- `set_depth_axis(logfile_path, unit=None, scale=None, major_step=None, minor_step=None)`
- `update_section(logfile_path, section_id, title=None, subtitle=None, depth_range=None, depth_range_unit=None)`
- `set_page_layout(logfile_path, page_patch=None, render_patch=None)`
- `set_matplotlib_style(...)`
- `set_section_view(logfile_path, section_id, title=None, subtitle=None, depth_range=None, depth_range_unit=None, unit=None, scale=None, major_step=None, minor_step=None, page_patch=None, render_patch=None)`
- `add_track(logfile_path, section_id, id, title, kind, width_mm, x_scale=None, grid=None, track_header=None, reference=None, annotations=None)`
- `update_track(logfile_path, section_id, track_id, patch)`
- `inspect_track_bindings(...)`
- `set_track_scales(...)`
- `add_annotation_object(logfile_path, section_id, track_id, annotation, position=None)`
- `update_annotation_object(logfile_path, section_id, track_id, annotation_index, patch)`
- `remove_annotation_object(logfile_path, section_id, track_id, annotation_index)`
- `remove_track(logfile_path, section_id, track_id, remove_bindings=True)`
- `bind_curve(logfile_path, section_id, track_id, channel, label=None, style=None, scale=None, header_display=None)`
- `add_curve_fill(logfile_path, section_id, track_id, channel, kind, ...)`
- `remove_curve_fill(logfile_path, section_id, track_id, channel)`
- `clear_track_bindings(logfile_path, section_id, track_id)`
- `bind_raster(logfile_path, section_id, track_id, channel, ...)`
- `update_curve_binding(logfile_path, section_id, track_id, channel, patch)`
- `update_raster_binding(logfile_path, section_id, track_id, channel, patch)`
- `remove_curve_binding(logfile_path, section_id, track_id, channel)`
- `remove_raster_binding(logfile_path, section_id, track_id, channel)`
- `move_track(...)`
- `set_heading_content(...)`
- `set_remarks_content(...)`
- `inspect_header_archetypes(...)`
- `inspect_packet_blueprints(...)` (transitional discovery surface)
- `apply_header_archetype(...)`
- `inspect_heading_slots(...)`
- `parse_key_value_text(...)`
- `preview_header_mapping(...)`
- `apply_header_values(...)`
- `inspect_style_presets(...)`
- `apply_style_preset(...)`
- `inspect_authoring_vocab(...)`
- `summarize_logfile_changes(...)`
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
- `wellplot://authoring/schema/patch.json`
- `wellplot://authoring/catalog/track-kinds.json`
- `wellplot://authoring/catalog/fill-kinds.json`
- `wellplot://authoring/catalog/track-archetypes.json`
- `wellplot://authoring/catalog/header-archetypes.json`
- `wellplot://authoring/catalog/packet-blueprints.json` (transitional)
- `wellplot://authoring/catalog/style-presets.json`
- `wellplot://authoring/catalog/header-fields.json`
- `wellplot://authoring/catalog/header-key-aliases.json`
- `wellplot://authoring/catalog/channel-aliases.json`

Packaged example ids:

- `cbl_log_example`
- `forge16b_porosity_example`

### Prompts

- `review_logfile(logfile_path)`
- `preview_logfile(logfile_path, focus=None)`
- `start_from_example(example_id, goal)`
- `author_plot_from_request(goal, logfile_path=None, example_id=None)`
- `revise_plot_from_feedback(logfile_path, feedback)`
- `ingest_header_text(logfile_path, source_text, source_description=None)`

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
  - `set_section_data_source(...)`
  - `replicate_section_structure(...)`
  - `update_section(...)`
  - `set_depth_axis(...)`
  - `set_page_layout(...)`
  - `set_matplotlib_style(...)`
  - `set_section_view(...)`
  - `add_track(...)`
  - `update_track(...)`
  - `set_track_scales(...)`
  - `add_annotation_object(...)`
  - `update_annotation_object(...)`
  - `remove_annotation_object(...)`
  - `remove_track(...)`
  - `bind_curve(...)`
  - `add_curve_fill(...)`
  - `remove_curve_fill(...)`
  - `bind_raster(...)`
  - `update_curve_binding(...)`
  - `update_raster_binding(...)`
  - `remove_curve_binding(...)`
  - `remove_raster_binding(...)`
  - `clear_track_bindings(...)`
  - `move_track(...)`
  - `set_heading_content(...)`
  - `set_remarks_content(...)`
  - `apply_header_values(...)`
  - `apply_header_archetype(...)`
  - `apply_style_preset(...)`
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

There is no immediate publish action. Before the normal release flow resumes:

1. Complete deterministic contract slices `0.6-A` through `0.6-E`.
2. Complete defaults/precedence and agent revalidation in `0.6-F` and `0.6-G`.
3. Resolve the MCP stdio integration test that currently does not complete
   reliably in the local release audit.
4. Run unit, schema/MCP parity, agent, docs, notebook, and installed-wheel
   acceptance gates.
5. Update version, changelog, release notes, and public references to the actual
   shipped surface.
6. Resume verify-only, TestPyPI, and PyPI publishing through the documented
   release workflow.

## Next Planned Slice

The next implementation slice is `0.6-A`: canonical contract inventory and
ownership. Do not add provider features, packet-specific reconciliation, or
convenience mutation verbs before this slice resolves the duplicated contract.

Required sequence:

1. inventory objects, fields, constraints, relationships, and current owners
2. implement strict canonical authoring models and generated schema
3. add YAML compatibility and renderer adapters
4. implement complete typed deterministic object operations
5. route MCP through the object service and enforce contract parity
6. add defaults with explicit precedence
7. rebase the agent and close release acceptance

Detailed plan:

- [docs/mcp-implementation-plan.md](mcp-implementation-plan.md)

## Product-Direction Risks In The Current Tree

The packet-planning experiment surfaced useful needs such as:

- phase planning
- deterministic verification
- explicit progress reporting

But it also exposed a product risk:

- packet-specific blueprint reconciliation can become a hidden authority that
  silently overrides explicit user instructions

That behavior does not match the intended user experience. Future MCP/agent
cleanup should keep the useful planning and verification lessons while
replacing hidden packet authority with explicit object-level edits plus
fallback defaults.

Additional deterministic risk:

- fields, defaults, enums, parsers, and patch keys are duplicated across model,
  schema, builder, MCP, and agent layers
- complete add/update/remove tool coverage does not exist for every persisted
  object, and getter coverage is uneven

The correction keeps MCP deterministic and provider-agnostic, but it does
change the implementation foundation: MCP becomes a thin projection of one
shared canonical object service rather than an independent dictionary-mutation
layer.

## Implementation Checkpoint (2026-05-06)

This section records the repo-local state after the `wellplot.agent`
implementation landed on `codex/release-mcp-launcher-fix`.

This is a historical checkpoint. Its recommended next steps are superseded by
the current `0.6-A` through `0.6-G` contract program above.

### Latest Branch Boundary

- branch in use during this checkpoint: `codex/release-mcp-launcher-fix`
- latest branch commit at this checkpoint: `881068c`
- commit message: `agent streamline credential onboarding`

### Delivered In This Slice

- `wellplot.agent` is implemented as the public host-side orchestration layer
- the shared core now owns:
  - request/result models
  - local stdio MCP runtime launch
  - tool replay through the provider loop
  - preview, validation, and change-summary aggregation
- provider adapters implemented in this branch:
  - OpenAI
  - one OpenAI-compatible path through `provider="openai_compat"`
- the natural-language notebook and example script now import the public API
  instead of embedding provider/MCP session glue
- credential guidance is now documented around:
  - `OPENAI_API_KEY`
  - notebook `getpass()` fallback
  - `.env.local` as the local persistent secret-file option
- loopback-compatible endpoints such as `http://localhost:11434/v1` now accept
  an automatic placeholder token when no real key is configured

### Explicit Deferral

- Anthropic is deferred from the current branch
- the adapter remains planned as a separate provider-specific follow-on task
- deferral is documented rather than left as an ambiguous unfinished item

### Verified Commands At This Checkpoint

- `uv run ruff check examples/mcp_natural_language_demo.py scripts/generate_example_notebooks.py src/wellplot/agent/providers/openai_compat.py tests/test_agent.py`
- `uv run python -m unittest tests.test_agent -v`
- `uv run python -m py_compile examples/mcp_natural_language_demo.py`
- `UV_CACHE_DIR=/tmp/uv-cache uv run --group docs mkdocs build --strict`

### Recommended Next Step

When work resumes:

1. keep the plan/docs state aligned with the implemented branch
2. merge or rebase `codex/release-mcp-launcher-fix` onto `main`
3. decide whether to add one explicit `openai_compat` example before the next
   release cut
4. revisit Anthropic as a separate adapter task instead of extending this
   branch indefinitely

## Historical Pause Checkpoint (2026-05-01)

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
