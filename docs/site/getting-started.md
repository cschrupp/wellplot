# Getting Started

The simplest way to understand `well_log_os` is to separate it into three concerns:

1. `WellDataset`: normalized input data
2. `LogDocument` / `LogBuilder`: layout and report composition
3. render functions: full or partial outputs

## Typical flow

1. Load LAS or DLIS, or ingest computed data from `numpy`/`pandas`.
2. Normalize and validate that data into a `WellDataset`.
3. Build a layout with YAML or `LogBuilder`.
4. Render a PDF report, a partial view, or notebook bytes.

## Quick pointers

- Use [YAML Workflow](workflows/yaml-workflow.md) if you want saved, editable layout files.
- Use [Python API Workflow](workflows/python-api.md) if you want notebook- or pipeline-driven log generation.
