# User Notebooks

These notebooks are the curated starting point for geologists, petrophysicists,
and other end users.

They differ from the developer notebooks in three ways:

- they teach how to build and adapt a production packet step by step instead of only reopening a shipped example
- they explain the YAML workflow in domain language: inspect data, create the template, add sections, bind curves, and render
- they include inline rendered checkpoints so the user can compare each stage with the expected visual result

## Available Notebooks

### YAML-First Production Recipes

- `cbl_log_example.ipynb`
  - Build a CBL/VDL interpretation packet from DLIS data one stage at a time, starting with a reusable template and finishing with the repeat pass.
- `forge16b_porosity_example.ipynb`
  - Build an open-hole porosity packet from a public LAS file one stage at a time, from reusable template to gas-crossover fill and the final two-window packet.

### Agent-Assisted Manual Recipe

- `agent_las_step_by_step.ipynb`
  - build one open-hole packet from a user LAS file through the public
    `wellplot.agent` API, starting from `create_project_session(...)`,
    `session.add_data_file(...)`, and `session.create_starter(...)` before
    revising the same draft cell by cell
  - manual and credentialed: requires `wellplot[agent,las,notebook]`
    plus an OpenAI API key at runtime

### Computed-Channel NumPy Recipes

- `computed_numpy/cbl_log_example_numpy_computed.ipynb`
  - Compute derived channels with NumPy arrays, then generate layout YAML with wellplot builders.
- `computed_numpy/forge16b_porosity_example_numpy_computed.ipynb`
  - Compute derived channels with NumPy arrays, then generate layout YAML with wellplot builders.

### Computed-Channel pandas Recipes

- `computed_pandas/cbl_log_example_pandas_computed.ipynb`
  - Compute derived channels with pandas tables, then generate layout YAML with wellplot builders.
- `computed_pandas/forge16b_porosity_example_pandas_computed.ipynb`
  - Compute derived channels with pandas tables, then generate layout YAML with wellplot builders.

## Runtime Note

- install the published package with the `notebook` extra and any data-source
  extras required by the example
- run the notebooks from a checkout of this repository so the example files,
  sample data, and preview assets are available

## Regenerate

```bash
uv run python scripts/generate_example_notebooks.py
```
