# CM-11 Development Memory

## Scope

CM-11 creates the static grammar boundary for restricted Authoring Programs.
It parses source into an AST and validates a deliberately small syntax
allowlist. It does not turn source into runtime behavior.

- **Migration baseline SHA:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Slice base SHA:** `a5aec78`
- **Scope:** AST parser, policy validator, pure adversarial tests, and
  migration evidence documentation.

## Decisions And Invariants

- `grammar.py` uses only `ast.parse`. It converts `SyntaxError` to the
  existing `ProgramSyntaxError` and maps parser/AST locations through one
  source-span helper. AST `col_offset` values are transformed into the existing
  1-based span convention without Unicode grapheme normalization.
- `ProgramPolicyLimits` is one immutable object with the provisional migration
  defaults: 16,000 source characters, 1,500 AST nodes, 300 statements, 250
  calls, 100 loop iterations, and nesting depth 8.
- The validator returns the parsed `ast.Module` unchanged. It does not compile
  source into bytecode, evaluate expressions, execute calls, resolve Python
  objects, invoke callbacks, or import code from the generated program.
- The grammar permits only expression method calls, one-name assignments,
  allowed literals/containers, keyword arguments, root/local-handle
  attributes, literal/local-literal bounded loops, and boolean or literal
  equality `if` conditions. A flat tuple `for` target is retained for the
  migration plan's resistivity-loop example.
- Calls must have exactly one public name receiver: the predeclared `wp` root
  or a previously assigned local handle. No bare calls, attribute chains,
  call chaining, private names, or dynamic iteration are accepted.
- Every other Python AST node is rejected by default. This includes imports,
  functions, classes, lambdas, comprehensions, mutation, operators, async
  syntax, reflection, and all private or dunder identifiers.
- Policy categories remain stable: parser failures are `ProgramSyntaxError`,
  limits are `ProgramLimitError`, unsupported syntax is `ProgramPolicyError`,
  and unavailable/private names are `ProgramNameError`.
- The no-execution test exposed that `ast.walk` lazily imports `collections`.
  The final validator uses a local `ast.iter_child_nodes` traversal instead.
  CPython implements `ast.parse` using `compile(..., PyCF_ONLY_AST)`; the test
  permits only that parse-only implementation detail and rejects bytecode
  compilation plus direct `open`, `eval`, `exec`, and `__import__` calls.

## Validation

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q
  tests/test_authoring_program_models.py
  tests/test_authoring_program_validator.py
  tests/test_agent_v2_architecture.py` passed: `73 passed in 1.02s`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check
  src/wellplot/authoring_program/models.py
  src/wellplot/authoring_program/errors.py
  src/wellplot/authoring_program/grammar.py
  src/wellplot/authoring_program/validator.py
  tests/test_authoring_program_models.py
  tests/test_authoring_program_validator.py
  tests/test_agent_v2_architecture.py` passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check
  src/wellplot/authoring_program/models.py
  src/wellplot/authoring_program/errors.py
  src/wellplot/authoring_program/grammar.py
  src/wellplot/authoring_program/validator.py
  tests/test_authoring_program_models.py
  tests/test_authoring_program_validator.py
  tests/test_agent_v2_architecture.py` passed: `7 files already formatted`.
- `git diff --check` passed.

## Runtime And Production Delta

- Public API, provider, MCP, LangGraph, routing, capability, and
  legacy-deletion delta: zero.
- Persistence, canonical YAML, rendering, notebook behavior, and intent
  generation delta: zero.
- Production additions are static syntax inspection only.

## Limitations And Deferrals

CM-11 does not interpret an AST, create SDK handles, resolve real Wellplot
methods, dispatch capabilities, allocate IDs, produce an intent, dry-run a
document, or persist anything. The allowed method shape is language policy,
not a capability registry or SDK API contract.

CM-12 owns restricted interpretation without `exec`. CM-13 owns deterministic
IDs and handles. CM-14 owns canonical intent compilation. CM-15 owns private
dry-run execution.

## Decision

**STOP after CM-11. Proceed to CM-12 only after this slice is committed and
pushed.**
