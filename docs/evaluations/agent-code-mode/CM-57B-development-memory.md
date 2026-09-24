# CM-57B Development Memory

## Baseline and authority

CM-57B is the deterministic production implementation of the validated typed-
worker input boundary. It is based on `015fa114e0dfb6c793535eb91eb95ee4429dd31c`,
with CM-57IB closed evidence at raw SHA-256
`23aeee3a2c6fa2951710139e46e13f7be6aee0b136659438066c56e9155a983b`.

The accepted boundary is the CM-57IB RS contract:

```text
authoritative_request
+ bounded SectionTask/source/channel input
+ applicable CapabilitySpec.semantic_metadata
```

The historical `build_typed_section_input()` projection remains unchanged for
closed diagnostics and still serializes only `section_task`, `capabilities`,
and `sources`.

## Provider boundary

The new provider contract is `TypedSectionProviderInput` with version
`cm57.typed-section-provider-input.v1`. `authoritative_request` is required by
`TypedSectionCompiler`, is preserved as user-authored text after the existing
path redaction, and is rejected when blank. It is not retained in the result
provenance after the provider call.

Semantic contracts are projected only from selected canonical capability specs,
in `SectionTask.capability_ids` order, with duplicate canonical capabilities
emitted once. Capabilities without metadata are omitted. The current provider
target vocabulary is exactly:

```text
binding.profile
binding.sample_axis.unit
binding.sample_axis.source_origin
binding.sample_axis.source_step
binding.sample_axis.tick_count
```

Scale targets under `binding.scale.*` and numeric targets under
`track.x_scale.*` are intentionally absent. The canonical semantic metadata
projection is bounded at 8192 UTF-8 bytes and fails before provider use rather
than truncating or dropping content. When no metadata applies, the optional
`semantic_contracts` field is omitted from serialized provider JSON.

The base prompt remains unchanged. The request-only prompt SHA-256 is
`7e519241911d3fbd61d8de4134c71ae69b98646a6b4e5a4ea61ba0a7a0318f69`; the
request-plus-metadata prompt SHA-256 is
`10ed56fc716165dca783f6d92805b7541f63b4044dcbcd4ac0207191f0771a80`.
The base prompt SHA-256 remains
`19b0e289d2fa8ea362840aa94d90ad43cdea5b2ebdc866363df1ef28a38f2d49`.
The response schema remains unchanged at
`93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4`.
The current raster metadata projection matches SHA-256
`67aa2d6f579343e60f9261eb654fd62bde21605b1c8c68f080b5b74ff01c3f46`.

## Scope and validation

CM-57B changes only the inactive typed worker boundary and deterministic test
coverage. Provider calls were `0`. The active LangGraph route remains
`ProgramSectionCompiler`; the typed semantic route is not active. Planner,
enricher, semantic compiler, capability declarations, identity allocation,
workflow, routing, and historical CM-56/CM-57IB evaluation files remain
unchanged.

CM-57C has not started. CM-57D is not authorized. Identity and title fidelity
remain separate slices. Stop after deterministic validation, commit, and push;
do not activate routing or run live inference in CM-57B.
