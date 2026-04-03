# Examples

The examples are grouped by workflow rather than by isolated feature.

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

Start with the example that matches your workflow rather than the example with the most features.

That keeps the first adaptation step smaller and makes debugging easier.
