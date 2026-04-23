# Examples

The examples are grouped by workflow rather than by isolated feature.

!!! note
    The production examples are the curated starting point for end users.

    Each production package documents its source data, supported scope, and
    public-data/IP remarks. The development examples in the repository root are
    still useful reference material, but many of them were built for feature
    development and validation rather than first-time-user guidance.

    Every example in the repository now also has a generated notebook under
    `examples/notebooks/`, but that directory is now split by audience:

    - `examples/notebooks/user/`
      - curated, output-included build tutorials for geologists,
        petrophysicists, and other end users
    - `examples/notebooks/developer/`
      - reference notebooks that mirror the raw example files and library flows

    Start in `user/` unless you explicitly want the raw example internals,
    source code, or lower-level implementation details.

    To run those notebooks in Jupyter or VS Code, install notebook support in
    the same environment. From a source checkout, `uv sync` includes
    `ipykernel` in `.venv`. From an installed-package workflow, start with
    `pip install "wellplot[notebook]"` and add `las` or `dlis` extras when the
    example requires those adapters.

## Production examples

- [Example 1: CBL Reconstruction](example-1-cbl-reconstruction.md)
  - canonical DLIS-backed packet example
  - shows `heading`, `remarks`, main/repeat log sections, reference overlays,
    dual-scale CBL, VDL, and tail composition
- [Example 2: Porosity Reconstruction](example-2-porosity-reconstruction.md)
  - canonical LAS-backed open-hole packet example
  - keeps the production report template while swapping in the replacement
    30/23a-3 well data, LAS-derived header metadata, and gas-crossover fill

## Programmatic API examples

- `examples/api_dataset_ingest_demo.py`
  - dataset creation from computed data
- `examples/api_dataset_alignment_demo.py`
  - sorting, unit conversion, and reindexing
- `examples/api_dataset_merge_demo.py`
  - merge policies and channel collisions
- `examples/api_layout_render_demo.py`
  - in-memory layout rendering
- `examples/api_partial_render_demo.py`
  - section, track, and window renders
- `examples/api_notebook_bytes_demo.py`
  - notebook-oriented PNG / SVG outputs
- `examples/api_end_to_end_demo.py`
  - ingest, compute, align, merge, render, serialize

## YAML/report examples

- `examples/cbl_job_demo.log.yaml`
  - coherent multi-section CBL job packet
- `examples/cbl_report_pages.log.yaml`
  - cased-hole report pages
- `examples/cbl_report_pages_open_hole.log.yaml`
  - open-hole report pages
- `examples/cbl_feature_showcase_full.log.yaml`
  - fills, VDL, overlays, and related rendering features

## Practical advice

Start with the example that matches your workflow and source format rather than
the example with the most features.

That keeps the first adaptation step smaller and makes debugging easier.

When in doubt:

- start in `examples/production/` for copyable user-facing packets
- use the repository-root examples to study isolated features or renderer
  behavior
