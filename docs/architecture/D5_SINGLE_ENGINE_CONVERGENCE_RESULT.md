# D5-2 Single-Engine Convergence Result

Status: `D5-2R2 IMPLEMENTED / READY FOR INDEPENDENT REVIEW`

Branch: `d5/single-engine-convergence`

Starting checkpoint: `c89525f65ea584d071a02c8c3be7146f08ed5679`

## Decision Boundary

D5-2R2 closes the single-engine repository boundary. It does not perform live
inference, change the provider/model configuration, or authorize D5-3.

The only supported authoring route is:

```text
public adapter
  -> shared composition root
  -> SemanticPlanner
  -> deterministic SemanticEnricher / source inspection
  -> canonical report or section semantic worker
  -> deterministic semantic lowering
  -> AuthoringDocumentIntent
  -> reconcile_authoring()
  -> AuthoringExecutor
  -> AuthoringService
  -> persistence / reload / render
```

Direct Notebook and MCP construct the same canonical dependency graph through
`wellplot.agent.composition`. Structured provider output is decoded and
validated at the canonical worker boundary; no plain-program worker or second
semantic compiler is available.

## Repository Closure

The D5 manifest is an independently derived AST import closure from the
canonical runtime entry points in:

```text
src/wellplot/__init__.py
src/wellplot/agent/__init__.py
src/wellplot/agent/direct_notebook.py
src/wellplot/agent/notebook.py
src/wellplot/mcp/agentic.py
src/wellplot/mcp/agentic_server.py
```

It is emitted by `scripts/d5_single_engine_attestation.py` as manifest
version `wellplot.d5.single-engine-production.v2` and checked against
`docs/architecture/D5_SINGLE_ENGINE_PRODUCTION_MANIFEST.json`.
The manifest contains the canonical production closure, including the
composition root, canonical workers, typed section worker, semantic lowering,
reconciliation, execution, persistence, MCP adapters, models, and rendering.
It no longer inherits the historical D4 component tuple.

The following executable source families were physically removed from
`src/wellplot` because they have no canonical callers:

- legacy `AuthoringSession` and stable-fallback authoring engine;
- legacy graph engine and program/report workers;
- typed-delivery and Semantic-IR V2/V2R compilers;
- visual-specific correction compiler;
- legacy OpenAI/program-provider adapters;
- standalone authoring-program parser, interpreter, runtime, and validator.

The retained `authoring_program` modules are only the deterministic identity
and intent-building substrate used by canonical lowering; the deleted parser,
interpreter, runtime, and validator were the independent executable engine.
Historical D4 manifests, fixtures, and evaluation records remain in Git
history/evidence; they are not used as the D5 production attestation.

The provider-free audit in
`scripts/check_d5_single_engine_reachability.py` verifies that the retired
source paths are absent, the required canonical components are present, the
canonical entry points can be imported and constructed, and no retired module
is loaded. It also checks that routing exposes only the canonical engine.

## Canonical Contracts

Section work uses a strict discriminated action union:

```text
reconstruct
update_curve_scale
add_track
add_fill
```

Existing objects are selected with request-local handles. Canonical document,
track, and binding identities remain host-owned. Source candidates and exact
channel kinds are validated before lowering.

Report work uses sparse `ReportSemanticResponse` data and lowers directly to
`AuthoringDocumentIntent`. No report-program compiler or executable program
is involved.

## Provider-Free Evidence

The replacement regression coverage exercises the canonical worker boundary
for report title revision, existing-curve scale revision, grounded track and
curve creation, grounded fill creation, missing-channel rejection, and the
real generated CBL artifact verifier. The first exact nine-turn rehearsal
exposed deferred in-memory Matplotlib figure cleanup and a stale deterministic
CBL report fixture. The bounded correction closes non-selected preview figures
as they are created and aligns the fixture with the already-frozen CBL-01
header contract. No renderer backend, semantic contract, fixture population,
or gold value was changed.

The corrected exact nine-turn rehearsal completed through the canonical route
with zero provider/endpoint/model calls: `9/9 PASS`, including real
persistence, reload, rendering, and CBL-01 through CBL-09 verification. The
observed run completed in 264.97 seconds and recorded the frozen 18 logical
structured calls.

The D4 harness remains historical evidence. Its attestation is mechanically
checked against the successor D5 manifest for this provider-free validation;
the D5 manifest itself is the active production integrity boundary.

## Validation

Provider, endpoint, and model calls: `0`.

Required validation for this checkpoint:

- canonical regression, D5 convergence, and D4R1 integration tests;
- exact provider-free nine-turn D4 rehearsal (`9/9 PASS`, 18 logical calls);
- D3 CBL and canonical semantic/revision/report tests;
- Direct Notebook and MCP composition tests;
- repository-wide runtime reachability audit;
- successor production attestation;
- Ruff, formatting, compilation, and `git diff --check`.

The final handoff records the observed test totals and the renderer/resource
failure separately from historical baseline failures. No live D4/D5 activity
is authorized by this result.

## Governance State

```yaml
D5-2R2:
  status: IMPLEMENTED / READY FOR INDEPENDENT REVIEW
  canonical_engine: FROZEN_FOR_REVIEW
  legacy_v1_engine_reachable: false
  stable_fallback_reachable: false
  visual_alternate_compiler_reachable: false
  program_workers_reachable: false
  semantic_ir_compilers_reachable: false
  successor_production_attestation: PASS
  provider_free_nine_turn_rehearsal: 9/9 PASS
  provider_model_calls: 0
  d5-3: NOT AUTHORIZED
```
