# 30/23a-3 Porosity Example

This package is production example #2 for `wellplot`.

It keeps the existing production report template and now uses the replacement
public LAS source:

- `workspace/data/30-23a-3 8117_d.las`

Unlike the CBL reconstruction package, this example is not trying to mirror a
separate reference PDF packet page by page. Its role is to show how to retain a
production-ready open-hole report template while swapping in a public LAS file
and LAS-derived heading metadata.

## Intended scope

This example retains the packet structure used by the earlier production
template and rebuilds it around the replacement LAS source. The curated subset
is:

- heading
- remarks
- upper interval open-hole review
- lower interval open-hole review
- tail

## Data-backed header note

The heading now pulls well metadata directly from the LAS well header, including
company, well, field, location, country, province, UWI, logging date, datum,
and elevation values.

The plotted channels focus on the curves that are present in the replacement
LAS and fit the retained porosity-oriented layout:

- `GR`
- `SP`
- `ILD`
- `ILM`
- `MSFL`
- `NPHI`
- `RHOB`
- `PEF`
- `DRHO`

The two strip sections reuse the same LAS over different depth windows so the
example stays compact while still showing the deeper resistivity interval.

## Files

- `base.template.yaml`
  - shared page, report, and style defaults with LAS-backed heading metadata
- `full_reconstruction.log.yaml`
  - example #2 packet built from the replacement LAS source
- `data-notes.md`
  - source file notes, metadata summary, and curve inventory

## Validate and render

From the repository root:

```bash
uv run python -m wellplot.cli validate \
  examples/production/forge16b_porosity_example/full_reconstruction.log.yaml

uv run python -m wellplot.cli render \
  examples/production/forge16b_porosity_example/full_reconstruction.log.yaml
```

Expected render target:

- `workspace/renders/30-23a-3_8117_porosity_reconstruction.pdf`

## Public Data and IP Note

This example uses publicly available or repository-provided demonstration data.
The generated packet is a new `wellplot` rendering that preserves source-backed
well metadata and curve relationships without claiming to be an original vendor
deliverable.

Keep that boundary intact when you adapt this package:

- retain factual attribution where it is part of the LAS metadata
- avoid copying proprietary artwork, tables, or vendor-only disclaimer pages
  that are outside the supported feature set
- confirm provenance and redistribution rights before sharing rendered outputs
  outside this repository
