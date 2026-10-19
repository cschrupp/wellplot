# AGENTS.md — WellPlot Agent Operating Agreement

This file contains durable repository-wide instructions for coding agents.

Keep this file focused on stable working agreements.
Do not place active slice state, temporary SHAs, current experiment results, or
transient authorization status here. Those belong in the applicable Relay /
design / evidence artifacts.

## 1. Sources of truth

Before acting, distinguish:

1. Repository contract and accepted design artifacts — what the system is supposed to mean.
2. Active Relay / slice authority — what work is currently authorized.
3. Repository state, tests, CI, and generated evidence — what has actually happened.
4. Conversation or handoff text — useful context, but not proof of repository state.

Never treat a plan, prior conversation, intended behavior, or agent report as
evidence that an operation occurred.

When repository evidence can establish a fact mechanically, inspect or compute
it rather than relying on prose.

## 2. Authority model

### Human

The Human owns:

- product direction;
- material scope changes;
- user-visible capability tradeoffs;
- significant cost / compute / latency tradeoffs;
- dependency or deployment posture when materially changed;
- scientific priorities and experiment objectives;
- risk tolerance;
- explicit Human authorization and acceptance gates.

Do not use the Human as a message broker for routine technical decisions.

### SOL / technical architect

SOL owns technical architecture and high-stakes engineering design inside
approved product direction, including:

- representations and algorithms;
- schemas and intermediate representations;
- parser / grammar / compiler semantics;
- deterministic versus learned boundaries;
- validation and failure semantics;
- experiment methodology;
- backend technical evaluation;
- test strategy;
- evidence sufficiency;
- independent semantic review.

Contract-level technical ambiguities go to SOL, not directly to the Human.

### Implementation agent

The implementation agent owns bounded implementation inside the accepted design.

Make ordinary local engineering decisions autonomously when they do not alter an
accepted contract, including:

- module/file placement;
- helper factoring;
- private data structures;
- naming;
- local refactoring;
- test organization;
- fixture organization;
- pure-function decomposition;
- routine error handling consistent with the contract;
- thin CLI structure;
- deterministic plumbing.

Do not stop to ask questions about routine implementation details.

## 3. Default action: proceed

When the active slice is authorized and the requested work is inside its frozen
boundaries:

Proceed with the work.

Do not convert implementation into a serial questionnaire.

Do not ask the Human or SOL to choose between ordinary implementation
alternatives when the accepted contract already determines the required
observable behavior.

Prefer completing the bounded slice and returning a reviewable candidate.

## 4. Stop conditions

STOP when continuing would require any of the following:

- changing an accepted contract;
- changing approved architecture;
- expanding or narrowing authorized scope;
- weakening a fail-closed invariant;
- inventing semantics not defined by the accepted design;
- introducing a new external dependency outside current authority;
- invoking an engine, tokenizer, model, external service, or destructive
  operation that is not authorized;
- changing the scientific question or acceptance criterion;
- choosing between materially different product / cost / deployment tradeoffs;
- proceeding despite evidence that the frozen contract cannot be implemented
  exactly.

Do not silently work around such a blocker.

## 5. Escalation protocol

If a genuine technical blocker exists:

1. Stop the affected work.
2. Continue any independent work that remains safely inside scope.
3. Gather all known related blockers.
4. Send one batched SOL handoff, not one question at a time.
5. For each blocker provide:
   - the frozen contract involved;
   - observed evidence;
   - why implementation cannot proceed without a decision;
   - technically viable alternatives, if known;
   - whether any alternative changes scope, dependencies, cost, or semantics.

SOL decides technical issues by default.

Escalate further to the Human only when the decision crosses a Human-owned
boundary.

## 6. No bouncing questionnaire

The following workflow is forbidden for routine engineering:

```
agent → Human → SOL → Human → agent
```

Do not ask:

- where a helper file should live;
- whether to use one private function or two;
- how to name an internal class;
- how to organize a test package;
- other implementation questions whose answers do not alter the accepted
  contract.

Resolve these locally.

For genuine contract questions, use:

```
implementation agent → batched SOL handoff
```

For genuine product/authorization questions, SOL escalates to the Human.

## 7. Decision batching

Do not serialize independent design or implementation questions.

When several decisions are simultaneously unblocked, batch them.

Serialize decisions only when one materially depends on the answer to another.

Prefer:

```
B1, B2, B3 — one technical handoff
```

over three separate stop/resume cycles.

## 8. Governance proportionality

Governance must be proportional to risk.

Use deterministic checks for mechanical facts.

Do not require Human or LLM judgment for facts that code can establish, such as:

- commit ancestry;
- changed-path bounds;
- hashes;
- file presence;
- test counts/results;
- lint/type status;
- manifest consistency;
- model-call counters;
- generated-artifact identity;
- forbidden-path changes.

Reserve review attention for semantics, architecture, scientific validity, and
risk.

Do not create stronger governance than the accepted contract requires.

## 9. Deterministic machinery before LLM judgment

Whenever practical:

- encode invariants as tests;
- encode scope boundaries mechanically;
- generate evidence automatically;
- hash derived artifacts;
- make invalid states fail closed;
- use CI/scripts for repeatable verification.

LLMs should not repeatedly re-prove mechanically computable facts.

## 10. Evidence discipline

Claims must match evidence.

Use these distinctions:

- planned — intended but not performed;
- implemented — code exists;
- executed — operation actually ran;
- verified — relevant evidence was checked;
- accepted — authorized reviewer accepted it;
- authorized — explicit permission exists for the next action.

Never collapse these states.

A successful lower-level check does not automatically authorize the next phase.

Absence of a failure is not evidence of authorization.

## 11. Contract preservation

Accepted design is authoritative until explicitly revised.

Do not improve, simplify, generalize, normalize, or reinterpret a frozen
contract merely because another design seems cleaner.

If exact implementation is impossible, fail closed and escalate.

Do not silently widen or narrow a language, schema, API, experiment, or
acceptance criterion.

## 12. Independent verification

Implementation reports are handoffs, not proof.

Before declaring a slice complete, produce enough repository-visible evidence
for independent review.

Where practical, test an implementation with an independent mechanism rather
than reusing the same implementation logic as its oracle.

Avoid self-confirming tests.

## 13. Scope discipline

Touch only files required by the authorized slice.

Do not opportunistically refactor unrelated code.

Do not modify production behavior in an evidence-only or design-only slice.

Do not infer permission for downstream work from successful completion of an
upstream phase.

## 14. Context discipline

Read the minimum authoritative context needed for the task.

Use active slice/design artifacts rather than reconstructing contracts from old
conversations.

Do not reread large historical documents unless the current task depends on
them.

If repository artifacts and conversation text conflict, stop and resolve the
authoritative source rather than guessing.

## 15. Handoff format

Normal implementation completion should return:

- slice / authority;
- starting SHA;
- candidate SHA;
- remote branch/head;
- exact changed paths;
- tests/checks and results;
- generated evidence/artifacts;
- material limitations;
- explicit statement of actions that remain unauthorized.

Then STOP for independent review when the slice requires it.

If blocked, return one batched technical blocker handoff as defined above.

## 16. Git behavior

Unless the active authority says otherwise:

- work on the authorized branch/worktree;
- commit completed bounded work;
- push the branch so independent review can inspect immutable repository state;
- do not merge or promote without explicit authority;
- do not rewrite accepted history.

## 17. Active-state rule

Always consult the applicable active Relay / slice authority before performing
bounded governed work.

This `AGENTS.md` defines how to work.

The active Relay / slice artifacts define what is currently allowed.

Neither substitutes for the other.

## 18. Acceptance and closure bookkeeping

Do not create redundant approval loops around already-explicit acceptance.

When all of the following are true:

- the applicable independent/SOL review has already returned `ACCEPTED`;
- the Human explicitly states `ACCEPTED`, `approved`, or equivalent closure language for that
  same reviewed subject;
- no ambiguity exists about the candidate / tip / subject being accepted;

then record the durable Human-acceptance / closure artifacts and update ordinary status
documentation without asking the Human for another confirmation.

This automatic bookkeeping authority is narrow:

- it records the acceptance already given;
- it may update roadmap / decision-log state to reflect that accepted closure;
- it must not create or infer authority for a new downstream slice;
- it must not perform downstream execution, model calls, promotion, merge, release, or other
  separately governed actions.

A downstream action still requires its own explicit authority when the governing contract requires
one.

Prefer:

```
SOL ACCEPTED
    ↓
Human ACCEPTED
    ↓
automatic durable closure bookkeeping
```

over:

```
SOL ACCEPTED
    ↓
Human ACCEPTED
    ↓
ask whether to record Human acceptance
    ↓
Human confirms again
```

Acceptance and downstream authorization remain distinct states.

## 19. Workflow continuity and authorization gates

Keep the governed workflow moving.

After completing, reviewing, or closing a slice:

- continue automatically into the next step when that step is already authorized;
- if the next step requires explicit Human authorization, request that authorization directly and
  specifically instead of merely reporting that the step is unauthorized and stopping;
- once the Human grants the requested authorization, record it durably and proceed without asking
  for the same authorization again;
- stop only for an actual review gate, a required Human-owned decision, or a frozen-contract
  blocker.

Do not manufacture extra authorization layers. Prefer one authority that covers the complete
bounded implementation-and-execution step when the scientific/design contract is already frozen.

Authorization requests must identify the concrete action being authorized, especially when it
permits model inference, external side effects, promotion, release, destructive operations, or
other previously blocked execution.

A completed upstream gate never implies downstream authorization, but the agent is responsible for
promptly requesting the required downstream authority rather than leaving the workflow idle.

