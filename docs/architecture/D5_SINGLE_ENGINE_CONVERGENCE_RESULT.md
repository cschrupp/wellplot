# D5-2 Single-Engine Convergence Result

Status: `D5-2R1 IMPLEMENTED / INDEPENDENT REVIEW PENDING`

Branch: `d5/single-engine-convergence`

Starting checkpoint: `ed4d8e9b13f2b76e953bf7645c1f0dcef966d2f8`

## Decision Boundary

D5-2 implements one provider-neutral semantic engine for the canonical
Direct Notebook, MCP agentic, and provider-free experiment compositions. It
does not perform live inference, change the provider/model configuration, or
rebaseline the frozen D4 live authorization.

The canonical route is:

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

Direct Notebook and MCP now construct their worker dependencies through
`wellplot.agent.composition`. The D4 provider-free experiment harness uses
the same notebook composition and canonical response boundary.

## Canonical Contracts

Section work uses a strict discriminated action union:

```text
reconstruct
update_curve_scale
add_track
add_fill
```

Existing objects are selected with request-local handles such as `curve-1`.
Canonical document, track, and binding IDs remain host-owned. The section
worker validates source candidates and exact channel kind before lowering.

Report work uses a sparse `ReportSemanticResponse`. It contains only report
owned mutations and lowers directly to `AuthoringDocumentIntent`; no report
program compiler or executable program is involved.

Worker diagnostics and metrics are provider-neutral. Structured failures are
classified without retaining raw provider output, including transport,
structured-output decode, structured-schema validation, semantic context, and
semantic lowering failures.

Generic identity allocation and inspection primitives now live outside the
historical authoring-program package. The canonical compiler preserves
existing semantic identities when grounded and allocates new identities only
at the deterministic lowering boundary.

## Parity Evidence

The provider-free product paths cover the previously accepted behavior set:

- CBL construction through the real typed route, including CBL-01 through CBL-09.
- Report title revision.
- Existing curve scale revision.
- New track and source-grounded curve binding.
- Grounded fill creation.
- Ambiguous target, unavailable source, and unavailable channel rejection.
- Clarified successive revision behavior.
- Missing-source and missing-channel safe failure with no mutation.

The exact frozen D4 rehearsal completed `9/9` turns with `18/45` logical
calls, real persistence, reload, rendering, and D4 grading. The canonical
worker boundary required the D4 evaluator to recognize `channel_missing` as
the canonical equivalent of the historical `typed.channel_missing` label;
the historical label remains accepted for retained evidence.

## D5-2R1 Reachability Closeout

The canonical runtime now has one authoring engine. `routing.py` accepts only
`engine="v2"`, and no routing path constructs the historical
`AuthoringSession`. The canonical Direct Notebook and MCP adapters share the
same composition root, planner, deterministic enrichment, canonical workers,
intent lowerer, reconciliation, executor, and service.

The independent stable-fallback execution path has been removed from the
authoring session. Visual correction now consumes the canonical worker result
contract and no longer constructs a program compiler. Historical source files
remain available as retained evidence artifacts, but the provider-free
reachability audit proves that canonical public entry points load none of the
legacy v1, stable-fallback, program/report-worker, typed-delivery, graph, or
Semantic-IR compiler modules.

The audit is executable at
`scripts/check_d5_single_engine_reachability.py`; the successor production
attestation is generated and checked by
`scripts/d5_single_engine_attestation.py` against
`docs/architecture/D5_SINGLE_ENGINE_PRODUCTION_MANIFEST.json`. The D4
component path set is preserved exactly; only its source hashes are
recomputed. The D4 attestation remains historical evidence and is not
rewritten.

## Validation

Provider, endpoint, and model calls: `0`.

The exact D4 rehearsal passed with `9/9` turns, `18/45` logical calls, real
persistence, reload, rendering, and frozen grading. The D3 CBL suite passed
`3` tests through the real DLIS/render path. The D2A-D2E delivery selection
passed `22` tests. The D5 convergence/reachability selection passed `24`
tests. The canonical agent, session, notebook, routing, and visual tests
passed `130` tests in the final focused run.

Static checks passed for all changed files: Ruff, format, compilation, and
`git diff --check`. Repository-wide Ruff still reports one pre-existing import
ordering issue in the untouched `src/wellplot/agent/graph/__init__.py`; it is
outside the D5-2R1 change footprint and does not affect the canonical audit.

No live D4 or D5 activity is authorized by this result.

## Governance State

```yaml
D5-2R1:
  status: IMPLEMENTED / INDEPENDENT REVIEW PENDING
  provider_model_calls: 0
  production_live_inference: NOT RUN
  d4_live_attestation: PRESERVED_AS_HISTORICAL
  successor_production_attestation: PASS
  d5-3: NOT AUTHORIZED
```
