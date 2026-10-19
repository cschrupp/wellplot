# WellPlot SLM-01 — D5-grounded 300-case semantic corpus review

## Result

The 152-case project-aligned corpus was audited against the current single-engine branch and expanded by **148 deliberately distinct semantic situations** to exactly **300 unique `(fixture, gold)` targets**.

Grounding baseline:

- branch: `d5/single-engine-convergence`
- commit: `560ec48d2b2809ed2feb55467da15195f527ec44`
- WELL-IR: `1.2-candidate`
- canonical production semantic action union: `reconstruct | update_curve_scale | add_track | add_fill`

The prior 152 targets were revalidated against the D5 schema/lowering contracts and classified by executable support. Their original fixture manifests were not present in the supplied export or current branch, so those 152 are marked `contract_audited_original_fixture_manifest_unavailable` rather than falsely claiming state-level re-execution. The 148 new cases ship with an explicit D5-style fixture manifest and were state-validated in ordered-program simulation.

The corpus does **not** pretend every WELL-IR operation is already a first-class D5 semantic action. Each case is classified as one of:

- `d5_current`: directly foldable to the current D5 canonical semantic-action lowerer;
- `d5_context_lowerable`: current D5 action after deterministic merge with grounded existing state;
- `authoring_supported`: not in the four D5 action variants, but representable by the canonical `AuthoringDocumentIntent` / authoring service;
- `resolver_extension`: needs a deterministic WELL-IR relation/move resolver before canonical authoring;
- `envelope_only`: ambiguity, unsupported, or invalid behavior.

## Real contracts used

The review was grounded in the current branch implementation rather than conversational shorthand:

- `src/wellplot/agent/code_mode/semantic_actions.py`
  - current section actions and deterministic lowering;
  - request-local `curve-N` handles;
  - fill kinds `between_curves`, `between_instances`, `to_lower_limit`, `to_upper_limit`, `baseline_split`;
  - exact channel-kind checking for new bindings.
- `src/wellplot/agent/code_mode/section_semantics.py`
  - `SemanticScale(kind, minimum, maximum, reverse, unit)`;
  - normal/reference/array track semantics, width, labels, curve style, raster boundaries.
- `src/wellplot/model/authoring.py`
  - canonical curve style and scale validation;
  - stable binding instances;
  - fill target requirements and same-track validation;
  - ordered section `depth_range`.
- `src/wellplot/model/intent.py` and `authoring_service.py`
  - sparse binding/style updates, removals, section depth range, object operations.
- D2B/D2C/D2D/D2E/D4 fixtures and result records
  - repeated source-channel bindings are legitimate distinct instances;
  - grounded missing-channel/source and ambiguous-section failures must fail closed;
  - GR lower-limit fill means the scale boundary, not a conditional threshold;
  - D4 contains two distinct CBL binding instances, which exposes the need for instance handles.

## Schema corrections discovered in this audit

The 1.1 candidate still missed real project semantics. Version 1.2 adds:

1. **Request-local curve handles** (`curve-1`, `curve-2`, …) so duplicate bindings such as the two CBL views can be addressed without leaking canonical binding IDs.
2. **`between_instances` fills**, which exist in the canonical authoring model and D5 semantic action vocabulary.
3. **`width_mm` on `create_track`**, because width is an explicit real track semantic in D2B and the canonical DTO.
4. **Append / before / after track creation placement**, so the common real request “add a track at the end” has a deterministic representation.

The model still does **not** learn canonical WellPlot IDs, filesystem paths, SDK calls, renderer internals, or full document JSON.

## Family-by-family audit

| Family | What the D5 audit found | Deliberate gap coverage added |
|---|---|---|
| Curve placement / reference resolution | Basic placement existed, but alias, ordinal/title target resolution and repeated-channel identity were not isolated. | Domain aliases, exact mnemonic resolution, track ordinal/title/id targets, request-local instance handles. |
| Display configuration | D5 separates scale kind/bounds/reverse/unit and canonical style fields. | Linear/log/tangential, partial scale patches, reversed axes, unit-bearing scales, color/style/width/alpha, focus and duplicate-instance selection. |
| Intervals | Canonical sections require ordered top/base; core unit conversion is strict. | Same-unit and cross-unit m/ft/cm cases, decimals, invalid ordering; unsupported unit guessing excluded. |
| Fills | Real fill semantics are five kinds and renderer compatibility matters. | Limit, baseline split, between-curves, between-instances, same-track/matching-scale gates, scale-repair-before-fill, fill color/alpha. |
| Relational targeting | `with`/`beside` require deterministic context resolution before authoring. | Curve/track anchors, handles, ambiguous relational references, movement preservation. |
| Track creation | D2B/D5 make title, width and grounded scalar bindings first-class. | Width, append, before/after placement, multi-binding order, reused channels, per-binding scales/styles. |
| Move/remove | Canonical removal exists; binding moves require preservation-aware deterministic lowering. | Exact curve/fill handles, duplicate-instance removal, absolute and relational moves. |
| Composition | Existing cases under-tested state dependencies across ordered operations. | Create→bind→configure, place→scale→fill, scale-repair→between-fill, interval+mutation, remove+update. |
| Ambiguity / unsupported / invalid | D5 is explicitly fail-closed at source, section, channel and structured semantic boundaries. | Duplicate candidates, no-focus pronouns, missing/unsupported capabilities, fill-axis incompatibility, canonical invalid values. |

## Coverage before and after

Family counts before:

```json
{
  "ambiguity_unsupported": 42,
  "composition": 32,
  "curve_placement": 10,
  "display_configuration": 21,
  "fills": 21,
  "intervals": 17,
  "relational_targeting": 9
}
```

Added gap cases:

```json
{
  "ambiguity_unsupported": 22,
  "composition": 16,
  "display_configuration": 27,
  "fills": 30,
  "intervals": 10,
  "move_remove": 4,
  "reference_resolution": 11,
  "relational_targeting": 8,
  "track_creation": 12,
  "track_targeting": 8
}
```

Final family counts:

```json
{
  "ambiguity_unsupported": 64,
  "composition": 48,
  "curve_placement": 10,
  "display_configuration": 48,
  "fills": 51,
  "intervals": 27,
  "move_remove": 4,
  "reference_resolution": 11,
  "relational_targeting": 17,
  "track_creation": 12,
  "track_targeting": 8
}
```

Final support-level counts:

```json
{
  "authoring_supported": 106,
  "d5_context_lowerable": 20,
  "d5_current": 77,
  "envelope_only": 67,
  "resolver_extension": 30
}
```

Final result-envelope counts:

```json
{
  "ambiguous": 10,
  "invalid": 14,
  "ok": 233,
  "unsupported": 43
}
```

## What the 148 additions cover

The additions were allocated by missing semantic situation, not by paraphrase quota:

- 10 reference/alias resolution situations;
- 8 track-target resolution situations;
- 8 relational placement situations;
- 12 scale-kind/direction/unit situations;
- 12 style and scale+style situations;
- 10 interval/unit-conversion situations;
- 8 limit-fill situations;
- 10 baseline-split situations;
- 12 between-curve / between-instance situations;
- 12 track-creation / multi-binding situations;
- 16 genuinely multi-operation compositions;
- 8 ambiguity situations;
- 8 explicit v1 capability-boundary situations;
- 6 invalid/contradictory situations;
- 4 exact move/remove situations;
- 4 focus/duplicate-instance revision situations.

Every added case carries a unique `gap.gap_id` and rationale. This makes it possible to reject a case during human review without losing track of which semantic coverage hole reopens.

## Validation

All 300 targets pass `well_ir_1_2_candidate.schema.json`.

Additional checks passed:

- exactly 300 rows;
- exactly 148 new gap IDs;
- zero duplicate `(fixture, canonical gold)` targets;
- ordered interval validation for every added executable case;
- positive logarithmic bounds where explicit;
- local-track references occur only after their `create_track` operation;
- added executable selectors resolve against the supplied D5-style fixture manifest;
- request-local curve/fill handles exist in their fixtures;
- core interval units are restricted to the real `SimpleUnitRegistry` set;
- successful between-curve/between-instance fills share a track and matching effective scales after preceding ordered scale updates are applied.

## Human review gate

The 148 new cases are **proposals**, not accepted gold. Their utterances have `reviewed=false` and provenance `review_status=needs_human_acceptance`. The migrated 152 retain their prior review provenance, but they now also carry a D5 lowering classification.

The recommended next gate is therefore a semantic review of the 148 `D5GAP-*` rows, grouped by `semantic_family` and `gap.support_level`. Only after that review should train/validation/held-out splits be frozen. Split by semantic/leakage group, not random utterance row, to prevent near-semantic leakage.
