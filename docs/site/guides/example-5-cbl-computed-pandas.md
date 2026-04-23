# Example 5: CBL Computed Channels With pandas

This guide follows the executed user notebook
`examples/notebooks/user/computed_pandas/cbl_log_example_pandas_computed.ipynb`.

It starts from the same public CBL/VDL source data used by
[Example 1](example-1-cbl-reconstruction.md), but uses pandas tables to
compute interpretation channels before generating the layout.

Use this example when you want to:

- load source channels from the CBL/VDL example data
- compute cement-bond interpretation curves with pandas
- attach those derived channels to a working `WellDataset`
- generate the report YAML with `LogBuilder` and `SectionBuilder`
- render from the in-memory report so the computed channels are available

## Notebook links

- [Open the notebook on GitHub](https://github.com/cschrupp/wellplot/blob/main/examples/notebooks/user/computed_pandas/cbl_log_example_pandas_computed.ipynb)
- [Download the notebook](https://raw.githubusercontent.com/cschrupp/wellplot/main/examples/notebooks/user/computed_pandas/cbl_log_example_pandas_computed.ipynb)

## Install and runtime model

Install the published package with DLIS, pandas, and notebook support:

```bash
python -m pip install "wellplot[dlis,pandas,notebook]"
```

Run the notebook from a checkout of this repository so the example files and
public sample data are available.

## Recipe structure

The notebook is organized in four steps:

1. inspect the source channels from the CBL/VDL production example
2. compute new channels in pandas and add them to the working dataset
3. create the YAML layout with `LogBuilder`, `SectionBuilder`, and `save_report(...)`
4. render the computed report from the in-memory report object

Choose this version when your derived-channel logic is easier to review in a
tabular workflow than in array expressions.

## What changes relative to Example 1

Example 1 is YAML-first and source-backed. This notebook is pandas-first:

- the derived channels are created from pandas tables in the notebook
- the layout is generated with builder functions instead of being hand-edited in YAML
- the saved YAML records the generated layout but not the in-memory computed arrays

That separation is useful when you want a readable notebook recipe for
petrophysical calculations and a reproducible layout artifact at the same time.

## Adapt this example safely

When you copy this recipe to your own well:

- keep the pandas computation cell separate from the layout cell
- replace the bond-index equation with your preferred cement-evaluation rule
- add every derived channel to `working_dataset` before creating the report builder
- use `LogBuilder` for repeatable YAML generation instead of copying and editing YAML by hand
- export computed data separately if you need a standalone file-only workflow

## Related guides

- [Example 1: CBL Reconstruction](example-1-cbl-reconstruction.md)
- [Python API Workflow](../workflows/python-api.md)
- [Examples](examples.md)
