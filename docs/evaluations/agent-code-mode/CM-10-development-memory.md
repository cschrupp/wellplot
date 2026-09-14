# CM-10 Development Memory

## Scope

CM-10 establishes pure, deterministic contracts and semantic errors for the
future restricted Authoring Program kernel. It intentionally adds no syntax,
execution, capability, provider, graph, MCP, or persistence behavior.

- **Migration baseline SHA:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Slice base SHA:** `5182d9c`
- **Scope:** program contracts, error taxonomy, pure tests, and migration
  evidence documentation.

## Decisions And Invariants

- `ProgramSource` retains original source text verbatim. A future parser owns
  syntax, normalization, and policy decisions.
- Source locations use 1-based positions and validated ordered spans.
- Diagnostics are strict, JSON-serializable, compact records with stage,
  severity, optional code, optional source span, message, and optional repair
  hint. They do not retain raw exceptions, provider values, or tracebacks.
- `ProgramMetrics` uses non-negative numeric measurements. A zero is a real
  measurement, not an unavailable-evidence sentinel. Names align with CM-03
  where the program kernel can measure them; evaluation-only metrics are not
  part of the runtime model.
- `ProgramArtifact` contains only the existing canonical
  `AuthoringDocumentIntent` fragment. CM-10 introduces no operation, command,
  statement, AST, SDK-call, or alternate desired-state representation.
- `ProgramExecutionResult` makes success/failure evidence explicit. Success
  requires an artifact and has no error diagnostic. Failure has diagnostics and
  cannot expose an artifact.
- `AuthoringProgramError` and its seven semantic subclasses each map
  deterministically to one stable `program.*` diagnostic code and one concise
  model-facing diagnostic.
- `wellplot.authoring_program.__init__` remains a docstring-only marker. The
  contracts import only canonical domain models and project errors, never the
  agent, LangGraph, MCP, or provider layers.

## Validation

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q
  tests/test_authoring_program_models.py tests/test_agent_v2_architecture.py`
  passed: `18 passed in 1.02s`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check
  src/wellplot/authoring_program/models.py
  src/wellplot/authoring_program/errors.py
  tests/test_authoring_program_models.py
  tests/test_agent_v2_architecture.py` passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check
  src/wellplot/authoring_program/models.py
  src/wellplot/authoring_program/errors.py
  tests/test_authoring_program_models.py
  tests/test_agent_v2_architecture.py` passed: `4 files already formatted`.
- `git diff --check` passed.

## Runtime And Production Delta

- Public API, provider, MCP, LangGraph, routing, capability, and
  legacy-deletion delta: zero.
- Persistence, canonical YAML, rendering, and notebook behavior delta: zero.
- Production additions are pure domain contracts only.

## Limitations And Deferrals

CM-10 does not parse source, construct an AST, define allowed statements,
execute SDK calls, compile intent, validate capabilities, dry-run a document,
or persist an artifact. It also does not decide which legacy modules may be
removed.

CM-11 owns AST grammar and policy validation. CM-12 owns the restricted
interpreter. CM-13 owns stable ID helpers. CM-14 owns conversion into canonical
intent fragments. CM-15 owns deterministic dry-run validation.

## Decision

**STOP after CM-10. Proceed to CM-11 only after this slice is committed and
pushed.**
