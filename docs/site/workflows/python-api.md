# Python API Workflow

Use the Python API when the log is part of a data-processing workflow.

## Best fit

- Jupyter notebooks
- computed channels
- alignment and merge operations before rendering
- automated report generation from scripts or services

## Main surfaces

- `well_log_os.api.dataset`
- `well_log_os.api.builder`
- `well_log_os.api.render`
- `well_log_os.api.serialize`

## Core workflow

1. Build or load a `WellDataset`.
2. Add curves/arrays/raster data.
3. Align, convert, sort, and merge channels.
4. Build the layout with `LogBuilder`.
5. Render a full report or partial output.
6. Save the layout YAML if needed.

## Example files

- `examples/api_dataset_ingest_demo.py`
- `examples/api_layout_render_demo.py`
- `examples/api_end_to_end_demo.py`
