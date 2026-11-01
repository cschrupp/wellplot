# Knowledge Delta Draft: Canonical NLP Authoring

```yaml
status: PREPARED / NOT AUTHORITATIVE
depends_on: WELLPLOT-NLP-CANONICAL-AUTHORING-ARCH-001
architecture_status: PENDING INDEPENDENT REVIEW
baseline_updated: false
```

This draft is retained for possible use after independent architecture
acceptance. It does not supersede any current active baseline item and does not
authorize implementation.

## Proposed Previous / New Knowledge

| Existing baseline authority | Possible delta after acceptance | Promotion condition |
| --- | --- | --- |
| K-01: one canonical engine | Preserve. Extend only the existing Code-Mode plan/worker graph and existing authoring service chain. | Architecture and implementation review both confirm no parallel path. |
| K-02: model semantics / host identity and mechanics | Permit a typed, request-local semantic operation proposal, but keep identity, source resolution, IDs, dependencies, mutation, persistence and rendering host-owned. | ADR explicitly approves planner operation scope and regression proves forbidden host mechanics cannot appear. |
| K-03/K-04: schema validity is not semantics; safety does not repair meaning | Preserve exactly; invalid or unauthorized semantic patches fail before lowering and do not publish. | Provider-free negative and no-publication tests. |
| R-01/R-05: input sufficiency and inspection state | Clarify bounded immutable document/source snapshots and distinct inspected, inspected-empty, not-inspected, unavailable states. | Source audit and tests establish facts are grounded and paths/sample payloads remain host-owned. |
| R-02/R-03/R-04: schema parity, required discriminators, capability closure | Preserve and apply to the operation contract and sparse patch schema. | Exact-schema and canonical-validation parity tests. |
| R-06: bounded correction and preservation | Preserve the current one-correction lineage; require exact operation scope and sibling/unrelated-state preservation. | Correction and failure tests pass with no expanded retries. |
| R-07/R-08: causal outcomes and controlled changes | Preserve; treat D5 binding smoke 002 as a contract diagnostic only. | Exact stage/owner failure assertions; future live use remains separately governed. |
| K-05/K-06/K-07: immutable evidence, smoke gate, canonical runtime | Preserve unchanged. | Historical artifacts and fresh exact-head live gate remain separate. |

## Non-Goals

- No new semantic engine, graph, planner runtime, CRUD executor, or YAML writer.
- No transfer of canonical identifiers, filesystem paths, or mutation authority
  to a model.
- No silent operation coercion, host semantic completion, or extra correction
  loop.
- No change to frozen D5 populations, gold, or C02.

## Promotion Checklist

Do not merge this draft into the active baseline until all are true:

1. The architecture ADR is independently accepted and Human-accepted.
2. The authorized implementation is complete and independently reviewed.
3. Provider-free regressions identify the new invariant at the relevant
   planner, contract, worker, lowering, and persistence boundaries.
4. The Knowledge Delta cites exact accepted implementation and test commits.
5. Current baseline text is edited only to the minimum necessary clauses;
   historical evidence is left immutable.
