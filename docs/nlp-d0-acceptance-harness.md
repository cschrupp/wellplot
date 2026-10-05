# NLP D0 Acceptance Harness

D0 freezes acceptance infrastructure for the two current scientist workflows:

- `CBL-CONSTRUCT`: construct and validate the supported CBL/VDL packet.
- `LAS-REVISE`: apply a requested revision to an existing canonical document.

This slice does not change NLP behavior, prompts, providers, planners,
compilers, renderers, persistence, or production routing.

## Result taxonomy

Every requirement is reported independently with one of:

```text
PASS
FAIL
NOT_CHECKABLE
```

The harness also reports `HARNESS_ERROR` when the acceptance specification or
verifier itself is invalid. A harness error is not a scientist-request failure.

For LAS results, `status` is the conservative aggregate: any unsupported
assertion makes the result `NOT_CHECKABLE`. `workflow_status` reports whether
the exercised requirements passed, so a scale revision can be known to pass
while unrelated dimensions remain outside that revision's evidence.

## CBL requirements

`scripts/verify_cbl_packet.py` reports:

| ID | Scope |
| --- | --- |
| `CBL-01` | Report heading and service titles |
| `CBL-02` | Remarks and report content |
| `CBL-03` | Section identity and order |
| `CBL-04` | Track identity, type, order, and width |
| `CBL-05` | Source/channel binding identity and multiplicity |
| `CBL-06` | Reference/depth-track semantics |
| `CBL-07` | Raster profile, axis, colorbar, and grid settings |
| `CBL-08` | Curve scales, labels, styles, widths, and presentation |
| `CBL-09` | Canonical validation plus supplied persistence/render evidence |

`CBL-09` is `NOT_CHECKABLE` when the caller does not supply execution evidence;
the verifier never infers a successful render from a valid YAML document.

## LAS requirements

`scripts/verify_las_revision.py` compares canonical before/after document
models, never raw file bytes. Acceptance specifications declare the intended
change paths and prohibited paths. The verifier checks:

| ID | Scope |
| --- | --- |
| `LAS-01` | Existing-document grounding |
| `LAS-02` | Report/header mutation |
| `LAS-03` | Track addition |
| `LAS-04` | Curve/binding addition |
| `LAS-05` | Scale change |
| `LAS-06` | Fill addition |
| `LAS-07` | Unrelated-state preservation |
| `LAS-08` | Ambiguity/missing-source fail-closed behavior |
| `LAS-09` | Persistence and render evidence |

If an ambiguous or unavailable-source request is expected to be rejected, the
acceptance specification requires zero canonical delta and execution evidence
with `accepted: false`. A mutation in that case is a failure even when the
requested operation itself appears successful.

The current fixture exercises a scale revision and a rejected no-op. Other
dimensions remain visible as `NOT_CHECKABLE` until the corresponding
deterministic acceptance specification is defined.

## Expected-answer isolation

Gold values live only in acceptance specifications and deterministic fixtures.
They are not imported into prompts, provider messages, planner context, or
runtime semantic intent.

## Validation boundary

The D0 tests include positive fixtures and controlled mutations for report
content, section/track order and type, channel identity, multiplicity,
reference meaning, raster settings, scales, styles, collateral revision
changes, rejected-request mutation, invalid canonical documents, and missing
execution evidence.
