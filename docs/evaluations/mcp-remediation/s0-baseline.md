# S0 Baseline and Freeze

Date: 2026-08-20

Status: baseline captured. This is evidence, not a claim that the MCP contract is compliant.

## Captured Surface

`tests/fixtures/mcp_contract_baseline_v1.json` was captured by a real MCP client through the same local stdio runtime used by `AuthoringSession`.

- Tools: 17, in returned wire order.
- Resources: 15.
- Prompts: 6.
- Resource templates: 4.
- Wire input schemas: 12,768 serialized bytes.
- Wire output schemas: 1,295 serialized bytes.
- Live stdio probe: `inspect_vocab(detail="summary")` returned 32,553 bytes to the client, including 10,817 bytes of structured content and 21,687 bytes of content blocks.
- Dispatch trace: `s0-live-stdio-trace.jsonl` records the same probe without payload contents: 34 argument bytes, 10,817 result bytes, 449.338 ms, success, and no mutation.

## Known Baseline Failures

These are deliberately recorded for later remediation; S0 does not correct them.

1. None of the wire-visible `operation` fields has an enum, despite the intended stable contract defining operation sets.
2. Sixteen wire-visible output schemas are generic objects with `additionalProperties: true`; `preview_logfile` has no output schema.
3. The default `inspect_vocab` response exceeds the 20 KB hard cap and the 12 KB P95 target.
4. The deterministic agent evaluator has passing positive and negative controls, but did not execute provider tasks. Two active tasks report `not_run` because no persisted draft was supplied; ten tasks are explicitly pending.
5. The installed-wheel smoke script still names legacy tools outside the current 17-tool surface.

## Fixture Audit

`examples/cbl_main.log.yaml` is present and tracked in this checkout. The earlier missing-fixture report was caused by the review bundle omitting a repository file, not by a source-tree defect. The real-wire test asserts its presence and, where Git metadata is available, tracking status.

## Verification

```text
uv run python scripts/capture_mcp_contract_baseline.py
env UV_CACHE_DIR=/tmp/wellplot-uv-cache WELLPLOT_MCP_TELEMETRY_PATH=docs/evaluations/mcp-remediation/s0-live-stdio-trace.jsonl uv run python scripts/capture_mcp_contract_baseline.py
uv run pytest -q tests/test_mcp_wire_contract.py tests/test_mcp_stable.py tests/test_mcp_server.py tests/test_mcp_service.py
uv run python scripts/run_agent_evals.py --mode deterministic --output docs/evaluations/mcp-remediation/s0-agent-deterministic.json
```

The MCP test selection passed with `141 passed, 2 skipped`. No provider evaluation was run: it remains opt-in through `WELLPLOT_RUN_LIVE_AGENT_EVALS=1`, avoiding unapproved external usage and cost.

## Freeze

Until S6, do not add tools, recovery branches, prompt heuristics, or authoring features. The next slice is S1: make the real wire schema, output schema, annotations, validation, and documentation share one source of truth.
