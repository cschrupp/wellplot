# CM-20 Development Memory

## Scope

CM-20 adds the optional v2 capability contract beside the current v1
`CapabilitySpec` behavior. It proves that one synthetic declaration can retain
its artifact/compiler contract while independently exposing static Code Mode
argument metadata and a host handler.

- **Migration baseline SHA:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Slice base SHA:** `f37284d`
- **Scope:** additive capability fields, construction invariants, a separate
  static v2 worker descriptor, synthetic dual-mode tests, and evidence docs.

## Contract

The existing v1 fields remain authoritative for the current graph:

- `artifact_model`
- `compiler`
- `planning_descriptor()`
- `worker_descriptor()`

The optional v2 fields are:

- `arguments_model: type[BaseModel]`
- `handler: CapabilityHandler`
- `worker_hints: tuple[str, ...]`
- `examples: tuple[str, ...]`

`arguments_model` and `handler` are an all-or-nothing pair. Neither means a
valid v1-only capability; exactly one fails construction. `supports_v2` is the
single derived capability check. Hints and examples default to empty tuples.

`code_mode_worker_descriptor()` is the only v2 descriptor. Its exact keys are
`id`, `category`, `description`, `aliases`, `allowed_parents`, `source_kinds`,
`worker_hints`, `examples`, and `arguments_schema`. The schema is generated
directly from the declared Pydantic model. The descriptor contains no handler,
compiler, callable, callable representation, module path, signature, or memory
address and is deterministic across repeated serialization.

Aliases are validated at declaration time: they must be non-empty strings,
case-insensitively unique, and must not redundantly repeat the capability ID.
Registry alias lookup remains globally unchanged.

## Validation

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q
  tests/test_capability_registry.py` passed: `7 passed in 0.64s`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q
  tests/test_capability_registry.py
  tests/test_authoring_program_inspection.py
  tests/test_authoring_program_runtime.py
  tests/test_authoring_program_intent_builder.py
  tests/test_authoring_program_identity.py
  tests/test_authoring_program_interpreter.py
  tests/test_authoring_program_validator.py
  tests/test_authoring_program_models.py
  tests/test_agent_v2_architecture.py` passed: `132 passed in 1.46s`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check` over the three
  changed Python files passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check` over the
  same three Python files passed.
- `git diff --check` passed.

## Runtime And Production Delta

- Existing built-in capabilities were not migrated and current graph-visible
  descriptor methods retain their previous shape.
- Handler execution, interpreter registration, provider, planner, LangGraph,
  MCP, routing, persistence, rendering, notebook, source inspection, and
  legacy deletion delta: zero.

## Limitations And Deferrals

CM-20 does not define a handler invocation context, execute a handler, compile
SDK calls, or create a v2-only capability. It does not modify current built-in
declarations or expose the v2 descriptor through planner catalogs. CM-21 owns
the first real report capability migration and may define the execution
context then.

## Decision

**STOP after CM-20. Proceed to CM-21 only after this slice is committed and
pushed.**
