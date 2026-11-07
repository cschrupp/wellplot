# A09-CAT-01 Knowledge Delta Candidate

Status: `IMPLEMENTATION_CANDIDATE / INDEPENDENT_REVIEW_PENDING`

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
- Semantic results bind the selected physical identity to the catalog release,
  catalog digest, and source revision. The reconciliation plan preserves this
  evidence. A verification helper rejects catalog or source revision drift.
- Physical identity, renderer addressability, and numerical sample availability
  remain separate. `UNADDRESSABLE` and `UNKNOWN` candidates cannot be bound.
- Untrusted channel descriptions are not interpreted as rules or instructions.
- Explicit user scale settings are retained; no implicit CBL scale is added.

## Qualification evidence

Provider-free regressions cover exact CBL/VDL selection, explicit CBL scale,
unknown vendor mnemonics, bare-GR ambiguity, explicit physical selection,
reviewed versus unreviewed rules, duplicate candidates, incomplete inventory,
addressability, digest/source drift, payload tampering, untrusted descriptions,
and reconciliation rejection without executable operations.

Validation reported for this candidate:

- 91 focused and adjacent authoring tests passed.
- Ruff lint, formatting, and Python compilation are to be recorded after final
  candidate checks.
- Provider, model, endpoint, scientific-campaign, and C02 calls: 0.
- Numerical sample loading, YAML publication, and renderer execution: not
  performed by this slice.

## Activation boundary and remaining work

No production semantic mappings are approved or activated. The current
notebook/MCP reconciliation entry points continue to use the empty default
catalog. The semantic evidence and revalidation contract are exercised through
the existing resolver/reconciler APIs, but must be connected to the shared
pre-publication verification boundary before any nonempty production catalog
can be enabled. This is an explicit activation prerequisite, not a claim that
catalog-backed persistence has been qualified.

The initial family mappings, source provenance/rights review, exhaustive-scope
evidence, and catalog release governance remain domain-review decisions. The
large family reference JSON files are not authoritative. Exact model-token
accounting, production resource qualification, provider-backed qualification,
and full A10 cross-product qualification remain separate gates.

The prior A09 attempt-003 terminal remains `FAIL`; this candidate neither
rewrites it nor treats its partial deterministic-stage evidence as a passing
integrated qualification.

## Review and promotion

Independent review must inspect the exact source/test diff, verify the zero-rule
runtime default and canonical ownership, and assess the activation prerequisite
above. Promotion into `docs/agent-code-mode-current-baseline.md` requires
independent acceptance and a later Knowledge Delta update. No baseline
promotion is included here.
