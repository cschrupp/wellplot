# User Notebooks

These notebooks are the curated starting point for geologists, petrophysicists,
and other end users.

They differ from the developer notebooks in three ways:

- they teach how to build and adapt a production packet step by step instead of only reopening a shipped example
- they explain the YAML workflow in domain language: inspect data, create the template, add sections, bind curves, and render
- they include inline rendered checkpoints so the user can compare each stage with the expected visual result

## Available Notebooks

- `cbl_log_example.ipynb`
  - Build a CBL/VDL interpretation packet from DLIS data one stage at a time, starting with a reusable template and finishing with the repeat pass.
- `forge16b_porosity_example.ipynb`
  - Build an open-hole porosity packet from a public LAS file one stage at a time, from reusable template to gas-crossover fill and the final two-window packet.

## Runtime Note

- install the published package with the `notebook` extra and any data-source
  extras required by the example
- run the notebooks from a checkout of this repository so the example files,
  sample data, and preview assets are available

## Regenerate

```bash
uv run python scripts/generate_example_notebooks.py
```
