# SR4 Ownership Contract

## Ownership rule

Model output, deterministic policy, final system semantics, and representation
consistency are separate evidence classes. A safety action may establish
`SYSTEM_SEMANTIC_CORRECT` without establishing `MODEL_SEMANTIC_CORRECT`.

The complete policy is machine-readable in
`tests/fixtures/semantic_ir_v2r_sr4/ownership_matrix.json` and
`ambiguity_policy.json`.

## Report

The accepted SR1/SR2 boundary remains unchanged:

- report presence is `DETERMINISTIC_BOUNDARY`;
- report content is `MODEL`.

SR4 does not reopen this decision.

## Reference semantics

Reference admissibility and reference meaning are distinct.

- Explicitly forbidden reference semantics may be removed by a bounded
  deterministic policy.
- Explicitly requested reference presence must be preserved; the model still
  owns kind and target.
- Conflicting instructions fail closed.
- Unspecified reference presence is not silently removable merely because the
  model generated it. The opt-in rule must be established by the WellPlot
  contract before deterministic removal receives system credit.
- `companion_depth_lane` and `reference_track(target=...)` remain distinct
  model semantics. Deterministic safety cannot convert one into the other.
- A reference target cannot be invented, retargeted, or inferred solely to
  make a plan valid.

## Representation consistency

The selected lifecycle is an explicit pre/post wrapper model:

```text
model_semantics
    = SemanticPlan + reference_intents before safety

safe_semantics
    = synchronized SemanticPlan + reference_intents after safety
```

The current `CompiledSemanticPlanV2R` is treated as a pre-safety model
projection for this contract. Until a synchronized post-safety wrapper exists,
the sidecar is diagnostic and cannot independently receive final system
semantic credit. If the capability plan and sidecar disagree at a boundary
where both are consumed, the result is
`REFERENCE_REPRESENTATION_CONFLICT` and must fail closed.

The rejected alternative is a legacy-plan-authoritative model that tolerates a
stale sidecar. Convenience is not sufficient justification for contradictory
semantic state.

## Garnet constraint ownership

Constraint placement is not judged by exact gold field location alone.

- `FEATURE_LOCAL` applies when the restriction belongs to one feature and
  neighboring features may legitimately differ.
- `SECTION_WIDE` applies when the restriction governs the whole visualization
  section independent of feature count.
- `EXPLICITLY_INHERITED` applies only when the contract defines propagation,
  compatible children, overrides, and observable equivalence.

Text in a goal, summary, or generic requirement is not executable inheritance.
An alternative placement is semantically equivalent only when scope,
downstream interpretation, multi-feature behavior, propagation, overrides, and
observable output all agree. Otherwise it is distinct, context-only, or
unresolved. Ambiguous scope fails closed.

## Annotation and unresolved requirements

Annotation semantics remain `MODEL` owned. Prose mentioning a marker or
annotation does not authorize deterministic creation of an annotation feature.
Such a transformation would need a separate semantics-preservation decision.

An explicit supported instruction must be represented structurally. An
unsupported or genuinely ambiguous instruction may remain unresolved. The same
instruction cannot be both represented and unresolved without an explicit
justification; otherwise it is unresolved overpromotion and remains a model
semantic error.
