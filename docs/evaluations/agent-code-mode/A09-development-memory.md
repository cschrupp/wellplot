# A09 — Inspection Security and Observable Failures

## Status

- State: security/observability tranche accepted; A09 overall open
- Accepted security/observability checkpoint: `7ea43a6548a8bd1e5b44eb20c085a7027932e0db`
- Accepted metadata-first design checkpoint: `daef5d171828495b2f0dfcea25ae372f0bc39af4`
- Current work: D1 joint semantic-catalog/source-inspection design candidate; D2 feasibility remains open
- Provider, model, and endpoint calls: `0`
- Scientific turns: `0`
- C02 exposure: `0`
- Live smoke: not run or authorized by this slice

## Scope Implemented

This bounded candidate hardens existing observation paths without introducing
a planner, worker, graph, provider route, or persistence engine:

- Graph stage traces record cancellation and re-raise it unchanged. Unexpected
  exception messages are omitted; only exception type/module and explicitly
  safe diagnostic attributes are retained.
- Compile/session diagnostics carry an optional bounded failure-owner category
  through the existing result projection.
- Safe inspection projections bind a normalized request digest to the result
  digest without retaining the request text or provider payload.
- Existing section-action observations bind request, source snapshot, work
  contract, operation contract, DTO, and contract-validation result by digest.
- The D5 custody verifier validates and correlates those digest fields.
- Source descriptions are excluded from the planner-facing projection, with a
  regression for prompt-injection text.

## Validation

Focused provider-free command:

```text
UV_CACHE_DIR=/tmp/uv-cache-wellplot PYTHONPATH=src:. uv run --frozen pytest -q \
  tests/test_d5_section_action_observability.py::test_custody_preserves_contract_and_result_digest_bindings \
  tests/test_agent_execution_trace.py tests/test_agent_session.py \
  tests/test_code_mode_enrichment.py tests/test_code_mode_workflow.py \
  tests/test_section_work_contract.py tests/test_mcp_agentic_transaction.py
```

Result: `107 passed`.

Full repository-suite status is not claimed. Historical D5 observability tests
include pre-existing schema/role assumptions and remain part of A10
compatibility triage.

## Deferred Resource-Safety Decisions

No fixed LAS/DLIS source-file byte ceiling is added. Total file size is not a
semantic admission criterion because valid source files can be multi-gigabyte
and contain numerical samples that need not enter model context. This deferral
does not establish parser resource safety.

Metadata-first LAS/DLIS inspection, deterministic channel resolution
(`UNIQUE`, `AMBIGUOUS`, `ABSENT`, `UNKNOWN`), and model-aware token budgeting
remain unimplemented pending a separate design review. Replacement controls
must establish finite parser memory/time, metadata-volume, read-query, and
complete-request token budgets, retaining a secondary serialized-byte cap.
A09 is not complete until these safeguards are accepted or the remaining
limitation is explicitly accepted.

## Accepted Metadata-First Design

The independent design review accepted the metadata-first inspection and
context-budget architecture at exact checkpoint
`daef5d171828495b2f0dfcea25ae372f0bc39af4`. F13 and F14 are closed at that
checkpoint. The accepted separation is:

1. Metadata resolution identifies declared channel objects.
2. A separate host-owned addressability check determines whether the exact
   object can be selected by the existing renderer/binding interface.
3. Numerical sample availability remains independently unverified unless
   explicitly checked.

Automatic binding requires a unique metadata candidate and proven existing
renderer addressability. Semantic roles may match physical mnemonics only by
trusted, versioned alias evidence; similar names alone do not establish
scientific equivalence. The design does not authorize modifying the scientific
loader or binding schema.

No fixed total LAS/DLIS file-size ceiling is permitted. Metadata-only parsing,
four-state resolution, model-aware complete-request token accounting, and
replacement parser safeguards remain implementation prerequisites. Numeric
budgets, DLIS containment, exact Qwen/llama.cpp token accounting, and alias
catalog governance are not decided by design acceptance.

The provider-free feasibility results and evidence limits are recorded in
`docs/evaluations/agent-code-mode/A09-resource-budget-feasibility.md`. They do
not promote implementation or authorize endpoint/model/scientific work.

## D1 Joint Catalog/Source Design Candidate

The documentation-only D1 integrated design candidate is
`docs/architecture/A09_JOINT_SEMANTIC_CATALOG_AND_SOURCE_INSPECTION_DESIGN.md`.
It coordinates the semantic-family catalog and metadata-only LAS/DLIS source
inspection through the existing authoring-context boundary. D1 acceptance is
pending independent review; this candidate is not implementation authority
and does not revise the accepted F13/F14 design checkpoint.

The four local `examples/families/*.json` inputs were audited read-only. Their
schema/count/collision findings and exact SHA-256 identities are recorded in
the D1 document and feasibility record. They are reference/collision material
only: no row or presentation default is trusted, no data was copied into
production, and source licensing/redistribution is unknown. The audit found
wildcard and exact-assignment collisions, heterogeneous/wildcard units,
nonphysical/status concepts, sparse presentation values, and incompatible
family labels across the compatibility projection. These findings require
curation and provenance before any rule is enabled.

The integrated proposal explicitly keeps separate:

1. Physical channel resolution: `UNIQUE`, `AMBIGUOUS`, `ABSENT`, `UNKNOWN`.
2. Semantic-family classification: reviewed match, candidate-only,
   unclassified, or unknown.
3. Existing-renderer addressability: addressable, unaddressable, or unknown.
4. Numeric sample availability: normally `NOT_CHECKED`.

It preserves exact literal channel selection for unclassified vendor channels,
does not infer family absence from a nonexhaustive catalog, and blocks binding
unless metadata identity is unique and existing renderer addressability is
proven. No source loader, binding schema, renderer, workflow, or baseline was
changed.

D1 review and D2 feasibility are distinct. D2 still needs a valid synthetic
RP66 fixture and measured containment, supported LAS correctness/resource
matrix, justified finite budgets, exact Qwen/llama.cpp tokenizer/template
accounting, and accepted catalog provenance/license/governance. No numeric
limits, mappings, or conversion rules were selected.

## Boundaries

The candidate does not alter scientific fixtures, populations, gold, C02, or
semantic operation behavior. It does not add source-size rejection, metadata
parsing behavior, or provider retries. No knowledge-baseline promotion is
made before independent acceptance.
