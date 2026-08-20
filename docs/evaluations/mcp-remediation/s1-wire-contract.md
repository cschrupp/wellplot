# S1 Wire-Contract Evidence

## Scope

S1 replaces the stable MCP projection's coarse callable annotations with typed
Pydantic models generated from the same compact contract profile used for the
server registration. This slice does not add tools, authoring operations, agent
fallbacks, or new capabilities.

## Contract Invariants

- `stable_tool_contract.yaml` remains the reviewed declaration of the 17 stable
  responsibilities and their behavior annotations.
- `stable_tool_profile()` builds a typed input model for every tool from that
  declaration and canonical authoring field models.
- The registered callable signature uses those input-model field annotations.
  The real MCP SDK therefore derives the same schema the profile exposes.
- Structured results use explicit inspection, validation, artifact, mutation,
  source-inspection, and header-fill result models. `preview_logfile` remains
  an image artifact without structured output.
- `tests/fixtures/mcp_contract_baseline_v1.json` is preserved as S0 historical
  evidence. `mcp_contract_baseline_v2.json` records the S1 surface.

## Real Stdio Results

Captured with:

```bash
env UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run python \
  scripts/capture_mcp_contract_baseline.py \
  --output tests/fixtures/mcp_contract_baseline_v2.json
```

- Tool count: 17.
- Operation-bearing inputs with advertised enums: 10.
- Structured output schemas: 16. `preview_logfile` is intentionally unstructured.
- Read-only, idempotent tools: `inspect_authoring`, `inspect_source`,
  `inspect_vocab`, `validate_logfile`, and `preview_logfile`.
- `tests/test_mcp_wire_contract.py` compares every live tool's description,
  input schema, output schema, and annotations against `stable_tool_profile()`
  without schema normalization.

## Residual SDK Limitation

FastMCP derives the top-level argument model from the callable signature. Its
public API currently uses the SDK default for unknown top-level arguments,
which is to ignore them. Nested typed payloads use `extra="forbid"` and reject
unknown properties. S9 owns the decision whether to change this protocol-level
behavior; S1 intentionally does not use private SDK internals to override it.

## Verification

The focused contract suite validates model constraints, output envelopes, real
stdio equality, and the existing stable projection behavior. Provider calls are
not part of S1.
