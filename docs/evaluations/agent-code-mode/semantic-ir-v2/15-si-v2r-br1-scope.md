# SI-V2R-BR1 Scope

## Decision

Run a finite, provider-free audit of the rejected SI-V2R live qualification.
The slice classifies the frozen residuals, inventories canonical validation
versus generated JSON Schema, and determines whether a provider-boundary
adapter is justified. It does not authorize live inference or production
integration.

## Frozen Inputs

- Live-result checkpoint: `4f37ef8d6fa441d138f399dd3ac1c45da331fb86`
- Raw population: `/tmp/si-v2r-live.jsonl`
- Raw population SHA-256: `9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08`
- Population: 48 rows, 24 cases, two attempts per case
- Historical decision: `SI_V2R_PROVIDER_BOUNDARY_REJECTED`

The historical scores remain immutable: 36/48 initial structural successes,
six terminal structural failures, 14/24 stable semantic passes, 42 compile
successes, and zero compiler invariant or reference-preservation failures.

## Hard Boundaries

BR1 makes zero provider, endpoint, worker, or program calls. It does not edit
`SemanticIRV2R`, the V2R compiler or registry, production planner/provider
code, the graph, CM58, ADR-CM57, or the frozen live-result documents. Any
adapter prototype, if later justified, remains isolated from production.

## Decision Sequence

```text
authenticate evidence
  -> classify residual mechanisms
  -> inventory canonical invariants
  -> audit generated JSON Schema
  -> resolve deployed converter provenance if possible
  -> compare direct schema, projection, wire-model, and weak-JSON options
```

The slice must not assume that a smaller schema is the solution. A provider
representation is structurally successful only after unchanged canonical
`SemanticIRV2R` validation and must not repair, infer, merge, split, or drop
semantic content.

## Evidence Classification

- Canonical V2R plus deterministic lowering: `EMPIRICALLY_SUPPORTED`.
- Semantic IR to deterministic compilation: `ADAPTED` from mature declarative
  compiler patterns.
- Provider-specific schema adaptation: `ESTABLISHED` as an integration
  pattern, but the WellPlot adapter is `NOVEL` until provider-free validation.
- Improved live reliability from an adapter: `UNRESOLVED` until a separately
  authorized live experiment.
