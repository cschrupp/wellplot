# D5-2 Single-Engine Convergence Result

Status: `IMPLEMENTED / INDEPENDENT REVIEW PENDING`

Branch: `d5/single-engine-convergence`

Starting checkpoint: `316297635d9c6ab81368bf92f14555c91213cd56`

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

## Reachability Audit

Importing the canonical composition, Direct Notebook adapter, and MCP agentic
adapter does not load `ProgramSectionCompiler`, `ReportProgramCompiler`,
`TypedDelivery*`, the legacy graph package, or SI-V2/SI-V2R compiler modules.
No canonical composition constructs those workers.

Historical modules and explicit compatibility surfaces remain in the tree for
the existing D0-D4 evidence and legacy APIs. In particular, the v1 routing
selector and visual-correction compatibility module still have source-level
references to historical program components. They are not silently selected
by the canonical Direct Notebook, MCP, or experiment composition. Removing
those explicit compatibility surfaces is outside this bounded convergence
commit and requires a separate compatibility decision.

## Validation

Provider, endpoint, and model calls: `0`.

Exact D4 rehearsal: `1 passed`, `9/9` turns, `18` logical calls.

D3 CBL suite: `3 passed`.

Active D5/D1-D2E/D4 regression selection: `143 passed`, `1 failed`.
The single failure is the frozen D4 contract-attestation test, which correctly
rejects the old checkpoint and production-component manifest after D5 source
changes. It is not a D5 behavior failure and must be mechanically
rebaselined before a future live campaign.

The last full-suite run before the final canonical D4 fixture/evaluator
adjustment reported `2606 passed`, `96 failed`, `10 skipped`, and `11
subtests`. Its failures were a mixture of existing baseline failures, frozen
evidence/attestation drift, and optional dependency provisioning limits; it
was not rerun after the final bounded test/evaluator adjustment.

Ruff, format checks, targeted Python compilation, and `git diff --check` are
required final checks for this checkpoint. No live D4 or D5-3 activity is
authorized by this result.

## Governance State

```yaml
D5-2:
  status: IMPLEMENTED / INDEPENDENT REVIEW PENDING
  provider_model_calls: 0
  production_live_inference: NOT RUN
  d4_live_attestation: STALE_AFTER_CONVERGENCE
  d4_rebaseline: REQUIRED_BEFORE_LIVE_USE
  d5-3: NOT AUTHORIZED
```
