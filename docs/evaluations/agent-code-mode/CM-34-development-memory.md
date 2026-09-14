# CM-34 Development Memory

## Scope

CM-34 adds a provider-neutral, bounded repair coordinator for a known failed
program. It returns candidate source to the caller and does not own semantic
revalidation or document mutation.

- **Slice base SHA:** `4ba854a`
- **Implementation scope:** compact repair prompts, one normal repair attempt,
  one explicit format-only second attempt, stable result evidence, and repair
  metrics.

## Contract

```text
known failed program + semantic task + SDK docs + ProgramDiagnostic
    -> ProgramRepairCoordinator
    -> ModelBackendProtocol.generate_program()
    -> candidate source or bounded failure evidence
```

`ProgramRepairResult` records source, diagnostics, repair count, generation-call
count, stable `ProgramRepairStopReason`, and `ProgramMetrics.program_repairs`.
The ordinary path permits one generation call. A second call requires the
explicit provider-neutral `ProgramRepairFormatFailure` signal; provider
failures are never converted into retries. The coordinator cannot make a
third call.

The repair prompt serializes only the semantic task, relevant SDK docs, prior
program, and stable diagnostic fields. It does not include document state,
source manifests, conversation history, raw provider exceptions, or arbitrary
worker context.

## Validation

- Focused CM-34/CM-33/CM-32/CM-31/provider-contract/architecture tests: `80 passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.

## Boundaries and Risks

- No live provider request was made. Tests use a fake provider-v2 backend.
- No semantic parser/policy validation, dry-run, persistence, document mutation,
  provider retry, planner, program worker, LangGraph, MCP, routing, visual QA,
  or legacy deletion is part of CM-34.
- Existing provider adapters remain unchanged; later integration must translate
  only explicit format failures into the second-pass signal.

## Decision

**PROCEED / STOP:** Implementation is ready for the isolated CM-34 commit.
After evidence finalization, stop before CM-40 implementation.
