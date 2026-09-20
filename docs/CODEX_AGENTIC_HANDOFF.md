# Codex Handoff - Historical v1 LangGraph Migration Record

> **Historical v1 guidance.** This document records the LG-1 through LG-4
> structured-graph migration that produced the current operational/reference
> implementation. It is not active implementation guidance for new agent
> architecture work. Current baseline: `68232ee`. CM-53 default v2 routing
> exists, but transition acceptance remains open. EXP-TW-00 through EXP-TW-08
> revised the planned section-worker boundary toward a static typed semantic
> worker and deterministic compiler. Read
> [`agent-code-mode-architecture.md`](agent-code-mode-architecture.md), the
> [Code Mode migration plan](wellplot_agentic_code_mode_migration_plan.md), and
> the [consolidated typed-worker memory](evaluations/agent-code-mode/EXP-TW-consolidated-development-memory.md)
> before making agent changes.

Read `docs/wellplot-agentic-natural-language-architecture.md` completely before changing code.

## Historical Immediate Objective

Integrate **LG-1 through LG-4 only**:

1. capability registry;
2. semantic planner;
3. generic report and section compiler workers;
4. LangGraph fan-out using `Send`;
5. deterministic merge into `AuthoringDocumentIntent`.

Do **not** persist the compiled intent yet.

## Hard constraints

- Do not rewrite the working MCP path.
- Do not modify controller heuristics in `agent/core.py` to make the graph work.
- Do not add CBL, VDL, image-track, or well-diagram branches to `workflow.py`.
- Do not let graph workers call MCP mutation tools.
- Do not let graph workers mutate YAML or `AuthoringService`.
- Do not create one permanent agent class per domain use case.
- Do not duplicate canonical schemas in YAML/prompt prose.
- Do not make all capability schemas visible to every model call.
- Do not add automatic edit-vs-reconstruct routing in this slice.

## Starter overlay

Copy the files under `overlay/` to the same paths in the repository.

The starter graph ends at:

```python
state["merged_intent"]
```

This must validate as `AuthoringDocumentIntent`.

## Required implementation tasks

### 1. Resolve integration imports

The expert-review ZIP is incomplete and omits some full-repository modules. Adjust imports only as required by the actual repository. Do not redesign the architecture while doing so.

### 2. Add optional dependency

Use:

```toml
graph = [
  "langgraph>=1.0,<2",
]
```

Do not remove the existing MCP dependency from the current `agent` extra yet.

### 3. Run existing tests before graph integration

Record baseline.

### 4. Run new registry tests

`test_capability_registry.py`

### 5. Enforce topology invariant

`test_graph_architecture_invariants.py` must remain green.

### 6. Build compile-only CBL evaluation

Input: frozen successful one-shot CBL natural-language prompt.

Capture:

- `ReconstructionPlan`;
- capability IDs selected;
- report artifact;
- each section artifact;
- merged `AuthoringDocumentIntent`;
- model call count;
- correction count.

Do not execute the intent.

### 7. Create deterministic assertions

At minimum verify that the merged intent contains the expected CBL sections and major requested component families.

## Stop condition

Stop after compile-only CBL evaluation is green.

Do not start direct execution (LG-5) in the same PR.

## Review questions before merge

- Does `workflow.py` know any scientific capability names? It must not.
- Can a mock `track.image` capability be registered without changing graph code? It must.
- Do section workers receive only selected capability schemas? They must.
- Does any worker mutate the draft? It must not.
- Does the graph call MCP? It must not.
- Is the old working path still intact? It must be.
- Did `core.py` grow materially? It should not.
