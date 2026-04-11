# Python API Workflow

Use the Python API when the log is part of a data-processing workflow.

## Stability note

This page documents the current programmatic surface as it exists in the repository today.

It should be treated as:

- usable
- intentionally designed
- still subject to refinement before the first production library release

## Best fit

- Jupyter notebooks
- computed channels
- alignment and merge operations before rendering
- automated report generation from scripts or services

## Main modules

- `wellplot.api.dataset`
- `wellplot.api.builder`
- `wellplot.api.render`
- `wellplot.api.serialize`

## Typical flow

1. create or load a `WellDataset`
2. add curves, arrays, or raster data
3. align, convert, sort, and merge channels
4. build the layout with `LogBuilder`
5. render a report or a partial scope
6. optionally save the resulting layout/report YAML

## Minimal example

```python
from wellplot import DatasetBuilder, LogBuilder, render_report

# Build data
working = (
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

# Build layout
builder = LogBuilder(name="demo")
builder.set_render(backend="matplotlib", dpi=180)
builder.set_page(size="A4", orientation="portrait")
builder.set_depth_axis(unit="ft", scale=240)
section = builder.add_section("main", dataset=working, title="Main")
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

# Render
render_report(report, output_path="demo.pdf")
```

## Reference examples

- `examples/api_dataset_ingest_demo.py`
- `examples/api_layout_render_demo.py`
- `examples/api_partial_render_demo.py`
- `examples/api_notebook_bytes_demo.py`
- `examples/api_end_to_end_demo.py`
