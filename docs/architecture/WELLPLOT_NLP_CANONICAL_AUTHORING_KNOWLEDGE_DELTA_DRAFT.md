# Knowledge Delta Draft: Canonical NLP Authoring

```yaml
status: STAGE 1 PROMOTED / STAGE 2 PENDING
depends_on: WELLPLOT-NLP-CANONICAL-AUTHORING-ARCH-001
architecture_status: ACCEPTED / NOT YET IMPLEMENTED
accepted_architecture_checkpoint: c6ec436619418b3831a1c9decd7d3c15efebb74c
baseline_updated: stage_1
implementation_authorized: true
```

Stage one has been incorporated into `docs/agent-code-mode-current-baseline.md`
after independent architecture acceptance and Human authorization. It records
the accepted architecture as not yet implemented. Stage two remains pending
independent implementation acceptance and will contain only verified
implementation evidence.

## Proposed Previous / New Knowledge

| Existing baseline authority | Stage 1: accepted architecture, not yet implemented | Stage 2: implementation evidence |
| --- | --- | --- |
| K-01: one canonical engine | Preserve; only the existing Code-Mode graph and authoring chain may be extended. Mark any accepted extension as not yet implemented. | Cite accepted implementation/test checkpoints and retain attestation evidence proving no alternate path. |
| K-02: model semantics / host identity and mechanics | Permit only the A00-accepted, request-local semantic operation proposal; host continues to own identity, source resolution, IDs, dependencies, mutation, persistence and rendering. | Verify schema, obligation binding and forbidden-field regressions at accepted implementation SHA. |
| K-03/K-04: schema validity is not semantics; safety does not repair meaning | Preserve exactly; invalid or unauthorized semantic patches remain rejected before lowering/publication. | Cite negative and no-publication regression evidence. |
| R-01/R-05: input sufficiency and inspection state | Accept only the architectural requirement for bounded host-owned context and distinct inspection states; do not claim snapshot/query implementation exists. | Cite source audit and tests for grounded facts, privacy/path limits, and inspection states. |
| R-02/R-03/R-04: schema parity, required discriminators, capability closure | Preserve; require parity and explicit discriminators for any accepted operation/patch schema. | Cite exact accepted schema hashes and parity/closure tests. |
| R-06: bounded correction and preservation | Preserve the accepted correction authority and require preservation; do not claim new patch preservation is implemented. | Cite correction/preservation tests and call-ceiling evidence. |
| R-07/R-08: causal outcomes and controlled changes | Preserve; keep D5 binding smoke 002 classified as contract evidence only. | Cite exact stage/owner regression evidence; live qualification remains separate. |
| K-05/K-06/K-07: immutable evidence, smoke gate, canonical runtime | Preserve unchanged. | Cite immutable evidence identities and independently accepted exact-head live gates where applicable. |

## Non-Goals

- No new semantic engine, graph, planner runtime, CRUD executor, or YAML writer.
- No transfer of canonical identifiers, filesystem paths, or mutation authority
  to a model.
- No silent operation coercion, host semantic completion, or extra correction
  loop.
- No change to frozen D5 populations, gold, or C02.

## Stage 1: Architecture Promotion

After independent review and Human architecture acceptance, update the active
baseline before A01 begins. The entry must state `ACCEPTED / NOT YET
IMPLEMENTED`, cite the accepted architecture commit, identify the precise
superseded planner restriction, retain all unchanged K/R invariants, and list
the implementation/regression obligations. This architecture-level promotion
does not claim runtime capability and does not authorize A01 by itself.

Stage one is promoted; no implementation capability is claimed.

## A03 Snapshot/Inspection Implementation Candidate

```yaml
status: IMPLEMENTATION CANDIDATE / NOT INDEPENDENTLY ACCEPTED
slice: A03
provider_model_endpoint_calls: 0
scientific_population_access: 0
```

The current provider-free A03 candidate extends the existing
`AuthoringInspectionFacade` and `SemanticEnricher`; it adds no query loop,
loader, graph, or execution path.

- A canonical document revision is SHA-256 over sorted-key canonical JSON of
  the immutable `AuthoringDocumentSpec` projection.
- Each selected source has a request-local `source-N` handle assigned from a
  deterministic candidate ordering. Existing sections receive `section-N`
  handles from canonical section order. Host contexts retain their private
  identity mapping; worker contracts receive only opaque handles.
- A shared `wellplot.document-inspection.v1` snapshot digest binds the
  document revision to the selected source handles, inspection states, and
  source revision tokens. Report and section worker contexts carry the same
  snapshot ID. The graph validates it before dispatch and before intent merge.
- Source revision tokens hash the canonical path plus filesystem device,
  inode, byte size, and nanosecond modification time. This is an optimistic
  metadata revision token, not a content hash; it avoids rereading potentially
  large LAS/DLIS assets. A later publication/commit boundary must perform the
  authoritative current-state check before writes.
- `not_inspected` channels are not represented as an authoritative empty
  inventory. Selected not-inspected sources pass through the existing loader;
  `unavailable` remains explicit and has no channel inventory; inspected-empty
  remains `inspected` with zero channels.
- Serialized enriched context is capped at 1,048,576 UTF-8 bytes and fails
  deterministically with `enrichment.inspection_context_limit`. The cap
  includes internal host-side context fields, making it conservative relative
  to the smaller model-facing worker contract.
- Absolute/canonical paths and channel descriptions remain excluded from the
  worker contract; a safe basename/approved label may identify a source.
  Injected descriptions are untrusted metadata and do not enter prompts.

This candidate does not implement optional worker queries, operation coverage,
or publication-time concurrency control. Those remain assigned to their
specified slices. The source revision token's metadata limitation is explicit
and must not be reported as byte-integrity verification.

## A04–A05 Host Operation Contract and Sparse Track Batch Candidate

```yaml
status: IMPLEMENTATION CANDIDATE / NOT INDEPENDENTLY ACCEPTED
slices: [A04, A05]
provider_model_endpoint_calls: 0
scientific_population_access: 0
```

- The canonical section work-contract builder now selects `add_tracks` for
  multiple track additions to an existing section. Track count no longer
  selects `reconstruct`; new-section construction continues to use the
  existing reconstruction action.
- `build_section_operation_contract()` compiles the planner inventory into
  `wellplot.section-operation-contract.v1`: bounded at 20 operations (the
  shared planner-wire/worker-schema maximum), with deterministic operation
  IDs, request hash, scope/snapshot binding, target-local handles, requirement
  IDs, ordering relations, and a schema digest. The
  count is a finite response-size guard, not a provider compatibility claim.
  Track facts must be covered once; planner-proposed explicit values must
  agree with compiled obligations. Existing `SectionWorkContract` remains the
  authority for semantic field values and preservation rules.
- Existing-section multi-add output is one `add_tracks` DTO containing one
  `operation_ref` and one sparse track patch per authorized `ADD_TRACK`. The
  canonical worker checks operation-set equality and operation-to-track
  ownership before grounding. The six-or-eight-existing-track reconstruction
  DTO is not accepted as an additive response.
- The existing `CanonicalSectionWorker`, graph dispatch, provider adapter, and
  `lower_section_action()` remain the only execution path. For shared legacy
  obligation validators only, the worker constructs a private, non-serialized
  section-shaped validation projection from the sparse patches. Lowering still
  receives `AddTracksAction` and independently invokes the existing single-
  track canonical lowerer for each patch, combining the resulting intent
  fragments; it does not compile or replace the existing section.
- Only `CREATE track` / `ADD_TRACK` is admitted by this contract slice; mixed
  fill, binding-update, move, remove, and section-field inventories fail closed
  before worker dispatch. The corresponding `add_tracks` DTO shares the
  planner's 20-operation schema bound.
- Planner-supplied operation conditions are currently rejected. The canonical
  request contract has no typed representation authorizing conditional
  omission, so valid source evidence alone cannot waive a mandatory request.
  Conditional omission remains unsupported until request-authored conditions
  can be compiled and bound independently of the planner proposal.
- Report-operation projection now requires exact request-obligation coverage
  and rejects fieldless `ENSURE` as an unverifiable no-op. Single-track
  operation-ref binding, report worker mapping, full canonical
  operation-to-intent coverage, transactional publication, and migration of
  remaining worker action families are not claimed complete here. They remain
  assigned to A06–A08 and require explicit regressions before acceptance.

Provider-free evidence currently covers operation ownership/value conflicts,
missing track coverage, rejection of planner-created conditions, exact
multi-add operation references, worker-level two-track validation and
lowering, preservation/reconciliation with pre-existing unrelated tracks,
schema strictness, and the existing planner/enrichment/work-contract suites.
This is not live provider compatibility or end-to-end persistence/render
qualification.

## A06 Report Operation Contract Candidate

```yaml
status: IMPLEMENTATION CANDIDATE / NOT INDEPENDENTLY ACCEPTED
provider_model_endpoint_calls: 0
scientific_population_access: 0
```

- The existing graph compiles a report operation contract from the one
  `ReportTask`, its request obligations, and the shared report snapshot.
  Request-local operation refs bind to an exact report-owned field and target
  slot; ambiguous metadata slots, unresolved values, unsupported object kinds,
  and out-of-scope ordering refs fail before report-worker dispatch.
- `CanonicalReportWorker` remains the only report worker. It receives the
  host-owned projection, preserves `ReportSemanticResponse`, applies the
  existing compiled report requirements and slot-group checks, validates
  obligations, then requires the exact set of response effect paths to equal
  the authorized contract paths before existing intent lowering. Unrequested
  title, page, depth, tail, slot, remark, and unit effects fail closed. No
  report-specific wire DTO, executor, or CRUD route was introduced.
- Explicit metadata slot resolution currently uses exact normalized equality
  against inspected slot keys/labels. It does not invent aliases. Service
  titles and remarks bind to request-local ordered slots. Existing typed
  report presentation order constraints are checked only when their targets
  resolve to ordered service-title/remark facts.
- The report DTO does not echo operation refs. The host retains the
  operation-to-target binding and verifies the resulting normalized field,
  target, and value; it does not claim model-output provenance per operation.
  The request-obligation compiler remains the authority for exact requested
  values, and unsupported report operation fields fail closed rather than
  being guessed.

Provider-free evidence covers exact metadata slot mapping, ambiguity refusal,
output value drift, ordering constraints, and integration with the existing
  planner, report worker, enrichment, workflow, and section-work-contract
  suites. This does not establish live provider compatibility or persistence,
rendering, or full mixed-request transaction behavior.

## Stage 2: Implementation Promotion

After independent implementation acceptance, update the baseline with only
verified implementation results. Require all of:

1. The authorized implementation is complete and independently reviewed.
2. Provider-free regressions identify the new invariant at the relevant
   planner, contract, worker, lowering, and persistence boundaries.
3. The Knowledge Delta cites exact accepted implementation and test commits.
4. Verified capability, exact regressions, and residual limitations are all
   explicit; unqualified behavior is not promoted.
5. Current baseline text is edited only to the minimum necessary clauses;
   historical evidence is left immutable.
