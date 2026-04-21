# 30/23a-3 Porosity Example

This package is production example #2 for `wellplot`.

It keeps the existing production report template and now uses:

- `workspace/data/30-23a-3 8117_d.las`

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
