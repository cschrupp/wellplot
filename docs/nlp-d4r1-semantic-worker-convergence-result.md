# WellPlot NLP D4R1 Semantic Worker Convergence

## Status

```yaml
slice: WELLPLOT-NLP-D4R1
baseline: 9b8b1a2cd18be8f42b98b33b18139b475a22a2e5
branch: implementation/nlp-d4r1-semantic-worker-convergence
provider_calls: 0
endpoint_calls: 0
model_calls: 0
live_campaigns: 0
independent_review: PENDING
```

## Decision Record

```text
DECISION:
Use strict typed structured responses for the supported DirectNotebook delivery
route, while retaining the historical program workers for compatibility and
frozen research fixtures.

PROJECT SCOPE:
WellPlot scientists must be able to describe report and well-log plot work in
natural language and have deterministic host code validate, apply, persist, and
render the resulting authoring intent.

EXTERNAL EVIDENCE:
The implementation follows the repository's existing Pydantic structured
provider boundary and typed intent/reconciliation contracts. It does not add a
new provider protocol or a second execution path.

ESTABLISHED PRACTICE:
Use a strict data contract at the model boundary and keep identity allocation,
resource validation, sequencing, and side effects in deterministic host code.

WELLPLOT DIFFERENCE:
The typed response is a delivery DTO. It uses request-local semantic handles;
canonical WellPlot IDs, source paths, SDK calls, and persistence remain host-owned.

OPTIONS CONSIDERED:
A. Continue using model-generated authoring programs.
B. Replace the supported route with typed semantic responses and deterministic
   host compilation.
C. Add a fallback or repair route between the two.

SELECTED APPROACH:
B. The supported DirectNotebook route uses one structured call per work unit,
with no program fallback or repair. Historical program compilers remain
available to existing frozen fixtures.

EVIDENCE CLASS:
ADAPTED

RISKS:
The typed DTO vocabulary must remain aligned with the canonical intent model;
future semantic additions require explicit DTO and host-compiler tests.

REVERSIBLE:
YES. The historical program compilers and their tests remain unchanged.

VALIDATION:
Provider-free DTO, compiler, graph, grounding, revision, reconstruction, and
report-boundary tests; existing D0-D3 delivery regressions; static checks.

STOP / REVISIT CONDITION:
Stop before changing canonical reconciliation, execution, renderer, frozen
live harness artifacts, or model qualification. Revisit if a required accepted
WellPlot operation cannot be represented by the typed DTO without leaking
canonical identity or SDK program source.
```

## Implemented Boundary

The default `DirectNotebookSession` graph now composes:

```text
semantic planner
    -> capability/report/section safety
    -> deterministic source enrichment
    -> TypedDeliveryReportCompiler or TypedDeliverySectionCompiler
    -> AuthoringDocumentIntent
    -> existing reconciliation, execution, persistence, reload, and render
```

The typed section compiler supports reconstruction, existing-curve scale
revision, new track plus source-grounded curve creation, and grounded fill
creation. It exposes only request-local handles to the model and allocates
canonical identities on the host. Scalar and array channel kinds are checked
against the inspected source without substitution.

Worker metrics remain zero for program characters, AST nodes, SDK calls,
repairs, and loop iterations. Provider transport failures retain the existing
provider diagnostic taxonomy; typed response or grounding failures are bounded
worker validation failures.

The report-boundary policy is `cm58.report-boundary.v3`. A report title request
that explicitly preserves existing plots is report-only. An unspecified empty
report task is removed when non-empty section work remains, while an empty
result still fails closed.

## Provider-Free Validation

```yaml
D4R1 focused typed tests: 8 passed
report-boundary tests: 64 passed
D0-D2E plus D4R1 regression group: 95 passed
D3 non-integration checks: 2 passed
program generation calls in typed tests: 0
repair calls in typed tests: 0
```

The existing real-DLIS D3 one-shot integration was not completed in this
environment because it exceeded the bounded local execution window without
producing a process result. It uses the historical program compilers directly
and was not used as evidence for the typed worker convergence.

Ruff and formatting checks pass for the changed Python files. `uv` validation
could not provision the frozen environment because PyPI DNS resolution failed;
the repository's existing local virtual environment was used for the reported
provider-free tests and static checks. No dependency or lockfile was changed.
