# CM-25 Development Memory

## Scope

CM-25 proves that an external capability can use the existing capability
contract without changing production orchestration or the restricted
interpreter. The fixture is deliberately test-only and is not registered in
the built-in catalog.

- **Slice base SHA:** `83384f7`
- **Implementation commit:** `5646c60`
- **Scope:** external-looking fixture capability, generic registry-held v1/v2
  execution tests, descriptor tests, architecture assertions, and evidence.

## Contract

The fixture declares both required surfaces:

```text
artifact_model + compiler       # existing v1 worker contract
arguments_model + handler       # additive v2 contract
```

The test exercises the generic path:

```text
fresh CapabilityRegistry
    -> register fixture CapabilitySpec
    -> resolve canonical id and alias
    -> validate arguments_model input
    -> invoke resolved handler
    -> assert exact AuthoringDocumentIntent
```

It also verifies deterministic planning, v1 worker, and v2 Code Mode
descriptors. The serialized v2 descriptor contains the argument schema, hints,
and examples but no callable, module path, handler name, or executable object.

The fixture imports only public capability and canonical intent contracts. It
does not import graph, MCP, provider, LangGraph, or interpreter layers. The
synthetic capability is absent from `create_builtin_registry()`.

CM-25 proves plugin extensibility over the existing canonical authoring domain.
It does not prove that adding a new canonical document object kind requires no
domain-model changes.

## Boundaries

- Production source changes: zero.
- No registry execution/compile/run API was added.
- No changes to workflow, planner, section worker, restricted interpreter,
  provider, LangGraph, MCP, routing, persistence, rendering, or legacy
  deletion were made.
- CM-30 owns the next provider/planner migration slice.

## Validation

- Focused plugin and registry tests passed: `13 passed`.
- Complete Code Mode regression selection passed: `163 passed`.
- Ruff check over the fixture and test passed.
- Ruff format check over the fixture and test passed.
- `git diff --check` passed.

## Decision

**PROCEED / STOP:** PROCEED to CM-30 planning; CM-25 committed and pushed.
STOP before CM-30 implementation until separately authorized.
