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

## SOL corrective for C2-I1 through C2-I3

Reviewed parent: `ab0a0642a2224456cc6a98a954d8ec87abb30e98`.
I1 adds the inspected plan's retained compilation to the existing entry guard;
missing or conflicting explicit custody cannot override a retained dependency.
I2 compares the regenerated aggregate against both the transported obligations
and the aggregate on the inspected plan. No other production source changed.

| Finding / adversarial coverage | Pytest node ID (without parameter suffix where grouped) |
| --- | --- |
| I1 explicit, stripped, retained-only and conflicting custody; no service | `tests/test_direct_notebook_transaction.py::test_c2_private_apply_rejects_before_service_construction` |
| I2 aggregate-only change, duplicate/omitted/altered/wrong-scope copies, scope hints and cardinality, absent/ambiguous named resolution, stripped graph custody | `tests/test_code_mode_workflow.py::test_c2_graph_rejects_attached_plan_before_dispatch` |
| I3 facade and session custody projections and public format parity | `tests/test_code_mode_workflow.py::test_graph_merges_report_and_sections_in_plan_order` |
| I3 normalized session bytes and digest | `tests/test_agent_session.py::test_c2_session_uses_exact_stripped_compiler_bytes` |
| I3 Notebook and MCP isolation | `tests/test_direct_notebook_transaction.py::test_c2_adapters_reject_without_publication` |
| Legacy private apply retains normal success | `tests/test_direct_notebook_transaction.py::test_notebook_semantic_postcondition_passes_before_persistence` |
| Named provenance, required anchors, and declaration forgery | `tests/test_d5_5j_obligations.py::test_c2_named_compilation_keeps_distinct_clause_and_selector_spans`, `tests/test_d5_5j_obligations.py::test_c2_named_scope_rejects_forged_declarations` |
| UTF-8, quoted non-interception and unsupported compounds | `tests/test_d5_5j_obligations.py::test_c2_compiler_preserves_literal_and_utf8_boundaries`, `tests/test_d5_5j_obligations.py::test_c2_rejects_unmatched_compound_without_salvaging_facts` |
| Existing C1 identity, relation, geometry, and original-byte tampering | `tests/test_d5_5j_obligations.py::test_request_dependency_original_provenance_and_roundtrip`, `tests/test_d5_5j_obligations.py::test_dependency_rejects_forged_fact_and_matching_pointer`, `tests/test_d5_5j_obligations.py::test_dependency_relation_and_evidence_cannot_be_replaced_or_stripped`, `tests/test_d5_5j_obligations.py::test_dependency_rejects_altered_endpoint_or_geometry`, `tests/test_d5_5j_obligations.py::test_request_dependency_rejects_fabricated_authority` |
| Zero provider calls, including stripped custody; legacy call behavior | `tests/test_code_mode_planner.py::test_c2_planner_stops_before_provider`, `tests/test_code_mode_planner.py::test_planner_makes_one_static_structured_call` |

Resolver limitation: the existing containment fallback can match an empty
subtitle on an otherwise unrelated section. The absent-section regression
uses populated, unrelated title and subtitle fields. Resolver behavior was not
changed; this should be reviewed before any future execution authorization.
The unconditional C2 guards do not depend on successful section resolution.

The exact seven-module command above passed again: **301 passed in 34.40 s**,
exit 0. Scoped `ruff check`, `ruff format --check`, `python -m py_compile`
on the five touched Python files, `git diff --check`, and the attestation
`--check` command above all exited 0. The manifest refresh changes only the
hash for `_private_apply.py`. No repository-wide run, live inference, dependent
workers, or C2 publication was performed.
