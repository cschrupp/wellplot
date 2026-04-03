# Concepts

## Dataset layer

`WellDataset` is the normalized data container.

It can hold:

- scalar channels
- array channels
- raster channels

Every channel must carry explicit axis information and units. The renderer should not guess whether a channel is depth-based, time-based, metric, or imperial.

Typical dataset operations:

- ingest from LAS / DLIS
- add computed channels from `numpy` / `pandas`
- validate channel shapes and axes
- sort indices
- convert index units
- reindex to another basis
- merge datasets with explicit collision policies

## Composition layer

Layout composition is separate from data ingestion.

Main composition objects:

- `LogBuilder`
- `ProgrammaticLogSpec`
- `LogDocument`
- sections
- tracks
- bindings
- report pages (`heading`, `remarks`, `tail`)

This separation is deliberate: research code should not need to care about page geometry until the point of composition.

## Track types

Current track families:

- `reference`
- `normal`
- `array`
- `annotation`

They have different responsibilities:

- `reference` defines the layout axis and can host overlay curves/events
- `normal` hosts scalar curves and fills
- `array` hosts raster/VDL-style displays
- `annotation` hosts intervals, text, markers, arrows, and glyphs

## Rendering layer

The render layer supports both report-style and notebook-style outputs.

Available scopes:

- full report
- section
- track
- depth/time window
- PNG / SVG bytes for notebooks

## Serialization

YAML remains a first-class saved format.

Important rule:

- YAML serializes layout/report structure
- in-memory dataset contents remain separate Python objects unless they originate from file-backed section sources
