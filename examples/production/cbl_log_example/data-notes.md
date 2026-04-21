# Data Notes

## Source files

This package depends on the real DLIS files already present in the repository:

- `workspace/data/CBL_Main.dlis`
- `workspace/data/CBL_Repeat.dlis`

Reference packet for structural comparison:

- `workspace/renders/CBL_log_example.Pdf`

## Required dependency

To render these files, install the DLIS extra:

```bash
uv sync --extra dlis
```

Or use an ephemeral run:

```bash
uv run --with dlisio python -m wellplot.cli render \
  examples/production/cbl_log_example/full_reconstruction.log.yaml
```

## Rendered channels

The production packet is built around the DLIS-backed channels used in the CBL
sections:

- `ECGR_STGC`
- `TT`
- `TENS`
- `MTEM`
- `CBL`
- `VDL`
- `STIT`
- `TDSP`
- `VSEC`

## Rendering notes

- `full_reconstruction.log.yaml` validates successfully through the CLI.
- Full DLIS-backed rendering is heavier than the LAS-based examples because the
  packet loads two source files and renders VDL raster output.
- When reviewing the result, compare packet structure, headings, remarks,
  section layout, and track content against the reference packet rather than the
  omitted vendor-only pages.

## Public Data and IP Note

- This example uses publicly available or repository-provided demonstration
  data.
- Rendered pages are independent `wellplot` outputs, not original vendor PDFs
  or official service-company deliverables.
- Trademarks and service names remain the property of their respective owners.
- Confirm provenance and redistribution rights before reusing outputs outside
  this repository.
