# CM-12 Development Memory

## Scope

CM-12 adds the generic restricted interpreter and its explicit runtime
dispatch substrate. It turns only CM-11-validated source into generic callback
dispatch evidence; it does not construct Wellplot authoring state.

- **Migration baseline SHA:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Slice base SHA:** `5883a0a`
- **Scope:** capability-neutral runtime registry, direct AST interpreter,
  dynamic execution budgets, deterministic generic journal, pure adversarial
  tests, and migration evidence documentation.

## Decisions And Invariants

- The only public entry point accepts an `AuthoringProgram` and reruns CM-11
  validation before any behavior occurs. It does not accept a raw AST as
  executable input.
- The interpreter dispatches directly by allowed AST node type. It does not
  use `exec`, `eval`, `ast.literal_eval`, source imports, dynamic Python
  attribute lookup, Python builtins lookup, callbacks from source, or a
  generated-code namespace.
- `RuntimeHandle` contains only stable token and kind strings. It carries no
  Python object. Root and handle calls resolve only through frozen explicit
  registries keyed by public method names and `(handle kind, method)` pairs.
- The allowed runtime value universe is recursive and closed: `None`, exact
  booleans/numbers/strings, lists, tuples, string-keyed dictionaries, and
  `RuntimeHandle`. Callback inputs are isolated copies; callback returns are
  recursively validated and copied before entering locals or the journal.
  Unsupported objects, cyclic containers, and non-string dictionary keys fail
  as `ProgramTypeError`.
- Registered callback failures become concise `ProgramCapabilityError` values
  without exposing callback tracebacks. Callbacks receive neither interpreter
  counters nor its journal and cannot reset a budget.
- Dynamic budgets independently count dispatched calls, generic journal
  entries, materialized recursive runtime value items, and leaf loop
  iterations. A dictionary costs one container, one item per string key, and
  the recursive cost of each value. Nested three-by-three loops record nine
  leaf iterations globally. Program metrics expose actual calls and loop work;
  `program_repairs` remains zero.
- The interpreter implements only boolean and `==`/`!=` conditions already
  admitted by CM-11. It uses safe values only, never host-object truthiness or
  overloaded behavior. Loop targets are temporary lexical bindings.
- CM-11 already admits flat tuple loop targets. CM-12 executes that existing
  grammar and makes no validator or grammar change. Any new program syntax is
  deferred to a separately authorized grammar slice.
- `CommandJournalEntry` is generic deterministic tracing evidence. It is not
  a command hierarchy, operation IR, transaction log, authoritative state, or
  future canonical intent representation.

## Validation

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q
  tests/test_authoring_program_models.py
  tests/test_authoring_program_validator.py
  tests/test_authoring_program_interpreter.py
  tests/test_agent_v2_architecture.py` passed: `88 passed in 1.27s`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check
  src/wellplot/authoring_program/models.py
  src/wellplot/authoring_program/errors.py
  src/wellplot/authoring_program/grammar.py
  src/wellplot/authoring_program/validator.py
  src/wellplot/authoring_program/runtime.py
  src/wellplot/authoring_program/interpreter.py
  tests/test_authoring_program_models.py
  tests/test_authoring_program_validator.py
  tests/test_authoring_program_interpreter.py
  tests/test_agent_v2_architecture.py` passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check` over the
  same ten Python files passed: `10 files already formatted`.
- `git diff --check` passed.

## Runtime And Production Delta

- Public API, Wellplot SDK, ID allocation, capability, canonical intent,
  AuthoringService, persistence, transaction, provider, MCP, LangGraph,
  routing, notebook, and legacy-deletion delta: zero.
- Production additions are a generic interpreter and registry substrate only.

## Limitations And Deferrals

CM-12 intentionally does not add real SDK handles, capability methods,
canonical identity allocation, `AuthoringDocumentIntent` construction,
deterministic dry-run behavior, rollback, persistence, or rendered output.
The synthetic callback registry is only an execution seam for security tests,
trace evidence, and later A/B analysis.

CM-13 owns deterministic IDs and real Wellplot SDK handles. CM-14 owns
canonical intent compilation. CM-15 owns dry-run semantics. No CM-11 grammar
extension is authorized by this slice.

## Decision

**STOP after CM-12. Proceed to CM-13 only after this slice is committed and
pushed.**
