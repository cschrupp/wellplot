# A10-SEM-HOST-02R Qualification Record

Status: `A10_SEM_HOST_02R2_PROVIDER_FREE_PASS — FINAL_HA_REVIEW_REQUIRED`

## Candidate

- Corrective implementation commit: `b398e7d4293f76ae1ff4a397e5b05e7f65b3cc93`
- Parent: `a259d4a43510a206e7836ea59885a3aac6a559f5`
- Branch: `engineering-d5-binding-path-repair`
- Provider/model/live calls: `0`
- Planner wire-schema change: none; `planner.py` is absent from the candidate diff.

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

Result: `321 passed in 14.25s`, exit code `0`, pytest stderr empty.

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
96f8665629be9312b71ff43d960c6c1eba16bf01a5c5e1d6ae1a69e33a496aa2  src/wellplot/agent/session.py
69e98a31d12da44b0f4663092346c90e9087e671f5d0d33031f0f06bbf86a193  src/wellplot/agent/code_mode/facade.py
8aa59abb937a02eb723e83591fde2d6ea6a5546912c2f1d7e2e6de433105d1ef  src/wellplot/agent/code_mode/enrichment.py
b57239082f39f5fa487bb85185fb7d2d9242a94d284de1fb0e3c0ddae9afbe03  src/wellplot/agent/code_mode/worker_contracts.py
4095170d84c18f1b44f319b560821c2b2c79d4ff33726c35a7c273be959bb043  tests/_mcp_fixtures.py
f620baec92641631066bad32e3d8b30c1c2d8bec7959ce409cd4064fe6624bd9  tests/test_host_02_scalar_binding.py
ad2005a7f4f74c67aae374898fcb84e80c6e5f172bad7c1cc4968c4ac532e3fc  tests/test_mcp_agentic_transaction.py
4bfd6634e27fd171fa27e341359b62bc242f51b42c6a908f8334f7471767408c  docs/architecture/D5_SINGLE_ENGINE_PRODUCTION_MANIFEST.json
```

The known stale Codex checkpoint-ref repack warning occurred during commit
maintenance. It did not affect the commit object, test results, or branch
content.
