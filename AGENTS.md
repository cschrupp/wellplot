# Repository Rules

## Project Decision Protocol

All agents working in this repository must read and follow
`docs/project-decision-protocol.md` before making material architectural,
implementation, evaluation, or remediation decisions.

Operational requirements:

- perform scope and external-evidence checks at material decision points;
- prefer primary sources and mature comparable implementations;
- do not experimentally rediscover established behavior when
  documentation/source/research can answer it;
- classify consequential decisions as `ESTABLISHED`, `ADAPTED`,
  `EMPIRICALLY_SUPPORTED`, or `NOVEL`;
- experiments must be finite and pre-bounded;
- autonomous agents may not silently expand project scope;
- major architecture changes require an explicit decision record and
  independent review.

The complete policy is in `docs/project-decision-protocol.md`.

## Active Knowledge Lifecycle

Before agent, architecture, implementation, or experiment work:

- read the relevant repository-owned Current Active Baseline after this file
  (`docs/agent-code-mode-current-baseline.md` for agent/Code-Mode work);
- perform the protocol's experiment non-rediscovery preflight before proposing
  or running an experiment;
- honor `SETTLED_ARCHITECTURAL_INVARIANT`, `IMPLEMENTATION_REQUIREMENT`, and
  `REGRESSION_REQUIREMENT` findings unless they are formally reopened through
  documented contradictory evidence and architecture review; and
- after accepted decision-bearing work, complete and incorporate a Knowledge
  Delta before starting a dependent slice.

Historical experiment files are evidence and provenance, not the normal
bootstrap source for current engineering decisions. Chat or agent memory is
non-authoritative. When a settled finding is mechanically testable, preserve
it with a regression or invariant check; otherwise record why it cannot be
tested mechanically.

## MCP Stabilization

During MCP stabilization, no runtime workaround may be added merely because a
provider emitted an unexpected tool call. First inspect the advertised MCP
schema. If the call is permitted or ambiguous under that schema, fix the
schema. A new regex intent heuristic, argument normalizer, fallback executor,
stage controller, or provider-specific branch requires a committed failing
live evaluation and must replace or delete equivalent complexity elsewhere.

## Operational Debt

Non-blocking operational debt belongs in `docs/backlog.md` and must not
interrupt an active scientific or architectural slice unless it becomes a
demonstrated blocker. Absence from Git or GitHub does not prove that an
intentionally local asset is missing; only a filesystem check establishes
local-file absence. Default to the existing canonical checkout and do not
create a new clone or worktree merely because a new slice or branch begins.
Independent SHA review does not require a second checkout; extra worktrees
require a real simultaneous-checkout need.
