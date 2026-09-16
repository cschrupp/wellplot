# CM-53R2 Development Memory

## Scope

CM-53R2 hardens the accepted CM-53 default-v2 route without changing routing,
provider adapters, graph topology, or the worker repair budget. It closes the
remaining prompt-grounding and bounded-planner-recovery gaps identified by the
post-CM-53R review.

- **Slice base SHA:** `7aa36d3`
- **Implementation commit:** `8ccbdf2` (`Harden CM-53R2 planner and enrichment`)
- **Production delta:** `+121 / -41` across planner, enrichment, worker,
  workflow, and facade modules
- **Test delta:** `+165 / -3` across the four focused Code Mode test modules
- **Runtime behavior delta:** planner recovery remains capped at two structured
  calls; reconstruction may downgrade only an unresolved advisory section hint
  to a new section and records a bounded warning

## Source Grounding

The section SDK reference now treats host-approved source handles neutrally:

```text
0 candidates       no wp.source(...) example and no source= argument
1 candidate        exact opaque candidate ID and source=source_1 example
N candidates       all exact opaque IDs, no source=source_N preference
```

The generic multi-candidate section example is intentionally source-free. The
worker and its CM-34 repair prompt still receive the same bounded reference,
while canonical paths and source metadata remain excluded from provider text.

## Hint Resolution

Semantic enrichment is now mode-aware:

```text
reconstruct
  exact/unique match       existing target
  unique containment match existing target
  unresolved hint          new target plus warning
  ambiguous hint           fail closed

revise
  exact/unique match       existing target
  unique containment match existing target
  unresolved hint          fail closed
  ambiguous hint           fail closed
```

The reconstruction downgrade emits only the fixed safe diagnostic
`enrichment.section_hint_unresolved_downgraded` with warning severity. It does
not expose the hint text, canonical section identity, source path, or document
structure. The warning travels in the transient enriched context and is
projected by the internal facade on successful and failed worker outcomes.

## Planner Call Budget

Planner recovery is one global two-call state machine:

```text
valid first plan                         1 structured call
first INVALID_RESPONSE -> valid plan    2 structured calls
first INVALID_RESPONSE -> invalid plan  2 calls, PlannerSemanticFailure
two INVALID_RESPONSE failures            2 calls, ProviderRequestError
semantic invalid -> valid correction     2 structured calls
semantic invalid -> invalid correction   2 calls, PlannerSemanticFailure
semantic invalid -> provider failure     2 calls, ProviderRequestError
other first provider failure             1 call, no retry
unexpected programming exception         propagates
```

Only `ProviderFailureCategory.INVALID_RESPONSE` receives the planner-level
structured-output retry. Provider retryability does not broaden this rule, and
there is no third planner call.

Semantic correction preserves the bounded summary, goals, capability IDs,
requirements, and constraints. It continues to omit source hints, existing
section hints, canonical identities, source paths, enriched channel context,
graph state, and provider response text. Path-shaped prose is redacted before
it enters the correction prompt.

## Validation

- CM-53R2 focused suite: `80 passed`.
- Ruff check: passed.
- Ruff format check: passed.
- `git diff --check`: passed.
- CM-43 deterministic tests remain included in the broader evaluation suite.
- No live CM-53 transition rows were written by this slice.

## Default-Route Probe

After deterministic validation, three exploratory calls used the frozen CBL
request with `engine` omitted and the required NVIDIA settings. All three
reached the v2 public route; none failed in planner structured-output recovery
or unresolved-hint handling. They nevertheless ended before common acceptance
with bounded worker/provider/dry-run failures, so this probe is not CM-43R2
acceptance evidence and the existing JSONL was intentionally left unchanged.

The result is useful boundary evidence: CM-53R2 removed the earlier planner
and enrichment stop points, but it did not claim to solve provider-generated
section correctness or broaden the acceptance contract.

## Decision

```text
CM-53 routing implementation       accepted
CM-53R robustness implementation   complete (`8ccbdf2`)
default v2 selection               accepted
automatic fallback                 0
planner third attempt              0
worker repair budget               unchanged
CM-53 transition closure           pending unchanged live gate
CM-60+                             blocked
```

**PROCEED / STOP:** Proceed to rerun the unchanged CM-43R2 NVIDIA cases through
the public default route with `engine` omitted. Stop CM-53 closure until the
live acceptance succeeds; do not weaken the common acceptance contract.
