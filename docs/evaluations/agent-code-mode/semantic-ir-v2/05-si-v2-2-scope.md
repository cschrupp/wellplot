# SI-V2.2 Scope

## Decision

```yaml
experiment: SI-V2.2
baseline: d461d756c45c63b9f59d1cdc532d031244dc14af
branch: eval/semantic-ir-v2-model-qualification
population: 24 frozen CM-59A requests x 2 attempts
provider_calls_maximum: 96
concurrency: 1
model: qwen3.6-35b-a3b
production_changes: 0
live_inference: separately authorized
```

SI-V2.2 qualifies the reduced semantic responsibility represented by
`SemanticIRV2`. It does not redesign SI-V2.1, compare providers, optimize the
prompt, or authorize production adoption.

The evaluation records four independent layers:

```text
L1  provider/schema structural validity
L2  deterministic semantic projection against frozen gold
L3  deterministic lowering to SemanticPlan
L4  CM-58.1 -> CM-58.2 -> CM-58.3 safety behavior
```

The essential invariant is:

```text
schema-valid != semantically correct
downstream safety rescue != model semantic understanding
```

Semantic scoring is completed before compilation and CM-58. A semantic failure
that later reaches the correct final system signature remains a model semantic
failure and is recorded separately as a safety rescue or final-system pass.

## Frozen Inputs

The exact 24 CM-59A request cases and the accepted SI-V2.1 semantic fixture are
used unchanged. The gold fixture is grader-only evidence. It is never included
in provider prompts, and case IDs are not included in the provider payload.

The sole human-authored provider prompt describes semantic responsibilities:
report/section allocation, curve/raster/reference/fill/annotation meaning,
context preservation, unresolved requirements, and the prohibition on host or
capability mechanics. It contains no capability identifiers and no corpus
examples.

The provider user payload contains only:

```json
{
  "request": "<frozen request text>",
  "mode": "reconstruct",
  "current_document_summary": {}
}
```

One initial structured call is allowed, followed by at most one generic
format/schema retry after an invalid structured response. There is no semantic
retry, capability correction retry, CM-58-informed retry, or request-specific
repair.

## Qualification Gates

The terminal decision is one of:

```text
SI_V2_MODEL_QUALIFIED
SI_V2_PROVIDER_BOUNDARY_REJECTED
SI_V2_MODEL_SEMANTIC_REJECTED
SI_V2_COMPILER_REJECTED
SI_V2_SAFETY_REJECTED
SI_V2_2_INCONCLUSIVE_INFRASTRUCTURE
```

Qualification requires all of the following:

- zero terminal structural failures;
- 24 stable cases and at least 22 stable semantic passes;
- at least 3 stable passes in every family;
- 2/2 semantic passes for Fig, Linden, Kestrel, and Xenon;
- no compiler invariant failure or semantic-pass signature mismatch;
- no CM-58 safety regression or wrong final escape.

Recovered structural failures remain visible as recovery dependency evidence.
Endpoint drift, authentication/configuration failure, transport failure, or a
partial population is infrastructure inconclusive, not a semantic rejection.

## Boundaries

No production planner/provider/graph, CM-58 implementation, worker,
`AuthoringDocumentIntent`, MCP, public API, or ADR changes are allowed. SI-V2.2
must not be imported into the active graph. A live result, regardless of its
decision, does not authorize production adoption or an ADR-CM57 revision.

If live evidence exposes a compiler or architectural deficiency, preserve the
evidence and stop at the corresponding terminal decision. Do not automatically
start a remediation experiment.
