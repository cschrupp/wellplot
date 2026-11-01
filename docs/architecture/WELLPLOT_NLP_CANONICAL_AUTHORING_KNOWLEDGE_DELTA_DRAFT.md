# Knowledge Delta Draft: Canonical NLP Authoring

```yaml
status: PREPARED / NOT AUTHORITATIVE
depends_on: WELLPLOT-NLP-CANONICAL-AUTHORING-ARCH-001
architecture_status: PENDING INDEPENDENT REVIEW
baseline_updated: false
```

This draft defines two distinct baseline-promotion milestones. The current
corrective only prepares the draft: it does not edit the active baseline,
supersede an active item, or authorize implementation.

## Proposed Previous / New Knowledge

| Existing baseline authority | Stage 1: accepted architecture, not yet implemented | Stage 2: implementation evidence |
| --- | --- | --- |
| K-01: one canonical engine | Preserve; only the existing Code-Mode graph and authoring chain may be extended. Mark any accepted extension as not yet implemented. | Cite accepted implementation/test checkpoints and retain attestation evidence proving no alternate path. |
| K-02: model semantics / host identity and mechanics | Permit only the A00-accepted, request-local semantic operation proposal; host continues to own identity, source resolution, IDs, dependencies, mutation, persistence and rendering. | Verify schema, obligation binding and forbidden-field regressions at accepted implementation SHA. |
| K-03/K-04: schema validity is not semantics; safety does not repair meaning | Preserve exactly; invalid or unauthorized semantic patches remain rejected before lowering/publication. | Cite negative and no-publication regression evidence. |
| R-01/R-05: input sufficiency and inspection state | Accept only the architectural requirement for bounded host-owned context and distinct inspection states; do not claim snapshot/query implementation exists. | Cite source audit and tests for grounded facts, privacy/path limits, and inspection states. |
| R-02/R-03/R-04: schema parity, required discriminators, capability closure | Preserve; require parity and explicit discriminators for any accepted operation/patch schema. | Cite exact accepted schema hashes and parity/closure tests. |
| R-06: bounded correction and preservation | Preserve the accepted correction authority and require preservation; do not claim new patch preservation is implemented. | Cite correction/preservation tests and call-ceiling evidence. |
| R-07/R-08: causal outcomes and controlled changes | Preserve; keep D5 binding smoke 002 classified as contract evidence only. | Cite exact stage/owner regression evidence; live qualification remains separate. |
| K-05/K-06/K-07: immutable evidence, smoke gate, canonical runtime | Preserve unchanged. | Cite immutable evidence identities and independently accepted exact-head live gates where applicable. |

## Non-Goals

- No new semantic engine, graph, planner runtime, CRUD executor, or YAML writer.
- No transfer of canonical identifiers, filesystem paths, or mutation authority
  to a model.
- No silent operation coercion, host semantic completion, or extra correction
  loop.
- No change to frozen D5 populations, gold, or C02.

## Stage 1: Architecture Promotion

After independent review and Human architecture acceptance, update the active
baseline before A01 begins. The entry must state `ACCEPTED / NOT YET
IMPLEMENTED`, cite the accepted architecture commit, identify the precise
superseded planner restriction, retain all unchanged K/R invariants, and list
the implementation/regression obligations. This architecture-level promotion
does not claim runtime capability and does not authorize A01 by itself.

The present corrective does not perform this edit.

## Stage 2: Implementation Promotion

After independent implementation acceptance, update the baseline with only
verified implementation results. Require all of:

1. The authorized implementation is complete and independently reviewed.
2. Provider-free regressions identify the new invariant at the relevant
   planner, contract, worker, lowering, and persistence boundaries.
3. The Knowledge Delta cites exact accepted implementation and test commits.
4. Verified capability, exact regressions, and residual limitations are all
   explicit; unqualified behavior is not promoted.
5. Current baseline text is edited only to the minimum necessary clauses;
   historical evidence is left immutable.
