# Computed-Channel NumPy Notebooks

These notebooks start from the same two production examples as the YAML-first user recipes,
but compute new interpretation channels with NumPy before building the layout.

The workflow is:

- load the public example data
- compute derived channels in Python
- attach those channels to a `WellDataset`
- use `LogBuilder` and `SectionBuilder` to create the YAML-style layout
- save the generated YAML with `save_report(...)`
- render from the in-memory report so computed channels are available

Important: the saved YAML is a layout artifact. It does not persist the computed channel arrays by itself.

## Available Notebooks

- `cbl_log_example_numpy_computed.ipynb`
- `forge16b_porosity_example_numpy_computed.ipynb`

## Regenerate

```bash
uv run python scripts/generate_example_notebooks.py
```
