# SR1 Ownership Decision Record

## DECISION

The SR1 evidence supports a later design review for deterministic ownership of
**report presence**, while leaving report content model-owned when report scope
is explicit.

## PROJECT SCOPE

The accepted SI-V2R/LQ0 architecture separates semantic planning from
deterministic lowering and CM-58 safety. The current residual is false-positive
`report_work` on section-only requests. SR1 is diagnosis only.

## EXTERNAL EVIDENCE

SR1 does not use external sources to claim a general language-model law. It
records bounded WellPlot evidence and the already accepted deterministic CM-58.2
contract. A follow-up implementation/design slice must perform the project
protocol's external-evidence check before changing ownership.

## ESTABLISHED PRACTICE

The evidence is consistent with a common compiler/pipeline split: a bounded
deterministic layer can enforce whether a document-level work unit is admissible
from explicit request scope, while a semantic model supplies content inside an
admissible document work unit. The applicability boundary is WellPlot's
request-language classifier and its known vocabulary.

## WELLPLOT DIFFERENCE

WellPlot already has `classify_report_boundary_intent()` and CM-58.2 repairs.
Unlike a generic document pipeline, WellPlot must preserve report notes and
mixed report-plus-section requests, so presence and content cannot be collapsed
into one boolean repair.

## OPTIONS CONSIDERED

1. Keep report presence entirely model-owned.
2. Let the deterministic boundary own report presence and retain model ownership
   of report content.
3. Add another prompt experiment or another model before deciding.

## SELECTED APPROACH

Recommend option 2 for a separately authorized design slice. Do not implement
it in SR1. The later slice must define how explicit report and mixed intents
preserve report content and how deterministic rejection is surfaced.

## EVIDENCE CLASS

`EMPIRICALLY_SUPPORTED` for this frozen corpus; not established as a universal
model or language rule.

## RISKS

- lexical coverage may be incomplete outside the corpus;
- an over-broad boundary could suppress legitimate document requests;
- mixed requests require preserving report content while changing presence only
  when the request evidence permits it;
- report content quality and presence quality must remain separately measured.

## REVERSIBLE

YES. No production behavior changed and the recommendation has not been
implemented.

## VALIDATION

Use the existing CM-58.2 policy, held-out provider-free request cases, explicit
report-content checks, and a fail-closed path for classifier uncertainty before
any live qualification.

## STOP / REVISIT CONDITION

Revisit if new provider-free cases disagree with the classifier, if report-only
or mixed report content is lost, or if a production integration cannot preserve
the distinction between report presence and report content.
