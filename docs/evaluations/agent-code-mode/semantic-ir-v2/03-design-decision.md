# SI-V2.1 Design Decision

## Decision Record

DECISION: Select Strategy B, leaf semantic intent plus deterministic
registry-driven closure, with orthogonal semantic primitives and a generic
extension path.

PROJECT SCOPE: Reduce model responsibility without changing production
planner behavior or violating capability-plugin extensibility.

EXTERNAL EVIDENCE: Declarative visualization grammars and compiler IRs
separate semantic intent from lower-level structure; PICARD supports keeping
syntax validation distinct from semantic validation.

EVIDENCE CLASS: ADAPTED and EMPIRICALLY_SUPPORTED after provider-free
representability testing.

## Strategies

### Strategy A: Semantic Primitives Plus Deterministic Bundles

This is clear for common concepts, but a central bundle catalogue risks making
the compiler the new capability authority and can hide ambiguity in bundle
names. It is retained as a design influence, not selected as the primary
registry shape.

### Strategy B: Leaf Semantic Intent Plus Deterministic Closure

The model emits curve, raster, reference, fill, and annotation meaning.
Capability-owned lowering rules map those meanings to existing capability
types. The generic compiler applies unique parent closure and fails when a
registered capability has multiple unresolved parents. A rule can explicitly
resolve a meaningful parent choice without editing the compiler.

### Strategy C: PlanIntent-Style Capability Lists

The supplied historical Phase B result showed that deterministic lowering is
plausible, but capability lists keep too much internal topology in the model
contract. The source is unavailable and its metrics are contextual only.

## Selected Provider-Facing Shape

SemanticIRV2 contains:

- summary;
- optional report intent;
- ordered section intents;
- ordered semantic features per section;
- source and existing-section hints;
- requirements, constraints, and unresolved requirements.

It does not contain provider fields, paths, canonical IDs, capability IDs,
parent chains, renderer details, or worker argument details.

## Lowering Invariants

1. Report intent injects report.standard.
2. A log-plot section intent injects section.log_plot.
3. Feature rules are registry-owned data, not central if/elif branches.
4. Unique parents are added transitively.
5. Multiple valid parents require an explicit rule choice or fail closed.
6. Capability type IDs are deduplicated only because SI-V2 emits type topology;
   semantic feature multiplicity remains in the ordered feature list and task
   requirements.
7. Capability order is deterministic and feature-stable.
8. Output is revalidated by SemanticPlan.model_validate() and the existing
   validate_semantic_plan() contract.
9. Input intent and registry objects are not mutated.

## ADR-CM57 Conflict

The selected design conflicts with the current ADR's prohibition on host
injection of missing capabilities. This is intentional prototype evidence only.
Production adoption requires an explicit ADR review and cannot be inferred from
this branch.

## Revisit Conditions

Rework or reject SI-V2 if any of the following occurs:

- a frozen case requires a semantic distinction the IR cannot preserve;
- a deterministic lowering rule guesses among meaningful parents;
- a plugin requires a central compiler edit;
- mandatory roots or unique closure remain model-owned;
- the current SemanticPlan is demonstrably clearer and no more responsible;
- same-environment regressions are attributable to SI-V2.
