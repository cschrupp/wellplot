# Wellplot Agentic Architecture Starter Kit

This kit is an **additive compiler and direct-execution migration starter** for
the August 27 Wellplot architecture.

## Contents

- `docs/wellplot-agentic-natural-language-architecture.md` — full architectural design and migration playbook.
- `CODEX_AGENTIC_HANDOFF.md` — constrained first task for Codex.
- `overlay/` — files to copy into the repository for LG-1 through LG-4.
- `wellplot-agentic-starter.patch` — equivalent unified patch for the new files and additive `graph` dependency.
- `wellplot-agentic-natural-language-architecture.docx` — formatted design document with rendered architecture diagrams.

## Starter scope

Implemented conceptually/code-wise:

1. modular capability registry;
2. compact planner catalogue and scoped worker catalogue;
3. semantic `ReconstructionPlan`;
4. generic report compiler;
5. generic section compiler;
6. LangGraph dynamic worker fan-out using `Send`;
7. deterministic artifact merge into `AuthoringDocumentIntent`;
8. architecture invariant test preventing domain capability names in graph topology.
9. direct, transactional application of merged intent through the existing
   resolution, reconciliation, and typed service layers.
10. read-only semantic verification of final canonical state against merged
    intent through the same resolution and reconciliation rules.
11. verified final-render and visual-review boundary with typed correction
    output and no direct mutation path.

Not implemented yet:

- production canonical-render adapter and vision-provider adapter;
- typed visual-correction repair routing;
- high-level MCP wrapper;
- deletion of legacy orchestration paths.

The direct executor does not call MCP, a provider, filesystem persistence, or
the renderer. It is deliberately limited to the existing canonical service
transaction boundary so a blocked resolution or failed operation rolls back
without mutating the supplied document.

## Verification in the full repository

Install the optional graph dependency, then run the focused compiler and
direct-execution suite:

```bash
uv run --extra graph pytest -q \
  tests/test_capability_registry.py \
  tests/test_graph_architecture_invariants.py \
  tests/test_reconstruction_compile_graph.py \
  tests/test_cbl_compile_only_graph.py \
  tests/test_direct_graph_executor.py \
  tests/test_graph_intent_verifier.py \
  tests/test_graph_finalization.py
```

The CBL test uses a frozen prompt and structured-output fixtures. It records the
semantic plan, selected capabilities, report and section artifacts, merged
intent, model-call count, and correction count without executing MCP tools.
The direct-executor test applies that frozen CBL intent to tracked scaffold and
source-context fixtures, including typed source channel kinds and explicit
header-slot aliases.
The graph verifier reruns the same canonical resolution and reconciliation
rules against the final document and passes only when no repair operations are
required.
Finalization verifies the in-memory document before calling a supplied renderer
and exposes visual-review corrections as typed data for a later compiler-owned
repair stage.
