# Getting Started

`wellplot` has two primary workflows:

- **YAML workflow**: good when the layout itself is a maintained artifact
- **Python API workflow**: good when the log is part of a notebook, script, or automated pipeline

Both workflows converge on the same architecture:

1. normalize data into `WellDataset`
2. define the layout as a document/report
3. render full or partial outputs

## Choose a workflow

Use the YAML workflow when you want:

- reusable templates and savefiles
- operator-editable job definitions
- report layouts stored as versioned assets

Use the Python API when you want:

- computed channels from `numpy` / `pandas`
- notebook-driven analysis
- automated report generation
- partial renders during research

## Minimal path

The shortest path into the library is:

1. install the package and optional extras you need
2. choose YAML or Python API authoring
3. render a single example
4. adapt that example to your own data

Base install:

```bash
python -m pip install wellplot
```

Notebook and data-source extras:

```bash
python -m pip install "wellplot[las,dlis,pandas,notebook]"
```

## Start with examples

Recommended first examples:

- YAML/report example: `examples/cbl_job_demo.log.yaml`
- Python API example: `examples/api_end_to_end_demo.py`
- Dataset ingestion example: `examples/api_dataset_ingest_demo.py`
- Partial rendering example: `examples/api_partial_render_demo.py`

## Basic mental model

Keep these concerns separate:

- `WellDataset` owns normalized data, axes, and units
- `LogBuilder` / `LogDocument` own layout and report structure
- render helpers own output generation
- YAML is serialization, not the only authoring path
