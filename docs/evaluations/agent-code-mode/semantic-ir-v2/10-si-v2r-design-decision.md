# SI-V2R Design Decision

## DECISION

Select a section-owned reference semantic and coarse report-work intent for a
parallel V2R planner contract. Keep V2R dormant and provider-neutral.

## PROJECT SCOPE

Reduce ambiguity at the planner boundary without moving channels, scales,
sample axes, paths, renderer concepts, canonical IDs, or report construction
into the planner. Lower only to the existing `SemanticPlan` and revalidate it.

## EXTERNAL EVIDENCE

- [Vega-Lite overview](https://vega.github.io/vega-lite/docs/) establishes a
  declarative visualization grammar that is compiled into a lower-level
  representation. Its scale and axis documentation distinguishes data domains
  from guide presentation. This supports semantic intent followed by
  deterministic lowering; WellPlot-specific source and track rules do not
  transfer.
- [Pandoc filters and AST](https://pandoc.org/filters.html) documents a reader
  to AST to writer pipeline, with document construction separated from the
  intermediate representation. This supports coarse report work without
  embedding report SDK calls; Pandoc's document domain is not WellPlot's.
- [PICARD](https://aclanthology.org/2021.emnlp-main.779/) demonstrates that
  syntactic constrained decoding and semantic correctness are separate
  concerns. It supports keeping schema validation distinct from semantic
  lowering; SI-V2R does not implement PICARD or any provider decoder.
- Compiler IR practice supports typed semantic analysis followed by explicit
  lowering and validation. It is an adapted architectural pattern, not a
  WellPlot dependency.

## ESTABLISHED PRACTICE

The repository already has first-class `track.normal`, `track.reference`,
`track.array`, section capabilities, and a separate report worker. The typed
section contract makes normal/reference/array semantic roles explicit. The
existing planner validates capability categories and parent closure.

## WELLPLOT DIFFERENCE

WellPlot's reference track is not merely a boolean modifier on every data
feature. A companion depth lane, data assigned to a reference track, and an
ordinary scalar/raster presentation are distinct meanings. The planner can
preserve that distinction without selecting channels or worker fields.

Report remarks and status belong to report work. Section annotations are visual
content inside a log panel. The planner retains coarse report requirements;
`report_worker.py` decides whether they become a remark, header field, title,
or another report-owned authoring operation.

## OPTIONS CONSIDERED

### A — Keep SemanticIRV2

Rejected as the final reconciliation because per-feature `reference: bool`
couples data meaning to a track-role decision and the frozen evidence shows
repeated reference representation failures.

### B — Section-level reference intent

Selected. `companion_depth_lane` adds a reference lane beside ordinary data;
`reference_track` targets one data feature explicitly. This preserves the
semantic distinction while allowing deterministic capability lowering.

### C — Planner-visible normal/reference/array roles

Retained as a downstream compiled representation, not as a model-owned list of
capability IDs or worker details. V2R expresses the meaning that selects those
roles.

### D — Reuse the typed section draft

Rejected for planner use. It owns channels, scales, source candidates, titles,
and worker-level binding details. Those remain enrichment/typed-worker
responsibilities.

## REPORT OPTIONS

Coarse `report_work` is selected over a generic `report` label because it makes
the planner/worker boundary explicit. A rich report AST was considered and
rejected: the report worker already owns titles, subtitles, fields, remarks,
pages, depth, output, and tail.

## SELECTED APPROACH

V2R uses:

- ordered section intents and semantic features;
- optional section-owned `reference_intent`;
- coarse `report_work` with goal, requirements, and constraints;
- registry-driven feature lowering and unique parent closure;
- explicit failure when parent selection is ambiguous;
- deterministic `SemanticPlan` validation after lowering.

No provider-specific or worker-specific field is present. A fresh 24-case
fixture and additional domain fixture cover ordinary scalar/raster,
companion/reference-track semantics, mixed features, multiplicity,
annotations, fills, report-only, and mixed report/section work.

## EVIDENCE CLASS

`ESTABLISHED`: existing capability and worker ownership boundaries.

`ADAPTED`: declarative IR, AST, PICARD, and compiler-lowering lessons.

`EMPIRICALLY_SUPPORTED`: the SI-V2R taxonomy and 24-case provider-free
representability checks.

`NOVEL`: the exact V2R section-owned reference encoding and its future provider
qualification contract.

## RISKS

The old model did not emit V2R, so offline adjudication cannot establish live
model capability. The selected reference semantics may still need clearer
provider wording. Report/section allocation remains a genuine model decision.
The V2R schema is a new contract and must not be activated without live
qualification.

## REVERSIBLE

V2R is isolated in parallel modules and evaluation fixtures. SI-V2, ADR-CM57,
CM58, production routing, and public APIs are unchanged. The experiment can be
discarded without migration.

## VALIDATION

Provider-free validation requires 24/24 CM-59A gold representability, all
additional domain fixtures, plugin extension, ambiguity fail-closed behavior,
equivalence tests, authenticated 48-row taxonomy, zero production imports, and
zero new attributable repository failures.

## MODEL CAPABILITY CONCLUSION

`NOT_ESTABLISHED`. The evidence identifies substantial contract-boundary
failures, including reference and report ownership, but also retains genuine
semantic failures. No live V2R generation occurred, so model intelligence and
contract quality cannot yet be separated completely.

## STOP / REVISIT CONDITION

Stop after provider-free implementation and independent review. A later live
qualification is justified only if this record remains accepted. Revisit if
gold representability, reference ownership, report ownership, plugin
extensibility, or regression gates fail.
