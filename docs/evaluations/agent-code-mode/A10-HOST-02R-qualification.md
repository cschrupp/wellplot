# A10-SEM-HOST-02R Qualification Record

Status: `A10_SEM_HOST_02R3_INDEPENDENT_REVIEW_PASS`

## Candidate

- Corrective implementation commit: `511c6a80489eb9745b6aa2bc3fddc8e801bb417b`
- Parent: `1b5207787c4e8fceb925435e64ea1cf8dcdc0d10`
- Branch: `engineering-d5-binding-path-repair`
- Provider/model/live calls: `0`
- Planner wire-schema change: none; `planner.py` changes are limited to
  host-context scope attachment and validation.

The unrelated notebook edits and untracked `examples/families/` directory were
preserved and were not included in the candidate.

This corrective closes the remaining HOST-02R qualification gaps without
introducing a second engine or workflow. Reviewed semantic request extraction
now uses canonical request-term normalization while preserving the exact
request span. The flagship path crosses the real work/operation contracts,
lowering, reconciliation, execution, request postconditions, and semantic
publication verification. Notebook and MCP regressions exercise the same
automatically generated semantic publication contract and both fail closed
before persistence when semantic verification rejects it.

## Corrective results

### R1 — Authoring-intent-gated semantic extraction

Reviewed catalog terms are recognized only in bounded authoring constructions
such as `Plot Gamma Ray.` and `Bind Gamma Ray.`. Informational or comparative
sentences do not create binding obligations. The obligation preserves the
exact requested phrase and request-byte span; it does not resolve `Gamma Ray`
to `GR` during request compilation.

### R2 — Host-derived implicit section scope

An implicit existing-section scope is represented by the internal
`ScopeDeclaration.origin=HOST_CONTEXT` marker with no request provenance. The
canonical document remains the only source for selecting the section. Explicit
request section declarations retain `origin=REQUEST` and their existing
provenance.

### R3 — Canonical compile failure envelope

Pre-worker `SectionWorkContractError` failures are projected by
`CodeModeCompileFacade` into the existing `CodeModeCompileResult` diagnostic
envelope. Codes are bounded under `host_contract.*`, messages are selected from
a fixed safe map with a generic fallback, and the failure owner is
`host_safety`. No adapter-specific exception handling was added.

### R4 — Exact replay versus collision

An existing derived binding ID is accepted as replay only when the selected
track, source handle, source revision, inspection snapshot, requested/physical
channel identity, and authorized default presentation state agree. Conflicting
label, scale, style, source lineage, physical identity, track, or channel state
returns `binding_identity_collision`; no replacement ID is allocated.

Source contexts now carry an incrementally computed source-content SHA-256,
revalidated against the source revision token, and the private semantic source
binding carries that digest. Provider-facing work contracts remain unchanged.

### R3 — HOST_CONTEXT scope authority closure

Anonymous existing-section scopes created by the host for bounded semantic
requests now ignore planner `existing_section_hint` values during assignment
and attachment. The actual host-owned scope declaration is used for lookup;
its attached hint is always `None`, so the existing-section resolver selects
exactly one eligible section or fails closed on zero or multiple candidates.
Explicit `REQUEST` section scopes retain their existing exact-target behavior.
Revision-mode validation permits a missing hint only when the attached scope
is the anonymous host context scope.

## Flagship provider-free path

`tests/test_host_02_scalar_binding.py::test_host02_flagship_chain_reaches_canonical_resolution_reconcile_and_verify`
exercises:

```text
Plot Gamma Ray.
-> reviewed request obligation
-> host contextual section/track/source binding
-> pre-worker expected semantic slot
-> ADD_BINDING contract
-> deterministic AddBindingAction fixture
-> AuthoringCurveBindingIntent
-> AuthoringContextResolver: Gamma Ray -> GR
-> reconcile_authoring: CREATE curve_binding
-> AuthoringService / execute_authoring_plan
-> shared semantic publication verification
```

The fixture is deterministic and provider-free. It does not alter the
scientific loaders, reconciler, executor, persistence implementation, or
planner wire schema.

The flagship assertions also require one host-owned binding with physical
mnemonic `GR`, preserve the existing section/track and source identity, and
pass the shared `verify_document_postconditions()` boundary before the
semantic publication check.

## Negative and parity coverage

The focused suites provide the following coverage without adding a parallel
engine:

- R1 informational-term rejection and bounded authoring positives: the new
  parameterized tests in `test_host_02_scalar_binding.py`.
- Section and track target missing/ambiguous/incompatible behavior:
  `test_section_work_contract.py` target and operation-contract tests.
- Source missing, ambiguity, unavailable state, and no-fallback behavior:
  `test_section_work_contract.py::test_requested_unavailable_source_fails_before_worker_generation`
  and `test_selected_source_missing_channel_and_unselected_inventory_disagreement_fail`.
- Addressability and exact physical identity: `test_authoring_context.py`
  four-state resolution tests and `test_semantic_catalog.py` addressability,
  duplicate-identity, and physical-precedence tests.
- Missing, extra, duplicate, reassigned, cross-source, snapshot, revision,
  content, and catalog-drift semantic evidence:
  `test_semantic_catalog.py` shared publication verifier and content-bound-rule
  tests.
- Worker omission, reassignment, duplicate realization, and operation
  contract safety: `test_section_work_contract.py` action-contract tests.
- New-parent and sparse-raster exclusion: HOST-02 tests
  `test_sparse_binding_rejects_new_parent_operation` and
  `test_sparse_binding_rejects_array_channel_kind`.
- Notebook and MCP shared-verifier ordering and no-publication rejection:
  `test_direct_notebook_transaction.py` and
  `test_mcp_agentic_transaction.py` semantic postcondition tests.
- Explicit physical requests, unrelated requests, empty-catalog compatibility,
  and CAT-03 activation containment: `test_semantic_catalog.py` physical,
  empty-catalog, and activation-guard tests.
- Automatic semantic-contract parity and fail-closed publication for both
  public adapters: `test_host02_automatic_semantic_contract_reaches_both_adapters`
  and `test_host02_automatic_semantic_failure_prevents_both_publications` in
  `test_mcp_agentic_transaction.py`.
- HOST_CONTEXT authority: `test_host_context_scope_ignores_planner_hint_for_unique_section`,
  `test_host_context_scope_hint_cannot_resolve_ambiguity`, and
  `test_host02_notebook_ignores_planner_hint_for_host_context_scope`.

No adapter constructs a HOST-02 semantic contract. Both adapters consume the
same shared post-publication verification boundary.

## Qualification command and results

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_host_02_scalar_binding.py \
  tests/test_section_work_contract.py \
  tests/test_code_mode_enrichment.py \
  tests/test_d5_5j_obligations.py \
  tests/test_code_mode_workflow.py \
  tests/test_direct_notebook_transaction.py \
  tests/test_mcp_agentic_transaction.py \
  tests/test_semantic_catalog.py \
  tests/test_authoring_context.py \
  tests/test_agent_session.py
```

Result: `324 passed in 17.73s`, exit code `0`, pytest stderr empty.

Additional gates:

- Ruff check: PASS.
- Ruff format check: PASS.
- Python compilation: PASS.
- `git diff --check`: PASS.
- `scripts/d5_single_engine_attestation.py --check`: PASS.
- `_PlannerWirePlan` schema SHA-256 before/after:
  `b6b05fec2caabbc62708d17b1d752d8888e6cf7e2b91b4b67889eb583b080cbb`.

The automatic Notebook/MCP parity tests use deterministic provider-free
responses through the existing canonical worker seams. No provider/model,
live, or scientific calls were made by the qualification.

## Candidate file digests

These SHA-256 values identify the committed implementation/test inputs used
for the qualification:

```text
98b5c1b0889d2782546f25c978820e0651363a0f6a9dade54f9b74f150654ee3  src/wellplot/agent/code_mode/obligations.py
7ff3b59dd9515bcaec0168b5cc3b9e0c0fc36026e632f8de0ce9585b2f6c8ddd  src/wellplot/agent/code_mode/planner.py
96f8665629be9312b71ff43d960c6c1eba16bf01a5c5e1d6ae1a69e33a496aa2  src/wellplot/agent/session.py
69e98a31d12da44b0f4663092346c90e9087e671f5d0d33031f0f06bbf86a193  src/wellplot/agent/code_mode/facade.py
8aa59abb937a02eb723e83591fde2d6ea6a5546912c2f1d7e2e6de433105d1ef  src/wellplot/agent/code_mode/enrichment.py
b57239082f39f5fa487bb85185fb7d2d9242a94d284de1fb0e3c0ddae9afbe03  src/wellplot/agent/code_mode/worker_contracts.py
48c4f5aba8d76c66d20f78e56685dfa2e40fb78f12a1b489ffaac9b0eda25686  tests/_mcp_fixtures.py
df2cb04d921ec85d6298cb503d0d1756b665d08b53b62abe632dfa11e767ec81  tests/test_host_02_scalar_binding.py
a81a42b9dc5cd23cabc1cd6deeceff27ea7346eaf64bfe6731e568a83319e715  tests/test_mcp_agentic_transaction.py
a421e6e09b499086c270a3e4ac786d4a80e6f03523b2e0178a6ad2ab50026839  docs/architecture/D5_SINGLE_ENGINE_PRODUCTION_MANIFEST.json
```

The known stale Codex checkpoint-ref repack warning occurred during commit
maintenance. It did not affect the commit object, test results, or branch
content.

## Independent acceptance

Independent review accepted HOST-02R3 as
`A10_SEM_HOST_02R3_INDEPENDENT_REVIEW_PASS`. GitHub verification confirms the
remote branch resolves to `fec44639c0dbf4d80861bad9742e98c1b30c6f25`; the
implementation lineage is `1b5207787c` -> `511c6a8048` -> `fec44639c0`.
The reviewer accepted the host-authority source behavior, the committed
qualification record, and the containment of the corrective without
independently rerunning the reported 324-test suite.

HOST-02R3 is closed. This acceptance does not authorize P8, a new live smoke,
provider/model calls, holdout access, baseline promotion beyond this recorded
Knowledge Delta, or semantic architecture expansion.
