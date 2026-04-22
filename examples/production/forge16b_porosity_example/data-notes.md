# Data Notes

This example depends on:

- `workspace/data/30-23a-3 8117_d.las`

No optional dependency extra is required beyond the default `wellplot`
installation because this package is LAS-backed.

## Packet facts from the LAS header

- well: `30/23a-3`
- company: `SHELL`
- field: `WILDCAT`
- location: `NORTH SEA`
- country: `UK`
- province: `UKCS`
- UWI: `8117`
- permanent datum: `MSL`
- logging measured from: `RKB`
- logging date: `SEP-OCT-1985`
- service company: `SCHLUMBERGER`

## Curves available in the replacement LAS

Relevant scalar channels include:

- `CAL`
- `CALI`
- `DRHO`
- `DT`
- `GR`
- `ILD`
- `ILM`
- `MSFL`
- `NPHI`
- `PEF`
- `RHOB`
- `SP`

## Supported reconstruction choice

The retained production template now focuses on a data-backed open-hole subset:

- gamma ray and spontaneous potential overview
- deep, medium, and flushed-zone resistivity review
- density-neutron porosity review with `RHOB`, `NPHI`, `PEF`, and `DRHO`
- upper and lower depth windows from the same LAS source

## Rendering notes

- `full_reconstruction.log.yaml` validates successfully through the CLI.
- The rendered packet reuses one LAS source across two depth windows instead of
  stitching together multiple files.
- The porosity track highlights density-neutron crossover with a dedicated
  crossover fill rather than a density-baseline fill.
- The packet is meant to demonstrate a reproducible open-hole layout, not to
  stand in for a certified vendor-issued log packet.

## Public Data and IP Note

- This example uses publicly available or repository-provided demonstration
  data.
- Rendered pages are independent `wellplot` outputs, not original vendor PDFs
  or official service-company deliverables.
- Trademarks and service names remain the property of their respective owners.
- Confirm provenance and redistribution rights before reusing outputs outside
  this repository.
