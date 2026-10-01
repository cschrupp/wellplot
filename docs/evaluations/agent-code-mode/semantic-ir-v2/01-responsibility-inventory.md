# SI-V2.1 Responsibility Inventory

## Governing Rule

If a structural decision follows uniquely from explicit semantic intent and
static registry/domain rules, deterministic host code owns it. If multiple
semantically meaningful alternatives remain, the intent must resolve the
choice or compilation fails closed.

## Current Capability Inventory

| Concept/capability | Current owner | Proposed SI-V2 owner | Derivation or ambiguity | Registry evidence | Extensibility effect |
| --- | --- | --- | --- | --- | --- |
| Report existence | SemanticPlan plus model-selected report.standard | Model owns report content intent; host injects report root | A report-level intent uniquely implies the standard report root | report.standard, category report | New report semantics register separately |
| report.standard | Model capability ID | Host deterministic root | One report intent has one current report root | Built-in root, no parent | No graph change for plugins |
| Log-plot section existence | SectionTask plus model-selected section.log_plot | Host deterministic root for a log-plot section intent | Current section intents are log-plot intents | section.log_plot, category section | A future section kind needs a new semantic rule |
| section.log_plot | Model capability ID | Host deterministic root | Unique for the selected section kind | Built-in root | Registry-owned mapping |
| Scalar display | track.normal plus binding.curve IDs | Model semantic feature curve | Scalar curve presentation is semantic; its structural bundle is unique | Track/binding parent metadata | Data-driven rule, not a central switch |
| Reference presentation | track.reference ID, sometimes alongside scalar/raster IDs | Model orthogonal reference distinction | Whether a reference/depth lane is intended is not derivable from a curve alone | track.reference description and parent | Separate semantic primitive avoids combination enums |
| Raster/image display | track.array plus binding.raster IDs | Model semantic feature raster | Array/raster presentation is semantic; bundle is unique | track.array, binding.raster | Data-driven rule |
| Curve fill | fill.curve ID | Model semantic fill feature with target | Fill is user-visible meaning; target binding is semantic | fill.curve parent is track.normal | Capability-owned rule |
| Section annotation | track.annotation plus annotation.typed IDs | Model semantic annotation feature | Annotation intent is semantic; track/object topology is deterministic | Annotation parent chain | Registry-owned rule |
| Parent closure | Model emits complete IDs and host validates | Host deterministic when exactly one parent exists | Unique closure is mechanical; multiple parents are ambiguous | allowed_parents | Generic closure supports plugins |
| Ambiguous curve parent | Model selects normal/reference indirectly | Model resolves through curve/reference semantics or explicit rule choice | binding.curve has two valid parents | allowed_parents=(track.normal, track.reference) | Compiler never picks registry order |
| Capability multiplicity | Capability IDs in SectionTask | Requirements/features and workers | IDs are types, not object instances | ADR-CM57 and planner model | Multiplicity remains semantic text/worker-owned |
| Source identity | source_hints plus enrichment | Model preserves hints; host resolves candidates | Ambiguous source identity cannot be inferred safely | SectionTask.source_hints | No source ID in IR |
| Existing-section target | existing_section_hint | Model preserves advisory hint | Host resolves actual target later | SectionTask.existing_section_hint | Revision remains outside compiler |
| Requirements/constraints | Free semantic text on tasks | Preserved verbatim in IR and lowered task | Scientific values may not be summarized away | requirements, constraints fields | Plugin-neutral |
| Unresolved requirements | SemanticPlan.unresolved_requirements | Preserved verbatim | Unsupported intent must remain visible | Existing planner contract | No silent fallback |

## Semantic Feature Shape

SI-V2 uses orthogonal semantic primitives rather than capability-shaped enums:

- curve with reference false or true;
- raster with reference false or true;
- fill targeting a curve feature;
- annotation;
- registered extension features.

The model does not emit capability IDs, mandatory roots, parent chains,
internal IDs, or object-instance multiplicity. It does emit the meaningful
distinction between ordinary and reference presentation, because that cannot be
derived from the existence of a curve or raster alone.

## Responsibility Classes

- MODEL_SEMANTIC: curve/raster choice, reference intent, fill/annotation
  intent, source clues, user requirements and constraints.
- HOST_DETERMINISTIC: report/section roots, unique parent closure, canonical
  capability ordering, and conversion to SemanticPlan.
- MODEL_AMBIGUITY_REQUIRED: source selection when multiple candidates remain;
  any capability rule with multiple meaningful parents unless intent resolves it.
- PASSTHROUGH_CONTEXT: source hints, existing-section hints, unresolved
  requirements, requirements, and constraints.
- WORKER_DETAIL_NOT_PLANNER: channels, scales, sample axes, styles, widths,
  labels, renderer mechanics, and object identity details.

## ADR-CM57 Conflict

ADR-CM57 currently requires the planner to select complete capability types
and forbids host closure injection. SI-V2 deliberately prototypes the opposite
split for uniquely derivable roots/parents. The prototype does not supersede or
edit the ADR. A later architecture review must choose KEEP, ADAPT, or REPLACE
if SI-V2 is accepted for qualification.
