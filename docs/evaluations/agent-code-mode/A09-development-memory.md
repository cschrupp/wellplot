# A09 — Inspection Security and Observable Failures

## Status

- State: security/observability tranche accepted; A09 overall open
- Accepted security/observability checkpoint: `7ea43a6548a8bd1e5b44eb20c085a7027932e0db`
- Accepted metadata-first design checkpoint: `daef5d171828495b2f0dfcea25ae372f0bc39af4`
- Current work: D1 accepted; D2 feasibility assessed 2026-11-03; parser,
  token, and catalog implementation remains unauthorized
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

## D2 Feasibility Result (2026-11-03)

The bounded D2 feasibility assessment and its decision table are recorded in
`docs/evaluations/agent-code-mode/A09-D2-feasibility-result.md`. It updates,
but does not promote or rewrite, the accepted D1 design.

- LASIO 0.32's EOF scan was confirmed from installed source. A temporary
  chunked-prefix prototype parsed generated LAS 1.2/2.0 examples with an empty
  sample matrix and returned `UNKNOWN` on test line/prefix-budget exhaustion.
  The marker rule follows CWLS LAS 2.0: the first reserved character after
  `~` chooses the section and the remainder is comment text. `~A` with a
  descriptive suffix is valid; `~Log_Data` remains outside this candidate.
  This is feasibility evidence, not production code or a complete format
  matrix.
- A 1,020-byte temporary RP66-style fixture generated with MIT `dliswriter`
  1.2.0 was accepted by locked `dlisio` 1.0.4. A metadata-only projection ran
  in a child with test-only AS/CPU limits and a parent timeout. No numerical
  curve APIs or scientific fixtures were used. The writer's `2**32` default
  output buffer was found to preallocate 4 GiB; the test explicitly supplied
  a smaller buffer. The writer is not a conformance validator.
- No numeric production parser limits were selected. Current cgroup memory
  enforcement is unavailable in the read-only WSL mount, and the empirical
  set does not represent multi-GB headers, DLIS scaling, or an accepted
  latency SLO. `RLIMIT_AS` is not direct RSS enforcement.
- Exact prompt-token admission remains blocked: the matching Qwen tokenizer,
  deployed llama.cpp build/template and schema-conversion behavior are not
  locally available. No endpoint `/apply-template` or `/tokenize` POST was
  made. Character ratios and generic tokenizers are not substitutes.
- Catalog governance recommendation: begin with zero active semantic-family
  mappings until each has domain-reviewed evidence, provenance and license
  status. Exact physical-channel selectors remain available. The supplied
  family JSON files remain untrusted reference/collision inputs; no mappings
  are approved by this study.

D2 feasibility is therefore delivered but not fully closed: numeric parser
budgets and exact model-token accounting remain open prerequisites, and the
catalog governance recommendation needs independent/domain acceptance before
mapping data can be enabled. A09 implementation and active-baseline promotion
remain unauthorized. The detailed primary references, observations, and
failure semantics are in the D2 result record.

## D1 Joint Catalog/Source Design Acceptance

The integrated A09-CAT/A09-SRC D1 design was accepted at exact checkpoint
`da23cd69792b4c75ed1da30bc0de35ca69ddcb38`. The complete decision and
Knowledge Delta are in `docs/architecture/A09_D1_ACCEPTANCE_RECORD.md`; the
design itself remains at
`docs/architecture/A09_JOINT_SEMANTIC_CATALOG_AND_SOURCE_INSPECTION_DESIGN.md`.
The accepted metadata-first foundation remains
`daef5d171828495b2f0dfcea25ae372f0bc39af4`; its historical document was not
rewritten.

F15/F16 are closed. Accepted F14 amendment: ambiguous bare `GR` requires
clarification, while an unambiguously qualified physical selector retains
exact-match precedence; family-level `ABSENT` requires complete inventory
and an explicitly reviewed exhaustive mapping for the relevant scope. The
catalog uses separate request-term-to-family and family-to-physical-channel
rules in one deterministic host resolver. Semantic resolution custody pins
`catalog_content_sha256` directly and an immutable release reference, with
digest revalidation before publication.

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

It also separates exact scientist request-term-to-family rules from
independently reviewed family-to-physical-channel rules. A single deterministic
host resolver executes those two stages; neither rule type establishes
physical inventory presence or renderer addressability. Semantic resolutions
carry `catalog_content_sha256` directly plus an immutable release reference,
and verify the digest again before publication.

The accepted design remains design-level only. The F14 amendment is accepted
as a design rule, but no production implementation, catalog mapping,
presentation preset, unit conversion, or resource budget is authorized by
D1.

It preserves exact literal channel selection for unclassified vendor channels,
does not infer family absence from a nonexhaustive catalog, and blocks binding
unless metadata identity is unique and existing renderer addressability is
proven. No source loader, binding schema, renderer, workflow, or baseline was
changed.

D1 review and D2 feasibility are distinct. The 2026-11-03 D2 feasibility
package established a tiny synthetic RP66-style fixture and contained metadata
parse, and a bounded synthetic LAS marker matrix. It did not establish DLIS
scaling, representative LAS behavior, or production budgets. Exact
Qwen/llama.cpp token accounting remains unavailable without matching local
assets/source. Catalog governance remains a recommendation awaiting
independent/domain acceptance; no semantic mappings or numeric limits were
selected. See `A09-D2-feasibility-result.md` for the evidence and remaining
gates.

## Boundaries

The candidate does not alter scientific fixtures, populations, gold, C02, or
semantic operation behavior. It does not add source-size rejection, metadata
parsing behavior, or provider retries. No knowledge-baseline promotion is
made before independent acceptance.
