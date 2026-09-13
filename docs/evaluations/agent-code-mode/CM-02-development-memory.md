# CM-02 Development Memory

## Scope

CM-02 creates a static, deterministic inventory of the current agent migration
topology. It does not import Wellplot runtime modules, alter any caller,
change routing, or authorize legacy deletion.

- **Migration baseline SHA:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Reachability analysis SHA:** `d92826130c433dd1ca95202949898c472cce398a`
- **Analyzer:** `scripts/check_agent_reachability.py`
- **Evidence:** `CM-02-reachability.json`

## Decisions And Invariants

- The analyzer parses source through `ast` and never imports Wellplot.
- Seeds retain provenance: one public package entry, two MCP entries, one
  notebook entry, and ten project-script entries.
- Each reachable module records one deterministic shortest import path for
  every reaching seed. Aggregate reachability is not used as a classification.
- Classifications include a rationale and express migration intent only. A
  reachable module can be `replace` or `delete-after-cutover`; an unreachable
  module is not thereby removable.
- Direct `TYPE_CHECKING` and `typing.TYPE_CHECKING` bodies are excluded from
  runtime reachability. Relative imports and direct-script sibling imports are
  resolved statically.

## Inventory Result

- 101 modules, 357 import edges, and 14 seeds were recorded.
- No local references remained unresolved. Required public, MCP, and notebook
  seeds have no unresolved known `wellplot.*` imports.
- Classification totals are: 54 `keep`, 24 `refactor`, 6 `replace`, 7
  `delete-after-cutover`, 10 `test-only`, and 0 `historical-doc-only`.
- All 13 required legacy and structured-worker modules remain reachable from a
  public runtime seed. None are reachable only from notebook or scripts, and
  none are currently unreachable.

This confirms the current v1 route still depends on every required migration
candidate. CM-02 authorizes no deletion and no caller refactoring.

## Validation

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q tests/test_agent_reachability.py tests/test_agent_v2_architecture.py`
  passed: `12 passed in 5.56s`.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff check scripts/check_agent_reachability.py tests/test_agent_reachability.py`
  passed.
- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run ruff format --check scripts/check_agent_reachability.py tests/test_agent_reachability.py`
  passed: `2 files already formatted`.
- `jq empty docs/evaluations/agent-code-mode/CM-02-reachability.json` passed.
- `git diff --check` passed.
- The test suite writes the same inventory twice and verifies byte-identical
  output. It also verifies that the committed manifest equals a fresh analysis.

## Runtime And Production Delta

- Runtime behavior delta: zero.
- Public API, provider, MCP, LangGraph, routing, capability, and legacy-code
  delta: zero.
- `src/wellplot` production LOC delta: zero.
- Development tooling delta: one 641-line static analyzer and one 216-line
  focused test module.

## Limitations And Deferrals

The inventory intentionally does not resolve `importlib.import_module`,
`__import__`, plugin entry points, or string-based module loading. It is a
static architectural map, not an observed runtime import trace or a whole
program proof.

CM-03 owns dual-engine A/B evaluation support. It may consume this inventory,
but must not treat the `delete-after-cutover` label as permission to remove
code. Legacy reachability and deletion remain governed by later cutover gates.

## Decision

**PROCEED to CM-03 only after this slice is committed and pushed.**
