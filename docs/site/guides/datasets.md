# Datasets

Datasets are the boundary between science code and layout code.

## Current dataset operations

- `add_curve(...)`
- `add_array(...)`
- `add_raster(...)`
- `add_series(...)`
- `add_dataframe(...)`
- `sort_index(...)`
- `convert_index_unit(...)`
- `reindex_to(...)`
- `merge(...)`
- `rename_channel(...)`

## Design rule

A channel must carry its own valid reference axis and units. Layout logic should not guess them.
