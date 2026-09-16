# CM-53R Development Memory

## Scope

CM-53R hardens the accepted CM-53 default-v2 route without changing routing.
It addresses provider-produced semantic plans that are structurally valid but
semantically invalid, and removes the worker's fake source candidate example.

- **Slice base SHA:** `1455d3e`
- **Implementation commit:** `55272d8` (`Harden Code Mode planner and worker prompts`)
- **Production delta:** `+202 / -34` across `planner.py`, `program_worker.py`,
  and `facade.py`
- **Test delta:** `+292 / -11` across the three focused Code Mode test modules
- **Runtime behavior delta:** one semantic planner correction is allowed after
  a structurally valid semantic validation failure; worker and repair prompts
  receive only exact host-issued source candidate IDs

## Worker Grounding

The executable section SDK reference is now generated from the bounded
`ResolvedSectionContext`:

```text
0 candidates       no wp.source(...) example and no source= argument
1 candidate        exactly that opaque candidate ID
N candidates       only those exact opaque candidate IDs
```

Canonical paths, root identifiers, and source metadata remain excluded. The
same generated reference is supplied to the initial worker prompt and the
existing CM-34 repair coordinator. No additional worker repair loop was added.

## Planner Correction Contract

Only the four explicit provider-semantic validation branches produce the new
typed `PlannerSemanticError` categories:

```text
unknown_capability
noncanonical_capability
wrong_task_category
missing_section_capability
```

The planner budget is fixed:

```text
valid first plan                    1 structured call
semantic invalid -> valid           2 structured calls
semantic invalid -> invalid         2 structured calls, bounded failure
ProviderRequestError                1 call, no correction
unexpected exception                propagates
```

The correction context contains only the mode, static capability catalogue,
capability selections from the previous plan, and a bounded diagnostic. It does
not add graph state, canonical identities, enriched source context, or program
source.

## Facade Boundary

`CodeModeCompileFacade` catches only the final typed planner semantic failure
and projects it as a safe `planner.<category>` diagnostic with zero workers and
no intent. Generic graph/programming exceptions remain exceptions. Routing,
engine selection, workflow topology, providers, MCP, persistence, rendering,
source discovery, capabilities, and legacy code are unchanged.

## Validation

- CM-53R focused suite: `68 passed`.
- Adjacent Code Mode/routing/architecture selection: `120 passed, 1 warning`.
- Ruff check: passed.
- Ruff format check: passed.
- `git diff --check`: passed.
- CM-43 deterministic acceptance tests remain included and passing.

The earlier three default-route live retries remain invalid transition
evidence: they reached v2 with the required NVIDIA fingerprint but failed
before common CBL acceptance. No live evidence rows were written.

## Decision

```text
CM-53 routing implementation       accepted
CM-53R robustness implementation   complete (`55272d8`)
default v2 selection               accepted
automatic fallback                 0
planner third attempt              0
worker fake source ID              0
CM-53 transition closure           pending unchanged live gate
CM-60+                             blocked
```

**PROCEED / STOP:** Proceed to rerun the unchanged CM-43R2 NVIDIA live cases
through the public default route with `engine` omitted. Stop CM-53 closure
until that live acceptance succeeds; do not weaken the common acceptance
contract.
