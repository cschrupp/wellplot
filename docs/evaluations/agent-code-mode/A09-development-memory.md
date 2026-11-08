# A09 — Inspection Security and Observable Failures

## Status

- State: A09-PARITY-01 accepted at `a12640591abbd6ff832a988ce1e6adc7c6fcfb79`; integrated CBL+VDL qualification remains unattempted and A09 overall open
- Accepted security/observability checkpoint: `7ea43a6548a8bd1e5b44eb20c085a7027932e0db`
- Accepted metadata-first design checkpoint: `daef5d171828495b2f0dfcea25ae372f0bc39af4`
- Current work: prepare fresh provider-free integrated CBL+VDL qualification
  in a new namespace; execution requires separate authorization
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

No fixed total LAS/DLIS file-size ceiling is permitted. For initial bounded
provider-free implementation, the required foundations are metadata-only
inspection, exact source/channel identity, four-state resolution, fail-closed
ambiguity, parser isolation, and reviewed finite provisional safety limits.
Production scaling and latency qualification, optimized resource budgets,
exact Qwen/llama.cpp token accounting, and approved scientific mappings are
later provider-backed/production-readiness gates. This stage distinction was
clarified by the 2026-11-04 D2 follow-up and does not reopen D1.

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
- The initial 1,020-byte RP66-style fixture was expanded into preserved
  `tests/fixtures/a09_d2_metadata/multifile_repeated_mnemonics.dlis` (2,364
  bytes; SHA-256
  `b98beba2bc6fedb70794da63d68dd09ac94abe02191fbfb53e6acd2eb85c08b9`). It
  parses as two logical files, three frames, and repeated channel mnemonics
  with distinct copy numbers. Strict-error child probes also show that
  truncated input fails while a SUL-only input can return zero logical files
  successfully; empty inventory must therefore be incomplete/`UNKNOWN`. The
  probe used test-only AS/CPU/wall limits. No numerical curve APIs or
  scientific fixtures were used. `dliswriter`'s `2**32` default buffer
  preallocates 4 GiB; fixture generation explicitly used a bounded buffer. The
  writer is not a conformance validator.
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

D2 feasibility is delivered but not fully closed. The 2026-11-04 continuation
records provisional, unmeasured end-to-end p95 qualification targets:

- LAS 1.2/2.0 bounded metadata inspection, up to 1,000 channels: 2 seconds.
- DLIS RP66 v1 cold inspection, up to 250 MiB: 30 seconds.
- DLIS RP66 v1 cold inspection, larger benchmark tier up to 1 GiB: 90 seconds.
- Valid cached inspection for an unchanged source: 1 second.

These are benchmark objectives, not accepted production SLOs, timeouts,
resource limits, or source-size admission ceilings. Larger files must not be
rejected solely by total size. Qualification is to run on the canonical
WSL2/local-storage environment, include subprocess startup in end-to-end
latency, separate startup/parser timing, and report cold/warm p50/p95/p99 plus
memory, CPU, wall, scanned bytes, metadata/output volume and limit behavior.
No production limits have been selected.

The remaining bounded matrix and dispositions are in
`A09-D2-feasibility-result.md`: LAS adversarial/format correctness; DLIS
positive inventory completeness and corruption, scale and containment; exact
Qwen/llama.cpp token accounting; and governance of a small reviewed catalog
batch. The project owner is nominated as the initial scientific/domain
reviewer, but acceptance of that role is pending. Codex may prepare candidate
rules but must not approve its own scientific mappings. No mappings are
approved; broad patterns remain suggestions. D1's four-state resolution and
canonical single-engine architecture remain controlling.

The bounded LAS adapter, supervised DLIS parser, and catalog must remain
internal capabilities behind the existing source-inspection/host-resolution
path. The child returns metadata only and cannot interpret intent or publish a
WellPlot document. Eventual implementation review requires an ownership and
source-reachability audit plus negative tests showing publication only via
the existing canonical `AuthoringService` path. Functional implementation
remains pending separate Human authorization; A09 promotion and production
qualification are not authorized.

### D2 planning review and F17 (2026-11-04)

D2 planning candidate `8dec3f37adcb8a90948cb7312ee3ec4a6fbde685` was accepted
for bounded functional implementation planning. Performance p95 targets,
representative scaling, optimized production budgets and exact provider token
accounting are deferred beyond provider-free functional development. Basic
parser isolation, finite provisional safety limits, deterministic source and
channel identity, four-state resolution, fail-closed ambiguity, and canonical
publication ownership remain implementation prerequisites. The proposed
finite profile and existing-component migration map are recorded in
`A09-D2-feasibility-result.md`; the values await separate review/authorization.

F17 records a duplicate-inspection path: MCP
`src/wellplot/mcp/agentic.py::_request_context()` eagerly loads all declared
sources, then Code Mode enrichment may load selected sources again through
`SemanticEnricher._load_source()`. The bounded implementation must unify these
through one request-scoped, source-revision-bound inspection result, defer
parsing until source-dependent obligations select a source, and reuse that
result for MCP reconciliation and publication revalidation. Structural-only
work must not inspect unrelated DLIS. Rich DLIS identities not supported by
the existing renderer remain `UNADDRESSABLE`. This is an implementation
integration clarification, not a D1 reopening or a new workflow.

The subsequent safety review accepted F17 and requires two documentation
corrections before functional implementation authorization. F18 applies the
proposed finite CPU/wall limits to LASIO parsing itself, not only prefix
scanning (1 GiB address space, 10 CPU seconds, 15 wall seconds; timeout or
limit returns incomplete/`UNKNOWN`). F19 requires one host-wide active parser
child across concurrent WellPlot processes, enforced at the existing loader
boundary with a process-shared nonblocking lock; busy means incomplete/
`UNKNOWN`. The supervising parent must enforce the aggregate 1 MiB stdout/stderr
limit incrementally, and lock lifetime must cover cancellation until the child
is gone. Add cross-process contention, cancellation, output-flood, abnormal
exit and terminal-inventory regressions. These are safety corrections, not
performance gates. Cross-process `flock` semantics are documented but not yet
qualified in this environment. See the updated D2 result and resource record.

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

## 2026-11-05 Integrated Qualification Candidate and Entrypoint Audit

The accepted DLIS metadata, scalar CBL loading, and VDL array-loading gates
remain narrow prior evidence at checkpoint
`1d65d8cd36fc6fb288ab3627ebfb9f9246506372`. The standalone CBL renderer probe
`a09-cbl-scalar-render-20261104-001` remains
`INDETERMINATE / TEST_HARNESS`: its single-figure assertion did not follow the
`RenderResult` contract, and it did not establish a renderer defect.

One integrated provider-free qualification was prepared under
`workspace/evaluations/a09-canonical-integration-20261105-001/`, using the
existing canonical metadata loader, physical-channel resolver, authoring
intent/reconciler/executor/service, persistence service, and WellPlot v1
render services. The exact invocation was
`uv run --frozen python workspace/evaluations/a09-canonical-integration-20261105-001/probe.py`.
It exited with code 2 before Python started because `uv` could not create a
temporary file under the read-only default cache `/home/user/.cache/uv`.
Per the one-attempt stop rule, no retry was made. Thus
the integrated qualification is `INDETERMINATE / PRE-PROBE ENVIRONMENT`, not
a functional PASS or FAIL. No metadata inspection, numerical load, YAML
publication, or rendering occurred in that attempt; provider/model/endpoint
calls and C02 access were zero. The command, stdout, stderr, exit code, and
probe are retained in that namespace. The probe compiled successfully before
execution, which did not load the source or render.

Static entrypoint audit at the same checkpoint confirms that notebook and MCP
share the `AgentSession`/Code Mode composition, reconciliation, executor,
`AuthoringService`, and canonical persistence service. The notebook's
`direct_notebook._apply_result()` explicitly runs
`verify_document_obligations()` and `verify_document_preservation()` before
persistence. MCP's `mcp.agentic._apply_session_result()` does not. The shared
reconciler/executor/service do not receive a request-obligation set and do not
invoke either verifier; `AuthoringService.validate()` performs typed document
validation only. This establishes a source-level parity gap, but not a
historical invalid-publication exploit. No adapter refactor was made.

Minimum corrective recommendation for independent review: factor the
post-lowering obligation and preservation checks into one shared deterministic
pre-publication boundary used by both adapters, and add an MCP regression that
proves a violated postcondition prevents persistence. Keep provider calls,
reconciliation authority, and persistence ownership unchanged. This
recommendation is not implementation authorization. A09 integrated functional
acceptance remains open pending a successfully executed bounded qualification
and independent review of both that result and the adapter-parity finding.

## A09-PARITY-01 Provider-Free Candidate (2026-11-05)

Following explicit bounded implementation authorization, the working candidate
adds `verify_document_postconditions()` in the existing obligations module. It
orchestrates the existing request-obligation and document-preservation checks
and reports which check rejected the private candidate. The direct notebook
adapter uses the shared boundary while retaining its existing result tuple and
failure status. The MCP agentic adapter invokes the same boundary after
canonical execution and typed validation, before the existing persistence
service; its persistence ownership and result shape remain unchanged.

Provider-free regressions in both adapter transaction modules cover an
unsatisfied request obligation, an otherwise-valid but unauthorized document
mutation, and a passing candidate continuing through the existing persistence
path. Rejections assert that persistence is not called and original YAML bytes
remain unchanged. The D5 production-component manifest was regenerated using
`scripts/d5_single_engine_attestation.py --write`.

Initial candidate validation: 71 tests passed across
`tests/test_direct_notebook_transaction.py`,
`tests/test_mcp_agentic_transaction.py`, and
`tests/test_d5_5j_obligations.py`; Ruff check and format check passed. The
verified `.venv` is Python 3.12.7 with pydantic 2.13.3, pytest 9.0.2, lasio
0.32, dlisio 1.0.4 and matplotlib 3.10.8, matching the corresponding
`uv.lock` pins. The prior `uv` cache issue is therefore avoidable for provider-
free tests with this interpreter; the integrated probe was not executed.
This remains an implementation candidate pending independent review, not an
A09 acceptance or baseline promotion. The previously failed integrated
qualification remains `INDETERMINATE / PRE-PROBE ENVIRONMENT` and was not
retried. No provider, model, endpoint, scientific, C02, numerical-source, or
YAML-publication operation was performed by this candidate work.

### A09-PARITY-01 Review Condition Correction

Independent review identified that MCP used a permissive `getattr(..., ())`
fallback for the obligations field. The corrective now types the application
boundary to `AgentSessionResult`, explicitly rejects nonconforming result
objects as `compile_failed`, and reads `session_result.obligations` directly.
A provider-free regression supplies a success-shaped object without the
obligations contract and verifies persistence is not invoked and original YAML
bytes remain unchanged. The final relevant test set passes 72 tests; Ruff
checks pass. At this entry it awaited final independent acceptance and did not
authorize or run integrated qualification; it was subsequently accepted at
`a12640591abbd6ff832a988ce1e6adc7c6fcfb79`.

## A09-PARITY-01 Acceptance and Integration Preflight (2026-11-05)

Independent review accepted exact commit
`a12640591abbd6ff832a988ce1e6adc7c6fcfb79` and its typed MCP result guard.
The accepted Knowledge Delta is promoted in
`docs/agent-code-mode-current-baseline.md`. A09 adapter parity is closed;
integrated CBL+VDL qualification remains unattempted.

Provider-free preparation verified the canonical root and Git top-level as
`/home/user/projects/well_log_os`, branch
`engineering-d5-binding-path-repair`, HEAD
`a12640591abbd6ff832a988ce1e6adc7c6fcfb79`, and the existing venv interpreter
and relevant locked dependency versions. The real source
`workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis` is
3,294,924 bytes with SHA-256
`a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640`.
The canonical metadata-only inspector resolved exact CBL and VDL physical
identities and reported both `ADDRESSABLE`; no numerical sample API was used.
CBL identity: DLIS logical file 0, CHANNEL name `CBL`, origin 61, copy 0,
frame 0, scalar, unit `mV`. VDL identity: DLIS logical file 0, CHANNEL name
`VDL`, origin 61, copy 0, frame 2, array, unit unspecified. The prepared
probe pins both identities and fails closed on drift.
The fresh proposed namespace is
`workspace/evaluations/a09-canonical-integration-20261105-002/`, confirmed
unused; its parent is writable. This was preparation, not an integrated test.

The prior namespace `...-001` remains immutable and
`INDETERMINATE / PRE-PROBE ENVIRONMENT`. No provider/model/endpoint calls,
scientific grading, C02 access, YAML persistence, or rendering occurred in
this preflight. A fresh execution attempt remains unauthorized pending the
preflight report and separate integration-smoke authority.

## WP-A09-CBL-SCALE-01 — Independent audit accepted (2026-11-06)

The read-only CBL measurement-semantics audit was accepted. It inspected the
existing CBL channel in `CBL_Repeat.dlis` using the canonical metadata path and
`wellplot.io.dlis.load_dlis`; it did not change production code, source values,
null handling, YAML, rendering, or prior qualification evidence. The source
SHA-256 was unchanged before and after:
`a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640`.

Identity is DLIS logical file 0, CHANNEL CBL (origin 61, copy 0), frame 0,
scalar, index TDEP, long name `CBL Amplitude`, declared unit `mV`, representation
code 2. The source tool is QSLT-BB (origin 61, copy 0). Representation code 2
establishes the stored numeric encoding, not an engineering-unit conversion.
The linked calibration records include `CBL_AMPLITUDE_NORMALIZATION`, method
`CALI_METHOD_NONE`, and gain coefficients of 1.0 with reference values 0.5;
the available evidence does not define a conversion from them. Preserve the
decoded measurements and do not multiply by 100 or call them dimensionless.

The canonical loader returned 523 samples, including 81 exact `-999.25`
sentinels. Excluding that sentinel solely for diagnostic statistics leaves 442
values ranging from approximately -0.1125 to 1.05 mV, with median 0.0625 and
P95 0.8. The sentinel was not masked in production. A fixed 0-1 mV display
would clip 47 negative and 4 above-range values; 0-10 and 0-100 mV avoid high
clipping but use only about 8% and 0.8% of the width at P95. A data-fitted
`-0.125..1.1 mV` scale is only a diagnostic display candidate, not an
authoritative acquisition calibration or universal default. Existing
binding-level `AuthoringScale`/YAML scale support is sufficient and affects
display limits, not sample values.

Disposition: `INDETERMINATE — MEASUREMENT SEMANTICS UNRESOLVED`, with the audit
accepted and closed. The outstanding vendor calibration interpretation and
the `-999.25` masking issue are separate concerns; no further CBL scale
investigation, implementation, render, or integration execution follows from
this acceptance. The latter remains tracked in `docs/backlog.md`. Evidence is
in `workspace/evaluations/wp-a09-cbl-scale-01-20261106-001/`; stdout SHA-256:
`04f0ef4a0e20f8cbe121d40c28b46ff652ebd2fd5e5002b9f49cac858ec3d242`.
Provider/endpoint calls were zero; rendering and YAML publication were not
attempted. Attempt 003's original terminal remains immutable and integrated
A09 qualification remains open.

## A09-CAT-01R — Foundation Acceptance (2026-11-07)

Independent review accepted the semantic-catalog foundation with disposition
`A09_CAT_01_FOUNDATION_ACCEPTED — ACTIVATION_DISABLED`.

- Foundation: `2c54149b9bc7e717c20db46e647e85c065b02dc1`.
- Corrective: `e44713cc37712aae18197284ccf40c0406f7ed04`.
- Review package SHA-256:
  `447e885490185bff7e154c3d3bceeadbac885dd170f556a0775d74f4805ae3e3`.
- Corrective closes IR-001 by blocking nonempty catalog content or
  pre-resolved semantic evidence at `reconcile_authoring()` before operations
  are produced. IR-002 is closed at foundation level by binding evidence to
  section/track/binding, exact physical identity encoded as canonical immutable
  JSON, catalog release/digest, and source revision. Supported identity shape
  and explicit addressability checks fail closed.
- Empty-catalog exact CBL/VDL authoring and explicit CBL scale regressions
  remain passing. The focused cross-component command reported 97 passed;
  Ruff, format, compile, single-engine attestation, and diff checks passed.
  The reviewer inspected supplied logs and source but did not independently
  rerun the tests.
- No production mappings are approved. `examples/families/` remains untrusted
  reference data. The reconciliation guard is mandatory and must not be
  removed or bypassed pending shared pre-publication verification.
- The verifier has no production caller; catalog-backed publication remains
  unqualified. The guard is not executor-wide for arbitrary preconstructed
  plans, and addressability must later be bound to the authoritative source
  snapshot, not inferred from an explicitly set field alone.
- No production mappings, provider/model/endpoint calls, C02 activity, YAML
  publication, integration smoke, or scientific execution occurred. A09
  integrated qualification remains open; attempt 003 remains `FAIL`. No A10,
  A12, or mapping activation authority is implied.

The next recommended slice is A09-CAT-02: connect the existing semantic
evidence verifier to the shared canonical pre-publication boundary used by
notebook and MCP, including source/catalog revision and binding identity
revalidation. This recommendation is not implementation authorization and
must not create another resolver, executor, or persistence path.

## A09-CAT-02D — Trusted Authority and Source Binding Design Candidate (2026-11-07)

The CAT-02 implementation preflight correctly stopped because notebook/MCP
transactions do not independently supply a nonempty approved catalog release,
and the reconciliation channel projection does not preserve per-candidate
source handle/revision through the publication boundary. The stop is accepted;
no code was changed.

Documentation-only candidate:
`docs/architecture/A09_CAT_02D_TRUSTED_CATALOG_AND_SOURCE_BINDING_DESIGN.md`.
It provisionally selects a host-owned request-scoped release pin by extending
the current host composition/transaction path and defines source identity as
inspection snapshot + request-scoped source handle + revision + exact physical
identity. The current compile facade does not own notebook/MCP transaction
construction; a shared transaction-context factory does not yet exist. The
design leaves the minimum integration point for CAT-02I review. Semantic
evidence remains derived and independently verified; the existing
`verify_document_postconditions()` stays the single publication gate.

The initial design compares this adapted repository approval model with
primary TUF and Sigstore references. It does not add a signing framework,
catalog service, runtime dependency, or storage mechanism. The R1 amendment
now resolves approval, source continuity, and evidence completeness at the
design-contract level; residual deployment-integrity and offline-revocation
assumptions remain explicit below.

Independent review returned `CHANGES_REQUIRED` with F20-F22. This R1 amendment
defines: (1) an accepted repository release record bound by a deployment-trusted
pin to exact catalog/manifest digests, with revocation effective on deployment
reload; (2) exact existing/new-section joins from section scope through
candidate ID, source handle, snapshot/revision, physical identity, and final
binding; and (3) an independently host-compiled expected semantic-binding set
whose entries must biject with evidence and final bindings. Filesystem
revision tokens remain optimistic metadata fingerprints, not content hashes.

CAT-02I is limited to trust/verifier integration, negative adapter publication
tests, empty-catalog compatibility, and isolated synthetic shared-verifier
tests. It must not bypass `semantic_catalog_activation_disabled` for positive
adapter transactions. CAT-03 owns separately authorized positive
catalog-backed transactions and any guard removal.

Status: `A09_CAT_02D_DESIGN_ACCEPTED / CAT-02I_AUTHORIZED`.
Independent review accepted F20-F22 but returned one narrow F23 correction:
the trust contract must distinguish exact artifact-byte
`catalog_artifact_sha256` from canonical semantic `content_sha256`. The R2
amendment binds both in the approval manifest, accepted release record, and
deployment pin; verifies raw bytes against the artifact digest; recomputes
canonical content identity after strict parsing; and repeats both checks
before publication. The two digests are explicitly independent and need not
be equal. Independent review accepted CAT-02D R2 and closed F20-F23. This
acceptance is design-level; it does not qualify integrated A09 execution.
CAT-02I is authorized as bounded provider-free implementation with the
activation guard retained. Positive catalog-backed notebook/MCP transactions
and guard removal remain CAT-03.

The CAT-01 activation guard remains mandatory. No mapping is approved,
`examples/families/` remains untrusted, and no implementation, baseline
promotion, integration rerun, provider call, or scientific execution is
authorized by the design amendment. A09 attempt 003 remains `FAIL`; integrated
qualification is open.

## A09-CAT-02I — Provider-Free Implementation Candidate (2026-11-07)

CAT-02I provider-free implementation candidate against the accepted CAT-02D R2
design is committed at `1d5673cd304beef549916816cb266c8e2f5e04d7`, parent
`7b72f5d96da31f233d913583c9f3c038fdee003a`. It extends the existing catalog,
authoring-context, enrichment, AgentSession/facade, shared postcondition, and
notebook/MCP transaction boundaries. It adds strict separate artifact-byte,
approval-manifest-byte, and canonical-content digest validation; a fixed
package-resource release pin; a request-scoped immutable release carried with
the host publication contract and revalidated before publication; exact
host-derived semantic expectation/source joins; and pre-publication semantic
verification through `verify_document_postconditions()`.

The CAT-01 `semantic_catalog_activation_disabled` guard remains unchanged.
No deployment pin or approved catalog is shipped, and no positive
catalog-backed adapter transaction is enabled. Synthetic positives exercise
the shared verifier only; notebook/MCP regressions confirm no publication
when semantic trust is absent. The focused provider-free suite passed 151
tests; Ruff, format, compilation, diff checks, and production-manifest
attestation passed. No provider/model/endpoint calls, numerical scientific
execution, A09 integration retry, C02 access, or active-baseline promotion
occurred. Candidate acceptance and CAT-03 activation remain pending
independent review and separate authorization. This Knowledge Delta has not
been promoted into the active baseline.
