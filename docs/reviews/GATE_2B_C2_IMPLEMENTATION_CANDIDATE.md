# Gate 2B-C2 implementation candidate

Status: submitted for SOL review; not accepted or activated.
Original authority baseline: `d6401a5dede0bf1035087a25fb2c371d5fa38bae`.
Direct parent: R8 clarification `962d2ff990d217c6f75517cee36ffeff550194d3`.

The canonical compiler now recognizes the two bounded productions and rejects
unmatched compound candidates without partial extraction. The existing dependency
verifier checks original facts, deterministic IDs, relation spans and request
scope; fresh anchor extraction checks named clause and selector custody. The
existing attachment transform produces scoped copies. The facade and session
carry the original compilation and scope binding in excluded fields, and the
private boundary checks the derived copies and current inspection snapshot.

Production stops before planner generation. The existing graph and private
apply boundaries independently refuse C2 work. Synthetic tests call existing
conversion, attachment, enrichment and receipt functions directly; no runtime
bypass was added. The production manifest refresh was necessary because all
eight touched runtime sources are members of the existing attested closure.

## Qualification

From the canonical checkout, using the existing Python 3.12 virtualenv:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_d5_5j_obligations.py tests/test_code_mode_planner.py \
  tests/test_code_mode_workflow.py tests/test_d5_single_engine_convergence.py \
  tests/test_agent_session.py tests/test_direct_notebook_transaction.py \
  tests/test_mcp_agentic_transaction.py
```

Result: **294 passed in 32.74 seconds**, exit 0.
Scoped Ruff lint/format, Python compilation, `git diff --check`, and
`PYTHONPATH=src .venv/bin/python scripts/d5_single_engine_attestation.py --check`
passed. The full repository suite was not run. Intermediate failures were in
new test fixtures (diagnostic code asserted as exception text, incomplete
document or wire fixtures), not historical regression failures.

## Review checks

| Check | Evidence |
| --- | --- |
| SCOPE_CHECK | PASS: bounded grammar, existing custody and three guards only. |
| NECESSITY_CHECK | PASS: one shared family classifier covers omitted custody; manifest changes are mechanical. |
| CANONICAL_REUSE_CHECK | PASS: existing fact, dependency, scope, attachment, resolver and snapshot APIs. |
| AUTHORITY_CHECK | PASS: R8 clarification governs; no provider calls, scheduling or publication. |
| PROVENANCE_CHECK | PASS: original bytes, fresh anchors, exact IDs and derived copies are checked. |
| SINGLE_ENGINE_CHECK | PASS: convergence tests and production attestation; no alternate route. |
| REGRESSION_CHECK | PASS: 294 provider-free tests in the selection above; no repository-wide claim. |
| GIT_CUSTODY_CHECK | PASS at local diff review: explicit paths only, separate clarification parent. |
| DRIFT_CHECK | PASS: C2 compiler/custody objective only; next gate is independent implementation review. |

Deferred: complete C1 REQUEST matrix, dependent execution, prerequisite
admission, sequencing, publication and live inference. Do not merge or activate.
