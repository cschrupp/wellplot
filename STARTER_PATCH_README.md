# Wellplot MCP — Control-Plane Rollback & Contract Completion Starter Patch

**Base reviewed:** `wellplot-mcp-expert-review-2026-08-22.zip`  
**Purpose:** provide a conservative starter patch for the regression where the stable MCP agent performs repeated inspection-only calls, hits the no-progress controller, and rolls back otherwise valid work.

This is intentionally **not** a full rewrite and it does **not** attempt to fix the full CBL stress prompt directly. It preserves the successful S1–S6/data-plane work from the remediation program and changes only the areas implicated by the current control-plane regression.

## What this patch changes

### 1. `src/wellplot/agent/core.py`

- Removes the new structure/content execution-stage machinery from the stable MCP path.
- Removes regex-derived mutation-tool whitelisting for the stable path.
- Removes the arbitrary "six non-mutating calls" blocker.
- Replaces it with a narrow semantic circuit breaker:
  - repeated identical successful read-only call against unchanged state -> feedback;
  - third identical repetition -> stop;
  - different inspection calls are allowed;
  - any successful mutation clears the read-signature counters.
- Keeps the existing repeated-error circuit breaker.
- Replaces the expensive pre-provider full `inspect_authoring` preflight with structural `validate_logfile`.
- Stops automatic catalog fallback execution in the primary stable loop. The legacy helper remains in the tree for now, but the main loop does not silently invoke it.
- Simplifies `_normalize_stable_tool_arguments` so the host no longer invents nested payloads or reshapes malformed raster/report/remarks requests. Contract-invalid provider calls should be fixed at the MCP schema boundary instead.
- Retains deterministic final-state/postcondition verification and rollback.

Net result against the uploaded Aug-22 file: **9153 -> 8684 lines (-469)**.

### 2. `src/wellplot/agent/tool_contract.py`

- Makes the canonical Pydantic field schema authoritative for the high-risk groups where the actual wire contract was still ambiguous: `header`, `track`, `curve`, and `raster`.
- Prevents the compatibility `extensions` field from bloating the provider-facing schema.
- Keeps the combined 17-tool schema under the existing 40k hard budget.

Current measured contract budget in this patch:

```text
tool_count:             17
input_schema_chars:     23,083
output_schema_chars:    13,535
combined_schema_chars:  37,013
```

This is deliberately selective. It does **not** yet convert every operation to a discriminated union; that should be the next contract slice after live evaluation confirms this starter behavior.

### 3. `src/wellplot/mcp/assets/defaults/stable_tool_contract.yaml`

- Removes alternate/duplicate public payload representations for curve, raster and fill mutations.
- Removes duplicated top-level remark fields; `edit_remarks(add)` has one public nested `remark` representation.
- Removes report-setting aliases that were only being repaired by the host.
- Keeps explicit section update fields (`title`, `subtitle`, `depth_range`) without importing a large full-section schema into every operation.

### 4. `src/wellplot/mcp/stable.py`

- Fixes direct generic-MCP handling of `edit_report_settings(operation="set_report")` so public `title` / `subtitle` fields are actually dispatched without relying on the embedded Wellplot agent's old host-side normalizer.

### 5. Architecture governance

`agent_eval_support.py` now counts:

- `src/wellplot/agent/tool_contract.py`
- `src/wellplot/mcp/stable.py`

in production-file metrics.

`check_agent_architecture.py` gains optional hard gates:

```text
--max-agent-line-growth N
--max-production-file-growth N
```

During stabilization, use `0` after establishing an approved post-patch baseline. This turns the architecture freeze from a report into an enforceable CI rule.

### 6. Regression tests

The patch updates the stable-loop tests to match the simplified architecture and adds a specific regression test proving that **five different legitimate inspections may precede the first mutation** without being classified as stalled.

It also preserves a test proving that the **same** successful inspection repeated three times is stopped.

The tool-contract tests assert that high-risk nested fields are structured rather than unconstrained objects and that curve/raster/remarks expose only one public payload shape.

## Local verification performed on this starter patch

```text
PYTHONPATH=src pytest -q \
  tests/test_agent_tool_contract.py \
  tests/test_agent_stable_loop.py

50 passed
```

All modified Python files also pass `python -m py_compile`.

The full MCP stable/wire suite could not be executed from the supplied review bundle because it omits `examples/cbl_main.log.yaml` (the same packaging limitation found during the review). `ruff` could not be executed in this offline environment because `uv` attempted to download an uncached Jupyter dependency. Neither limitation is being treated as a code pass.

## Recommended application procedure

1. Create a branch from the exact revision used to create the Aug-22 expert-review ZIP.
2. Apply `wellplot-mcp-control-plane-starter.patch`, or copy the files from this bundle preserving paths.
3. Run your normal full test suite in the real repository, including the MCP wire tests and lint/format checks.
4. Run the **small 12-task step-by-step live-provider matrix first**. Do not start with the full CBL packet prompt.
5. Record for each task:
   - final-state pass/fail;
   - tool sequence;
   - tool calls before first mutation;
   - repeated identical reads;
   - invalid tool calls;
   - rollback/fallback use;
   - result bytes/tokens;
   - provider/model.
6. If the small matrix is stable, establish a new approved architecture/eval baseline.
7. Turn on the architecture growth gates with `0` allowed growth during the remainder of stabilization.
8. Only then run the full CBL prompt as an integration stress test.

## What this starter patch intentionally does NOT solve yet

Do not let Codex compensate for these by adding new controller branches. They are separate follow-up slices:

1. **Operation-specific input schemas.** `operation=add/update/move/...` still needs discriminated-union or equivalent conditional requirements so the MCP schema itself describes operation-specific required fields.
2. **Remaining generic report/section objects.** Some report/page/depth/section payloads are still generic objects. Tighten them selectively while keeping the schema budget bounded.
3. **Legacy orchestration deletion.** Desired-state, direct-operation, catalog-fallback and older planning pathways still exist elsewhere in `core.py`. This patch removes them from the primary stable-loop decision path where implicated, but does not perform the larger deletion sprint.
4. **SDK v2 migration.** Keep deferred until the behavioral regression is stable.
5. **Environment/secret isolation.** Still a separate security slice.

## Review rule for subsequent Codex changes

During MCP stabilization, do **not** accept a new regex intent heuristic, argument-repair normalizer, stage controller, provider-specific branch, or fallback executor merely because a provider produced a bad call.

First inspect the real `tools/list` schema. If the bad call is permitted or ambiguous under that schema, fix the schema. Any unavoidable runtime workaround should reference a named failing live-eval case and should preferably replace more code than it adds.
