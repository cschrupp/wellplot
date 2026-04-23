# Example 4: Porosity Computed Channels With NumPy

This guide follows the executed user notebook
`examples/notebooks/user/computed_numpy/forge16b_porosity_example_numpy_computed.ipynb`.

It starts from the same public LAS source used by
[Example 2](example-2-porosity-reconstruction.md), but computes porosity and
gas-crossover channels in Python before generating the layout.

Use this example when you want to:

- load source channels from the open-hole porosity example
- compute porosity and gas-crossover curves with NumPy
- attach those derived channels to a working `WellDataset`
- generate the report YAML with `LogBuilder` and `SectionBuilder`
- render from the in-memory report so the computed channels are available

## Notebook links

- [Open the notebook on GitHub](https://github.com/cschrupp/wellplot/blob/main/examples/notebooks/user/computed_numpy/forge16b_porosity_example_numpy_computed.ipynb)
- [Download the notebook](https://raw.githubusercontent.com/cschrupp/wellplot/main/examples/notebooks/user/computed_numpy/forge16b_porosity_example_numpy_computed.ipynb)

## Install and runtime model

Install the published package with LAS and notebook support:

```bash
python -m pip install "wellplot[las,notebook]"
```

Run the notebook from a checkout of this repository so the example files and
public sample data are available.

## Recipe structure

The notebook is organized in four steps:

1. inspect the source channels from the LAS-backed production example
2. compute new channels with NumPy and add them to the working dataset
3. create the YAML layout with `LogBuilder`, `SectionBuilder`, and `save_report(...)`
4. render the computed report from the in-memory report object

This gives you one reproducible workflow where interpretation math and layout
generation both live in Python.

## What changes relative to Example 2

Example 2 keeps the packet YAML-first and source-backed. This notebook changes
two things:

- the porosity and gas-crossover channels are computed in the notebook
- the layout is generated with builder functions rather than edited directly in YAML

The saved YAML remains useful as a layout artifact, but it does not persist the
computed arrays. To reproduce the derived channels, rerun the notebook or
export the computed dataset separately.

## Adapt this example safely

When you copy this recipe to your own well:

- keep the NumPy computation cell separate from the layout cell
- replace the matrix and fluid density constants with values appropriate for your reservoir
- add every derived channel to `working_dataset` before creating the report builder
- use `LogBuilder` for repeatable YAML generation instead of copying and editing YAML by hand
- export computed data separately if you need a standalone file-only workflow

## Related guides

- [Example 2: Porosity Reconstruction](example-2-porosity-reconstruction.md)
- [Python API Workflow](../workflows/python-api.md)
- [Examples](examples.md)
