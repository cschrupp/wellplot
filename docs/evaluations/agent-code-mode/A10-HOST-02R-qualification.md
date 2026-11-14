# A10-SEM-HOST-02R Qualification Record

Status: `A10_SEM_HOST_02R_PROVIDER_FREE_PASS — INDEPENDENT_REVIEW_REQUIRED`

## Candidate

- Corrective implementation commit: `ad46ff7718ea2cbabdb28be4640d2793408735a4`
- Parent: `4a52b7dc4aeda686f518cabd704b2c0765e116c4`
- Branch: `engineering-d5-binding-path-repair`
- Provider/model/live calls: `0`
- Planner wire-schema change: none; `planner.py` is absent from the candidate diff.

The unrelated notebook edits and untracked `examples/families/` directory were
preserved and were not included in the candidate.

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

Result: `316 passed in 8.45s`, exit code `0`, pytest stderr empty.

Additional gates:

- Ruff check: PASS.
- Ruff format check: PASS.
- Python compilation: PASS.
- `git diff --check`: PASS.
- `scripts/d5_single_engine_attestation.py --check`: PASS.
- `_PlannerWirePlan` schema SHA-256 before/after: `b6b05fec2caabbc62708d17b1d752d8888e6cf7e2b91b4b67889eb583b080cbb`.

## Candidate file digests

These SHA-256 values identify the committed implementation/test inputs used
for the qualification:

```text
d7dbebaf581410e47e4ac12471a9ab07ebb62997d8a91d531a293278bf9e6f77  src/wellplot/agent/code_mode/obligations.py
69e98a31d12da44b0f4663092346c90e9087e671f5d0d33031f0f06bbf86a193  src/wellplot/agent/code_mode/facade.py
8aa59abb937a02eb723e83591fde2d6ea6a5546912c2f1d7e2e6de433105d1ef  src/wellplot/agent/code_mode/enrichment.py
b57239082f39f5fa487bb85185fb7d2d9242a94d284de1fb0e3c0ddae9afbe03  src/wellplot/agent/code_mode/worker_contracts.py
520f70d3dce63bb18bce40aa02003195638eae4d6c46f6d9a5eea0c09e3d7ba8  tests/test_host_02_scalar_binding.py
327ab9eedebb4f75739b755021229da3ca38d35cb8dbdb4c560a0c9a6aa1bf0a  docs/architecture/D5_SINGLE_ENGINE_PRODUCTION_MANIFEST.json
```

The known stale Codex checkpoint-ref repack warning occurred during commit
maintenance. It did not affect the commit object, test results, or branch
content.
