# Deferred Work

These operational items are outside the active D5-5H semantic-contract
closeout. They must not interrupt an active scientific or architectural slice
unless new evidence makes one a demonstrated blocker.

## Local-Asset Registry / Preflight

Maintain a registry of intentionally local LAS/DLIS assets with expected
relative paths, sizes, and SHA-256 values. Distinguish `NOT_TRACKED`,
`LOCAL_UNVERIFIED`, `MISSING`, and `VERIFIED`. Consider an optional
`scripts/check_local_assets.py` helper.

## Local Checkout / Worktree Simplification

Default to one canonical checkout. A new branch does not imply a new worktree,
and independent SHA review does not imply a second checkout. Use additional
worktrees only for genuinely simultaneous checkout needs and prune obsolete
folders after branch/SHA reachability is proven.

## Shared Local-Asset Provisioning

Consider one permanent local asset root with links into exceptional worktrees;
never commit the scientific asset bytes.

## Mainline Integration / Promotion

After D5 closure, inspect and integrate the main-only MCP launcher change in a
dedicated promotion review. Do not rebase the accepted development lineage
merely for topology tidiness.

## Filesystem Cleanup

Inventory stale clones and worktrees, then remove only after branch and commit
reachability is proven. This is not on the current D5 critical path.
