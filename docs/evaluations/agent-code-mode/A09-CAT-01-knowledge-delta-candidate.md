# A09-CAT-01 Knowledge Delta Candidate

Status: `CORRECTIVE_CANDIDATE / INDEPENDENT_REVIEW_PENDING`

This candidate records the provider-free semantic-catalog foundation added on
the `engineering-d5-binding-path-repair` development lineage. It is not an
accepted Knowledge Delta and has not been promoted into the Current Active
Baseline.

## Decision

Adapt the accepted A09 D1 design within the existing `AuthoringContextResolver`
and `reconcile_authoring()` path. Keep request-term recognition separate from
physical-channel matching, and require reviewed, provenance-bearing rules for
semantic resolution. The production default catalog contains zero families
and zero active rules. The untracked files under `examples/families/` remain
reference material and are not loaded by production code.

Classification: `ADAPTED` from the accepted A09 D1 catalog and canonical
authoring contracts. No new resolver service, authoring graph, scientific
loader, executor, renderer, or persistence path is introduced.

## Candidate behavior

- The immutable catalog contract has a version, release reference, canonical
  content digest, provenance records, review metadata, request-term rules,
  physical-channel rules, and stable family identities.
- Only rules marked reviewed, with approved review and permitted provenance
  status, can participate in semantic matching. Candidate and deprecated rules
  are inert.
- Matching is order-independent. Multiple family interpretations or physical
  candidates fail as ambiguous rather than selecting the first catalog item.
- Exact physical selection remains usable with the empty catalog. An explicit
  physical selector includes the complete physical identity.
- Incomplete inventories cannot establish absence. Family-level absence stays
  open-world because no reviewed exhaustive-scope contract is implemented.
- Isolated semantic-resolution evidence binds section, track, binding ID,
  selected physical identity, catalog release/digest, and source revision. The
  selected identity is stored as canonical immutable JSON. A verifier rejects
  scope, identity, catalog, or source-revision drift.
- Physical identity, renderer addressability, and numerical sample availability
  remain separate. `UNADDRESSABLE` and `UNKNOWN` candidates cannot be bound.
- Catalog-backed resolution requires a nonempty supported LAS/DLIS physical
  identity and an explicitly supplied `ADDRESSABLE` value; model defaults do
  not establish addressability.
- `reconcile_authoring()` blocks any nonempty catalog or pre-resolved semantic
  evidence with `semantic_catalog_activation_disabled`, before returning
  executable operations. The canonical executor rejects the resulting plan.
- Untrusted channel descriptions are not interpreted as rules or instructions.
- Explicit user scale settings are retained; no implicit CBL scale is added.

## Qualification evidence

Provider-free regressions cover exact CBL/VDL resolution and reconciliation,
explicit CBL scale, unknown vendor mnemonics, bare-GR ambiguity, explicit
physical selection, reviewed versus unreviewed rules, duplicate candidates,
incomplete inventory, addressability, physical identity shape, scope/identity/
digest/source drift, payload tampering, untrusted descriptions, and fail-closed
reconciliation/execution when catalog activation is disabled.

Validation reported for this candidate:

- Original focused cross-component command plus corrective regressions:
  `97 passed`, exit code `0`.
- Ruff lint, formatting, Python compilation, and single-engine attestation:
  `PASS`.
- Provider, model, endpoint, scientific-campaign, and C02 calls: 0.
- Numerical sample loading, YAML publication, and renderer execution: not
  performed by this slice.

## Activation boundary and remaining work

No production semantic mappings are approved or activated. The current
notebook/MCP reconciliation entry points use the empty default catalog. In
addition, direct `reconcile_authoring()` calls with nonempty catalogs or
pre-resolved semantic evidence now fail closed before generating operations.
The resolver can still be exercised in isolation for provider-free catalog
development, but its result cannot pass canonical reconciliation while
activation is disabled. The evidence verifier is not yet wired into the shared
pre-publication boundary; catalog-backed persistence remains unqualified and
activation must stay blocked until that later slice is independently accepted.

The initial family mappings, source provenance/rights review, exhaustive-scope
evidence, and catalog release governance remain domain-review decisions. The
large family reference JSON files are not authoritative. Exact model-token
accounting, production resource qualification, provider-backed qualification,
and full A10 cross-product qualification remain separate gates.

The prior A09 attempt-003 terminal remains `FAIL`; this candidate neither
rewrites it nor treats its partial deterministic-stage evidence as a passing
integrated qualification.

## Review and promotion

Independent review must inspect the exact corrective source/test diff, verify
the activation guard, immutable binding-scoped evidence, zero-rule runtime
default, and canonical ownership. Promotion into
`docs/agent-code-mode-current-baseline.md` requires independent acceptance and
a later Knowledge Delta update. No baseline promotion is included here.
