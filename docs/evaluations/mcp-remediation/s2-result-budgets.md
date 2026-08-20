# S2 Result-Budget Evidence

## Scope

S2 limits normal stable-MCP responses without changing the 17-tool surface or
adding authoring capabilities. The server now returns compact mutation evidence,
scoped inspections, and explicit full-detail exceptions.

## Result Rules

- `create_draft` reports the saved draft, starter, and section identities. It
  does not return a document snapshot.
- Mutations return `changed_fields` and only the changed canonical values.
  Serialization-only compatibility extensions and generated labels equal to a
  binding channel are excluded from the evidence.
- `inspect_authoring(detail="summary")` returns identities and concise object
  facts. `detail="full"` is the explicit complete-object exception.
- `inspect_vocab(detail="summary")` without a family returns only the available
  families and resource URIs. A requested family returns its compact usable
  values; `detail="full"` returns the selected catalog payload.
- `inspect_source(include_metadata=false)` returns channel summaries. Full well
  metadata and provenance require `include_metadata=true`.

## Live Stdio Measurements

Measured by `tests/test_mcp_wire_contract.py` against the production local
stdio server with a cloned CBL fixture:

| Response | Client-visible bytes |
| --- | ---: |
| `create_draft` | 664 |
| `inspect_authoring(detail="summary")` | 3,773 |
| `inspect_source()` | 3,976 |
| `inspect_vocab(detail="summary")` | 2,365 |
| `inspect_vocab(family="track")` | 3,529 |
| `edit_section` minimal diff | 2,310 |
| `validate_logfile` | 313 |
| `inspect_authoring(detail="full")` | 37,928 |

The seven normal responses have a measured P95 of 3,976 bytes. The
`create_draft` plus summary-inspection pair is 4,437 bytes. Both are below the
S2 4 KB ordinary-result target, 12 KB P95 limit, and 20 KB hard default cap.
The 37,928-byte complete authoring inspection is permitted only through its
explicit `detail="full"` request.

The separately captured `mcp_contract_baseline_v3.json` probe records the
default vocabulary-index response at 2,268 bytes using compact JSON encoding.

## Contract Evidence

- `tests/fixtures/mcp_contract_baseline_v1.json` remains the S0 baseline.
- `tests/fixtures/mcp_contract_baseline_v2.json` remains the S1 typed-schema
  baseline.
- `tests/fixtures/mcp_contract_baseline_v3.json` records S2's compact output
  models and updated inspection descriptions.

## Verification

```bash
env UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q \
  tests/test_mcp_wire_contract.py \
  tests/test_mcp_stable.py
env UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check \
  src/wellplot/mcp/stable.py \
  src/wellplot/agent/tool_contract.py \
  tests/test_mcp_stable.py \
  tests/test_mcp_wire_contract.py
env UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check \
  src/wellplot/mcp/stable.py \
  src/wellplot/agent/tool_contract.py \
  tests/test_mcp_stable.py \
  tests/test_mcp_wire_contract.py
```
