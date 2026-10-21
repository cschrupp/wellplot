# WellPlot Project Decision Protocol

This protocol is a standing project-governance rule for humans, Codex, and
other autonomous or agentic contributors.

At every material architectural, implementation, evaluation, or remediation
decision point, WellPlot must check both the current project scope and relevant
external evidence before committing to a direction.

## Purpose

WellPlot should make consequential decisions using:

```text
project scope
+
established external knowledge
+
comparable-system evidence
+
bounded WellPlot-specific validation
```

rather than:

```text
ad-hoc invention
+
open-ended experimental search
```

The objective is not merely to make a current test pass. It is to build
WellPlot using the strongest available combination of established knowledge,
analogous systems, domain requirements, and reproducible local evidence.

## A. Scope Check

Before every material architectural, implementation, remediation, or evaluation
decision, review the relevant:

- project scope,
- current architecture,
- accepted contracts,
- previous decisions,
- active slice objective,
- ownership boundaries between components.

Explicitly answer:

- What problem are we solving?
- Is it actually part of the agreed WellPlot scope?
- Is the proposed change necessary?
- Does the concern already belong to another deterministic layer?
- Are we accidentally solving a broader or different problem?
- Does this duplicate existing functionality?
- Does this invalidate an earlier accepted architectural decision?
- Is additional complexity justified?

A local test failure or experimental observation must not silently redefine
project scope.

If the proposed solution requires an architecture or scope change, identify
that explicitly as a separate decision.

## B. External Evidence Check

Before inventing a solution, investigate how the same or analogous problem is
handled externally.

Prioritize evidence in this order:

1. Official documentation and reference implementations.
2. Mature open-source projects solving comparable problems.
3. Peer-reviewed papers and strong preprints.
4. Established software-engineering patterns and standards.
5. Benchmarks and reproducibility studies.
6. Relevant upstream issues, bug reports, and postmortems.
7. Community practices only when stronger sources are unavailable.

Prefer primary sources.

For software dependencies, confirm that sources apply to the actual
version/build WellPlot uses.

## C. Comparable-System Check

Do not search only for exact WellPlot terminology.

Look for analogous systems such as:

- natural-language-to-program systems,
- semantic planners,
- agentic coding systems,
- constrained generation,
- structured-output systems,
- compilers and intermediate representations,
- visualization specification languages,
- document-authoring agents,
- deterministic validation/safety architectures,
- geological/petrophysical interpretation software when relevant.

Explicitly state which analogy applies and where it stops applying.

## D. Evidence Classification

Every significant decision should classify its evidence basis as one of:

```text
ESTABLISHED
Supported directly by mature implementations, documentation,
research, or broadly accepted engineering practice.

ADAPTED
Established technique adapted to WellPlot.

EMPIRICALLY_SUPPORTED
Not strongly established externally, but supported by bounded
WellPlot evidence.

NOVEL
A WellPlot-specific design for which strong precedent was not found.
```

Novel decisions are allowed.

They must not be described as established best practice.

## E. Novel Decision Rule

Before accepting a `NOVEL` solution, document:

- why established approaches are insufficient,
- alternatives considered,
- expected benefit,
- additional complexity,
- likely failure modes,
- reversibility,
- validation method,
- evidence that would cause the design to be abandoned.

Prefer reversible experiments before irreversible architecture.

## F. Decision Record

For consequential decisions, create a concise decision record using this
structure:

```text
DECISION:
<what was decided>

PROJECT SCOPE:
<relevant WellPlot objective/constraint>

EXTERNAL EVIDENCE:
<key papers/projects/docs/issues consulted>

ESTABLISHED PRACTICE:
<what comparable systems normally do>

WELLPLOT DIFFERENCE:
<why our system is the same or different>

OPTIONS CONSIDERED:
<A / B / C>

SELECTED APPROACH:
<choice>

EVIDENCE CLASS:
ESTABLISHED / ADAPTED / EMPIRICALLY_SUPPORTED / NOVEL

RISKS:
<bounded list>

REVERSIBLE:
YES / NO

VALIDATION:
<how the decision will be tested>

STOP / REVISIT CONDITION:
<what evidence would invalidate it>
```

Small decisions may use a shortened version.

Major architecture decisions should use the complete version.

## G. Research Before Architecture

For architectural decisions, follow:

```text
scope review
→ external research
→ comparable-system analysis
→ alternatives
→ explicit decision
→ implementation
→ bounded qualification
```

Do not follow:

```text
implementation
→ repeated failure
→ experiments
→ more experiments
→ search for justification afterward
```

## H. Experiments Are Not a Substitute for Existing Knowledge

Before authorizing an experiment, ask:

> Can this question be answered more reliably from source code, documentation,
> a paper, a benchmark, or a mature implementation?

If yes, investigate that first.

Experiments should answer **WellPlot-specific uncertainty**, not rediscover
established external knowledge.

## I. Finite Experiment Rule

Every experiment must have:

- a specific question,
- a bounded population,
- predetermined outcomes,
- predetermined acceptance criteria,
- maximum call/runtime budget,
- a terminal decision.

Do not create an indefinite chain where every experiment automatically
authorizes another experiment.

If repeated experiments stop producing decision-changing information, escalate
to an architectural review.

## J. Contradictory External Evidence

If external evidence contradicts current WellPlot design, explicitly record:

```text
current WellPlot assumption
external evidence
applicability
consequence if correct
```

Then explicitly choose one of:

```text
KEEP
ADAPT
REPLACE
INVESTIGATE
```

Do not silently ignore contradictory evidence.

## K. Version Relevance

For dependencies including, but not limited to:

- llama.cpp,
- Pydantic,
- OpenAI-compatible APIs,
- Docling,
- Qdrant,
- Python,
- Plotly,
- Bokeh,

verify:

```text
WellPlot version/build
versus
source/documentation version
```

Do not rely only on generic or current documentation if WellPlot uses another
build/version.

## L. Autonomous Codex / Agent Rule

Autonomous agents may research external sources within an already authorized
decision scope.

They may not use external research as justification to silently expand project
scope.

If evidence suggests a major architecture change outside the authorized task:

```text
document finding
document proposed alternative
stop that branch of implementation
continue only with separately authorized work
```

Do not autonomously redesign WellPlot.

## M. Independent Review Separation

For consequential handovers, separate:

```text
FACTS FROM WELLPLOT EVIDENCE

FACTS FROM EXTERNAL SOURCES

ENGINEERING INFERENCES

NOVEL WELLPLOT DESIGN CHOICES
```

This should make the rationale auditable later.

## N. Standing Principle

WellPlot should prefer known good engineering, domain-specific adaptation, and
bounded empirical validation over ad-hoc invention and unbounded
experimentation.

## O. Active Knowledge Lifecycle

Historical evidence and current project authority are separate concerns. A
result may be strong evidence without yet being an active project constraint.
WellPlot therefore tracks two independent dimensions.

### Evidence strength

Use one of:

```text
ESTABLISHED
ADAPTED
EMPIRICALLY_SUPPORTED
NOVEL
```

### Project knowledge status

Use one of:

```text
SETTLED_ARCHITECTURAL_INVARIANT
IMPLEMENTATION_REQUIREMENT
REGRESSION_REQUIREMENT
CONDITIONAL_TECHNIQUE
GENUINELY_OPEN_QUESTION
SUPERSEDED_DO_NOT_REPEAT
```

Evidence strength describes why a claim is credible. Project knowledge status
describes how the claim governs current work. They must not be conflated.

### Active baseline and promotion

Each substantial evolving architecture or domain with durable experimental
knowledge must have a concise repository-owned Current Active Baseline. It is
decision memory, not an experiment archive. Historical records remain
immutable evidence and are linked from the baseline for provenance.

An independently accepted, decision-bearing result is not fully closed until
its Knowledge Delta has been incorporated into the relevant active baseline:

```text
Promoted:
Changed:
Superseded:
New open questions:
No-change findings:
Required baseline/regression updates:
```

The next dependent design or experiment must not begin while applicable,
accepted decision-bearing knowledge is absent from the active baseline.
Repeated experiments caused by missing or stale project memory are a
methodology failure: pause experimental progression, repair the active
knowledge, then resume technical work.

### Non-rediscovery preflight

Before authorizing a new experiment, record:

- the applicable current-baseline constraints;
- the exact genuinely open question;
- why source, documentation, current baseline, and prior evidence do not
  already answer it;
- the exact new controlled variable;
- the settled findings inherited unchanged; and
- which possible outcomes would change a project decision.

If accepted prior knowledge already answers the question, do not run the
experiment.

### Reopening settled knowledge

A settled item may be reopened only when concrete contradictory evidence is
documented, its applicability is assessed, and an explicit architecture
review chooses `KEEP`, `ADAPT`, `REPLACE`, or `REOPEN`. A new experiment proposal
cannot silently turn a settled item into an open question.

When settled knowledge is mechanically testable, promote it to a regression or
invariant test. If it is not reasonably testable, record why in the decision
record.

### Authority and bootstrap order

For project engineering knowledge, the default authority order is:

```text
repository standing rules
→ current active baseline
→ current accepted architecture/design decisions
→ implementation contracts and regression tests
→ historical reconciliation
→ experimental/development archives
→ conversation/chat memory
```

An explicit later supersession overrides an earlier document. Chat memory is
useful context but is non-authoritative.

For agent and architecture work, bootstrap in this order:

```text
AGENTS.md
→ relevant Current Active Baseline
→ active slice/design
→ source and contracts relevant to the task
```

Consult historical archives for provenance, contradiction investigation, or
genuinely unresolved questions, not as the normal first source of current
project decisions. Keep active baselines concise: retain the finding, status,
applicability boundary, provenance, implementation/regression consequence, and
reopening condition rather than copying raw traces or chronology.
