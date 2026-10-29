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

Nonblocking architectural hygiene discovered during independent review of the
accepted binding-path repair `e9c7d9ec414dbf5d0ea945bc61780e537a63e0d2`:

- Remove or relocate the dormant historical `TypedSectionCompiler` and
  `TypedSectionGenerationResult` path from
  `src/wellplot/agent/code_mode/typed_section_worker.py` after proving there
  are no required callers, exports, fixtures, or migration dependencies. Do not
  wire it into the canonical composition while it remains.
- Reconcile or archive `docs/typed-section-worker-contract.md`. Its CM-54/55
  language describes a transitional future/heterogeneous worker architecture
  and must not be mistaken for current routing authority.
- Harden `scripts/check_d5_single_engine_reachability.py` (or a companion
  check) so canon compliance can detect prohibited dormant alternate compiler
  classes/symbols inside otherwise allowed canonical modules, not only
  alternate modules/imports/entry points.
- Replace the current source-string guard for "one model-backed correction
  protocol" with an AST/call-graph or equivalently semantic invariant when the
  cleanup is undertaken, while preserving the behavioral one-call fail-closed
  regression for grounding failures.

This cleanup is deliberately **outside the current D5 critical path**. The
accepted runtime remains the shared composition root with one
`CanonicalSectionWorker` and one `RepairContract` correction protocol. Promote
this backlog item only if the dormant code becomes reachable, causes ambiguity
in active maintenance, or the current qualification work closes.

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
