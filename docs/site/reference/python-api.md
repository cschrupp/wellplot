# Python API

This page summarizes the supported public Python surface for `wellplot`.

## Import layers

The library exposes two import layers:

- `wellplot`
  - convenience top-level package exports
  - best for users who want a compact public surface
- `wellplot.api`
  - programmatic workflow entry points only
  - best when you want a narrower, explicitly application-facing API

## `wellplot.api`

The current `wellplot.api` surface is intentionally compact and grouped by
workflow:

### Dataset construction

- `DatasetBuilder`
  - fluent in-memory dataset builder
- `create_dataset(...)`
  - create an empty `WellDataset` with metadata and provenance

### Report composition

- `LogBuilder`
  - top-level programmatic report builder
- `SectionBuilder`
  - fluent builder for one log section
- `ProgrammaticLogSpec`
  - normalized in-memory report specification with attached datasets

### Rendering

- `build_documents(...)`
  - turn a `ProgrammaticLogSpec` into render-ready `LogDocument` objects
- `render_report(...)`
  - render the full report or a filtered subset
- `render_section(...)`
  - render one section
- `render_track(...)`
  - render one track inside one section
- `render_window(...)`
  - render a depth- or time-window subset
- `render_png_bytes(...)`
- `render_svg_bytes(...)`
- `render_section_png(...)`
- `render_track_png(...)`
- `render_window_png(...)`

### Serialization

- `document_to_dict(...)`
- `document_from_dict(...)`
- `document_to_yaml(...)`
- `document_from_yaml(...)`
- `save_document(...)`
- `load_document_yaml(...)`
- `report_to_dict(...)`
- `report_from_dict(...)`
- `report_to_yaml(...)`
- `report_from_yaml(...)`
- `save_report(...)`
- `load_report(...)`

## Typical workflow

```python
from wellplot import DatasetBuilder, LogBuilder, render_report

dataset = (
    DatasetBuilder(name="demo")
    .add_curve(
        mnemonic="GR",
        values=[70.0, 72.0, 75.0],
        index=[8200.0, 8201.0, 8202.0],
        index_unit="ft",
        value_unit="gAPI",
    )
    .build()
)

builder = LogBuilder(name="demo")
builder.set_render(backend="matplotlib", dpi=180)
builder.set_page(size="A4", orientation="portrait")
builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)

section = builder.add_section("main", dataset=dataset, title="Main")
section.add_track(
    id="depth",
    title="",
    kind="reference",
    width_mm=16,
    reference={"axis": "depth", "define_layout": True, "unit": "ft"},
)
section.add_track(id="gr", title="", kind="normal", width_mm=30)
section.add_curve(
    channel="GR",
    track_id="gr",
    label="Gamma Ray",
    scale={"kind": "linear", "min": 0, "max": 150},
)

report = builder.build()
render_report(report, output_path="demo.pdf")
```

## Dataset API

### `create_dataset(...)`

Use `create_dataset(...)` when you want a direct `WellDataset` object without a
fluent builder chain.

Main inputs:

- `name`
- `well_metadata`
- `provenance`

### `DatasetBuilder`

Use `DatasetBuilder` when you need to ingest or normalize computed data before
rendering.

Core methods:

- `add_curve(...)`
  - add a scalar curve from values and a shared index
- `add_array(...)`
  - add a 2D sampled array channel
- `add_raster(...)`
  - add an array channel with raster display metadata
- `add_series(...)`
  - adapt a pandas-style series
- `add_dataframe(...)`
  - adapt a pandas-style dataframe into multiple curves
- `add_channel(...)`
- `add_or_replace_channel(...)`
- `rename_channel(...)`
- `sort_index(...)`
- `convert_index_unit(...)`
- `reindex_to(...)`
- `merge(...)`
- `build()`

Important behavior:

- all channels in a `WellDataset` share one logical index domain
- the builder validates the dataset when you call `build()`
- `merge(...)` supports collision policies such as replace, rename, skip, and
  error

## Builder API

### `LogBuilder`

`LogBuilder` creates a report-level mapping that can later be rendered or
serialized.

High-value methods:

- `set_render(...)`
- `set_page(...)`
- `set_depth_axis(...)`
- `set_depth_range(...)`
- `set_header(...)`
- `set_footer(...)`
- `set_heading(...)`
- `set_remarks(...)`
- `set_tail(...)`
- `add_section(...)`
- `build()`
- `save_yaml(...)`

### `SectionBuilder`

Each section owns track definitions plus section-scoped channel bindings.

High-value methods:

- `add_track(...)`
- `add_curve(...)`
- `add_raster(...)`

Track kinds accepted by `add_track(...)`:

- `reference`
- `normal`
- `array`
- `annotation`

## Render API

### `build_documents(...)`

Use this when you want the normalized `LogDocument` objects without rendering
yet.

Useful options:

- `section_ids`
- `track_ids_by_section`
- `depth_range`
- `depth_range_unit`
- `include_report_pages`

### `render_report(...)`

Use this for the normal end-to-end rendering path.

Behavior:

- uses the backend configured in `ProgrammaticLogSpec`
- returns a backend `RenderResult`
- writes to `output_path` when provided
- returns in-memory figures when no output path is provided for matplotlib

### Scoped render helpers

Use these when you need notebook previews or targeted debugging:

- `render_section(...)`
- `render_track(...)`
- `render_window(...)`

The PNG/SVG byte helpers are the notebook-oriented equivalents of those scoped
render flows.

## Serialization API

### Document helpers

Use document helpers when you already have a normalized `LogDocument`.

- `document_to_dict(...)`
- `document_from_dict(...)`
- `document_to_yaml(...)`
- `document_from_yaml(...)`
- `save_document(...)`
- `load_document_yaml(...)`

### Report helpers

Use report helpers when you are persisting the report/logfile-style mapping.

- `report_to_dict(...)`
- `report_from_dict(...)`
- `report_to_yaml(...)`
- `report_from_yaml(...)`
- `save_report(...)`
- `load_report(...)`

Boundary:

- dataset contents are not embedded into YAML
- YAML persists the layout/report mapping, not the in-memory numeric arrays

## Top-level `wellplot`

The top-level package re-exports:

- the full `wellplot.api` surface
- core model types such as `WellDataset`, `ScalarChannel`, `RasterChannel`,
  `LogDocument`, `TrackSpec`, and report-page specs
- logfile/YAML helpers such as:
  - `load_logfile(...)`
  - `build_documents_for_logfile(...)`
  - `validate_logfile_mapping(...)`
  - `get_logfile_json_schema(...)`
  - `render_from_logfile(...)`

Use top-level imports when they make a script shorter and clearer.

Use `wellplot.api` imports when you want a narrower public surface for notebook
or application code.

## Stable examples

For working reference code, start with:

- `examples/api_dataset_ingest_demo.py`
- `examples/api_dataset_alignment_demo.py`
- `examples/api_dataset_merge_demo.py`
- `examples/api_layout_render_demo.py`
- `examples/api_partial_render_demo.py`
- `examples/api_notebook_bytes_demo.py`
- `examples/api_end_to_end_demo.py`
