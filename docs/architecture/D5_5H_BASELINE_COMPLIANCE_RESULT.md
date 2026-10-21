# D5-5H Baseline-Compliance Implementation Result

```yaml
authority: WELLPLOT-D5-5H-BASELINE-COMPLIANCE-CLOSURE-IMPLEMENTATION-AUTH-001
parent: 1eb0bda4ab191158f10b2ff0a5fb245ae67d153b
branch: design/d5-5g-inspectable-historical-claim-revalidation
provider_model_calls: 0
endpoint_calls: 0
live_experiments: 0
production_component_set: UNCHANGED
production_attestation: PASS_AFTER_MECHANICAL_HASH_REBASELINE
```

## Scope

This slice applies the accepted Agent / Code-Mode Current Active Baseline to
the existing canonical composition root. It adds no planner, DTO, worker,
compiler, validator, repair engine, provider adapter, or execution path.
Historical campaign artifacts, requests, gold, and sealed evidence remain
immutable.

## Compliance Matrix

| Item | Provider-visible or host-owned proof | Status |
| --- | --- | --- |
| H-01 / G1 | `SemanticPlan` schema requires `report_task` or `section_tasks`; Python validation remains authoritative. | PASS |
| H-01 / G2 | `existing_section_hint` is required in provider mappings, nullable for reconstruction, and required semantically for revision. | PASS |
| H-02 / G3 | Unique capability parents are added deterministically; ambiguous legal parents fail with a bounded diagnostic and do not call the model. | PASS |
| H-03 / G4 | Revision context exposes title, kind, width, channel, label, scale, and depth facts without IDs, paths, or mutation handles. | PASS |
| H-04 / G5 | Source inventory distinguishes `inspected`, `not_inspected`, and `unavailable`, including inspected-empty. | PASS |
| H-05 / G6 | Canonical report title/subtitle fields remain distinct from general, service-title, and detail slot groups. | PASS / EXISTING CANONICAL CONTRACT |
| H-06 / G8 | Negative grading can require exact diagnostic code and failure owner, plus no intent, mutation, persistence, or substitution. | PASS |
| H-07 / G9 | Historical request/gold/campaign artifacts are unchanged; the current mutable verifier remains the evaluation surface. | PASS / NO SUCCESSOR REQUIRED |
| H-08 / G7 | Full-plan correction, machine-readable repair scope, deterministic path diff, out-of-scope rejection, and final canonical validation are enforced. | PASS / END-TO-END RETENTION OPEN |

## Provider-Visible Sufficiency Audit

Every model-owned scored fact is supplied by a bounded semantic contract or
explicit host projection:

| Scored fact | Input/provenance | Host-owned boundary |
| --- | --- | --- |
| report title and subtitle | `ReportSemanticResponse.title` / `.subtitle` and explicit report task | lowering and persistence |
| section target | natural-language `existing_section_hint` plus revision inventory | section identity resolution |
| track title, kind, width | revision inventory semantic facts | track identity and mutation |
| binding channel, label, scale | revision inventory semantic facts | channel resolution and lowering |
| source/channel availability | source labels plus inspection state and bounded channel facts | source selection and loading |
| capability closure | provider capability types plus registry metadata | deterministic parent closure |
| negative outcome | observed diagnostic code/owner and canonical before/after custody | grading, persistence, and execution |

No row relies on a hidden fixture, host ID, filesystem path, expected artifact,
or post-hoc answer rewrite. Host IDs, paths, mutation, persistence, rendering,
and final verification remain outside the provider contract.

## Validation

Provider-free focused and adjacent suites pass for the implemented contracts.
The historical D4 nine-turn rehearsal was also attempted without provider
activity; this checkout does not contain the historical tutorial DLIS inputs,
so it terminates before turn one with `evidence_integrity_failure`. That is an
execution-environment custody limitation, not semantic acceptance evidence.

The D5-5H result therefore does not claim live or end-to-end scientific
qualification. G7 retention remains explicitly open for a later bounded study.
