# D5-5H Semantic-Contract Repair Design

```yaml
authority: WELLPLOT-D5-5G-FORENSIC-CAUSAL-CORRECTION-AND-D5-5H-DESIGN-AUTH-001
parent_checkpoint: ab9944e693eb530d9716263c2a951fb60bbb0e76
design_basis: D5-5G sealed Qwen live evidence plus D5-5F historical reconciliation
status: DESIGN ONLY / READY FOR INDEPENDENT REVIEW
implementation: NOT AUTHORIZED
provider_model_calls: 0
endpoint_calls: 0
live_execution: NOT AUTHORIZED
src_wellplot_changes: 0
```

## Decision

D5-5H is a bounded semantic-contract study to restore representation fidelity
before any further model comparison. It does not repair the sealed
`d5-5g-qwen-live-001` campaign and does not change the accepted canonical
engine.

The study has two explicit defects to close:

1. The provider-facing schema admitted a JSON object with `summary` and
   `unresolved_requirements` but no `report_task` or `section_tasks`, while the
   canonical `SemanticPlan.validate_work_units()` invariant rejects that object.
2. The D5-5G experimental context used `current_document_summary.sections` and
   `source_summary.candidates[].identity`, while the production workflow uses
   `current_document_summary.existing_section_hints` and
   `source_summary.sources[].labels`.

The scientific variables remain the D5-5G A0/A1/B0/B1/C0 variables. The
correction is to make their common scaffolding canonical and their provider
contract structurally honest before any live rerun is considered.

## Decision record

### Project scope

WellPlot uses one canonical semantic engine:

```text
canonical composition
-> SemanticPlanner / SemanticPlan
-> deterministic safety and enrichment
-> canonical lowering, reconciliation, execution, verification
```

D5-5H may add provider-free study fixtures, schema-contract checks, custody
joins, and documentation. It may not add a planner, worker, validator,
correction engine, compiler, executor, provider adapter, or shadow path.

### External evidence

The design follows established schema practice rather than relying on prompt
prose:

- JSON Schema defines `required`, `anyOf`, `oneOf`, `allOf`, and conditional
  subschemas as structural validation mechanisms. See the [JSON Schema
  combining](https://json-schema.org/understanding-json-schema/reference/combining)
  and [conditional validation](https://json-schema.org/understanding-json-schema/reference/conditionals)
  references.
- OpenAI-compatible structured-output APIs document that `json_schema` strict
  adherence is limited to the provider-supported JSON Schema subset; the
  provider-facing contract must therefore be tested against that subset rather
  than assumed from a Python model. See the [Chat Completions response-format
  reference](https://platform.openai.com/docs/api-reference/chat/object).
- Pydantic supports custom JSON Schema generation separately from runtime
  validators. A runtime `model_validator` is not evidence that its invariant is
  present in the generated provider schema. See [Pydantic custom JSON
  schema](https://docs.pydantic.dev/2.12/errors/usage_errors/#custom-json-schema).

These sources establish the general technique. They do not establish the
WellPlot-specific schema encoding or provider compatibility; those remain
bounded empirical questions.

### Historical evidence

The D5-5F reconciliation and TW-07/TW-08 findings establish that requiredness
and discriminator representation can materially change structured-generation
outcomes. The applicable principle is:

```text
type invariants must be represented in the type/schema boundary,
not only in instructions or an after-the-fact host validator
```

The historical result supports the constraint, not a claim that one old worker
or schema should be restored. Historical mechanisms remain evidence, not
production authority.

### Options considered

| Option | Treatment | Reason |
| --- | --- | --- |
| Keep the current optional work-unit fields and rely on the Pydantic after-validator | REJECTED | It repeats the demonstrated schema/runtime gap. |
| Encode report-or-section presence directly with a provider-compatible `oneOf`/`anyOf` or equivalent required structure | STUDY CANDIDATE | It preserves `SemanticPlan` while making the no-work-unit class structurally inadmissible, subject to provider subset validation. |
| Replace the canonical plan with a second provider DTO and translate it later | REJECTED | It creates a duplicate semantic contract and a second interpretation boundary. |
| Add a model-specific repair or retry for empty plans | REJECTED | It changes execution semantics and obscures the first divergence. |
| Reuse the production context builders and project their safe fields into D5-5H | SELECTED | It directly closes the observed context-fidelity defect without a new engine. |

### Selected approach

Use the existing production workflow/context builders as the single source for
D5-5H planner inputs. Derive the provider-facing contract from the canonical
`SemanticPlan` contract, then prove provider-schema/runtime equivalence for the
specific no-work-unit invariant before live authority is considered.

The exact schema encoding is not silently chosen here. D5-5H must select only
an encoding that passes the provider-compatible structured-output contract
checks and canonical Pydantic validation. If the provider subset cannot encode
the invariant, the study must document that boundary and use a narrow,
explicitly validated equivalent; it must not leave the gap implicit.

Evidence class: **ADAPTED** for the schema/context method, with
WellPlot-specific compatibility results classified **EMPIRICALLY_SUPPORTED**.

## Required design constraints

### A. Canonical context fidelity

The D5-5H fixture factory must obtain or reproduce the production workflow's
canonical safe summaries, then assert their shape before any provider-shaped
request is built:

```yaml
current_document_summary:
  existing_section_hints:
    - title
    - subtitle
source_summary:
  version: <canonical version>
  sources:
    - labels: <canonical labels>
      channels: <canonical channel records>
```

`sections`, `selected_source_candidates`, `grounded_target`,
`grounded_source`, `candidates[].identity`, and other D5-5G shortcut fields may
remain test metadata, but they must not substitute for the canonical planner
context. A provider-free equality/projection test must compare the D5 context
with the production workflow output for the same synthetic document/source
state.

Evidence class: **EMPIRICALLY_SUPPORTED**, because the mismatch was directly
observed in the sealed campaign and source inspection.

### B. Provider/runtime contract equivalence

The no-work-unit object must be impossible at the provider-facing contract.
The provider-free study must prove all of the following:

1. The exact wire schema is derived from the canonical `SemanticPlan` contract.
2. A response with neither `report_task` nor `section_tasks` is rejected at the
   provider-facing structural boundary.
3. A minimal valid report-task response and a minimal valid section-task
   response are accepted by both the provider-contract checker and canonical
   `SemanticPlan` validation.
4. Ordinary malformed field cases remain bounded structured failures.
5. The selected encoding is compatible with the supported structured-output
   subset; unsupported schema features fail the study rather than being
   silently removed.

This is a contract-equivalence proof, not a claim that every possible semantic
rule can be delegated to JSON Schema. Canonical host validation remains
authoritative for semantic and scientific constraints after structural
acceptance.

Evidence class: **ADAPTED** from JSON Schema structural composition and
**EMPIRICALLY_SUPPORTED** only after the finite WellPlot checks pass.

### C. Historical TW reconnection

D5-5H must explicitly retain the D5-5F/TW record:

```yaml
TW-07/TW-08 lesson:
required/discriminator representation changes structured-generation outcomes

reconnected principle:
type invariants belong at the schema/type boundary, not only in prompt prose

not authorized:
restore historical typed-worker runtime or promote historical scores to proof
```

Axis A may continue to vary only the authorized provider-facing requiredness
representation. The corrected common context and work-unit invariant must be
identical across A0 and A1. Axis B may continue to vary only capability-local
contract text. Axis C may observe the existing canonical correction path only.

Evidence class: **HISTORICALLY_DEMONSTRATED** for the requiredness lesson;
**ADAPTED** for its use in the current single-engine study.

### D. Single engine and custody

The accepted `SemanticPlan`, canonical composition, existing provider boundary,
wire observer, and custody joins remain the only execution surfaces. D5-5H may
not reconstruct request/response bodies, add an observer, or create a shadow
validator. Synthetic provider-free responses must use the existing custody
interfaces and must never be mixed with sealed live artifacts.

Evidence class: **ESTABLISHED** within the accepted D5 architecture.

### E. G successor population

The later G-successor rerun may use the same five labels:

```text
D5-5G-A0 / D5-5G-A1 / D5-5G-B0 / D5-5G-B1 / D5-5G-C0
```

The corrected scaffolding is not a new scientific variable. Before any live
authority, provider-free proof must show:

- canonical context equality/projection for all five cases;
- no-work-unit rejection at the provider-facing boundary;
- valid work-unit acceptance through canonical `SemanticPlan` validation;
- A, B, and C request differences remain limited to their frozen variables;
- C still makes at most one correction call and preserves protected state;
- one shared canonical engine and one custody path;
- no replay, selective rerun, or historical-artifact mutation.

The live population, model, and call budget require a separate explicit
authority after this design and its implementation are independently reviewed.

## Finite provider-free acceptance matrix

| Check | Required result |
| --- | --- |
| Production context projection | Exact canonical keys and values for the synthetic state |
| Empty work-unit object | Rejected before canonical semantic grading |
| Minimal report task | Provider-contract and `SemanticPlan` validation pass |
| Minimal section task | Provider-contract and `SemanticPlan` validation pass |
| A0/A1 | Only frozen requiredness representation differs |
| B0/B1 | Only capability-local contract text differs |
| C0 | Existing correction path, one bounded correction call maximum |
| Custody | Existing wire observer and joins; no headers/credentials |
| Architecture | `src/wellplot/**` unchanged; single-engine attestation passes |
| Execution | Provider/model/endpoint calls = 0 |

Any failure in context equality or contract equivalence invalidates the study
candidate. It must not be repaired with a prompt tweak, model-specific branch,
or post-hoc response rewrite.

## Stop and revisit conditions

Revisit the design if:

- the provider's supported schema subset cannot express the work-unit
  invariant;
- the canonical production context cannot be projected without losing required
  semantics;
- the only passing route requires a second semantic model or execution path;
- A/B/C variables cannot be isolated after canonical context correction; or
- provider-free evidence still cannot distinguish structured rejection from
  canonical semantic failure.

Those outcomes require a documented architecture decision, not an automatic
live rerun.

## Governance boundary

```yaml
D5-5G forensic correction: ACCEPTED AS DESIGN BASIS / ARTIFACTS PRESERVED
D5-5H design: READY FOR INDEPENDENT REVIEW
D5-5H implementation: NOT AUTHORIZED
D5-5G live rerun: NOT AUTHORIZED
D5-5H live execution: NOT AUTHORIZED
D5-5I: NOT AUTHORIZED
provider/model calls: 0
endpoint calls: 0
```

This document defines the next bounded study. It does not implement or execute
the proposed repair.
