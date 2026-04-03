# Datasets

Datasets are the boundary between science code and layout code.

## Core object

`WellDataset` is the canonical normalized container.

The public API is designed so computed results can be added back into the dataset cleanly instead of forcing users through a file-loader path.

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

## Rules for computed channels

A computed channel should provide:

- a numeric reference axis
- an explicit axis unit
- compatible value shape
- a value unit when known

The renderer should not need to infer whether the basis is depth or time, feet or meters, or whether samples align with another channel.

## Merge policy

Dataset merges support explicit collision handling:

- `error`
- `replace`
- `rename`
- `skip`

That makes it practical to keep raw channels and processed channels together without silently overwriting one another.

## Example files

- `examples/api_dataset_ingest_demo.py`
- `examples/api_dataset_alignment_demo.py`
- `examples/api_dataset_merge_demo.py`
