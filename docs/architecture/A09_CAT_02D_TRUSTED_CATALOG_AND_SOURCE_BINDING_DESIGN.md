# A09-CAT-02D — Trusted Catalog and Source Binding Design

**Status:** `A09_CAT_02D_DESIGN_ACCEPTED` (R2; implementation remains gated)
**Parent baseline:** `44a6fea47fb2d3e5c9d296080c73070ba13ed645`
**Prerequisite:** A09-CAT-01 accepted; semantic catalog activation disabled
**Implementation:** Not authorized by this design slice
**Provider/model/endpoint, integration, scientific, and C02 activity:** None

## 1. Executive Decision

Independent design review accepted the R2 contract and closed F20-F23.
Acceptance is architecture-level only: CAT-02I may implement trust and shared
verification while keeping semantic activation disabled; positive
catalog-backed notebook/MCP transactions and any activation-guard removal
remain CAT-03 work. A09 integrated qualification remains open.

Select **Option A: a host-owned, immutable, request-scoped catalog release
context, selected before semantic resolution by extending the existing host
composition/transaction path**. Bind source identity with a request-scoped source handle
and revision, then bind the exact physical channel within that source and the
section/track/binding scope. The existing
`verify_document_postconditions()` remains the sole publication verifier.

Evidence class: `ADAPTED` for repository-reviewed release pinning and
request-scoped authority; `ESTABLISHED` for independently checking content
integrity and rejecting stale revisions; `NOVEL` for the exact source-handle
and semantic-binding transport proposed here. No nonempty catalog release is
selected or activated. The CAT-01 `semantic_catalog_activation_disabled`
guard remains mandatory until separately implemented, reviewed, and
authorized. Empty-catalog exact-channel behavior remains unchanged.

### Decision Record

- **Scope:** Bind semantic family requests to one trusted, inspected,
  renderer-addressable physical channel and persist only after shared
  pre-publication verification.
- **External evidence:** TUF separates trusted metadata from artifacts and
  uses signatures, hashes, versions, expiration, and rollback checks. It is an
  analogy, not a mandate to implement TUF or an online update service.
- **Comparable-system limit:** TUF addresses distributed update repositories
  and stronger adversarial distribution threats. WellPlot's initial catalog
  is an offline repository asset; the analogy stops at independent authority,
  integrity, version pinning, and revocation discipline.
- **Options:** A, host-owned pinned release context; B, catalog identity only
  in the reconciliation plan; C, fetch again at publication.
- **Selected:** A. B makes derived output self-authorizing. C introduces a
  second acquisition authority and may observe a different release.
- **Risks:** Repository governance is the trust root, not a defense against
  compromised repository permissions or host. Source handles are request-local.
  No production catalog release is approved.
- **Reversible:** Yes; keep the release selector empty and guard active.
- **Validation:** Provider-free contracts and notebook/MCP no-publication
  regressions plus independent review. Helper success is not activation.
- **Stop/revisit:** Stop if approval cannot be tied to a separately accepted
  repository change, section/source binding is not unique, or revisions cannot
  be revalidated before persistence.

## 2. Existing Ownership and Verified Gap

| Concern | Existing owner | Current contract and limitation |
| --- | --- | --- |
| Catalog schema, digest, evidence | `semantic_catalog.py` | Immutable catalog/evidence; helper verifies a supplied catalog, which must itself be trusted. |
| Source discovery and inspection | `SemanticEnricher` / `LogfileSourceLoader` | Request-scoped `EnrichedSemanticContext` carries revisions and physical identities; snapshot validation is reusable. |
| Composition and transaction setup | `create_canonical_compile_facade()` plus notebook `_load_document_context()` / MCP `_request_context()` | Compile root builds planner/workers; adapters construct persistence contexts separately. No shared transaction-context factory currently selects catalog authority. |
| Semantic resolution | `AuthoringContextResolver` | Creates deterministic evidence, but current evidence lacks source handle and inspection snapshot ID. |
| Operation planning | `reconcile_authoring()` | Carries evidence; CAT-01 rejects nonempty catalogs and pre-resolved evidence before executable operations. |
| Publication verification | `verify_document_postconditions()` | One shared notebook/MCP gate for obligations and preservation; semantic evidence is not yet checked. |
| Persistence | Existing notebook/MCP transaction paths and `AuthoringService` | Snapshot/dependency revisions are checked before canonical persistence. |

Notebook/MCP currently call `reconcile_authoring()` without a nonempty
approved catalog. `reconciliation_channels()` projects inspected channels
into section candidates but does not retain an explicit source handle/revision
on each selected candidate. A canonical binding names a mnemonic, not a
globally unique physical channel. This explains the CAT-02 preflight stop; it
does not permit inferring trust from evidence. Option A therefore extends the
existing host composition/transaction path to create one host-only authority
context used by both adapters; it does not claim that a shared transaction
factory exists today. A09-CAT-02I must decide the smallest way to avoid
duplicating release selection in the two adapters.

## 3. D-01 — Catalog Authority Contract

### 3.1 Trust anchor and release selection

Propose a **repository-reviewed release artifact and approval manifest,
selected by host code as an extension to the existing canonical composition
and transaction path, with a deployment-pinned digest as the runtime trust
anchor**:

1. A catalog artifact is immutable per release and carries its existing
   canonical `content_sha256`, `catalog_id`, `catalog_version`, and
   `release_ref`. The release separately identifies `catalog_artifact_sha256`,
   the SHA-256 of the exact packaged artifact bytes. These digests have
   different meanings and are not required to be equal.
2. An approval manifest records `catalog_artifact_sha256` and
   `content_sha256` as separate fields, plus catalog identity,
   approval-record reference, review scope, and `approved`/`revoked` status.
   The manifest is not self-authenticating: a status string or digest does not
   prove scientific approval.
3. An independently Human-accepted repository release record approves the
   exact `catalog_artifact_sha256`, canonical `content_sha256`, and
   `approval_manifest_sha256`, and identifies the accepted repository commit
   and review record. This record establishes **scientific approval** through
   project governance; the manifest cannot approve itself.
4. The trusted application deployment carries a pinned release descriptor
   whose integrity is covered by the existing application deployment/package
   trust boundary. The pin includes the exact release identity and digests
   from the accepted record. This is the runtime **deployment trust** anchor.
   CAT-02I may not substitute a mutable branch name, catalog-provided digest,
   environment override, or semantic evidence for this pin.
5. The canonical host selects only the deployed pin. Neither the model, the
   catalog artifact, nor reconciliation evidence can select or alter it.
   Unreviewed `examples/families/` content is never eligible.
6. Before resolution, validate in this exact order: (1) verify that the
   installed pin is available from the trusted application deployment;
   (2) verify raw approval-manifest bytes against
   `approval_manifest_sha256`; (3) strictly validate manifest schema and
   approval fields against the pin and accepted approval record, including
   status `approved`; (4) verify raw catalog artifact bytes against
   `catalog_artifact_sha256`; (5) parse and strictly validate the catalog;
   (6) recompute canonical semantic `content_sha256`; (7) verify that
   `content_sha256`, `catalog_id`, `catalog_version`, and `release_ref` match
   the trusted pin. Retain this immutable host-only descriptor for the
   request. The full catalog is not sent to the model.
7. Immediately before publication, repeat steps 1-7 against the same trusted
   deployment pin and the current manifest/catalog bytes. Reject missing,
   changed, malformed, revoked, or inconsistent content. Evidence is compared
   to the independently retained pin and never selects it.
8. `catalog_artifact_sha256` establishes exact packaged-byte integrity;
   canonical `content_sha256` establishes semantic-content identity. Neither
   digest establishes scientific approval or deployment trust. Scientific
   approval comes from the accepted review record; runtime authority comes
   from integrity of the deployed application carrying the pin. These are
   distinct claims.
9. Revocation or replacement requires a new independently accepted repository
   release and a new trusted application deployment with an updated pin.
   Existing processes/packages do not learn of remote changes immediately;
   revocation takes effect for a process after that deployment is installed or
   reloaded. A local artifact changed under an old pin fails digest validation
   immediately. No instantaneous remote-revocation guarantee is claimed.
10. Missing/invalid pin or approval disables semantic-family resolution and
    blocks publication. Explicit physical-channel requests remain available in
    empty-catalog mode.

This offline model assumes the existing trusted application deployment
process protects the installed pin. If that deployment-integrity assumption is
not accepted, stop and request a separate security decision; do not add
signatures, a key service, TUF, or another configuration root in CAT-02I.

### 3.2 Host-only release descriptor

```text
pin_schema_version
approved_release_id
catalog_id
catalog_version
release_ref
content_sha256
catalog_artifact_sha256
approval_manifest_sha256
approval_record_ref
approved_repository_commit
```

`catalog_artifact_sha256` is the SHA-256 of exact packaged catalog bytes;
`content_sha256` is the existing canonical semantic-content digest. They are
independent values and must not be compared for equality. Validation order is
deployment-pin trust, approval-manifest byte digest and strict schema/approval
fields, catalog artifact byte digest and strict catalog schema, recomputed
canonical content digest, then exact catalog metadata equality to the pin.
Repeat this complete sequence before publication. The host retains the parsed
`SemanticChannelCatalog` once per transaction. The descriptor is supplied
independently to reconciliation and shared publication verification; it must
not be copied from evidence or the plan and treated as trusted.

### 3.3 Failure states

| Condition | Required outcome |
| --- | --- |
| No release selected | Literal mode remains; semantic-family request is blocked/unresolved. |
| Manifest/artifact absent, invalid, or digest mismatch | `semantic_catalog_untrusted`; no publication. |
| Release unapproved or revoked | `semantic_catalog_unapproved`; no publication. |
| Release/content differs from transaction pin | `semantic_catalog_stale`; no publication. |
| Evidence names another release/version/digest | `semantic_evidence_mismatch`; no publication. |

These are proposed safe classifications on the existing
`DocumentPostconditionError`, not adapter-specific validators.

## 4. D-02 — Source-to-Binding Identity Contract

### 4.1 Source identity

Use the existing host-owned `SourceCandidate.candidate_id`,
`SourceContext.handle`, `SourceContext.revision_token`, and
`DocumentInspectionSnapshot.snapshot_id`. The authoritative private
transaction relation is:

```text
section_scope → section_source_candidate_id → candidate_id
              → source_handle → (snapshot_id, revision_token)
              → physical_identity_json → track_id/binding_id
```

The handle is unique only within one transaction snapshot, not a durable
global source ID. A path may remain in private host state for file access and
existing revision checks, but it is not semantic evidence or model context.
Physical identity alone is not a source identifier: two files may contain
identical DLIS identities or LAS ordinals.

### Required joins and cardinalities

1. In the private transaction source map, every inspected
   `SourceContext.handle` resolves to exactly one permitted
   `SourceCandidate.candidate_id`, and that candidate resolves to exactly one
   canonical path/format and captured revision. Handles are unique within the
   snapshot. Missing, duplicate, or contradictory associations fail closed.
2. For each existing section, the host resolves canonical `data_source` to
   exactly one candidate through the already-resolved source inventory. The
   private relation is checked against inspected `SourceContext` and
   `SnapshotSource`; it is never reconstructed from semantic evidence.
3. For each new section, before its resulting document object exists, the
   authorized request/source slot or canonical new-section operation resolves
   to exactly one candidate. The host records
   `new_section_scope_key → candidate_id`. When reconciliation assigns the
   section ID, the plan carries a one-to-one scope-key-to-section-ID mapping.
   The verifier checks this relation and the final section `data_source`
   against that candidate. Missing or multiple source assignments block.
4. Each catalog-backed binding maps to exactly one selected section source.
   Physical identity is matched only within that source's complete inspected
   inventory. Snapshot, handle, revision, and physical identity distinguish
   identical channels in different files.
5. At publication, the verifier checks binding section/track/binding IDs
   against the final document and host-owned scope map, and confirms that the
   same source remains selected for that section.
6. Any missing, duplicate, ambiguous, cross-section, cross-source, or
   contradictory relation blocks publication. No filename, mnemonic, or
   candidate ordering fallback is allowed.

Reuse the existing request-scoped `EnrichedSemanticContext` and inspection
result; do not parse a source again solely for publication. Preserve F17 lazy
inspection: structural-only requests do not inspect unrelated sources.
Incomplete inventory, unknown addressability, and revision mismatch block.

`file_revision_token()` hashes resolved path plus filesystem device, inode,
size, and modification time. It is an optimistic identity/change-detection
token, **not a cryptographic guarantee over file contents**. Do not claim full
content authentication from it.

### 4.2 Evidence and final-document verification

Extend immutable `SemanticResolutionEvidence` with:

- `inspection_snapshot_id`;
- `source_candidate_id` and `source_handle`, joined by the private transaction
  map;
- existing source revision and canonical physical identity.

Retain section/track/binding and catalog fields. Evidence remains derived,
never authoritative. The verifier establishes from host-supplied
`EnrichedSemanticContext` that:

1. Snapshot is valid for the document and sources.
2. The host relation yields exactly one section → candidate → source-handle
   chain within the named snapshot.
3. That source is inspected, inventory-complete, and has the recorded current
   revision.
4. Exactly one channel within that source has the exact physical identity and
   requested mnemonic.
5. Addressability is explicitly `ADDRESSABLE`; missing, defaulted,
   `UNKNOWN`, or `UNADDRESSABLE` blocks semantic binding.
6. Resulting canonical document has exactly one matching section/track/binding
   and its channel agrees with the selected inspected channel.
7. Evidence and bindings are one-to-one: no missing, extra, duplicate, or
   contradictory semantic claims.

Reuse `validate_enriched_snapshot()` for document/source revision checks. The
shared verifier validates evidence against this same request-scoped context;
the adapter's existing final snapshot validation remains immediately before
persistence to close the stale-state window.

### 4.3 Minimum proposed extensions

| Existing contract | Proposed minimum extension | Classification |
| --- | --- | --- |
| Host composition/request context | Select and hold one deployment-pinned approved release; absent pin disables semantic mode. | Necessary for trusted authority |
| Host transaction source map | Bind section scope and existing `data_source`, or new-section source slot, to candidate ID → source handle → snapshot/revision; keep paths private. | Necessary for source identity |
| `DocumentInspectionSnapshot` / `ResolvedSectionContext` | Preserve and validate source handles/revisions and section-source association; reuse the same inspection result. | Necessary for source identity |
| Candidate/per-source inventory | Preserve candidate ID, source handle, revision, and physical identity through `reconciliation_channels()` without flattening ownership. | Necessary for source identity |
| `SemanticResolutionEvidence` | Add snapshot ID, candidate ID, and source handle; retain scope, catalog, revision, and physical identity. | Necessary for source identity/publication |
| Host-compiled semantic expectation | Carry the expected semantic-binding set compiled from request obligations/authorized semantic operations, independently of resolver evidence. | Necessary for evidence completeness |
| `AuthoringReconciliationPlan` | Carry observed resolver evidence plus host binding assignments used to join expected slots to final binding IDs. Never derive expectations or authority from observed evidence. | Necessary for verification join |
| `verify_document_postconditions()` | Accept host-supplied trusted release and source context; invoke existing semantic helper; add `semantic` error category. | Necessary for publication |
| Notebook/MCP transaction contexts | Supply the same trusted context to the shared verifier; no adapter-level duplicated checks. | Necessary for publication |
| Full catalog in worker input | None; retain host-side and expose only bounded relevant facts. | Optional/deferred |
| Signatures/TUF client | None initially; separate security decision if threat model demands it. | Optional/deferred |

### 4.4 Mandatory expected semantic-binding set (F22)

Observed `SemanticResolutionEvidence` cannot establish its own completeness.
The host must retain an independent expected set compiled alongside the
authoritative request obligations and authorized semantic operations, before
resolver evidence is produced. The minimum record is an immutable
`ExpectedSemanticBinding` entry with:

```text
request_sha256
requirement_id
scope_key                 # request-bound existing/new section scope
track_scope_key
binding_slot_key          # host-owned slot, before final binding ID exists
channel_request_kind      # SEMANTIC_FAMILY | EXPLICIT_PHYSICAL | UNRESOLVED
requested_term
authorized_source_scope   # optional request constraint, not selected source
```

The request/obligation compiler must classify every channel request as
`SEMANTIC_FAMILY`, `EXPLICIT_PHYSICAL`, or `UNRESOLVED` using the accepted
request interpretation contract. `UNRESOLVED` blocks; it is never converted
to literal mode because evidence is absent. The expected semantic set is the
entries marked `SEMANTIC_FAMILY`, keyed by host requirement/scope/track/binding
slot. Reconciliation supplies a separate host-created mapping from each
expected slot to exactly one final section ID, track ID, and binding ID.

Minimal transport: add `expected_semantic_bindings` to the host-owned session
or transaction result alongside existing `RequestObligation`s, and preserve
the slot-to-final-binding assignment in the reconciliation plan. The shared
verifier receives the expected set directly from the host request result, the
assignment map from reconciliation, and observed evidence from the plan. It
must not rebuild the expected set from the plan's evidence. When there are no
expected semantic bindings, any observed semantic evidence is unexpected and
fails; when there are expected bindings, exactly one evidence record and one
final binding must match each expected entry, with no extras or duplicates.

This makes literal-vs-semantic interpretation explicit: a semantic request
cannot silently become a literal-channel request, and a missing evidence record
is detectable even if the resolver omitted it entirely.

## 5. Canonical Data Flow

```text
existing host composition
  ├─ select approved release pin (or empty/literal-only mode)
  ├─ load and verify artifact + approval manifest
  └─ create host-only transaction context
       ├─ existing inspection snapshot
       ├─ section → source-handle binding
       ├─ source revisions and physical inventory
       └─ pinned catalog descriptor
             ↓
existing planner/workers (no authority)
             ↓
existing SemanticEnricher / AuthoringContextResolver
  select source, reviewed rule, and exact physical channel; emit evidence
             ↓
existing reconciler and AuthoringReconciliationPlan
             ↓
existing executor/service private candidate and validation
             ↓
existing verify_document_postconditions()
  obligations → preservation → semantic evidence vs. independent inputs
             ↓
existing snapshot revalidation → canonical persistence/reload
```

The model cannot select catalog, source handles, physical identity, revision,
or approval facts. No side resolver, executor, or persistence route is added.

## 6. Publication and Failure Semantics

Retain obligation and preservation checks. Compare the independently
host-compiled expected semantic-binding set against observed resolver evidence
and host binding assignments. For every expected entry require exactly one
evidence record and one final canonical binding. Reject missing, unexpected,
duplicate, substituted, scope-changed, or contradictory evidence. Evidence
without trusted catalog/source context fails. Empty expected set plus empty
evidence remains a no-op for verified explicit-physical requests; unresolved
request interpretation blocks earlier and cannot be reclassified as literal.

Proposed sequence:

1. Canonical private execution and document validation.
2. Request-obligation verification.
3. Document-preservation verification.
4. Semantic evidence against approved release, source snapshot, selected
   identity, addressability, resulting binding, and exact expected-set
   completeness.
5. Existing snapshot/revision revalidation immediately before publication.
6. Existing canonical persistence and reload.

Reject with `DocumentPostconditionError.check == "semantic"` and a safe stable
code. No retry, partial mutation, persistence, or rendering. Discard the
private candidate. Executor tests on arbitrary preconstructed plans do not
prove publication safety; qualification must show notebook and MCP each reach
the single shared verifier before their existing persistence method.

## 7. Required State Walkthroughs

| Case | Expected boundary/result |
| --- | --- |
| Exact CBL/VDL, empty catalog | Existing literal resolution; no semantic evidence; unchanged. |
| Explicit CBL scale | Existing obligation/preservation checks; catalog irrelevant. |
| One source, reviewed semantic match | A synthetic isolated-verifier fixture may pass against the deployment-pin contract. CAT-02I does not publish a catalog-backed transaction while the guard is active; production mapping is not approved. |
| Two sections, different sources | Each section's source handle/revision verified independently. |
| New section with source slot | Before a document section exists, host binds the authorized source slot to one candidate under a new-section scope key; reconciliation maps it to one final section ID and verifier checks that exact mapping. |
| Two sources with identical physical IDs | Snapshot + source handle + revision distinguish; wrong/missing handle fails. |
| Unapproved release | `semantic_catalog_unapproved`; no publication. |
| Digest mismatch | `semantic_catalog_untrusted`; no publication. |
| Release replaced mid-transaction | Pin revalidation gives `semantic_catalog_stale`; no publication. |
| Stale source revision | Snapshot/semantic check fails; no publication. |
| Source substitution | Section/source handle or revision mismatch; no publication. |
| New section has no unique source slot/candidate | Reconciliation or verification rejects missing/non-unique `new_section_scope_key` mapping. |
| Channel belongs to another section | Section-source binding check fails. |
| Unsupported renderer identity | Missing/unknown/unaddressable fails. |
| Same mnemonic ambiguous within source | Resolver reports ambiguity; no evidence/publication. |
| Evidence references nonexistent binding | Result-document scope check fails. |
| Binding ID/physical identity tampered | Exact comparison fails. |
| Expected semantic evidence omitted | Host-compiled expected set has no one-to-one observed evidence match; no publication. |
| Unexpected or duplicate semantic evidence | Observed set is not exactly equal to expected set; no publication. |
| Semantic request treated as explicit literal | Host request classification/requirement mismatch blocks before reconciliation/publication. |
| Missing trusted catalog | Semantic claim fails closed; literal path remains. |
| Missing/incomplete inspection | No semantic publication. |
| Direct evidence without authority | CAT-01 guard rejects; any later injection fails shared verifier. |

## 8. Alternatives and Tradeoffs

### Catalog authority

| Option | Assessment |
| --- | --- |
| **A — Host-owned release context through canonical composition** | **Selected.** One independent request pin shared by both adapters and revalidated before publication. |
| **B — Identity only in reconciliation plan** | Rejected: derived plan cannot independently prove its own release was approved. |
| **C — Fetch again at publication** | Rejected: no authority service exists; a second fetch adds availability/freshness behavior and may select a different release. Re-read of the same pinned local artifact is part of A. |

TUF is relevant for separation of trust metadata/artifacts and its hash,
version, expiry, and rollback controls. A digest alone lacks approval and
freshness semantics. The initial repository model is weaker against repository
or host compromise. Sigstore illustrates a stronger signature/identity option
but requires a separate identity and verification policy.

### Source identity

| Approach | Assessment |
| --- | --- |
| Transaction-scoped handle + revision + physical identity | **Selected:** reuses request handles/revisions and distinguishes identical channel identities across files without exposing paths. |
| Raw path | Rejected as semantic identity: mutable and environment-specific; private file access/revision checks only. |
| Physical identity without source binding | Rejected: channel identities are source-local and may repeat in another file. |

## 9. CAT-02I / CAT-03 Qualification Boundary

The CAT-01 `semantic_catalog_activation_disabled` guard remains mandatory.
CAT-02I is **trust and verifier integration only**:

1. Implement the deployment-pinned trusted release contract, host source map,
   independently compiled expected semantic-binding set, and shared verifier.
2. Keep production semantic activation disabled for the entire CAT-02I slice.
3. Add negative notebook/MCP no-publication tests, empty-catalog compatibility
   regressions, and isolated synthetic shared-verifier positives. A synthetic
   verifier positive is contract evidence only; it must not bypass the
   reconciler guard or be presented as a catalog-backed transaction.
4. Independently review CAT-02I implementation before any activation work.

CAT-03 is a distinct later qualification. It may prepare a narrowly reviewed
catalog release and positive end-to-end notebook/MCP transactions only under
separate Human authorization and accepted authority. Removing
`semantic_catalog_activation_disabled` requires explicit CAT-03 acceptance
and activation authorization, plus:

1. A small scientifically reviewed, provenance-cleared artifact and approval
   manifest with exact digests and an approved deployment pin.
2. Negative no-publication regressions for authority, source, identity,
   ambiguity, and evidence omission.
3. Positive provider-free end-to-end transactions with approved mappings and
   source/binding identity preserved.
4. Independent implementation acceptance and explicit decision to remove the
   activation guard.

Isolated verifier success, private reconciliation success, and digest match do
not satisfy activation.

## 10. Provider-Free Qualification Matrix

| Group | Required evidence | Preserve |
| --- | --- | --- |
| Compatibility | Empty-catalog CBL/VDL and explicit scale pass. | Literal behavior unchanged. |
| Authority positive | Synthetic approved release passes the shared verifier in isolation. | No production-path bypass; not activation evidence. |
| Catalog negative | Unapproved/revoked, bad digest, replaced release/manifest, missing pin. | Reject before persistence. |
| Source negative | Stale revision, missing/incomplete inspection, substitution, wrong section. | Never trust evidence's source claim alone. |
| Identity negative | Wrong ID, duplicate mnemonic, missing/unknown/unaddressable channel. | Identity/addressability remain separate. |
| Document negative | Missing/extra/duplicate evidence, absent binding, altered scope/channel. | One-to-one evidence/document binding. |
| Adapter safety | Notebook and MCP reject semantic claims before persistence and preserve YAML bytes while activation remains disabled. | No duplicate checks, test-only bypass, or alternate path. |
| Architecture | Manifest/reachability attestation. | No new resolver, graph, executor, loader, renderer, or persistence path. |

Report helper tests separately from actual transaction-flow tests.

## 11. Open Decisions and Risks

F20-F22 are resolved at design-contract level by the deployment pin, explicit
source join/cardinality rules, and independent expected-evidence set. They
still require implementation and independent review. Residual risks and
implementation qualifications are:

1. **Deployment integrity assumption:** The host trusts the installed
   application deployment carrying the release pin. If current deployment
   controls do not establish this, pause before CAT-02I for a separate security
   decision; do not silently add cryptographic infrastructure.
2. **Offline revocation:** A newly accepted revocation takes effect when the
   updated trusted deployment is installed/reloaded. Existing processes do not
   observe a remote repository change immediately.
3. **Artifact packaging:** CAT-02I must select an existing package-data
   convention and verify that the pinned catalog and manifest ship in the
   trusted deployment. `examples/families/` remains excluded.
4. **Optimistic source revision:** The current token detects common identity
   and change drift from filesystem metadata; it is not a cryptographic content
   hash. A content-authentication requirement needs a separate decision.
5. **Mechanical coverage:** CAT-02I must test source-handle uniqueness,
   existing/new-section joins, and exact expected/observed evidence equality
   through the shared verifier and both publication adapters.

No production implementation, mapping activation, baseline promotion,
integration rerun, or provider/scientific execution is authorized.

## 12. Primary External References

- TUF specification, trusted metadata, hashes, versions, expiry and rollback:
  <https://theupdateframework.github.io/specification/latest/>
- TUF metadata roles and snapshot/timestamp purposes:
  <https://theupdateframework.io/docs/metadata/>
- Sigstore verification overview, artifact signatures, identity, trust root,
  and transparency proof: <https://docs.sigstore.dev/about/overview/>

These primary references support the trust-model comparison only; no runtime
framework or dependency is selected.
