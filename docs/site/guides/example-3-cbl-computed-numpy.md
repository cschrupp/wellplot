# Example 3: CBL Computed Channels With NumPy

This guide follows the executed user notebook
`examples/notebooks/user/computed_numpy/cbl_log_example_numpy_computed.ipynb`.

It starts from the same public CBL/VDL source data used by
[Example 1](example-1-cbl-reconstruction.md), but moves the workflow into
Python so you can compute interpretation curves before building the layout.

Use this example when you want to:

- load source channels from the CBL/VDL example data
- compute cement-bond interpretation curves in Python with NumPy
- attach those derived channels to a working `WellDataset`
- generate the report YAML with `LogBuilder` and `SectionBuilder`
- render from the in-memory report so the computed channels are available

## Notebook links

- [Open the notebook on GitHub](https://github.com/cschrupp/wellplot/blob/main/examples/notebooks/user/computed_numpy/cbl_log_example_numpy_computed.ipynb)
- [Download the notebook](https://raw.githubusercontent.com/cschrupp/wellplot/main/examples/notebooks/user/computed_numpy/cbl_log_example_numpy_computed.ipynb)

## Install and runtime model

Install the published package with DLIS and notebook support:

```bash
python -m pip install "wellplot[dlis,notebook]"
```

Run the notebook from a checkout of this repository so the example files and
public sample data are available.

## Recipe structure

The notebook is organized in four steps:

1. inspect the source channels from the CBL/VDL production example
2. compute new channels with NumPy and add them to the working dataset
3. create the YAML layout with `LogBuilder`, `SectionBuilder`, and `save_report(...)`
4. render the computed report from the in-memory report object

That split is deliberate. It keeps petrophysical logic separate from layout
logic, which makes review and adaptation easier.

## What changes relative to Example 1

Example 1 is YAML-first. This notebook is Python-first.

The practical differences are:

- the derived channels are created in the notebook instead of being read from a file
- the layout is generated with builder functions instead of being hand-edited in YAML
- `save_report(...)` writes a reusable layout artifact for inspection
- `render_report(...)` must still use the in-memory report because YAML alone does
  not persist the computed arrays

## Adapt this example safely

When you copy this recipe to your own well:

- keep the NumPy computation cell separate from the layout cell
- replace the bond-index equation with your preferred cement-evaluation rule
- add every derived channel to `working_dataset` before creating the report builder
- use `LogBuilder` for repeatable YAML generation instead of copying and editing YAML by hand
- export computed data separately if you need a standalone file-only workflow

## Related guides

- [Example 1: CBL Reconstruction](example-1-cbl-reconstruction.md)
- [Python API Workflow](../workflows/python-api.md)
- [Examples](examples.md)
