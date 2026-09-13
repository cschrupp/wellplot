# CM-00 Baseline Evidence Manifest

- **Frozen reference:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Reference branch:** `mcp-stabilization`
- **Scope:** Documentation and evidence scaffolding only. No runtime behavior,
dependencies, prompts, provider configuration, or production imports changed.

## Reproduction Inputs

Structural measurements are taken from the frozen Git tree, not the working
tree:

```bash
git show f03f76b:src/wellplot/agent/core.py | wc -lc
git archive --format=tar f03f76b src/wellplot/agent | tar -xO | wc -lc
git archive --format=tar f03f76b src/wellplot/agent/graph | tar -xO | wc -lc
git ls-tree -r --name-only f03f76b -- src/wellplot/agent/graph | rg '\\.py$' | wc -l
git grep -h '^def test_' f03f76b -- tests | wc -l
```

The frozen CBL request is
`tests/fixtures/agentic_cbl/frozen_prompt.txt`. Its compile-only contract is
`tests/fixtures/agentic_cbl/compile_contract.json`.

## Evidence Status

| Evidence | Status | Classification |
|---|---|---|
| Structural baseline | Captured in `CM-00-baseline.json` | Structural |
| Repository Ruff format check | `failed_preexisting` | Deterministic baseline condition |
| Deterministic full suite | `failed_before_completion` | Deterministic baseline failure |
| Architecture checks | `not_applicable_at_CM-00` | Not available |
| Frozen CBL compile-only replay | `not_run` | Not available |
| Full live CBL reconstruction | `not_reproducible_at_CM-00` | Historical observational evidence only |
| Simple-section live run | `not_run` | Not available |
| Report live run | `not_run` | Not available |
| Revision live run | `not_run` | Not available |

Known historical CBL traces are diagnostic history. They do not establish a
release baseline unless the exact frozen commit, provider/model configuration,
request, and verifier outcome are reproducibly captured.

The deterministic suite has a known baseline failure before completion:

```text
tests/test_agent.py::AgentTests::test_server_command_prefers_sibling_entry_point
TypeError: _server_command() missing 1 required positional argument: 'server_module'
```

The focused command completed with `1 failed, 66 passed in 6.33s`:

```bash
UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q --maxfail=1
```

The existing `scripts/check_agent_architecture.py` is a legacy remediation
budget check that requires an earlier L0 baseline. It is not a Code Mode
architecture guard and is therefore not applicable until CM-01 adds the v2
AST import-invariant test.

The repository-wide `ruff format --check src tests` command also reports 17
pre-existing files that would be reformatted. CM-00 does not reformat unrelated
runtime or test files.

## Decision

**PROCEED to CM-01 after this CM-00 documentation/evidence-only commit.**

The known v1 test failure is baseline evidence to preserve and compare; CM-01
does not authorize repairing it as incidental migration work. The decision
authorizes architecture guards only. It does not authorize a v2 runtime package,
feature flag, provider change, program interpreter, SDK, LangGraph node,
capability change, or v1 deletion.
