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

## Live Execution Safety Gate

No agent may consume an irreversible live, scientific, benchmark, or one-shot
campaign authority until all of the following have independently passed:

1. static/provider-free qualification of the exact executable and frozen inputs;
2. execution-environment qualification proving that the actual runtime is
   explicitly permitted and able to reach every required LAN/network endpoint,
   credential source, filesystem location, subprocess/runtime facility, and
   other external resource;
3. non-generative readiness/identity checks;
4. a separate live smoke, under its own authority and fresh non-scientific
   namespace, that exercises the real provider/harness path through the minimum
   bounded live operation needed to establish provider construction, request
   serialization, structured-output handling, custody, accounting, and orderly
   termination; and
5. independent acceptance of that smoke before scientific authority is issued.

`STARTED` must never be the first point at which the project discovers whether
the real execution environment, LAN access, provider construction,
structured-output path, or live harness works.

Project authorization to use an endpoint does not establish sandbox, LAN, DNS,
credential, filesystem, subprocess, or runtime permission. A smoke authority
and a scientific campaign authority are separate and non-transferable. A
failed or inconclusive smoke does not authorize or consume a scientific
campaign. Scientific campaigns use fresh namespaces and must not be used for
infrastructure discovery.

Separate smoke authority and evidence namespace through the canonical live
harness; do not create a separate live smoke harness or parallel execution
path. Smoke mode must stop before the canonical scientific campaign runner
consumes the frozen population.

Sandbox denial, LAN/DNS/routing restrictions, credential isolation, filesystem
restrictions, provider-construction failure, or harness-initialization failure
are environment/harness evidence, not model or scientific evidence.

The complete gate, authority-consumption rules, and failure classification are
defined in `docs/project-decision-protocol.md`.

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
