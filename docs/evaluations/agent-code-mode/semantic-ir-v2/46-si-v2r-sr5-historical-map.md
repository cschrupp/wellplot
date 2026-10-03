# SI-V2R-SR5 Historical Applicability Map

## Population

The authenticated raw population contains 48 rows from 24 cases. Six attempts
remain `NOT_EVALUABLE` because their historical structural output was
unavailable. Aggregate counts in `applicability_summary.json` are explicitly
multi-dimensional and are not additive scores.

| Dimension or blocker | Rows |
| --- | ---: |
| Report-presence contract applicability | 42 structurally evaluable rows |
| Report-presence interventions retained | 10 |
| Unspecified-reference policy blockers | 4 |
| Reference representation conflicts | 4 |
| Reference rows eligible for later system credit | 10 |
| Depth-column scope blockers | 2 |
| Annotation model-owned residual rows | 4 |
| Unresolved-requirement model-owned residual rows | 2 |
| Structural `NOT_EVALUABLE` attempts | 6 |

These are applicability counts, not recovered passes or new semantic scores.

## SR3 target cases

### Garnet

The report-presence boundary is `CONTRACT_APPLICABLE`; historical report
overreach and the CM58.2 action remain visible. The depth-column prohibition is
`BLOCKED_BY_UNRESOLVED_CONTRACT` because SR4 does not define whether the
restriction is feature-local, section-wide, or explicitly inherited. Surviving
text is not treated as semantic credit.

### Verde

The report-presence boundary is `CONTRACT_APPLICABLE`. The model's reference is
unspecified and the safe capability projection disagrees with the preserved V2R
reference representation. The primary reference state is therefore
`BLOCKED_BY_REPRESENTATION_CONFLICT`, with the separate
`UNSPECIFIED_REFERENCE_POLICY` blocker retained as well. Historical CM58.1
removal is not treated as an SR4-authorized deterministic repair.

### Amber

Report presence is `CONTRACT_APPLICABLE` and report content remains separately
owned by the model. Interval-marker placement is `MODEL_OWNED` annotation
semantics. SR5 does not infer an annotation feature or use CM58 to produce a
new result.

### Iris

The unspecified model reference carries the unresolved SR4 opt-in blocker and
the reference dimension is primarily `BLOCKED_BY_REPRESENTATION_CONFLICT`.
Annotation placement and unresolved promotion are both `MODEL_OWNED`. Frozen
residual labels remain associated with SR3 roots and are not collapsed into a
new score.

## Family and anchor reporting

The machine-readable case and family projections report structural
evaluability, applicability states, blockers, and SR3 roots for all six
families. They do not report family pass rates or recompute anchor statuses.
Fig, Linden, Kestrel, and Xenon remain applicability references only; their
historical status is owned by frozen SR2/LQ0 records.

## Regrade readiness

The map is complete as a classification, but only partially ready for a later
regrade. Report presence and some reference-presence cases have defined SR4
rules, while unspecified-reference policy, representation conflicts, and
depth-column scope still block material dimensions. A regrade must therefore
be separately scoped and must not treat applicability as correctness.
