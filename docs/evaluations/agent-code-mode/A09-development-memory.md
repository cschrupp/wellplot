# A09 — Inspection Security and Observable Failures

## Status

- State: provider-free implementation candidate; independent review pending
- Base: `e1a0c481c26c281dab68f522a2e84f8d8920f893`
- Provider, model, and endpoint calls: `0`
- Scientific turns: `0`
- C02 exposure: `0`
- Live smoke: not run or authorized by this slice

## Scope Implemented

This bounded candidate hardens existing observation paths without introducing
a planner, worker, graph, provider route, or persistence engine:

- Graph stage traces record cancellation and re-raise it unchanged. Unexpected
  exception messages are omitted; only exception type/module and explicitly
  safe diagnostic attributes are retained.
- Compile/session diagnostics carry an optional bounded failure-owner category
  through the existing result projection.
- Safe inspection projections bind a normalized request digest to the result
  digest without retaining the request text or provider payload.
- Existing section-action observations bind request, source snapshot, work
  contract, operation contract, DTO, and contract-validation result by digest.
- The D5 custody verifier validates and correlates those digest fields.
- Source descriptions are excluded from the planner-facing projection, with a
  regression for prompt-injection text.

## Validation

Focused provider-free command:

```text
UV_CACHE_DIR=/tmp/uv-cache-wellplot PYTHONPATH=src:. uv run --frozen pytest -q \
  tests/test_d5_section_action_observability.py::test_custody_preserves_contract_and_result_digest_bindings \
  tests/test_agent_execution_trace.py tests/test_agent_session.py \
  tests/test_code_mode_enrichment.py tests/test_code_mode_workflow.py \
  tests/test_section_work_contract.py tests/test_mcp_agentic_transaction.py
```

Result: `107 passed`.

Full repository-suite status is not claimed. Historical D5 observability tests
include pre-existing schema/role assumptions and remain part of A10
compatibility triage.

## Deferred Resource-Safety Decisions

No fixed LAS/DLIS source-file byte ceiling is added. Total file size is not a
semantic admission criterion because valid source files can be multi-gigabyte
and contain numerical samples that need not enter model context. This deferral
does not establish parser resource safety.

Metadata-first LAS/DLIS inspection, deterministic channel resolution
(`UNIQUE`, `AMBIGUOUS`, `ABSENT`, `UNKNOWN`), and model-aware token budgeting
remain unimplemented pending a separate design review. Replacement controls
must establish finite parser memory/time, metadata-volume, read-query, and
complete-request token budgets, retaining a secondary serialized-byte cap.
A09 is not complete until these safeguards are accepted or the remaining
limitation is explicitly accepted.

## Boundaries

The candidate does not alter scientific fixtures, populations, gold, C02, or
semantic operation behavior. It does not add source-size rejection, metadata
parsing behavior, or provider retries. No knowledge-baseline promotion is
made before independent acceptance.
