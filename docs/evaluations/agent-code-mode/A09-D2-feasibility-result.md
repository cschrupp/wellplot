# A09 D2 Feasibility Result

**Date:** 2026-11-03; DLIS follow-up 2026-11-04
**Accepted design:** D1 integrated catalog/source design at
`da23cd69792b4c75ed1da30bc0de35ca69ddcb38`
**Disposition:** Feasibility evidence sufficient for bounded implementation
planning; finite provisional safety controls and implementation authorization
remain open
**Scope:** Provider-free, synthetic-only, documentation/evidence work

## Executive result

D2 established a feasible bounded-prefix path for tested synthetic LAS
1.2/2.0 headers and a synthetic RP66-style DLIS corpus exercising multiple
logical files, frames, and repeated channel mnemonics. It confirmed that the
canonical `dlisio` reader indexes the entire physical file, and that a
supervised child can be exercised with address-space/CPU limits plus a parent
timeout. This is mechanism evidence only; no production thresholds are
justified.

Exact Qwen/llama.cpp request-token admission could not be established without
the deployed tokenizer, model/template and server implementation. Catalog
governance can be specified, but the available family files do not establish
licensed, domain-reviewed semantic mappings. Accordingly, no mappings are
approved and no numeric parser budgets are selected. **This D2 result is not
implementation authorization.** The current implementation gate split is
recorded in section 6 below.

## 1. LAS metadata-only feasibility

### Established behavior

The locked project environment has LASIO `0.32`. Installed-source inspection
confirms that `lasio.read(..., ignore_data=True)` skips parsing numeric samples
but still calls `find_sections_in_file()`, which reads lines until EOF to find
section markers. `readline()` also has no application-provided per-line bound.
The earlier synthetic 1/8/32 MiB tail measurements show the cost: about
0.72/5.71/23.99 seconds while peak RSS remained near the interpreter import
baseline. `ignore_data=True` alone is not bounded metadata inspection.

### Synthetic marker probe

A temporary chunked scanner prototype, not committed as production code, was
tested against generated inputs. It stopped at the data-section header and
passed only that prefix to LASIO with `ignore_data=True`:

| Input | Result |
| --- | --- |
| LAS 1.2, CRLF, `~A` | Two expected curve headers; data shape `(0, 2)` |
| LAS 2.0, LF, `~ASCII` | Two expected curve headers; data shape `(0, 2)` |
| LAS 2.0, CRLF, `~A (ASCII log data)` | Two expected curve headers; data shape `(0, 2)` |
| Comment/text mention of `~A`, `~V`, or LAS 3 `~Log_Data` | No supported data marker; `UNKNOWN` |
| Synthetic header record over test line bound | `UNKNOWN_LINE_LIMIT` |
| Prefix over test cumulative bound | `UNKNOWN_TOTAL_LIMIT` |

The marker rule was corrected against the [CWLS LAS 2.0 specification](https://www.cwls.org/wp-content/uploads/2014/09/LAS_20_Update_Jan2014.pdf): a section starts when `~` is the first non-space character; the first reserved character after it identifies the section and the rest of the marker line is comment text. Thus a descriptive suffix after `~A` is valid. LAS 3 `~Log_Data` is not admitted to the LASIO 0.32 candidate without separate qualification.

The scanner used finite test-only chunk, line and total-prefix values. Those
are not proposed runtime limits. The probe did not cover the full valid
encoding/line-ending/header-order space, adversarial inputs, wrap modes,
representative geology distributions, or production cold-I/O behavior. No
total source-file size cutoff is recommended or authorized.

**Classification:** LASIO EOF scan is `ESTABLISHED` by installed source;
bounded-prefix parsing is `EMPIRICALLY_SUPPORTED` for the listed synthetic
cases; a production adapter is an `ADAPTED` design candidate pending complete
matrix and budget review.

## 2. DLIS fixture and containment feasibility

`dlisio.dlis.load()` documentation states that it scans the complete physical
file to build an index because DLIS does not provide random access. Metadata
caching trades CPU for memory; it does not avoid the index scan. Sample-array
accessors such as `Frame.curves()` were not called during the D2 metadata
probe. See the [dlisio 1.0.4 API](https://dlisio.readthedocs.io/en/stable/dlis/api.html).

The separate [`well-id/dliswriter`](https://github.com/well-id/dliswriter)
project documents an MIT-licensed writer based on RP66 v1, but describes
itself as beta and is not a normative conformance validator. Its
[PyPI 1.2.0 wheel](https://pypi.org/project/dliswriter/1.2.0/) was downloaded
to `/tmp`; SHA-256 `0f86a7b37a6e01eacc81f62a86e67b870f1439fb359510b9b7e8255f3c4f0cc2`
matched the published wheel digest. It was not installed into the project
environment or dependency set.

The writer defaults `output_chunk_size` to `2**32` and preallocates a bytearray
of that size. The initial fixture attempt exposed this 4 GiB default and was
terminated before producing a fixture. An explicit 65,536-byte writer buffer
produced a 1,020-byte synthetic physical DLIS with one logical file, one
frame, and `DEPTH`/`GR` channels. `dlisio` 1.0.4 loaded it and returned the
expected source identities and frame-channel membership. No sample curve API
was invoked. The temporary fixture was deleted after the probe.

The same fixture was parsed in a child process with test-only `RLIMIT_AS` of
1 GiB, `RLIMIT_CPU` of 10 seconds, and a parent timeout of 15 seconds. It
exited successfully and emitted only a bounded metadata projection. Separately
recorded OS probes showed that address-space/CPU limits and parent process-group
termination are available. The WSL2 cgroup v2 mount is read-only and exposes
no writable per-job `memory.max`; `RLIMIT_AS` constrains virtual address space,
not measured RSS.

This proves only that a tiny generated file can be parsed in a supervised
process under test values. It does not establish RP66 conformance breadth,
large or malformed-file safety, multi-logical-file identity, scaling, peak
RSS, cache strategy, or suitable production limits. The writer's 4 GiB default
is a concrete warning that fixture-generation tools also need explicit
resource parameters.

**Classification:** full-file indexing and cache trade-off are `ESTABLISHED`
by dlisio documentation/source; the tiny generated fixture and child run are
`EMPIRICALLY_SUPPORTED`; supervised metadata parsing is an `ADAPTED` design
candidate. Production memory containment remains an open decision between an
accepted `RLIMIT_AS` contract and providing a writable delegated cgroup or
equivalent OS job limit.

### Expanded repeatable fixture/corruption probe (2026-11-04)

A larger synthetic fixture is preserved at
`tests/fixtures/a09_d2_metadata/multifile_repeated_mnemonics.dlis`:

```text
bytes: 2364
SHA-256: b98beba2bc6fedb70794da63d68dd09ac94abe02191fbfb53e6acd2eb85c08b9
generator: dliswriter 1.2.0, output_chunk_size=65536
reader: locked dlisio 1.0.4
```

It has two logical files. The first has two frames and repeats `DEPTH` and
`GR` with distinct channel copy numbers (`0` and `1`); the second repeats the
same mnemonics in a separate logical-file context. A metadata-only projection
returned two logical files, channel counts `[4, 2]`, frame counts `[2, 1]`,
and the expected channel membership/copy numbers. No numerical curve API was
called. The fixture was parsed in a child process with test-only
`RLIMIT_AS=1 GiB`, `RLIMIT_CPU=10 s`, and an 8-second parent timeout. It
completed successfully. These are test limits, not production budgets.

The same child harness used `dlisio.common.ErrorHandler` with `info`, `minor`,
`major`, and `critical` all set to `Actions.RAISE`:

| Synthetic input | Strict parser result | Required host interpretation |
| --- | --- | --- |
| Preserved valid fixture | 2 logical files; 4/2 channels; 2/1 frames | Complete only after validating the projection and terminal inventory marker |
| Empty bytes | `EOFError` | `UNKNOWN` / inspection failure |
| 39-byte partial storage-unit label | `RuntimeError` | `UNKNOWN` / inspection failure |
| 80-byte storage-unit label only | Successful parse with 0 logical files | `UNKNOWN` / incomplete; never `ABSENT` |
| Valid fixture truncated by one final byte | `RuntimeError` | `UNKNOWN` / inspection failure |

This falsifies the weaker rule “clean child exit means complete inventory”:
the SUL-only input exits successfully but contains no logical files. The
supervisor must require at least one logical file and a complete, valid bounded
projection before marking inventory complete; otherwise channel resolution is
`UNKNOWN`. Non-info parser violations should fail closed. This still does not
prove that every semantically incorrect but syntactically parseable mutation
will be detected, nor does it establish coverage of all RP66-v1 structures.

The file is synthetic test data only, not a production asset or conformance
corpus. Its external generator remains outside project dependencies; the
fixture itself can be read with the locked project `dlisio` installation.

## 3. Resource budgets

No finite production thresholds are selected. The existing LAS measurements
and synthetic DLIS fixtures are not representative distributions. The
following owner-proposed objectives now bound the next qualification work;
they are provisional targets, not measured capabilities, production SLOs,
timeouts, resource limits, or source-size admission ceilings:

| Operation and qualification tier | Provisional end-to-end p95 target |
| --- | ---: |
| LAS 1.2/2.0 bounded metadata inspection, up to 1,000 channels | 2 seconds |
| DLIS RP66 v1 cold inspection, files up to 250 MiB | 30 seconds |
| DLIS RP66 v1 cold inspection, larger tier above 250 MiB and up to 1 GiB | 90 seconds |
| Valid cached metadata inspection for an unchanged source | 1 second |

The DLIS tiers define benchmark strata only. A source larger than 1 GiB must
not be rejected solely for its total size. A latency-target miss is a
performance failure; reaching a separately approved safety/resource limit
must yield an incomplete result and `UNKNOWN`, blocking publication. Do not
turn a target into an enforced deadline without separate evidence and review.

Qualification must run on the supported canonical WSL2/local-storage
environment, bind exact Python/parser/runtime identities, and report cold and
warm behavior. Include subprocess startup in end-to-end latency and separately
report startup and parser time. The finite matrix must measure separately:

- bounded LAS header bytes, records, line sizes, curve counts, encodings,
  marker variants, and sample-tail independence;
- DLIS physical bytes, visible/logical records, logical files, frames,
  channels, free-form metadata, cache mode, and malformed/corrupt cases;
- child startup separately from parser CPU and wall time, peak RSS and VSZ,
  limit-trigger behavior, parent cancellation, result bytes, and query count;
- repeated cold/warm runs, with exact tool/library/runtime identities.
- end-to-end p50/p95/p99 and individual outliers against each provisional
  target; do not aggregate different source tiers or cache states.

Choose distinct finite limits for header bytes/records, metadata objects,
projected output bytes, query count, parser CPU, wall time, and process memory
from the measured supported envelope plus a reviewed margin. Any limit breach
must produce an incomplete result and channel-resolution `UNKNOWN`, never
`ABSENT`. Total LAS/DLIS source bytes are not themselves an admission ceiling.

**Disposition:** `RESOURCE_BUDGETS_OPEN`; no numbers are inferred from these
probes. The provisional latency objectives are `UNVERIFIED`; no operational
limit or file-size ceiling is selected.

## 4. Exact Qwen/llama.cpp request-token accounting

Static inspection of `src/wellplot/agent/providers/openai_compat_v2.py` shows
that WellPlot sends the configured model, system/user messages, configured
request options, optional output-token bound, and a Pydantic-generated strict
`response_format: json_schema`. The deployed llama.cpp server build and exact
Qwen tokenizer/GGUF/template are not locally available. The project environment
also lacks the model-specific tokenizer tooling. Therefore exact token count,
context-window fit, and the server's JSON-schema-to-prompt/grammar conversion
are unestablished.

The [llama.cpp server API](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
documents `/apply-template` and `/tokenize` as non-inference operations, but
they are POST calls and were not invoked. Current D2 did not use the endpoint.
An offline acceptance must bind the same GGUF tokenizer, chat template,
server build, frozen thinking-off options, rendered-message framing, response
schema conversion, output reservation, context capacity, and request
projection. If schema is compiled to a grammar rather than inserted into the
prompt, its cost needs a separate grammar/schema resource bound, not a
character-to-token estimate. The serialized request also needs an independent
byte ceiling.

**Disposition:** `TOKEN_BUDGET_UNAVAILABLE`; do not substitute generic
tokenizers, character ratios, previous response usage, or silent truncation.
This gate requires exact local artifacts/source or a separately authorized
non-generative server capability check.

## 5. Catalog governance

The four supplied `examples/families/*.json` files remain untrusted
reference/collision data. Their presence and prior collision audit establish
neither provenance, license, nor correctness. The existing channel aliases
are not versioned with per-rule evidence, and source-candidate aliases must
not bypass the accepted governed resolver.

Governance recommendation for an initial release: **zero active semantic
family-to-physical-channel mappings** until each rule is documented and
reviewed. Exact physical selectors explicitly supplied by the scientist
remain available. For every proposed mapping, require source URL/revision and
exact evidence location, license/redistribution status, request-term versus
physical-channel rule type, exact identities, units/source/frame scope,
exhaustiveness claim, collision analysis, named domain reviewer, software
schema reviewer, immutable release version, canonical digest, and regression
evidence. Activation creates a new content-addressed catalog release; it never
rewrites past resolution evidence. Missing/untrusted/stale data yields
`UNKNOWN` or clarification, not guessed equivalence or family-level
`ABSENT`.

No initial mapping is approved by this feasibility result. The zero-active-rule
recommendation requires independent/domain acceptance; it is not silently
promoted to the active baseline.

## Decision table

### Candidate supported-input envelope (proposal; not approved)

- **Runtime:** current canonical WSL2/Python 3.12 environment with locked
  LASIO 0.32 and DLISIO 1.0.4. This does not claim portability to other
  OS/runtime combinations.
- **LAS:** versions 1.2 and 2.0, standard ASCII header syntax through a
  terminal A/data-section marker, supporting tested LF/CRLF and descriptive
  marker comments. LAS 3 `~Log_Data`, undocumented encodings, and malformed or
  incomplete inventories remain unsupported until separately qualified.
- **DLIS:** RP66-v1 physical files accepted as a single physical source by
  DLISIO 1.0.4, including multiple logical files, frames, and compound channel
  identity. The preserved synthetic fixture demonstrates only the listed
  subset; it is not an acceptance envelope for all RP66 object types or
  vendor extensions.
- **Inspection output:** technical metadata only; no curve sample arrays or
  free-form descriptions in model context. Metadata identity, renderer
  addressability, and sample availability remain independent facts.
- **Failure:** parser error, budget exhaustion, empty/partial inventory,
  unrecognized required identity, or incomplete projection returns `UNKNOWN`
  and blocks binding/publication. It never implies `ABSENT`.

This envelope is a candidate for owner review. It does not set maximum source
bytes, header/record counts, metadata objects, projected bytes, CPU, RSS/VSZ,
wall time, or concurrency. The provisional latency objectives above bound
measurement but are not yet an accepted production SLO; the provider's
900-second timeout is not an inspection SLO.

| Item | Evidence status | Result | Remaining gate |
| --- | --- | --- | --- |
| LAS bounded-prefix feasibility | Synthetic LAS 1.2/2.0 cases; installed LASIO source; CWLS marker rule | Candidate supported; not production-qualified | Complete format/adversarial matrix and budgets |
| DLIS fixture and child containment | 2,364-byte generated multi-logical/multi-frame fixture; strict-error corruption matrix under test-only child limits | Feasible for provider-free tests; empty inventory must fail closed | Scaling matrix and accepted memory contract |
| Numeric parser/resource limits | Provisional p95 targets proposed; representative distributions and resource measurements absent | Open; no production constants selected | Functional implementation needs reviewed provisional safety limits only; production readiness needs measured matrix and approved operational limits |
| Exact Qwen token accounting | Provider request source inspected; model/tokenizer/build absent | Blocked; exact count unavailable | Provision pinned local assets/source or authorize endpoint capability calls |
| Catalog governance | D1 invariants plus untrusted local catalogs; project owner nominated as initial domain reviewer, acceptance pending | Governance process proposed; no mappings approved | Accept reviewer role; prepare evidence-backed initial batch and obtain domain/license plus independent schema review |

## Bounded D2 qualification matrix and remaining decisions

The following is the remaining provider-free qualification scope. It is
finite by strata and failure classes; it does not authorize production code or
choose resource constants.

| Gate | Bounded inputs / measurements | Required disposition |
| --- | --- | --- |
| LAS correctness | LAS 1.2/2.0; LF/CRLF; standard marker/comment variants; reordered and long records; malformed/missing markers; hostile descriptions; up to 1,000-channel target stratum; sample tails varied independently | Exact inventory and no sample arrays; incomplete/limit/corrupt cases are `UNKNOWN`; report p95 against 2-second target |
| DLIS identity/completeness | Preserved multi-LF/multi-frame/repeated-mnemonic fixture; copy-number and LF/frame identity; SUL-only, empty, partial-SUL, truncated, malformed, and incomplete-enumeration cases | Require positive completeness evidence; empty/incomplete inventory is `UNKNOWN`, never `ABSENT`; no numerical curve APIs |
| DLIS scaling/containment | Synthetic RP66-v1 tiers through 250 MiB and 1 GiB, cold subprocess and cache states, controlled LF/frame/channel/record counts, sparse/large sample regions | Report startup/parser/end-to-end latency, p50/p95/p99, RSS/VSZ, CPU, wall, scanned bytes, output bytes and limit behavior against 30/90-second targets; characterize larger files without size-based rejection |
| Cache | Same source identity and unchanged revision; valid hit, stale identity, corrupt cache | Valid hit target p95 <=1 second; stale/corrupt cache is not trusted and falls back to bounded inspection or `UNKNOWN` |
| Token admission | Exact deployed Qwen tokenizer/GGUF, llama.cpp build, template, thinking-off options, request framing, JSON-schema conversion, output reservation and context limit | Exact request admission or bounded blocker; no generic tokenizer or character-ratio substitution; no endpoint call absent separate authorization |
| Catalog release | Candidate rules for GR, SP, depth, basic resistivities, neutron porosity, bulk density, sonic and caliper; exact source/revision/evidence/license/collision records | No rule active by inclusion alone; project-owner domain review requires explicit acceptance, plus independent software/schema review; wildcard rules remain suggestions |

For latency qualification, record the measurement method and sample count
before each run; include subprocess startup in end-to-end values and keep
cold/warm and size tiers separate. A failed target is reported as
`TARGET_NOT_MET`, not converted into a parser admission limit. Production
resource budgets remain a later decision based on the measured distributions,
supported input envelope, enforceable OS controls, and explicit safety margin.

The nominated initial catalog domain reviewer has not yet accepted the role.
Codex may assemble candidate mappings and evidence but must not approve its
own scientific assertions. The initial batch is a review scope, not a set of
approved mappings. Vendor technical documentation can support exact mnemonic
meaning; CWLS/RP66 format specifications establish representation/identity,
not scientific equivalence. Broad patterns such as `GR*` and `DT*` remain
suggestions pending separate qualification. Presentation defaults require
their own review and must not be inferred from semantic classification.

The bounded LAS adapter, supervised DLIS parser, and semantic catalog remain
internal capabilities of the existing source-inspection and host-resolution
path. The DLIS child returns metadata evidence only; it does not interpret
scientist intent or construct/persist a WellPlot document. Eventual
implementation acceptance must include a source-reachability/ownership audit
and negative tests proving that successful publication still goes only
through the canonical `AuthoringService` path. Existing scientific loaders
and renderer semantics remain unchanged.

## Implementation and production-readiness gates (2026-11-04)

This gate split supersedes any wording elsewhere in the D2 records that could
make performance qualification a prerequisite for initial functional
implementation. It does not authorize implementation; it defines the bounded
plan to submit for independent review and later Human authorization.

| Requirement | Before bounded functional implementation | Before provider-backed/production readiness |
| --- | --- | --- |
| Accepted canonical architecture | Required: D1 remains controlling | Required |
| LAS/DLIS feasibility | Existing synthetic evidence is sufficient to begin bounded development | Expanded correctness, scaling, containment and supported-envelope qualification |
| Parser isolation and resource safety | Required: isolate DLIS parsing and set finite provisional safety limits; breaches return incomplete/`UNKNOWN` | Harden and measure enforceability, memory behavior, and operational resource budgets |
| Source identity and deterministic channel resolution | Required: define exact source/channel identity, four outcomes, ambiguity and fail-closed semantics | Fully validate against supported LAS/DLIS inventory variations, duplicates, frames, and renderer addressability |
| Production latency SLO and p95 benchmarks | Not required | Required; current targets remain provisional until measured and accepted |
| Representative large-file scaling | Not required | Required; qualification tiers are not size admission ceilings |
| Exact Qwen/llama.cpp token accounting | Not required for provider-free implementation | Required before the affected provider-backed qualification; no generic estimate substitutes |
| Scientific semantic mappings | Synthetic mappings may be used only in isolated deterministic tests | Each active production mapping requires domain evidence/review, provenance/license disposition, and independent schema/software review |
| Canonical publication ownership | Required: existing reconciliation/CRUD/YAML route and source-level ownership tests | Required, including integration qualification |

Finite provisional parser-safety limits are distinct from performance
objectives. Their concrete values and enforceable mechanism must be proposed
and reviewed before implementation starts; this record does not invent them.
The implementation may not convert latency targets, DLIS benchmark tiers, or
source byte counts into rejection thresholds. A safety-limit breach must
produce incomplete evidence and `UNKNOWN`, never `ABSENT` or successful
publication.

### Provisional parser-safety profile for review (not authorized)

To make the implementation boundary reviewable, the following finite initial
development profile is proposed. These values bound parser work and emitted
metadata; they are not claims of broad format support, performance, or
production memory guarantees. They require independent review and explicit
Human implementation authorization before code is written.

| Control | Proposed initial value | Enforcement and rationale |
| --- | ---: | --- |
| LAS maximum line | 2 MiB | Chunked scanner refuses an over-limit line and returns incomplete/`UNKNOWN`; aligns with the largest synthetic single header record exercised, but the scanner limit itself still needs regression coverage. |
| LAS cumulative header prefix | 16 MiB | Scanner stops before reading beyond the bounded prefix; over-limit/missing marker is incomplete/`UNKNOWN`. Provisional safety cap only, not a total-file limit. |
| LAS channel records | 5,001 | Stop inventory construction and return incomplete/`UNKNOWN` above cap; the largest synthetic channel inventory exercised was 5,001. |
| LAS parser address space / CPU / wall | 1 GiB / 10 seconds / 15 seconds | Run LASIO prefix parsing in the supervised parser child; set limits before parsing and terminate/reap its process group on wall expiry. All breaches return incomplete/`UNKNOWN`; this path is not yet implemented. |
| DLIS child address space | 1 GiB per child | Set `RLIMIT_AS` before importing/using DLISIO. This bounds virtual address space, not RSS; unsupported or unavailable enforcement fails closed. |
| DLIS child CPU time | 90 seconds | Set `RLIMIT_CPU`; signal/exit caused by the limit is incomplete/`UNKNOWN`. Mechanism exists, but this proposed value has not been tested on scaled inputs. |
| DLIS wall time | 120 seconds | Parent monotonic deadline; start a killable process group and terminate/reap the entire group on expiry. Timeout is incomplete/`UNKNOWN`. |
| DLIS projected metadata objects | 5,001 channel entries | Child counts projected channel entries and stops before emitting excess; output never certifies inventory completeness after truncation. |
| Child metadata output and serialized inspection context | 1 MiB each | Parent enforces a 1 MiB aggregate stdout/stderr cap incrementally while reading, requesting at most remaining-cap-plus-one bytes before terminating/rejecting excess; existing `MAX_SERIALIZED_INSPECTION_CONTEXT_BYTES` is 1 MiB. Never accumulate an unbounded pipe result. |
| Host-wide parser concurrency | 1 active child across WellPlot processes on this host | Acquire one nonblocking process-shared OS lock before launch, held through child termination/reap; fail closed as incomplete/`UNKNOWN` if busy. Every inspection entry point must use the same gate. |

No total source-file-byte ceiling is proposed. The proposed 120-second wall
guard is greater than the 90-second provisional p95 objective, so missing a
latency target remains observable as a performance result before the
independent safety deadline. These caps may cause a valid but unusually large
metadata inventory to resolve `UNKNOWN`; do not claim `ABSENT`. `RLIMIT_AS`
does not provide a direct RSS guarantee. Production readiness still requires
measured scaling, memory characterization and review of whether a writable
cgroup/job limit is required. A rejected proposed value must be replaced by
another finite, enforceable, fail-closed value before implementation
authorization.

The containment mechanisms follow the platform semantics documented by
[Python 3.12 `resource`](https://docs.python.org/3.12/library/resource.html),
[Python 3.12 `subprocess`](https://docs.python.org/3.12/library/subprocess.html),
and the Linux [`getrlimit(2)`](https://man7.org/linux/man-pages/man2/getrlimit.2.html)
and [`flock(2)`](https://man7.org/linux/man-pages/man2/flock.2.html) manuals.
The proposed host-wide gate is a nonblocking exclusive advisory lock on a
canonical host-local runtime-state file shared by every WellPlot process. Hold
it until the child is terminated and reaped; do not unlink the lock file while
in use. The lock descriptor must remain held if the supervisor exits before
the child, so pass it to the direct child or prove equivalent lifetime
ownership. All loaders must honor the same gate because `flock` is advisory.
Cross-process lock/lifetime behavior still requires provider-free regression
tests. If the shared local lock path or semantics cannot be verified, do not
launch a parser child. `RLIMIT_AS`
constrains virtual address space, `RLIMIT_CPU` constrains CPU seconds, and
process-group termination is needed to contain descendants; none is
equivalent to a measured RSS cgroup limit.

### Bounded provider-free functional implementation candidate

Subject to separate implementation authorization, the candidate is limited to
metadata extraction, deterministic semantic resolution, and proving
integration with the existing authoring path. Exact existing entry points to
extend or preserve are:

| Existing component / entry point | Bounded change boundary |
| --- | --- |
| `src/wellplot/agent/composition.py::create_canonical_dependencies` | Keep the single composition root and inject the existing `LogfileSourceLoader`/`SemanticEnricher`; no new graph, planner, or worker. |
| `src/wellplot/agent/code_mode/source_loader.py::LogfileSourceLoader.load` and `SourceLoaderProtocol` | Add metadata-only LAS/DLIS extraction behind the existing loader contract. A supervised DLIS child is only a parser/metadata mechanism and returns bounded evidence; it cannot resolve intent or create/persist documents. |
| `src/wellplot/agent/code_mode/enrichment.py::SemanticEnricher.enrich`, `._select_sources`, and `._load_source` | Inspect only sources required by source-dependent obligations; preserve allowed-root checks, source revision tokens, cache/snapshot validation, bounded projections, and incomplete/unknown outcomes. Structural-only work must not open unrelated DLIS files. |
| `src/wellplot/agent/inspection.py::AuthoringInspectionFacade` | Extend fixed read-only projections only for required, sanitized metadata evidence; do not expose raw source paths, samples, or free-form untrusted descriptions to the model. |
| `src/wellplot/authoring_context.py::AuthoringContextResolver.resolve` and existing channel-resolution helpers | Add deterministic catalog-backed request-term interpretation and physical-channel resolution to the existing resolver. Preserve exact physical selectors, four-state resolution, ambiguity, provenance/version checks, and fail-closed behavior. |
| `src/wellplot/model/intent.py::AuthoringDocumentIntent` | Preserve as the provider-neutral desired-state boundary. Do not create a second canonical intent or persist parser/catalog-specific identities as model authority. |
| `src/wellplot/authoring_reconciler.py::reconcile_authoring`, `src/wellplot/authoring_executor.py::AuthoringExecutor.execute`, and `src/wellplot/authoring_service.py::AuthoringService` | Reuse unchanged as the canonical plan, CRUD execution, and validated document mutation route except for narrowly required integration fixes reviewed separately. |
| Existing YAML and renderer paths | Preserve unchanged. Metadata inspection must not become an alternate loader for scientific rendering or an alternate persistence route. |

### F17 — MCP eager inspection / duplicate source loading

The source audit for accepted D2 planning candidate `8dec3f37adcb8a90948cb7312ee3ec4a6fbde685`
found an existing integration defect, not an architecture change:

- `src/wellplot/mcp/agentic.py::_request_context()` currently invokes
  `LogfileSourceLoader.load()` for every declared source before planning and
  builds `available_channels` from that eager projection.
- The same request can subsequently reach
  `SemanticEnricher._load_source()` in
  `src/wellplot/agent/code_mode/enrichment.py`, which loads selected sources
  again. The MCP reconciliation step then consumes the earlier channel
  projection.

The bounded implementation plan must route both call sites through one
request-scoped canonical inspection result and one consistent source revision
identity. `_request_context()` should resolve declared source paths/formats
and capture source revision evidence without parsing every source. After the
planner, enrichment should inspect only source candidates selected by
source-dependent obligations; structural-only work must not needlessly index
DLIS. The bounded inspected projection and its revision must then be carried
through the existing `CodeModeCompileResult`/`AgentSessionResult` boundary (or
an equivalently narrow extension of those existing contracts) for MCP
reconciliation and final pre-publication revalidation. Do not load the source
again to reconstruct `available_channels`.

The implementation must also preserve the existing distinction between
metadata identity and renderer addressability. The current DLIS rendering
loader in `src/wellplot/io/dlis.py` selects the first logical file and stores
channels by mnemonic; richer metadata identities it cannot address must be
`UNADDRESSABLE`, never silently substituted or used to justify a second
scientific loader/binding schema. D2 remains sufficient for planning this
functional implementation; F17 is a required integration item, not a reason
for another broad feasibility cycle.

F17 acceptance regressions must prove: (1) a structural-only request performs
zero source parser loads; (2) one source selected by source-dependent
obligations is inspected once and the same bounded projection feeds worker
context and reconciliation; (3) a source revision change between candidate
resolution, inspection, compilation, and publication fails closed; (4) a
declared but unselected DLIS source is not indexed; (5) a richer logical-file,
frame, or repeated-mnemonic identity unsupported by the renderer returns
`UNADDRESSABLE`; and (6) successful persistence remains reachable only through
the existing canonical publication route.

### F18/F19 — Parser-time and aggregate-concurrency safeguards

The accepted F17 plan is conditionally complete on two narrow safety
corrections. F18 requires the LASIO parse itself, not only prefix scanning, to
run under finite CPU and wall-time containment. The proposed LAS limits are
10 CPU seconds and 15 wall seconds in the same supervised parser-child
mechanism used for DLIS; timeout, abnormal exit, or limit exhaustion returns
incomplete evidence/`UNKNOWN`.

F19 replaces per-request-only concurrency with one host-wide active parser
child. The proposed Linux/WSL2 mechanism is a nonblocking process-shared
exclusive `flock` at the existing `LogfileSourceLoader` boundary. Hold it
until the child is terminated and reaped. A busy lock fails closed with a
bounded `inspection_busy`/`UNKNOWN` result rather than launching another child.
The lock descriptor must survive supervisor cancellation while the child
remains alive, for example by passing it to the direct child; no parser
descendant may outlive group cleanup. Combined stdout/stderr must be read
incrementally with a strict 1 MiB cap before accumulation. Valid process exit
alone is insufficient without a complete projection and terminal inventory
evidence.

Required negative regressions: pathological bounded-prefix LAS parser reaches
CPU and wall limits and is killed/reaped; two independent requests/processes
race and prove at most one child is active; lock contention returns the
bounded incomplete result; cancellation and supervisor failure do not release
capacity while a child remains alive; the lock becomes available after child
termination; output flood is stopped at the byte cap without unbounded
allocation; and successful exit with truncated/missing terminal inventory
evidence remains `UNKNOWN`. Preserve F17 lazy-inspection, single-load,
revision-revalidation, and renderer-`UNADDRESSABLE` tests.

Implementation qualification must include source-level reachability/ownership
tests proving the metadata adapter is reachable only through the existing
inspection path, does not call numerical sample loaders, and cannot construct
or publish a WellPlot document. End-to-end provider-free tests must prove that
successful authoring still reaches `AuthoringDocumentIntent` and then only the
existing reconciliation, CRUD, `AuthoringService`, YAML, and renderer
boundaries. Negative tests must cover no parallel graph/engine/loader,
untrusted metadata injection, stale source/catalog identity, duplicate or
ambiguous channels, incomplete inventories, unsupported renderer addressing,
and safety-limit exhaustion.

The candidate remains subject to independent implementation review. Provider-
backed qualification, scientific qualification, production latency/scaling
acceptance, active catalog release, and baseline promotion are separate later
gates. Current disposition: `D2_FEASIBILITY_SUFFICIENT_FOR_IMPLEMENTATION_PLANNING`;
`FUNCTIONAL_IMPLEMENTATION_PENDING_AUTHORIZATION`.

The planning package was independently accepted against commit
`8dec3f37adcb8a90948cb7312ee3ec4a6fbde685`. F17 is recorded as a required
implementation integration clarification: unify MCP eager inspection and
enrichment inspection through one request-scoped, revision-bound projection.
This does not reopen D1, close D2 production qualification, or authorize
implementation.

## References

- Canadian Well Logging Society, [LAS Version 2.0 specification](https://www.cwls.org/wp-content/uploads/2014/09/LAS_20_Update_Jan2014.pdf).
- LASIO 0.32, [reader source documentation](https://lasio.readthedocs.io/en/latest/_modules/lasio/reader.html) and [encoding documentation](https://lasio.readthedocs.io/en/latest/encodings.html).
- Equinor, [DLISIO 1.0.4 API](https://dlisio.readthedocs.io/en/stable/dlis/api.html) and [error handling](https://dlisio.readthedocs.io/en/stable/dlis/errors.html).
- Python Software Foundation, [Python 3.12 `resource`](https://docs.python.org/3.12/library/resource.html) and [`subprocess`](https://docs.python.org/3.12/library/subprocess.html) documentation.
- Linux man-pages, [`getrlimit(2)`](https://man7.org/linux/man-pages/man2/getrlimit.2.html).
- Well ID, [dliswriter source](https://github.com/well-id/dliswriter) and [PyPI 1.2.0 artifact](https://pypi.org/project/dliswriter/1.2.0/).
- ggml-org, [llama.cpp server API](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

## Boundaries and accounting

No production source, config, dependency, active baseline, D1 design, frozen
population/gold, D5/C02 evidence, or family JSON was modified. No scientific
LAS/DLIS asset was read for these probes. Generated LAS variants were
temporary; the expanded synthetic DLIS fixture is preserved at
`tests/fixtures/a09_d2_metadata/multifile_repeated_mnemonics.dlis`. It contains
only synthetic samples and metadata. No provider, generation, model, endpoint,
smoke, scientific-turn, or C02 call occurred.

```text
provider generation calls = 0
model generation calls = 0
endpoint calls = 0
scientific turns = 0
C02 exposure = 0
production source changes = 0
active-baseline promotion = 0
```
