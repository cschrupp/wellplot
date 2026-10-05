# NLP D1 Existing-Curve Scale Revision

D1 proves one complete revision through the notebook-facing natural-language
path. It deliberately uses deterministic planner and worker backends in tests;
it does not qualify a live model or change the provider route.

## Frozen Scope

- Starting checkpoint: `94d66380b463b70f81b1266b9439f655dbdf6a43`
- Public API: `DirectNotebookSession.revise(...)`
- Request: `Change the Gamma Ray curve scale to a linear scale from 10 to 100.`
- Existing target: the grounded `GR` curve binding in the fixture's existing
  normal track
- Before scale: `0` to `100`, linear
- After scale: `10` to `100`, linear

The revision worker receives a bounded inventory of exact existing track and
curve identities. The host selects no scientific target by fuzzy matching. The
program must select the grounded track and curve handles before updating the
scale, and canonical reconciliation still receives deterministic inspected
source-channel candidates. Missing source files leave channel context absent;
the existing `channel_context_missing` safety check remains fail-closed.

## Acceptance Evidence

The positive integration case enters through `revise`, persists and reloads the
document, renders a non-empty PDF, and passes the frozen D0 verifier:

```text
LAS-01 PASS
LAS-05 PASS
LAS-07 PASS
LAS-09 PASS
```

The integrated no-op case starts with the requested minimum already satisfied.
It leaves the document unchanged and the verifier reports `LAS-05 FAIL`, so a
no-op cannot be credited as an exercised scale transition. Invented track or
binding identities fail without mutation. Construction-oriented worker tests
remain green.

## Verification

```text
Focused D1 and existing worker/enrichment tests: 52 passed
Adjacent D0/notebook/facade/session/context/reconciler tests:
  103 passed, 1 known baseline failure
Ruff check: PASS
Ruff format: PASS
Compilation: PASS
git diff --check: PASS
Provider calls: 0
Endpoint calls: 0
Real model calls: 0
```

The adjacent baseline failure is
`test_project_session_uses_example_seed_and_declared_sources_only`; it
reproduces at the D0 checkpoint because the isolated checkout lacks the
fixture-referenced `workspace/data/30-23a-3 8117_d.las` asset.

The full repository run remains a diagnostic result rather than a D1 gate:
`2521 passed, 35 failed, 10 skipped, 11 subtests passed`. The failures include
the known repository/evidence-artifact baseline and historical tests asserting
that production files remain unchanged relative to earlier research
checkpoints. No provider or endpoint activity occurred.

## Boundaries

No canonical schema, renderer, persistence, source-loader semantics, planner
architecture, V2R route, CBL behavior, or live provider path was changed.
D2 ambiguity handling and D3/D4 work remain unauthorized.
