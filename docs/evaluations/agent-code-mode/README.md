# Agent Code Mode Evaluation Evidence

This directory records reproducible evidence for the migration from the v1
structured graph to Code Mode v2. It is not a location for provider anecdotes
or mutable notebook output.

## Evidence Categories

Every result must identify exactly one category:

- **Structural:** source-tree measurements and public-surface inventories made
  from a named commit.
- **Deterministic:** commands and fixtures that complete without a live model.
- **Live reproducible:** a named provider/model/configuration/request can be
  rerun with a trace and canonical verifier result.
- **Historical observational:** useful diagnostic material that cannot be
  reproduced from the frozen commit. It is never release-baseline evidence.
- **Not available:** evidence has not been captured. Use `not_run`,
  `not_available`, or `not_reproducible_at_CM-00`; never infer a result.

## Files

- `CM-00-baseline.json` is the machine-readable frozen structural and evidence
  manifest.
- `CM-00-baseline.md` records the CM-00 scope decision and repeatable capture
  commands.
- `CM-00-development-memory.md` records the decisions, evidence, and explicit
  deferrals made while completing CM-00.
- `CM-02-reachability.json` is the deterministic static import inventory used
  to distinguish current reachability from planned migration disposition.
- `CM-03-development-memory.md` records the dual-engine evaluation contract:
  task-level engine labels, explicit unavailable metrics, the v2
  `not_implemented` evidence path, and incremental v1/v2 comparisons.
- `CM-10-development-memory.md` records the pure Authoring Program source,
  diagnostic, artifact, result, metric, and semantic-error contracts.
- `SCORECARD_TEMPLATE.md` defines the required fields for each later slice.

Evidence names use the migration slice identifier. A record is immutable once
committed; a later capture receives a new file rather than editing historical
results.

## Development Memory

Every completed Code Mode migration slice must add a committed
`CM-XX-development-memory.md` file in this directory. The memory is a concise
maintainer handoff, not a replacement for the machine-readable scorecard. It
must record:

- the committed slice scope and explicit non-goals;
- decisions and invariants established by the slice;
- validation commands and their outcomes, including known baseline failures;
- live-provider observations only when clearly labelled as reproducible or
  historical; and
- deferred work and the narrow authorization for the next slice.

The slice memory is written before the slice commit and pushed with its
evidence. Do not rewrite a historical memory after it is committed; add a new
memory record when later evidence supersedes an earlier decision.
