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

The bounded A07 shared-identity allocator corrective was independently
accepted at `c0ea8b9a7ebc0d9590fdf13286adfbd367c7e8ed`. The broader A07
operation-mapping and compatibility matrix remains open for A10 qualification;
the accepted corrective is not evidence that every A07 requirement is complete.
A08 is a provider-free implementation candidate based on that checkpoint and
is awaiting independent review. The narrow corrective for review findings
F09-F11 binds MCP publication to YAML/template/source snapshot revisions,
reports post-publication preview failures without claiming rollback, and
classifies failed restoration distinctly. Candidate tests cover these cases in
addition to phase/dependency ordering, cycles, private-candidate CRUD failure,
staged replacement failure, and reload rollback. A09 remains on hold; no live
or scientific execution is authorized.

A08 publication semantics are intentionally bounded: same-directory
`os.replace()` provides atomic file visibility on POSIX, but rollback after a
post-replacement reload error may expose the candidate briefly to concurrent
readers. Revision checks are optimistic, not a cross-process compare-and-swap;
writers bypassing the canonical persistence path can race between the final
check and replacement. File revision tokens use resolved path and filesystem
metadata, not full source-content hashing. Directory-entry crash durability is
not claimed because the parent directory is not fsynced. These limitations
must remain explicit in independent review and A10 acceptance.
