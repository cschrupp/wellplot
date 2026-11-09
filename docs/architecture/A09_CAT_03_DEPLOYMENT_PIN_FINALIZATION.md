# A09 CAT-03 Deployment Pin Finalization

## Decision

The CAT-03 deployment pin is finalized against the documentation-only
repository release-acceptance record. This finalizes deployment trust for the
accepted candidate; it does not constitute positive qualification or
controlled-activation acceptance.

## Repository Trust Sequence

- Accepted CAT-03 implementation and R1: `7370a6eb4d983eb6e6578d539cc6242f4f8060d6`
- Repository release-acceptance record: `a0eca857f797ab6514e1fd5933229a71fe287f71`
- `approved_repository_commit` in the finalized pin: `a0eca857f797ab6514e1fd5933229a71fe287f71`
- Pin-finalization commit: this documentation and pin change; it is intentionally not the repository commit named by the pin.

## Bound Release Identities

- Human/domain approval record SHA-256: `162f21dd3d3a558b5554a9bd10082c1bd60ac0a1b5c5f589456bce70fbf738c2`
- Canonical catalog content SHA-256: `bbe9e40439c263c3471b0532bdfb59f4b66d17ba2fa4d5b0a68727dba619b49d`
- Catalog artifact SHA-256: `8a7cccaaa19eeeb6ada7ab794bf4361f14968730c5edb29a23daffd5e4abd414`
- Approval-manifest SHA-256: `1da34bd238652694376de33d5baf3dbfe894e816e519979b2a7f4dd0ebf52f9a`

The catalog and approval manifest are byte-identical to the accepted R1
artifacts. Only `release-pin.json` changed in the packaged release.

## Scope and Status

The accepted rule remains `Gamma Ray` → family `gamma_ray` → exact `GR`,
scalar, `gAPI`, scoped only to
`workspace/data/30-23a-3 8117_d.las` with SHA-256
`7e6c69c65713dc33303362ab91b767eb06371fd24a31856add8650e6d3bee1a9`.
`CGR`, `GRD`, bare `GR` as a semantic alias, wildcard mappings, conversions,
transformations, and display presets remain excluded.

- Deployment trust: **finalized**.
- Positive provider-free Notebook/MCP qualification: **pending separate
  authorization**.
- CAT-03 controlled activation: **not accepted**.
- A09 integrated qualification: **open**.
- Provider/model execution, YAML publication, C02 activity, and scientific
  execution: **not authorized by this record**.
