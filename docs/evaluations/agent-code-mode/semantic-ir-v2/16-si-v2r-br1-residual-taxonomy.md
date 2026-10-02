# SI-V2R-BR1 Residual Taxonomy

The taxonomy is derived from the authenticated 48-row population by
`scripts/semantic_ir_v2r_br1_boundary_audit.py`. Family labels are retained as
historical reporting dimensions; they are not used as failure classifiers.

## Derived Result

| Mechanism | Rows | Stable cases |
|---|---:|---:|
| `NONE` | 28 | 14 |
| `REPORT_FALSE_POSITIVE` | 10 | 5 |
| `ANNOTATION_ERROR` | 4 | 2 |
| `STRUCTURAL_UNAVAILABLE` | 6 | 3 |

The six structural rows all retain the historical `schema_validation` reason,
but the raw invalid payload is not preserved. They are therefore classified as
`UNKNOWN_SCHEMA_VALIDATION_FAILURE`, not as a proven decoder JSON-Schema
violation or a proven Pydantic model-validator failure.

## Allocation Family

The frozen allocation-family result remains 0/4 stable semantic passes. The
mechanism audit says something narrower:

- Tamarind: both attempts preserve three sections and their order; the failure
  is an invented report task.
- Willow: both attempts preserve two independent scalar sections; the failure
  is an invented report task.
- Verde: both attempts preserve two sections and their order; the failures are
  an invented report task and extra companion references.
- Umber: both attempts are structurally unavailable, so allocation is not
  evaluable.

Allocation-mechanism status: `PARTIAL`. The family score is not evidence that
Qwen merged or reordered sections.

## Garnet

Both attempts preserve a raster section and omit a reference intent, but place
the omission constraint in the section goal instead of the feature constraint
owner, while also inventing report work. This does not establish failure to
understand negative reference intent. Negative-reference understanding is
`NOT_ESTABLISHED`; context ownership is the observed failure.

## Model Conclusion

`qwen_intrinsic_incapability = NOT_ESTABLISHED`. The residual evidence mixes
report routing, annotation/context ownership, and unavailable structural rows;
it does not isolate intrinsic inability to perform the V2R semantic role.
