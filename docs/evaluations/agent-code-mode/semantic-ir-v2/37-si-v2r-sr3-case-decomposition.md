# SR3 Case Decomposition

All conclusions below are `EMPIRICALLY_SUPPORTED` interpretations of the
authenticated generated semantic objects. Both attempts of every target case
show the same root set: `ROOT_STABLE`.

## Garnet

Request: present one waveform image view and omit any depth column.

The model emits one raster feature and repeats the omission in section/report
goals, but the expected feature-owned constraint is absent from
`feature.constraints`. CM58.1 takes no action; CM58.2 removes the section-only
report overreach; CM58.3 takes no action.

Root:

```text
CONSTRAINT_OWNER_MISPLACEMENT
```

The generated text preserves the omission concept, but not under the feature
constraint owner required by the frozen gold. The sole
`REQUIRED_CONTEXT_OWNER_ERROR` is therefore classified as `ROOT`, not as a
separate model misunderstanding. A diagnostic owner-move of the existing
textual constraint to `feature.constraints` predicts collapse of that leaf;
this is not applied to the model or counted as a pass.

## Verde

The model emits the correct scalar and raster sections, but adds
`companion_depth_lane` reference intent to both sections. The request contains
no reference instruction, and the same two unrequested references appear in
both attempts. CM58.1 removes both references; CM58.2 removes the report
overreach; CM58.3 takes no action.

Root:

```text
UNREQUESTED_REFERENCE_INFERENCE
```

The single `REFERENCE_FALSE_POSITIVE` mechanism is classified as `ROOT`. A
diagnostic deletion of the generated references collapses that leaf without
using the gold object as a replacement.

## Amber

Report content is present and independently correct. The section contains the
scalar curve, while the interval-top marker is represented as section-level
requirements/constraints rather than as an annotation feature. CM58.1,
CM58.2, and CM58.3 take no action.

Root:

```text
ANNOTATION_WRONG_OWNER
```

`ANNOTATION_ERROR` is the direct root. Section order, feature kind,
multiplicity, and required-context errors are consequences of the missing
annotation feature and are not counted as independent roots. A diagnostic
reclassification of the existing marker text into an annotation feature
predicts collapse of the four projection-level leaves; context ownership is
not silently repaired.

## Iris

The model emits the scalar curve but adds `companion_depth_lane`, omits the
annotation feature, and leaves the complete request in `unresolved_requirements`.
Both attempts have the same structure. CM58.1 removes the unrequested
reference; CM58.2 and CM58.3 take no action.

Roots:

```text
UNREQUESTED_REFERENCE_INFERENCE
ANNOTATION_WRONG_OWNER
UNRESOLVED_PROMOTION
```

The reference false positive is a separate root from annotation placement.
The unresolved request is a second generated decision, retained as its own
root rather than being compressed into the annotation diagnosis. Feature kind,
multiplicity, section order, annotation, and context leaves are assigned as
root/consequence relationships in the machine-readable artifact.
