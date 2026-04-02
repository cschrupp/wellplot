# Concepts

## Dataset

`WellDataset` is the normalized data container. It holds scalar, array, and raster channels with explicit index axes and units.

## Composition

Layout composition is independent from data ingestion.

Main objects:

- `LogBuilder`
- `ProgrammaticLogSpec`
- `LogDocument`
- sections
- tracks
- bindings
- report pages (`heading`, `remarks`, `tail`)

## Rendering

The same logical layout can be rendered as:

- a full PDF report
- a selected section
- a selected track
- a bounded window
- PNG / SVG bytes for notebook use

## YAML vs Python

Use YAML when you want:

- persistent saved layouts
- templated job configs
- easy hand-editing

Use Python when you want:

- programmatic channel generation
- notebook-driven analysis
- automated report generation
- direct control over partial renders
