# Wellplot Agentic Architecture Starter Kit

This kit is an **additive compile-only migration starter** for the August 27 Wellplot architecture.

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

Not implemented yet:

- persistence/execution;
- direct reconciliation bridge;
- deterministic final verifier;
- final rendering;
- visual QA/repair;
- high-level MCP wrapper;
- deletion of legacy orchestration paths.

That boundary is deliberate. The first integration PR should prove the new compiler decomposition without putting the working persistence path at risk.

## Verification performed in this environment

- All starter Python files pass `py_compile` syntax validation.
- `test_graph_architecture_invariants.py` passes.
- Full import/test execution could not be performed from the supplied expert-review ZIP because that review bundle omits application modules imported by `wellplot.model` (for example `wellplot.errors`).
- LangGraph itself is not cached in this offline container, so the graph execution test is included but uses `pytest.importorskip("langgraph")`.

Run the complete test suite in the full repository/environment after installing the new optional `graph` extra.
