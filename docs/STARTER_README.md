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
12. compile-only revision entry point that scopes graph work to planner-selected
    sections and records unaffected sections for deterministic preservation.
13. transactional revision facade that compiles, executes, verifies, and rolls
    back the canonical document when final semantic verification fails.
14. transactional reconstruction facade that compiles, executes, verifies, and
    rolls back the canonical document when final semantic verification fails.
15. deterministic source-context assembly from a canonical logfile and its
    declared LAS/DLIS section sources.
16. opt-in high-level MCP operations that invoke injected graph dependencies
    and persist only verified canonical documents.

Not implemented yet:

- production canonical-render adapter and vision-provider adapter;
- typed visual-correction repair routing;
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
  tests/test_graph_finalization.py \
  tests/test_graph_revision.py \
  tests/test_graph_revision_execution.py \
  tests/test_graph_reconstruction_execution.py \
  tests/test_graph_source_context.py \
  tests/test_mcp_agentic.py
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
Revision compilation passes a JSON-safe snapshot of the existing canonical
document to the same graph in explicit `revise` mode. It returns a partial
intent for only planner-selected sections; existing sections outside that scope
remain owned by deterministic reconciliation.
The revision execution facade uses the existing direct executor and verifier;
it restores the pre-revision canonical snapshot if final verification fails.
The reconstruction execution facade provides the equivalent transaction for a
full graph-compiled request. This is the application boundary required before a
high-level MCP adapter can be added without duplicating execution logic.
Source-context assembly loads the canonical starter document and all declared
section data sources before compilation. It exposes JSON-safe graph facts and
typed channel candidates, without depending on MCP, a provider, or persistence.
The high-level MCP operations are opt-in server registrations. Their hosting
application injects a configured compiled graph at startup; clients provide
only a logfile path and natural-language request, never provider credentials or
internal source context.

## Agentic MCP Host

The stable `wellplot-mcp` entry point remains deterministic and provider-free.
Use the separate `wellplot-agentic-mcp` entry point only for graph-compiled
natural-language requests. It requires both optional dependencies:

```bash
uv sync --extra agent --extra graph
export WELLPLOT_AGENTIC_PROVIDER=openai_compat
export WELLPLOT_AGENTIC_MODEL='provider/model-name'
export WELLPLOT_AGENTIC_BASE_URL='https://provider.example/v1'
export WELLPLOT_AGENTIC_API_KEY='...'
wellplot-agentic-mcp
```

`WELLPLOT_AGENTIC_SERVER_ROOT` optionally fixes the allowed project root, and
`WELLPLOT_AGENTIC_TIMEOUT` configures the provider request timeout in seconds.
Credentials are process configuration only; they are never accepted by the MCP
tools or written to the logfile.
