# S6 Real-Wire and Provider-Evaluation Evidence

## Scope

S6 replaces internal-only confidence with client-visible evidence. It does not
add MCP tools, new agent fallback logic, or provider-specific recovery rules.

## Real Stdio Conformance

`tests/test_mcp_wire_contract.py` starts the production MCP server through
`LocalStdioMcpRuntime` and exercises all 17 stable responsibilities with one
minimal valid request. The coverage includes draft creation, scoped inspection,
source inspection, vocabulary discovery, all mutation families, validation,
preview, and final rendering.

The same suite verifies that:

- every non-preview tool returns the advertised structured-output envelope;
- every non-preview valid response is at most 20 KB client-visible JSON;
- missing required fields fail over stdio for all tools that declare them;
- every operation-bearing tool rejects an invalid operation value over stdio;
- `inspect_vocab` rejects an invalid enum value over stdio;
- all six prompts resolve through the real protocol and refer only to stable
  tool names;
- all 15 static resources and four resolved production-example resources are
  readable through the real protocol.

## Resource Budget

The current static and resolved resource set contains 19 readable resources.
All resources are non-empty. The largest is
`wellplot://authoring/schema/canonical.json` at 943,651 UTF-8 bytes.

That resource remains available only through an explicit client read. It is a
resource/context-overload risk, not a normal tool-result budget exception:
agents must use `inspect_vocab` and scoped resources first and must not add the
canonical schema to routine context automatically. The real-client regression
limit is 1 MB, preventing unreviewed growth while preserving the full canonical
schema artifact.

## Known Protocol Limitation

FastMCP currently ignores unknown top-level tool arguments. S6 records the
behavior with a real `inspect_vocab` call rather than treating it as a passing
strict-validation test. This is classified as `contract/schema` and remains
owned by the protocol-boundary decision already recorded for S9. Nested typed
payloads continue to reject unknown properties.

## Provider Evaluation Status

No live-provider matrix is committed with this slice. It requires explicit,
repeatable runs against two materially different provider families and a task
suite with complete deterministic final-state assertions. The local evaluation
runner remains opt-in through `WELLPLOT_RUN_LIVE_AGENT_EVALS=1`; credentials,
provider output, and ad-hoc notebook state are intentionally excluded from this
evidence commit.

S7 must not remove host behavior based on this local conformance result alone.
Before S7, capture versioned live evidence with per-task correctness, tool
calls, tool errors, retries, context/result volume, latency, and a failure
classification from the remediation playbook.

## Verification

```bash
env UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q \
  tests/test_mcp_wire_contract.py
env UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check \
  tests/test_mcp_wire_contract.py
env UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check \
  tests/test_mcp_wire_contract.py
```
