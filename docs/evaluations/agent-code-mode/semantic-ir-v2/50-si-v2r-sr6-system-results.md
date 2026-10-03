# SI-V2R-SR6 System Results

## Population

The authenticated population contains 48 rows across 24 cases and two
attempts. Six terminal structured-response rows remain non-evaluable. The
frozen model result is 28/48 semantic passes and 14/24 stable passes. The SR2
ownership-adjusted result is 34/48 and 17/24.

## Contract-bounded result

SR6 derives:

| Measure | Result |
| --- | ---: |
| Contract-bounded system passes | 34/48 |
| Contract-bounded stable passes | 17/24 |
| System-recovered attempts versus model | 6 |
| System-recovered stable cases versus model | 3 |
| Additional row changes versus SR2 | 0 |
| Structural `NOT_EVALUABLE` attempts | 6 |

The zero additional changes are itself evidence: SR5 eligibility was consumed
without expanding the contract. Report-presence recovery was already present
in SR2, and no eligible reference-admissibility row had a residual that could
be credited.

## Residual cases

- Garnet remains failed because the depth-column scope is unresolved.
- Verde remains failed because the reference overreach is blocked by both the
  unspecified-reference policy and representation conflict.
- Amber remains failed on annotation ownership and associated semantic leaves.
- Iris remains failed on reference representation/policy, annotation, and
  unresolved-requirement semantics.

The complete row-level residual and transition accounting is in
`tests/fixtures/semantic_ir_v2r_sr6/`.

## Interpretation

These are system-contract statuses, not a new model qualification. The frozen
model score and the historical provider decision remain unchanged. SR6 does
not establish provider compatibility, model qualification, or production
readiness.
