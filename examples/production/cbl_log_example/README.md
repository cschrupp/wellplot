# CBL/VDL Reconstruction Example

This package is production example #1 for `wellplot`.

It reconstructs the supported portion of a real CBL/VDL packet using the DLIS
files already stored in the repository and a reference PDF for visual
comparison.

## Source files

Primary data inputs:

- `workspace/data/CBL_Main.dlis`
- `workspace/data/CBL_Repeat.dlis`

Visual reference:

- `workspace/renders/CBL_log_example.Pdf`

## Intended scope

This package is the packet-level baseline for the production examples. The
supported subset is:

- heading page
- first-page remarks
- main-pass log section
- repeat-pass log section
- tail page
- realistic scalar headers, reference overlays, dual-scale CBL, and VDL raster
  rendering

The package intentionally omits content that does not map cleanly to the
current `wellplot` feature set, including calibration reports, vendor parameter
tables, borehole sketches, proprietary disclaimer pages, and unsupported table
or graphics layouts.

## Files

- `base.template.yaml`
  - shared page geometry, report styling, heading content, and tail defaults
- `full_reconstruction.log.yaml`
  - the full supported packet with remarks, sections, data sources, and
    bindings
- `data-notes.md`
  - source-file notes, dependencies, and rendered-channel coverage

## Validate and render

From the repository root:

```bash
uv run python -m wellplot.cli validate \
  examples/production/cbl_log_example/full_reconstruction.log.yaml

uv run python -m wellplot.cli render \
  examples/production/cbl_log_example/full_reconstruction.log.yaml
```

Expected render target:

- `workspace/renders/CBL_log_example_full_reconstruction.pdf`

## Public Data and IP Note

This example uses publicly available or repository-provided demonstration data.
The generated packet is a new `wellplot` rendering that preserves factual well
and service context without claiming to be the original vendor-authored
deliverable.

Keep that boundary intact when you adapt this package:

- retain factual attribution where it is part of the source metadata
- avoid copying proprietary disclaimer pages, tables, or artwork that are not
  reproduced by the supported feature set
- confirm provenance and redistribution rights before sharing rendered outputs
  outside this repository
