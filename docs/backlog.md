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
