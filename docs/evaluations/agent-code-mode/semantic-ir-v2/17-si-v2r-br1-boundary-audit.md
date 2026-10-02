# SI-V2R-BR1 Boundary Audit

## Canonical Schema

The canonical V2R schema was generated provider-free from
`SemanticIRV2R.model_json_schema()`.

- SHA-256: `d84cdef165ba6d060addd3ed73b018a1f10a3e70ef4a674b5d1a06352c0d58d8`
- Canonical schema metrics are frozen in
  `tests/fixtures/semantic_ir_v2r_br1/canonical_schema_audit.json`.
- The corresponding SI-V2 metrics are persisted beside them in the same audit
  artifact for descriptive comparison only; metric reduction is not treated as
  a reliability result.

The schema explicitly represents string length, feature kinds and their
required discriminators, minimum feature count, and forbidden extra fields.
Canonical field validators additionally reject whitespace-only collection
items; `minLength` alone does not establish that nonblank semantic rule.
The following remain canonical-runtime rules: unique feature IDs, reference
target requirements, companion-target exclusion, reference target membership,
fill-to-curve membership, and the requirement that report or sections exist.

## Validation Matrix

The malformed fixture matrix demonstrates the boundary directly. Relational
invalid objects such as a missing reference target, duplicate semantic ID, or
fill targeting a raster can pass the generated JSON Schema and still fail
canonical Pydantic validation. Unknown feature kinds and extra fields are
rejected by both layers.

This means the historical provider reason `schema_validation` does not by
itself identify whether the constrained decoder rejected JSON Schema or the
host rejected a structurally parsed object through a model validator.

## Deployed Converter

The frozen endpoint evidence authenticates the endpoint/model catalog but does
not authenticate a llama.cpp binary, grammar converter build, or converter
warning stream. The exact deployed converter is therefore
`DEPLOYED_CONVERTER_VERSION_UNRESOLVED`. Current upstream documentation is
external context, not run-root-cause evidence.

The official [llama.cpp grammar documentation](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
documents a supported JSON-Schema subset and recommends inspecting generated
grammars and converter warnings. That motivates a future pinned-toolchain
audit, but does not justify claiming that this historical endpoint used the
same implementation.

## External Evidence

| Source | External fact | WellPlot applicability | Limit | Consequence |
|---|---|---|---|---|
| [JSONSchemaBench](https://arxiv.org/abs/2501.10868) | Structured-output evaluation separates schema coverage, efficiency, and output quality. | Directly relevant to separating structural and semantic metrics. | Benchmark schemas and providers differ from WellPlot. | Keep independent structural, canonical, and semantic gates. |
| [Pydantic validators](https://github.com/pydantic/pydantic/blob/main/docs/concepts/validators.md) | Model-level validators express constraints beyond field typing. | Matches V2R relational invariants. | Pydantic does not prove decoder enforcement. | Inventory runtime-only invariants explicitly. |
| [PydanticAI schema transformers](https://pydantic.dev/docs/ai/api/pydantic-ai/providers/#bedrockjsonschematransformer) | Providers may need schema-subset transformations at the adapter boundary. | Supports Option B as an established pattern. | Does not select a WellPlot transformation. | Prefer a lossless projection before a second model. |
| [PICARD](https://aclanthology.org/2021.emnlp-main.779/) | Incremental constrained decoding improves syntactic admissibility. | Supports syntax/meaning separation. | Text-to-SQL is not visualization planning. | Do not credit syntax success as semantic understanding. |
| [Vega-Lite](https://vega.github.io/vega-lite/docs/) | Declarative visualization IR is lowered deterministically into a lower-level form. | Supports retaining V2R plus deterministic lowering. | Vega-Lite has different semantics and providers. | Preserve V2R/compiler separation. |
