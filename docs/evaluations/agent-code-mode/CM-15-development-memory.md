# CM-15 Development Memory

## Scope

CM-15 introduces a Wellplot-specific `ProgramRuntime` that privately
reconciles, executes, and validates the canonical intent compiled by CM-14.
It is deliberately an execution boundary, not a parser, interpreter, or
second authoring implementation.

- **Migration baseline SHA:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Slice base SHA:** `66f06ef`
- **Scope:** isolated canonical document execution, typed artifact-free
  failure results, explicit context forwarding, focused tests, and migration
  evidence documentation.

## Decisions And Invariants

- `ProgramRuntime.dry_run()` receives CM-12/CM-14 evidence and canonical
  intent directly. It never reparses or reruns the source program.
- The supplied `AuthoringDocumentSpec` is deep-cloned before constructing the
  private `AuthoringService`. No caller-owned document is passed to execution;
  the private post-execution document is not returned, persisted, rendered, or
  serialized by this runtime.
- CM-15 reuses the canonical stack without a shadow reconciler or executor:
  `reconcile_authoring`, `execute_authoring_plan`, and
  `AuthoringService.validate` are the only semantic authorities.
- Context is entirely caller-provided: current document, optional scaffold,
  defaults, available channels, channel aliases, and header aliases. CM-15
  performs no source inspection or project-state acquisition.
- A successful result contains the exact supplied canonical intent in a
  `ProgramArtifact`. Any failed reconciliation, execution, or validation has
  no artifact and converts to compact typed `ProgramDryRunError` diagnostics.
  Public diagnostics do not contain raw exceptions, tracebacks, provider
  objects, or authoring-service internals.
- The runtime owns no capability-specific logic. Channel ambiguity, missing
  source context, track compatibility, and scope checks remain lower-layer
  canonical reconciliation behavior.

## Validation

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q
  tests/test_authoring_program_runtime.py` passed: `7 passed in 0.78s`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q
  tests/test_authoring_program_runtime.py
  tests/test_authoring_program_intent_builder.py
  tests/test_authoring_program_identity.py
  tests/test_authoring_program_interpreter.py
  tests/test_authoring_program_validator.py
  tests/test_authoring_program_models.py
  tests/test_agent_v2_architecture.py` passed: `116 passed in 1.37s`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check
  src/wellplot/authoring_program/program_runtime.py
  tests/test_authoring_program_runtime.py` passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check` over the
  same two Python files passed: `2 files already formatted`.
- `git diff --check` passed.

## Runtime And Production Delta

- Production addition: one private dry-run runtime module below the existing
  Authoring Program contracts and intent builder.
- Direct canonical dependencies: `wellplot.model`,
  `wellplot.authoring_context`, `wellplot.authoring_reconciler`,
  `wellplot.authoring_executor`, and `wellplot.authoring_service`.
- Agent, legacy agent core, MCP, provider, LangGraph, source inspection,
  persistence, rendering, notebooks, public routing, feature flags, and
  legacy deletion delta: zero.

## Limitations And Deferrals

CM-15 does not expose a public Code Mode route, persist a document, emit
canonical YAML, render output, acquire authoring context, define capabilities,
or run provider/graph logic. It also does not return the private document
produced during dry run.

CM-16 owns the next authorized execution integration. No provider, graph,
MCP, routing, or legacy-deletion work is included in this slice.

## Decision

**STOP after CM-15. Proceed to CM-16 only after this slice is committed and
pushed.**
