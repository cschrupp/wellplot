# Data Notes

This example depends on:

- `workspace/data/30-23a-3 8117_d.las`

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
