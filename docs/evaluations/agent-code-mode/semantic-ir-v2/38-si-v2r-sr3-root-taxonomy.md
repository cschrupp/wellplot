# SR3 Root Taxonomy and Ownership Analysis

## Root prevalence

| Mechanism | Attempts | Cases | Cases |
| --- | ---: | ---: | --- |
| `UNREQUESTED_REFERENCE_INFERENCE` | 4 | 2 | Verde, Iris |
| `ANNOTATION_WRONG_OWNER` | 4 | 2 | Amber, Iris |
| `CONSTRAINT_OWNER_MISPLACEMENT` | 2 | 1 | Garnet |
| `UNRESOLVED_PROMOTION` | 2 | 1 | Iris |

The two mechanisms affecting two cases tie as the dominant root prevalence.
Raw leaf counts are intentionally not used as prevalence because Amber and
Iris contain correlated consequences.

The new generic mechanism `ANNOTATION_WRONG_OWNER` is required because the
existing candidate labels did not distinguish annotation meaning represented
as section prose from an annotation represented as a separate section. It is
not named after a case.

## Leaf classification

Across the four cases and eight attempts, all observed leaves receive a
bounded classification. Six leaf occurrences are direct roots and eight are
consequences in the case-level unique-label projection; no leaf is unexplained.

- Garnet context ownership is the direct constraint-owner root.
- Verde and Iris reference false positives are direct unrequested-reference roots.
- Amber and Iris annotation errors are direct annotation-owner roots.
- Iris unresolved requirements are a direct unresolved-promotion root.
- Feature kind, feature multiplicity, section order, and context errors caused
  by missing annotation structure are consequences.

## Existing safety interaction

CM58.1 already removes the unrequested references in Verde and Iris. SR3 keeps
the model reference error visible while recording the safety action; it does
not change SR2 scoring. This is evidence for a future ownership question, not
a production decision.

CM58.2 remains the accepted deterministic report-presence owner. It removes
the report overreach in Garnet and Verde and leaves Amber/Iris unchanged.
CM58.3 takes no action on these four rows.

Suggested ownership classifications, not decisions:

| Root | Classification |
| --- | --- |
| `UNREQUESTED_REFERENCE_INFERENCE` | `DETERMINISTIC_SAFETY_CANDIDATE` |
| `CONSTRAINT_OWNER_MISPLACEMENT` | `IR_CONTRACT_CANDIDATE` |
| `ANNOTATION_WRONG_OWNER` | `MODEL_SEMANTIC` |
| `UNRESOLVED_PROMOTION` | `MODEL_SEMANTIC` |

These classifications require separate authorization before any implementation
or scoring change.

## Diagnostic counterfactuals

Only copied semantic projections are transformed:

- remove unrequested references;
- move the existing textual Garnet constraint diagnostically to the feature
  constraint owner;
- reclassify existing marker text as an annotation feature.

No missing content is synthesized, no whole gold object is copied, and none of
these counterfactuals changes the frozen evidence or counts as a model pass.
