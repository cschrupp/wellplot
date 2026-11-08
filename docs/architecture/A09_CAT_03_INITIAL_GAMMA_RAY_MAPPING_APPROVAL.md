# CAT-03 Initial Mapping Approval

## Decision

`APPROVED — narrowly scoped initial CAT-03 mapping`

**Domain reviewer:** Carlos Schrupp

**Role:** Project Owner / Wireline & Petrophysics Domain Reviewer

## Approved Rule

- **Semantic request term:** `Gamma Ray`
- **Semantic family:** `Gamma Ray`
- **Physical rule:** exact mnemonic `GR`
- **Required unit:** `gAPI`
- **Required channel kind:** scalar
- **Source scope:** `workspace/data/30-23a-3 8117_d.las`
- **Source SHA-256:** `7e6c69c65713dc33303362ab91b767eb06371fd24a31856add8650e6d3bee1a9`
- **Reviewed physical identity:** LAS curve index 7
- **Required resolution:** exactly one `GR`, `ADDRESSABLE`

No unit conversion, normalization, sample transformation, borehole
correction, calibration interpretation, or display preset is authorized.
Bare `GR` remains an explicit physical-channel selector and is not a semantic
request alias. `CGR`, `GRD`, and all other gamma-related mnemonics are excluded.

The source-content SHA is a host-enforced applicability constraint. The
filesystem revision token remains a separate optimistic transaction-change
check and is not treated as a content-authentication digest.

## Scientific Provenance

The [SLB Curve Mnemonic Dictionary, GVR4](https://www.apps.slb.com/cmd/ToolItem.aspx?code=GVR4)
is a terminology reference supporting `GR` as Gamma Ray. It is not authority
for wildcard mappings, related mnemonics, transformations, or scientific
interchangeability. The mapping is an exact rule approved by the domain
reviewer above.

## Rights and Redistribution

- **SLB reference:** `REFERENCE_ONLY / REDISTRIBUTION_NOT_ESTABLISHED`. Cite
  the URL and record the narrow factual assertion; do not copy or redistribute
  dictionary tables or substantial vendor content.
- **LAS fixture:** `LOCAL_QUALIFICATION_ASSET / REDISTRIBUTION_NOT_ESTABLISHED`.
  The catalog binds its relative path and SHA only; it does not contain the
  source bytes. Do not package or publish the LAS file unless separate rights
  evidence is established.
- **Approval record:** internal project decision record; no third-party
  source material is embedded beyond a URL and the approved rule metadata.

## Applicability Boundary

This approval establishes only `Gamma Ray` → exact `GR` with unit `gAPI` and
scalar/addressable requirements for the exact source path and content digest
above. It does not establish that every `GR` in every source is equivalent,
that `CGR` or `GRD` are substitutes, that all `gAPI` channels are Gamma Ray,
or that Gamma Ray-family channels are interchangeable.

Any broader applicability requires separate domain review and catalog
approval. This record does not itself authorize provider/model execution,
scientific grading, C02 activity, or production promotion.
