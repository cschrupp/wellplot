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

## Per-Turn Scope Drift Check

Before **every agent turn** that plans, implements, reviews, tests, or authorizes governed
work, compare the proposed action against the currently accepted active slice.
Use repository-owned active authority, design, and baseline artifacts, not chat
memory or the latest implementation suggestion. Establish:

1. **Objective:** the active slice's concrete product or technical goal.
2. **Exit criteria:** the smallest observable outcome or evidence that closes it.
3. **Scope firewall:** what the slice authorizes and forbids, especially the one
   canonical semantic engine and authoring workflow. Do not add a second
   semantic engine, shadow scorer that claims host authority, independent
   orchestrator, fallback workflow, or parallel path, even if evaluation-only
   or only partly implemented. A separately authorized mode that genuinely
   reuses an accepted canonical harness is not a second engine by itself.
4. **Next gate:** the next authorized action and whether provider/model calls,
   benchmark/holdout use, mutation, deployment, or other live work are permitted.
5. **Necessity:** whether the proposed change resolves a demonstrated present
   blocker or merely builds infrastructure for a hypothetical future question.

If an action fails this check, **do not expand the slice to accommodate it**.
Keep or recover the canonical path, retire redundant partial paths rather than
leave dormant alternatives, and defer speculative scoring, harness, governance,
or acceptance machinery. Report the concrete scope conflict at the existing
handoff boundary; escalate only if resolving it changes an accepted contract
or needs Human authority.

If aligned, proceed within existing authority without asking for another
approval. Record `DRIFT_CHECK: PASS` or `DRIFT_CHECK: FAIL` and the active slice
objective in material handoffs. Keep routine checks brief; this check creates
**no new approval gate, workflow, ledger, score, or independent review cycle**.

This adapts Seneca's outcome-first / progressive-qualification and
no-recursive-governance rules to WellPlot. It does not override the standing
Project Decision Protocol, frozen evidence, or separate live-authority gates.

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

Before contacting a configured LAN inference endpoint, request approval for
LAN execution through the tool's sandbox escalation mechanism (for Codex,
`sandbox_permissions: "require_escalated"`). Use approved LAN execution for
both non-generative readiness requests and any separately authorized live
smoke or campaign invocation. An approved readiness probe does not establish
LAN access for a later runner launched in the default sandbox. If approval
is unavailable or denied, stop before contacting the endpoint.

All D5 live campaign launches must use the version-controlled
`scripts/run_d5_live_campaign.sh` launcher from the canonical checkout. Invoke
it with `preflight` for the existing provider-free preflight or `execute` for
the separately authorized live run, followed by the population and quoted
authorization descriptor path. The `execute` invocation itself must run with
approved LAN execution; do not run readiness under escalation and then launch
the campaign in the default sandbox. The launcher owns only canonical cwd,
Python/module invocation, quoting, the standard watchdog, and exit propagation.
Credential loading, readiness, provider construction, validation, accounting,
and custody remain in the canonical campaign runner. Do not invoke that runner
directly or create ad hoc shell wrappers, scripts, or commands for campaigns.

Separate smoke authority and evidence namespace through the canonical live
harness; do not create a separate live smoke harness or parallel execution
path. Smoke mode must stop before the canonical scientific campaign runner
consumes the frozen population.

Sandbox denial, LAN/DNS/routing restrictions, credential isolation, filesystem
restrictions, provider-construction failure, or harness-initialization failure
are environment/harness evidence, not model or scientific evidence.

The complete gate, authority-consumption rules, and failure classification are
defined in `docs/project-decision-protocol.md`.

## Canonical Live Runtime

For the current WellPlot host, live and evidence-bearing execution has one
persistent canonical repository/runtime root:

```text
/home/user/projects/well_log_os
```

Any credential-bearing endpoint check, provider-backed smoke, scientific or
benchmark campaign, or durable campaign-custody operation must run from that
canonical checkout. Before consuming live authority, both the resolved working
directory and Git top-level must identify that path.

Disposable clones and worktrees, including `/tmp/...`, are implementation-
and review-only. They must not be used for live qualification, credentials,
local scientific assets, or durable evidence. Do not copy or symlink
`LLAMA_CPP_API_KEY.txt` into a temporary worktree to make live execution
work.

The machine-local credential source for the current host remains
`/home/user/projects/well_log_os/LLAMA_CPP_API_KEY.txt`; never print or commit
its contents. Canonical non-secret provider/runtime settings remain exclusively
in `config/wellplot.yaml`. Do not create another config layer, provider path,
semantic engine, live-smoke harness, or evaluation-only authoring engine to
work around execution-root problems.

A temporary/secondary worktree is permitted only for a real simultaneous-
checkout implementation or review need, and must hand off any later live work
back to the canonical persistent checkout.

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

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:46cd31e7 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   bd dolt push
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->
