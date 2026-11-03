# A09 Metadata-First Inspection and Context-Budget Design

**Status:** DESIGN CANDIDATE — F13/F14 corrective for independent review
**Scope:** A09 source inspection, channel resolution, and model-context/resource
budgets only
**Implementation:** Not authorized by this design document
**Provider/model/live/scientific execution:** None authorized

## Decision Summary

Design the existing canonical source-inspection path to obtain LAS/DLIS
metadata without materializing numerical samples, resolve requested channels
deterministically into `UNIQUE`, `AMBIGUOUS`, `ABSENT`, or `UNKNOWN`, and
admit a complete provider request only when it fits both a trustworthy
model-specific token budget and the existing serialized-byte safety cap.

Do not reject a source solely because its total file size is large. Replace
that proposed guard with bounded inspection work and an explicit distinction
between complete inventory and incomplete inspection. A budget or parser
failure must yield `UNKNOWN` (and a bounded inspection failure), never
`ABSENT`.

This design extends the existing `LogfileSourceLoader`,
`SemanticEnricher`, `AuthoringInspectionFacade`, source-resolution contracts,
snapshot validation, and canonical planner/worker path. It does not add a
second ingestion engine, autonomous inspection agent, provider path, semantic
engine, CRUD route, or persistence route. Existing full-data LAS/DLIS loaders
remain available to scientific rendering and other existing consumers.

## Scope and Current State

The current enrichment/source-loader path reaches `load_dataset_from_source`
and the full LAS/DLIS loaders. Those loaders are appropriate for numerical
rendering, but are not the metadata inspection boundary needed to ground
semantic authoring. In particular, the current LAS loader accesses curve
arrays, while the DLIS loader obtains frame curves. The A09 metadata path must
not do either.

The existing authoring architecture already owns the necessary integration
points: source candidates and revisions, bounded inspection context,
`SemanticEnricher`, `AuthoringInspectionFacade`, deterministic source
resolution, and snapshot revalidation. The design is to specialize inspection
within those existing boundaries, not create a parallel source service.

The current serialized-inspection context cap remains a secondary safety
control. It is not a model token budget and must not be represented as one.
The existing planner-facing projection intentionally excludes free-form
channel descriptions; preserve that prompt-injection defense unless a separate
review proves a specific sanitized field is necessary.

## Decision Record

**DECISION:** Use bounded metadata-first inspection and host-owned four-state
channel resolution; budget the complete provider request using the exact
runtime/model tokenizer where available, with the existing byte cap as a
separate backstop.

**PROJECT SCOPE:** Ground semantic authoring in trusted source metadata while
keeping numerical samples out of model context and preserving the single
canonical authoring engine.

**EXTERNAL EVIDENCE:** LAS places curve metadata before sample data; LASIO
documents `ignore_data=True` for header-only reading. DLISIO exposes logical
files, frames, and channel metadata separately from sample retrieval, but its
loader scans/indexes the file. llama.cpp documents tokenizer-aware input
counting extensions; these are version/build-specific and not assumed to be
available on the deployed endpoint.

**ESTABLISHED PRACTICE:** Separate metadata from bulk measurements, use
stable compound identities when names are not unique, count tokens with the
target model's tokenizer, and fail explicitly when complete input cannot fit
the context budget.

**WELLPLOT DIFFERENCE:** LAS/DLIS sources can be multi-gigabyte and DLIS
metadata discovery may require scanning/indexing the physical file. A total
file-size admission rule is therefore both semantically unrelated to prompt
size and liable to reject valid inputs. The metadata path must instead bound
its own work and report uncertainty honestly.

**OPTIONS CONSIDERED:** (A) full sample-loading then projection; (B) metadata-
only parser APIs within the canonical loader; (C) a new parser/inspection
service. Select B. A wastes memory and may expose samples; C duplicates
ownership and lifecycle. For hard DLIS resource containment, choose no
mechanism yet: compare in-process limits with supervised process isolation as
an open implementation decision.

**SELECTED APPROACH:** Existing canonical source-loader and inspection
contracts gain metadata-only extraction, completeness/resource outcomes,
four-state channel resolution, and full-request budget admission. Preserve
the existing full loaders for consumers that need numerical data.

**EVIDENCE CLASS:** `ADAPTED` for reuse of the existing host-mediated
inspection/snapshot architecture; `ESTABLISHED` for metadata/sample
separation and model-token counting; `NOVEL` for WellPlot's unified resolution
result and its exact snapshot binding.

**RISKS:** Parser APIs may scan the whole file; DLIS index/cache memory may
scale with metadata or file structure; tokenizer behavior may differ from the
server's actual chat template; metadata strings can contain prompt injection;
incomplete inventory can be mistaken for absence; filesystem revision checks
may not detect every concurrent writer.

**REVERSIBLE:** Yes. Implement behind the existing inspection boundary and
retain the full loaders unchanged. Do not alter scientific rendering.

**VALIDATION:** Provider-free parser tests, deterministic resolution matrix,
resource-limit fault injection, complete-request token-count tests, snapshot
staleness tests, prompt-injection tests, and single-engine reachability tests.

**STOP / REVISIT:** Revisit if the locked parser versions cannot provide
metadata without numerical arrays, if their resource behavior cannot be
bounded safely in the supported runtime, if exact request token counts cannot
be obtained, or if the metadata path changes existing scientific loader
behavior.

## Proposed Inspection Contract

### Metadata-only extraction

1. **LAS:** Add a metadata-only path inside the existing source-loader
   boundary using LASIO's header-only option (`ignore_data=True`) where
   supported by the installed version. Extract only required well/header and
   curve metadata. Do not access `las.index`, curve values, numpy arrays, or
   any API that materializes samples. Preserve existing full `load_las()` for
   rendering. The locked LASIO version is newer than the cited v0.31 docs;
   its exact API and whether it stops reading at the data section must be
   confirmed from installed source and tests before implementation.
2. **DLIS:** Use the existing DLISIO load/index path and traverse logical-file,
   frame, and channel metadata only. Do not call `Frame.curves()` or
   `Channel.curves()` in enrichment/inspection. Do not retain sample arrays.
   Record that the parser may scan/index the full file and that memory/time
   cost is not independent of total source size. Keep existing full-data
   loaders untouched for rendering.
3. Produce a bounded, immutable metadata projection. Free-form descriptions
   remain untrusted and are excluded from planner input by default. If a
   future contract requires them, they require separate sanitization,
   provenance, and injection review.
4. Report separately: `inventory_complete`, `inspection_status`,
   `declared_channel_metadata`, `binding_addressability`, and
   `sample_availability`. Metadata inspection establishes declaration, not
   numerical sample existence, readability, quality, or usable sample count.
   Unless verified through an explicitly authorized non-model mechanism,
   sample availability is `NOT_CHECKED`.

5. **Binding addressability is a separate gate.** A metadata result of
   `UNIQUE` identifies exactly one declared metadata object; it does not prove
   that the existing scientific loader and mnemonic-keyed dataset/binding
   schema can address that exact object. Before automatic binding, the host
   must prove the selected metadata identity maps one-to-one to the exact
   channel the existing loader will expose to rendering. Model this separately
   as `ADDRESSABLE`, `UNADDRESSABLE`, or `UNKNOWN`, without changing the
   existing authoring binding schema or numerical loader in A09. Permit
   automatic binding only for metadata `UNIQUE` plus addressability
   `ADDRESSABLE`. `UNADDRESSABLE` includes a channel in an unconsumed logical
   file, a same-mnemonic collision the loader resolves to a different object,
   or any compound identity the current binding API cannot select. Unknown
   mapping is `UNKNOWN`, never an implicit best-effort match. Return a typed
   unsupported/unresolved outcome and require clarification or a later
   separately reviewed architecture change; do not silently substitute.
   Numerical sample availability remains independent and may still be
   `NOT_CHECKED`.

   The current implementation audit makes this distinction material:
   `load_dlis()` selects the first logical file, materializes frame curves,
   and resolves same-name channels into a dataset dictionary keyed by
   mnemonic. The metadata inspector may discover objects outside that
   addressable subset or distinguish objects that the renderer collapses.
   This design records those as unaddressable; it does not change those
   loader semantics.

### Channel resolution states

Resolution is a deterministic host result, not a model-selected index:

| State | Required evidence | Meaning |
| --- | --- | --- |
| `UNIQUE` | Inspection complete for the selected source/scope; exactly one candidate satisfies the request and trusted constraints | Exactly one metadata candidate is identified; binding still requires the separate addressability gate. |
| `AMBIGUOUS` | Inspection complete; at least two plausible candidates remain | No candidate is selected by ordering or vendor convention; request clarification or return a typed ambiguity. |
| `ABSENT` | Inspection complete, relevant source/frame inventory fully enumerated, supported format, no resource limit or parse uncertainty, and zero matching candidates | The requested channel is not declared in that completed scope. |
| `UNKNOWN` | Any incomplete scan, unsupported/uncertain format, parser error, budget exhaustion, stale snapshot, unresolved source/frame scope, or untrusted/inconsistent identity | The system cannot establish presence or absence. Do not treat as absent. |

Candidate matching follows this ordered, host-owned policy:

1. **Explicit physical channel identity:** If the request carries a
   source/frame-qualified identity or explicitly names a canonical mnemonic
   as a physical channel, exact normalized identity is evaluated first. It
   must resolve to exactly one metadata candidate. A collision is
   `AMBIGUOUS`; alias matching must not override or break the tie.
2. **Trusted semantic role/alias:** Otherwise, resolve the requested role
   only through an authoritative, versioned alias catalog. The catalog entry
   must record its stable ID/version (or content digest), canonical role,
   accepted request terms, and explicitly reviewed physical mnemonics, with
   provenance for the mapping. Aliases are equality-based after the catalog's
   defined normalization; no substring, edit-distance, vendor-convention, or
   naming-similarity expansion is allowed. If exactly one candidate matches
   the trusted role and request constraints, continue to addressability
   checking. If multiple candidates match, return `AMBIGUOUS`; do not rank or
   select one by order.
3. **No trusted mapping:** A source-qualified/explicit physical identity is
   treated literally: if complete scoped inventory contains no exact match,
   it is `ABSENT`. A natural-language role/alias that is not recognized by
   the pinned catalog cannot be declared absent from the source; its
   resolution is `UNKNOWN` and the user must clarify or select a catalogued
   role. For a recognized role, zero candidates among that version's
   explicitly listed mnemonics is `ABSENT` only after complete inventory. A
   missing or inconclusive metadata field never creates a positive alias
   match or proves absence.

For example, a request for `GR` first matches a physical `GR` channel if one
is uniquely present. If no exact `GR` candidate exists, the pinned catalog
determines whether `GR` is a recognized semantic-role term and which physical
mnemonics that role authorizes. If reviewed evidence in that entry makes both
`GR_STGC` and `GR_CORR` plausible, the result is `AMBIGUOUS` and the scientist
must choose. The names alone do not establish equivalence. If the pinned
entry does not list those mnemonics, do not infer that either is GR; a
recognized role with no listed candidate can be `ABSENT` only after complete
inventory. If `GR` is not recognized by the catalog and is not present as an
exact mnemonic, return `UNKNOWN` for clarification rather than guessing.

Candidate matching also honors explicit source, frame, unit, dimensionality,
and channel constraints. If two candidates share a mnemonic, retain distinct
source/frame identity. For DLIS, preserve the library's compound channel
identity (object type, name, origin, copy number) and frame/logical-file
identity. For LAS, retain source identity and curve ordinal as well as
mnemonic, because duplicate mnemonics may occur. A unique metadata identity
must still pass the separate renderer-addressability gate above.

The resolution record should bind the selected source candidate and revision,
inspection/parser identity, relevant inventory projection, pinned alias
catalog identity/version, request interpretation, constraints, candidate
identities, metadata resolution state, separate binding-addressability state,
and completeness evidence into the existing snapshot/provenance mechanism. A
stale revision invalidates the resolution and yields `UNKNOWN` until
reinspected. `sample_availability` is recorded independently and is not
implied by either metadata uniqueness or renderer addressability.

## Resource-Safety Policy

There is no total source-file byte ceiling. Resource limits apply to inspection
work and produced metadata, not to the source's `stat()` size. Limits must be
finite and independently observable:

- wall-clock and CPU time for inspection;
- peak resident memory, including native parser/index allocations;
- maximum enumerated logical files, frames, channels, and metadata records;
- maximum projected metadata bytes and candidate count;
- maximum deterministic read/query operations per authoring task;
- maximum complete provider-request token count and serialized bytes.

No numeric limits are selected in this design. Derive them from supported
runtime capacity and representative small, large, malformed, and adversarial
fixtures; publish the chosen values and failure semantics for review before
implementation. Exceeding a limit returns a bounded `INSPECTION_BUDGET_EXCEEDED`
or equivalent and resolution `UNKNOWN`; it must not return a partial inventory
as complete and must not dispatch a worker on truncated mandatory evidence.

**Important DLIS boundary:** `dlisio.dlis.load()` may scan/index the full
source synchronously. A Python-level timeout around a synchronous/native call
does not guarantee interruption, and `tracemalloc` does not account for all
native allocations. The implementation design must decide whether the
supported deployment can rely on process/container quotas or needs a
supervised parser process with OS-enforced memory and wall-time limits. This
is not authorization to add a service or alternate ingestion engine; any
process boundary must remain a deterministic implementation detail of the
canonical inspection facade. If hard containment is unavailable, that
residual limitation must be explicitly accepted before A09 can be called
complete.

LAS permits unwrapped records whose line length is not fixed by the format.
Therefore, a line-length guard must not silently redefine valid LAS as
malformed. Any parser/input budget must return an explicit incomplete/unknown
result. Verify the locked LASIO behavior for early termination at the sample
section and for adversarially large headers before choosing a parser-level
limit.

## Complete Provider-Request Budget

The current serialized-byte cap remains an independent last-resort guard. Add
a model-aware budget over the **complete request as actually sent**, including
system/developer/user messages, conversation history, structured-output
schema, tool declarations where applicable, chat-template framing, and
special tokens. Reserve the configured completion allowance and required
runtime margin; do not budget only the visible metadata text.

The counter must correspond to the configured model/runtime tokenizer. Do not
use `tiktoken` as a generic Qwen tokenizer or a character/word heuristic as a
silent substitute. Preferred order:

1. Reuse a trustworthy token-count capability in the existing provider adapter
   or the exact local model tokenizer/template.
2. Consider llama.cpp's input-token-count endpoint only after confirming that
   the deployed build supports it, that it counts the same request/template
   path, and that the readiness/security contract permits its use. The
   upstream extension is not assumed to be portable or available.
3. If no exact or accepted conservative counter exists, fail closed before
   generation with a typed `TOKEN_BUDGET_UNAVAILABLE` outcome. Do not silently
   truncate required instructions or source facts.

Deterministic pruning may remove only irrelevant candidates/metadata under
the host's declared relevance rules, with an auditable projection. It may not
drop a mandatory request obligation, change source ownership, or choose among
ambiguous candidates. The admitted request's token count, tokenizer/runtime
identity, byte count, and projection digest should be available to existing
bounded custody, without storing raw source bodies.

## Alternatives Rejected

- **Reject all files over a fixed number of bytes:** rejected; unrelated to
  semantic input and excludes valid multi-gigabyte sources.
- **Load all samples and then project headers:** rejected; wastes memory and
  risks accidental sample exposure.
- **Call curves and discard arrays immediately:** rejected; still incurs
  numerical materialization and peak memory.
- **Select the first matching mnemonic:** rejected; converts ambiguity into
  silent semantic choice.
- **Treat parser timeout/error as `ABSENT`:** rejected; absence requires a
  complete inventory.
- **Use generic token estimates or truncate to fit:** rejected; request
  framing/tokenization varies by model and required semantics must be
  preserved.
- **Add an autonomous inspection agent or second parser service:** rejected;
  the canonical host facade owns deterministic read-only inspection.

## Open Decisions Before Implementation

1. What finite time, CPU, RSS, inventory-count, metadata-byte, and query
   budgets are supported by the canonical deployment, and what evidence sets
   them?
2. Can the canonical runtime impose hard limits on synchronous DLISIO native
   scanning, or is a supervised process boundary necessary? What OS/runtime
   is in scope?
3. Does locked LASIO v0.32's `ignore_data=True` avoid reading/materializing
   LAS samples in all supported LAS versions, and how are large/unwrapped
   headers bounded without violating format behavior?
4. What exact token-count mechanism matches the configured Qwen model and
   llama.cpp chat template? Is the runtime extension available and acceptable,
   or must the existing adapter own a local tokenizer capability?
5. Which source/frame constraints are explicit user-authorized filters, and
   which require clarification rather than narrowing candidates?
6. What governed source/version and review process will maintain the trusted
   semantic alias catalog, including role mappings such as Gamma Ray? Until a
   mapping is approved, mnemonic resemblance does not establish equivalence.
7. Which metadata fields may be exposed to planner/worker context? Default:
   stable technical metadata only; free-form descriptions remain excluded.
8. What bounded outcome/custody fields represent budget exhaustion, unknown
   inventory, and unavailable token counting without misclassifying them as
   provider or semantic failures?

These decisions must be closed before production implementation. Do not
introduce chosen numeric defaults during implementation by convenience.

## Migration and Review Plan

1. Independently review this design against the current source-loader,
   inspection facade, enrichment snapshots, provider adapter, baseline K-01
   through K-07, and A09 scope.
2. Close the open decisions above using installed dependency source and bounded
   provider-free benchmarks/fixtures; do not make endpoint or model calls.
3. Implement metadata-only extraction behind the existing canonical source
   loader and preserve full-data loaders for existing consumers.
4. Add typed resolution/completeness and snapshot binding without changing
   planner ownership or semantic execution.
5. Add full-request token admission in the existing provider path; retain the
   byte cap as a distinct backstop.
6. Run provider-free test matrix and single-engine attestation; independent
   implementation review precedes any A10 qualification.

### Invariant-preservation matrix

| Invariant | Design preservation | Required regression |
| --- | --- | --- |
| K-01 one canonical engine | Inspection enriches existing host context; no second agent/parser service | Reachability/attestation finds one planner-worker-execution path |
| K-02 host owns source identity and availability | Metadata resolution, alias policy, and renderer addressability are host-owned | Model cannot choose by order, alias inference, or introduce a handle |
| K-03 valid structure is not semantic correctness | Resolution status is distinct from worker/schema validity | Valid but ambiguous request fails/clarifies before generation |
| K-04 safety does not repair semantics | No guessed candidate or silent truncation | Ambiguous/unknown inputs fail closed; requirements remain outstanding |
| Snapshot integrity | Inspection result binds to source revision and identity | Change/reorder source metadata; stale resolution is rejected |
| Metadata/render identity | Metadata `UNIQUE` is insufficient without exact addressability through the existing renderer path | First-logical-file limitation and same-mnemonic collision return typed unaddressable/unknown; no substitution |
| Trusted semantic matching | Versioned alias entry is the only role-equivalence authority | `GR` exact, trusted `GR_STGC`/`GR_CORR` ambiguous, missing alias not guessed |
| No sample exposure | Metadata route never calls curve sample APIs | Monkeypatch sample APIs to fail; metadata inspection still succeeds |
| No false absence | `ABSENT` requires complete relevant inventory | Inject timeout/parse/count limit; result is `UNKNOWN`, not `ABSENT` |
| Complete-request budget | Token counter sees schema/template/messages and reserved output | Exact request boundary cases; missing counter fails before provider call |
| Resource safety | Finite inspection budgets with explicit owner/outcome | Memory/time/metadata/query limit tests and no partial dispatch |

## Acceptance Criteria for This Design

- Independent review accepts the canonical integration boundary and states.
- No fixed total source-file byte ceiling is introduced.
- Metadata inspection is explicitly distinguished from numerical availability.
- Four states have non-overlapping, testable predicates; incomplete means
  `UNKNOWN`.
- Duplicate channel identities preserve frame/source/ordinal identity.
- Metadata uniqueness and renderer addressability are separate; automatic
  binding requires both a unique metadata match and proven exact
  addressability through the current scientific loader/binding schema.
- Alias/role matches use an authoritative versioned catalog with explicit
  provenance; exact mnemonic, trusted alias, absent alias, and ambiguous role
  behavior are tested separately. Mnemonic resemblance alone never implies
  scientific equivalence.
- No-match is `ABSENT` only after complete scoped inspection.
- Context limits include the complete provider request and a model-specific
  token count plus serialized-byte cap.
- No silent truncation of mandatory instructions or guessed channel choice.
- DLIS hard-resource enforcement and all numeric budgets are decided before
  implementation, not invented in code.
- Full-data loaders and scientific rendering behavior remain unchanged.
- A09 remains open until replacement parser safeguards and token-budget
  behavior are implemented and accepted, or the residual limitations are
  explicitly accepted.

## External References

Sources below support design constraints, not claims that WellPlot's locked
versions already satisfy every behavior. Verify exact installed versions
before implementation.

1. USGS, [LAS format overview](https://www.usgs.gov/programs/national-geological-and-geophysical-data-preservation-program/las-format): LAS section/header organization.
2. Canadian Well Logging Society, [LAS 2.0 specification (Jan. 2014)](https://www.cwls.org/wp-content/uploads/2014/09/LAS_20_Update_Jan2014.pdf): header/data organization and unwrapped-record behavior.
3. LASIO, [v0.31 API documentation](https://lasio.readthedocs.io/en/v0.31/lasio.html): documents `ignore_data=True`; WellPlot's lock is newer, so verify v0.32 source/API.
4. DLISIO, [DLIS API](https://dlisio.readthedocs.io/en/stable/dlis/api.html) and [curve/sample access](https://dlisio.readthedocs.io/en/stable/dlis/curves.html): distinguishes metadata objects from curve sample retrieval and documents compound channel identity. The loader's full-file scan/index implications must be treated separately from sample materialization.
5. llama.cpp, [server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md): upstream tokenizer/input-token-count facilities are build-specific extensions; verify deployed compatibility before relying on them.
6. OpenAI, [token counting guide](https://developers.openai.com/api/docs/guides/token-counting): general evidence that complete request framing matters; it is not a tokenizer specification for Qwen/llama.cpp.
7. OpenAI tiktoken, [README](https://github.com/openai/tiktoken/blob/main/README.md): model-to-tokenizer mapping is provider/model-specific; do not treat it as a generic tokenizer for the configured local Qwen model.
