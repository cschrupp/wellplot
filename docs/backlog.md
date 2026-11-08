# Deferred Work

These items are outside the active repaired-baseline confirmation path. They
must not interrupt an active scientific or architectural slice unless new
evidence makes one a demonstrated blocker.

The active scientific sequence is:

```text
CM/TW evidence
    -> active baseline
    -> accepted deterministic D5-5H implementation
    -> Knowledge Delta promotion
    -> one bounded repaired-baseline end-to-end confirmation
    -> investigate only genuinely residual semantic failures
```

Historical rediscovery and new model comparison are not part of this sequence
unless that confirmation exposes a genuinely new failure and the
non-rediscovery preflight authorizes follow-on work.

## Active-Baseline Editorial Consistency

Fold these harmless wording corrections into the next appropriate docs-only
design/closeout commit; do not create a standalone blocking slice:

- O-05 should describe end-to-end semantic qualification of the already
  accepted implementation, not whether D5-5H can become implementation
  authority.
- G7 live/end-to-end correction retention is an open qualification/evidence
  question, not an unimplemented deterministic gap.
- Baseline regression wording should say future work must preserve and exercise
  the accepted D5-5H schema/inventory/preservation/grading regressions, not add
  them again.

## Canonical Section-Worker Cleanup / Attestation Hardening

The provider-free implementation tranche is complete as candidate work and is
pending independent review. It retires the dormant `TypedSectionCompiler` /
`TypedSectionGenerationResult` implementation and its shadow-specific
executable consumers, preserves applicable invariants on the canonical worker
path, archives the historical contract wording, and adds AST-based retirement
checks. This backlog item closes only after independent review accepts the
candidate; no live smoke or scientific execution is implied.

## Legacy Roadmap / Release-Wording Reconciliation

The current agent road correctly supersedes the historical CM-54 through CM-58
sequence, but some lower roadmap/release-assessment prose still describes
CM-53/CM-54...58 as active release gating. Reconcile that wording before a
release or mainline-promotion decision. Preserve the historical CM sequence as
history; do not reactivate it as current work.

## Local-Asset Registry / Preflight

Maintain a registry of intentionally local LAS/DLIS assets with expected
relative paths, sizes, and SHA-256 values. Distinguish `NOT_TRACKED`,
`LOCAL_UNVERIFIED`, `MISSING`, and `VERIFIED`. Consider an optional
`scripts/check_local_assets.py` helper.

## Local Checkout / Worktree Cleanup

The live-runtime decision is no longer deferred: credential-bearing readiness,
provider-backed smoke/scientific execution, local scientific assets used by
those runs, and durable campaign custody use the canonical persistent checkout
at `/home/user/projects/well_log_os`.

The remaining deferred work is housekeeping only: inventory and prune obsolete
clones/worktrees after branch/SHA reachability is proven. Additional worktrees
are implementation/review-only and require a genuine simultaneous-checkout
need.

## Shared Local-Asset Provisioning

Do not build a second live asset root or provision live scientific assets into
temporary worktrees. The canonical persistent checkout remains the live asset
authority. If a non-live implementation/review worktree needs synthetic or
read-only development fixtures, provision them without turning that worktree
into a live runtime and never commit the scientific asset bytes.

## Mainline Integration / Promotion

After D5 closure, inspect and integrate the main-only MCP launcher change in a
dedicated promotion review. Do not rebase the accepted development lineage
merely for topology tidiness.

Also reconcile the long-lived D5 branch naming/topology at promotion time
rather than creating branch-management work on the current scientific path.

## Filesystem Cleanup

Inventory stale clones and worktrees, then remove only after branch and commit
reachability is proven. This is not on the current D5 critical path.

## Deterministic Fill-Relation Contract

The section work contract currently fixes fill target, color, and alpha when
explicitly requested, but does not yet compile the fill relation (for example,
`to_lower_limit`) into the deterministic contract. Keep this as a known
semantic-contract gap; do not claim fill relation is fully request-compiled
until a bounded provider-free implementation and regression are accepted.

## Section Action Observability

D5-WORKER-OBS-01 was accepted at
`6f0ef73d2a73b1a01d40767264e8dea0bbad3b45`. The fresh binding smoke
`d5-binding-smoke-6f0ef73d-002` is sealed as `SMOKE_CONTRACT_FAIL`: the
schema-valid response had eight track handles where the deterministic contract
required exactly two; semantic lowering was not reached. This is engineering
contract evidence, not scientific evidence. The opt-in controlled-capture
policy and 30-day authorized-deletion procedure are recorded in
`docs/architecture/D5_WORKER_ACTION_OBSERVABILITY.md`.

## Canonical NLP Authoring Architecture Remediation

`WELLPLOT-NLP-CANONICAL-AUTHORING-ARCH-001` A00 was accepted at
`c6ec436619418b3831a1c9decd7d3c15efebb74c`; its stage-one Knowledge Delta is
active and marks the architecture `ACCEPTED / NOT YET IMPLEMENTED`. A01-A11
are authorized as bounded provider-free implementation slices through the
existing canonical graph and CRUD engine. Do not alter frozen D5/C02 evidence,
run live smoke, or execute scientific campaigns under this authorization.
Stage-two baseline promotion follows independent implementation acceptance and
may record only verified contracts, regression evidence, exact checkpoints,
and residual limitations.

A09 security/observability is accepted at
`7ea43a6548a8bd1e5b44eb20c085a7027932e0db`; A09 overall remains open. The
security/observability tranche adds failure ownership, safe
exception/cancellation stage traces, request/result and worker-contract digest
linkage, and prompt-injection projection coverage. The fixed source-file byte
ceiling is explicitly rejected: multi-gigabyte LAS/DLIS files must not be
rejected solely by total file size. This does not close parser resource-safety
requirements.

The metadata-first inspection/channel-resolution design and its F13/F14
closure were accepted at exact checkpoint
`daef5d171828495b2f0dfcea25ae372f0bc39af4` and are recorded in
`docs/architecture/A09_METADATA_FIRST_INSPECTION_AND_CONTEXT_BUDGET_DESIGN.md`.
The provider-free feasibility and resource-budget results are recorded in
`docs/evaluations/agent-code-mode/A09-resource-budget-feasibility.md`. Stock
LASIO 0.32 avoids sample-array parsing with `ignore_data=True` but scans the
complete file for section markers; a bounded prefix-to-data-marker adapter is
a candidate, not implemented. The 2026-11-03 D2 feasibility result is in
`docs/evaluations/agent-code-mode/A09-D2-feasibility-result.md`: a small
generated LAS 1.2/2.0 marker matrix parses bounded prefixes with LASIO and
empty sample arrays; a preserved 2,364-byte synthetic RP66-style fixture
covers two logical files, multiple frames, repeated mnemonics and copy numbers.
DLISIO 1.0.4 loaded the fixture in a child under test-only limits; strict-error
truncation probes passed, and SUL-only input was correctly identified as an
empty-but-incomplete inventory case. These establish feasibility, not
production limits, broad format conformance, or representative performance.
WSL2 process address/CPU limits and parent wall termination are available, but
writable cgroup memory enforcement is not. No parser budgets are selected.
The 2026-11-04 D2 continuation records provisional, unmeasured end-to-end p95
qualification targets: LAS 1.2/2.0 bounded inspection up to 1,000 channels in
2 seconds; DLIS RP66 v1 cold inspection up to 250 MiB in 30 seconds and the
larger tier up to 1 GiB in 90 seconds; and a valid unchanged-source cache hit
in 1 second. These are qualification objectives only, not production SLOs,
timeouts, safety limits, or source-size rejection thresholds. Larger files
must not be rejected solely by total size. The remaining bounded matrix covers
LAS adversarial correctness, DLIS inventory completeness/corruption/scaling
and containment, exact Qwen/llama.cpp token accounting, and a small governed
catalog proposal. The project owner is nominated as initial domain reviewer,
pending explicit acceptance; no mappings are approved and Codex must not
approve its own scientific assertions. See
`docs/evaluations/agent-code-mode/A09-D2-feasibility-result.md` and
`A09-resource-budget-feasibility.md`. D2 feasibility is sufficient for
bounded functional implementation planning: performance targets, p95
benchmarks, representative scaling, optimized budgets, and exact model-token
accounting are not prerequisites to provider-free implementation. Basic parser
isolation, finite reviewed provisional safety controls, exact source identity,
deterministic four-state resolution, and fail-closed publication remain
required. Production/provider-backed readiness retains the deferred scaling,
latency, resource, token-accounting, and domain-approved catalog gates. No
production implementation, binding-schema or scientific-loader change,
baseline promotion, provider call, endpoint call, or live/scientific
qualification is authorized. Functional implementation remains pending
separate authorization; A09 remains open.

The D2 planning candidate was independently accepted at
`8dec3f37adcb8a90948cb7312ee3ec4a6fbde685`. Review finding F17 requires the
bounded implementation plan to reconcile eager source inspection in
`src/wellplot/mcp/agentic.py::_request_context()` with later loading in
`SemanticEnricher._load_source()`. Use one request-scoped, source-revision-bound
inspection projection; inspect only when source-dependent work selects a
source; reuse the projection for reconciliation and final revalidation. A
structural-only request must not parse unrelated DLIS. Rich metadata identities
not supported by the existing DLIS renderer remain `UNADDRESSABLE`. The exact
entry points, provisional safety-control proposal and source-ownership tests
are recorded in the D2 feasibility result. F17 does not reopen D1 or authorize
source implementation.

The follow-up independent safety review accepts F17 and adds F18/F19 before
functional implementation authorization. F18 requires finite CPU and wall
containment around LASIO parsing itself (proposed development values: 10 CPU
seconds and 15 wall seconds, using the supervised parser child). F19 requires
one host-wide active parser child across concurrent processes, a shared
nonblocking lock at the existing loader boundary, safe lock lifetime through
child cleanup, and an incrementally enforced aggregate 1 MiB stdout/stderr
cap. Limit, timeout, lock-busy, cancellation, abnormal-exit, output-flood and
incomplete-inventory cases must fail closed to `UNKNOWN`. These are safety
requirements, not performance blockers. Cross-process lock semantics remain
to be regression-qualified. No implementation is authorized.

The accepted documentation-only D1 joint semantic-catalog/source-inspection
design is recorded in
`docs/architecture/A09_JOINT_SEMANTIC_CATALOG_AND_SOURCE_INSPECTION_DESIGN.md`.
It integrates the accepted metadata-first design with a governed normalized
catalog and read-only inspection contract through the existing authoring
context. D1 was independently accepted at
`da23cd69792b4c75ed1da30bc0de35ca69ddcb38`; F15/F16 are closed, including the
narrow F14 amendment for ambiguous bare-token interpretation and family-level
absence. The accepted historical F14 document was not rewritten. Request-term
recognition is distinct from physical-channel classification, and semantic
resolutions bind the catalog content digest plus immutable release reference.
The acceptance and Knowledge Delta are recorded in
`docs/architecture/A09_D1_ACCEPTANCE_RECORD.md`. D1 does not authorize
implementation, select production aliases/defaults or resource budgets, or
promote the active baseline. Four supplied family
JSON files were audited as untrusted reference/collision data; exact findings
and digests are in the D1 design and feasibility record. D2 feasibility is
documented, but numeric parser-budget selection, exact model-token accounting,
and independent/domain acceptance of catalog governance remain open. A09
implementation remains unauthorized.

The bounded A07 shared-identity allocator corrective was independently
accepted at `c0ea8b9a7ebc0d9590fdf13286adfbd367c7e8ed`. The broader A07
operation-mapping and compatibility matrix remains open for A10 qualification;
the accepted corrective is not evidence that every A07 requirement is complete.
A08 is a provider-free implementation candidate based on that checkpoint and
is awaiting independent review. Its F09-F11 corrective binds MCP publication
to YAML/template/source snapshot revisions, reports post-publication projection
failures without implying rollback, and classifies failed restoration
distinctly. The follow-up F10-R1 correction contains failures in validation,
summary, inspection, preview, and draft-text projection while preserving the
published/rollback state and warning users not to retry a persisted change.
Provider-free transaction and adjacent canonical-path regressions pass.

QUAL-01 full-suite triage is not a PASS. The following failures were
reproduced at A07 parent `c0ea8b9a7ebc0d9590fdf13286adfbd367c7e8ed` and are
classified as pre-existing baseline, stale historical contract, or missing
local evidence rather than A08 regressions:

- `test_inventory_output_is_deterministic_and_rewrites_identically` and
  `test_required_migration_modules_are_classified_in_current_inventory`:
  reachability inventory still requires absent `wellplot.agent.core`.
- `test_profile_budget_is_bounded_and_smaller_than_diagnostic_contract`:
  measured schema is 45,297 characters versus the stale 40,000 limit.
- `test_protected_runtime_modules_do_not_depend_on_the_fixture`: expected
  `src/wellplot/agent/graph/workflow.py` is absent.
- CM56R7 evidence-analysis tests: required local
  `/tmp/cm56r6-authoritative-qwen-rerun.jsonl` is absent.
- CM57P10/P8 source-fingerprint tests: frozen provider-base hash differs;
  CM57P2/P4 prompt-hash tests and CM57P6/P7 schema-hash tests also have stale
  pins.
- CM57P3/P5 planner self-tests and
  `test_graph_safety_runs_before_enrichment_and_workers` fail on pre-existing
  planner wire/scope or capability-safety expectations.

The unfiltered repository suite remains unqualified; the candidate must not
claim a full-suite PASS from these filtered provider-free results. A09 has
focused provider-free candidate evidence but remains subject to independent
review and the explicitly deferred resource-safety design. No live or
scientific execution is authorized by that candidate evidence.

A08 publication semantics are intentionally bounded: same-directory
`os.replace()` provides atomic file visibility on POSIX, but rollback after a
post-replacement reload error may expose the candidate briefly to concurrent
readers. Revision checks are optimistic, not a cross-process compare-and-swap;
writers bypassing the canonical persistence path can race between the final
check and replacement. File revision tokens use resolved path and filesystem
metadata, not full source-content hashing. Directory-entry crash durability is
not claimed because the parent directory is not fsynced. These limitations
must remain explicit in independent review and A10 acceptance.

## A09 Integrated Qualification and Adapter-Parity Follow-up (2026-11-05)

The A09 integrated CBL+VDL qualification candidate at checkpoint
`1d65d8cd36fc6fb288ab3627ebfb9f9246506372` is
`INDETERMINATE / PRE-PROBE ENVIRONMENT`: the sole invocation stopped in `uv`
before Python launch because its default cache directory was read-only. It
did not inspect or numerically load the source, persist YAML, or render; no
provider/model/endpoint calls or C02 access occurred. Do not count this as a
functional result or retry within that one-attempt authorization. Evidence is
in `workspace/evaluations/a09-canonical-integration-20261105-001/`.

Static audit found that notebook applies request-obligation and document-
preservation postconditions before persistence, while MCP does not explicitly
apply them and no shared lower layer does so. This is a verified parity gap,
not proof of a previously published invalid document. Track a narrow shared
pre-publication verifier plus an MCP no-persistence regression for the next
reviewed corrective; do not refactor adapters or promote A09 until separately
authorized and independently reviewed. The earlier isolated CBL render probe
remains `INDETERMINATE / TEST_HARNESS`, not renderer failure.

### A09-PARITY-01: adapter postcondition parity review

A provider-free candidate introduces one shared pre-publication verifier for
the existing request-obligation and document-preservation checks and invokes
it from both the notebook and MCP adapters. Focused regressions cover rejected
obligations, unauthorized candidate mutations, and successful continuation to
canonical persistence in both paths, including the public MCP revise operation.
Initial candidate validation reported 71 relevant provider-free tests plus
Ruff and manifest checks. Do not retry the unrelated A09 canonical integration
probe, promote the baseline, or infer that A09 integrated functional
qualification passed from this adapter candidate.

The review condition requiring explicit typed MCP obligations consumption is
covered by a corrective regression: a success-shaped non-`AgentSessionResult`
without obligations is rejected as `compile_failed` before persistence. The
corrective was accepted at `a12640591abbd6ff832a988ce1e6adc7c6fcfb79` and
promoted to the active baseline. A09 integrated CBL+VDL qualification remains
open. Provider-free preflight confirms the accepted source identity and exact
CBL/VDL metadata identities; a fresh namespace is prepared, but execution is
not authorized. Preserve the failed `...-001` attempt unchanged.

## WP-A09-CBL-SCALE-01 — Accepted read-only audit

The measurement-semantics and display-scale audit for
`CBL_Repeat.dlis` was independently accepted. Preserve the selected channel as
CBL Amplitude with its declared `mV` unit. The file's linked
`CBL_AMPLITUDE_NORMALIZATION` and related calibration metadata do not define a
supported conversion to apply; do not multiply samples by 100 or infer that
the values are dimensionless. A binding-level fixed scale is supported by the
existing authoring contract and changes presentation only. The proposed
`-0.125..1.1 mV` range is a data-fitted diagnostic candidate, not a universal
CBL default. Calibration semantics remain unresolved pending authoritative
QSLT/SSLT documentation. The exact `-999.25` null/masking behavior remains a
separate WellPlot v1 ingestion concern and was not modified. Audit evidence is
in `workspace/evaluations/wp-a09-cbl-scale-01-20261106-001/`; the captured
stdout SHA-256 is
`04f0ef4a0e20f8cbe121d40c28b46ff652ebd2fd5e5002b9f49cac858ec3d242`.
No production code, rendering, YAML publication, model/provider call, or
integration rerun was part of this audit. This finding does not change the
historical terminal of attempt 003 or establish integrated A09 qualification.

## A09-CAT-01 — Foundation Accepted, Activation Disabled

The semantic-catalog foundation and corrective are independently accepted at
`2c54149b9bc7e717c20db46e647e85c065b02dc1` and
`e44713cc37712aae18197284ccf40c0406f7ed04`. The current reconciler blocks
nonempty catalog content and pre-resolved semantic evidence before producing
operations. Preserve this guard. No production family mappings are approved;
`examples/families/` remains an untrusted reference corpus.

The foundation does not qualify catalog-backed publication. Its evidence
verifier has no production caller, the guard is reconciliation-level rather
than executor-wide, and explicitly populated addressability is not yet proven
to originate in the trusted source snapshot. A future A09-CAT-02 should connect
the existing evidence contract to the shared notebook/MCP pre-publication
postcondition boundary and verify source/catalog revision plus exact binding
scope and physical identity before persistence. Do not add another resolver,
executor, or publication path. A09 integrated qualification remains open;
attempt 003 remains `FAIL`. No mapping activation, integration run, A10/A12
qualification, or provider/scientific authority follows from this acceptance.

## A09-CAT-02D — Trusted Catalog and Source Binding Design

Design candidate prepared from the CAT-02 preflight stop at baseline
`44a6fea47fb2d3e5c9d296080c73070ba13ed645`. It proposes one host-owned,
request-scoped approved catalog release pin and binds semantic evidence to a
source handle, inspection snapshot/revision, exact physical identity, and
section/track/binding in the existing authoring path. The shared
`verify_document_postconditions()` remains the sole publication verifier.

Initial independent design review returned `CHANGES_REQUIRED` (F20-F22); R1
resolved those findings and R2 resolved F23. Independent review accepted
CAT-02D R2 as `A09_CAT_02D_DESIGN_ACCEPTED`. The accepted contract distinguishes
exact artifact-byte `catalog_artifact_sha256` from canonical semantic
`content_sha256`, binds both in the approval manifest/release record and
deployment pin, and specifies separate validation of each. It also freezes
the deployment-pinned approval chain, source joins/cardinality for existing
and new sections, and the host-compiled expected semantic-binding set.

CAT-02I is authorized as a bounded provider-free implementation slice. It
must keep activation disabled, use isolated synthetic verifier positives,
and must not use a test-only adapter/reconciler bypass. Positive
catalog-backed notebook/MCP transactions and any guard removal belong to
separately authorized CAT-03.

The CAT-01
`semantic_catalog_activation_disabled` guard remains mandatory. No catalog
artifact is approved, `examples/families/` remains untrusted reference data,
and no production code, tests, activation, baseline promotion, integration
qualification, provider call, or scientific execution is authorized. Open
residual risks include reliance on existing application deployment integrity,
offline revocation requiring deployment reload, package-data selection, and
the non-cryptographic nature of filesystem revision tokens. See
`docs/architecture/A09_CAT_02D_TRUSTED_CATALOG_AND_SOURCE_BINDING_DESIGN.md`.

The design uses TUF/Sigstore only as trust-model comparisons; it does not
select a runtime framework or add a dependency. After independent design
acceptance, implementation requires its own applicable authorization. A09
integrated qualification remains open and attempt 003 retains its historical
`FAIL` terminal.

### CAT-02I implementation candidate (2026-11-07)

CAT-02I provider-free implementation is being prepared for independent review
on the existing development branch. It extends the existing catalog,
authoring-context, enrichment, AgentSession/facade, shared postcondition, and
notebook/MCP transaction boundaries. It adds strict separate artifact-byte,
approval-manifest-byte, and canonical-content digest validation; a fixed
package-resource release pin; a request-scoped immutable release carried with
the host publication contract and revalidated before publication; exact
host-derived semantic expectation/source joins; and semantic verification at
the existing shared pre-publication boundary.

The CAT-01 `semantic_catalog_activation_disabled` guard remains unchanged.
No deployment pin or approved catalog is shipped, and no positive
catalog-backed adapter transaction is enabled. Synthetic positives exercise
the shared verifier only; notebook/MCP regressions verify no publication when
semantic trust is absent. Candidate commit
`1d5673cd304beef549916816cb266c8e2f5e04d7` is based on
`7b72f5d96da31f233d913583c9f3c038fdee003a`; its focused provider-free suite
passed 151 tests, Ruff/format/compile/diff checks passed, and the single-engine
manifest attestation passed. Independent acceptance and CAT-03 activation
remain pending. No baseline promotion, integration retry, provider call, C02
access, or scientific execution occurred.

### CAT-02I independent acceptance (2026-11-07)

Independent review accepted CAT-02I and its test-only R1 corrective as
`A09_CAT_02I_ACCEPTED — ACTIVATION_REMAINS_DISABLED`. Accepted lineage:
CAT-02D `7b72f5d96da31f233d913583c9f3c038fdee003a`, implementation
`1d5673cd304beef549916816cb266c8e2f5e04d7`, review-status commit
`cce30be6bc4ce6eff61e70a1f0062d695e8ebbe9`, and R1 tests
`7c6f6df850e94f2cf408e0b2035c56264da0d18e`.

The accepted contracts cover independently pinned catalog artifact and
canonical-content trust, transaction-scoped source/binding continuity,
host-derived expected semantic evidence, and verification at the existing
shared pre-publication boundary. Notebook/MCP semantic rejection remains
non-publishing. The R1 tests reach production `verify_semantic_publication()`;
the reported committed-tree focused validation is 177 passed. Independent
review inspected the source and test patch but did not rerun that suite.

This acceptance does not activate a catalog: keep
`semantic_catalog_activation_disabled`; approve no production mapping; treat
`examples/families/` as untrusted reference data; and do not claim a positive
catalog-backed notebook/MCP transaction is qualified. CAT-03 requires separate
authorization. A09 integrated qualification remains open and attempt 003
retains its historical `FAIL`. No provider/model/endpoint, C02, live, or
scientific execution occurred. CAT-02 is closed; this record does not release
CAT-03 or change the integrated-qualification gate.
