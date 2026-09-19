# EXP-TW-06 Development Memory

## Baseline and question

- Frozen baseline: `2e317e1`.
- Implementation checkpoint: `5c4b3a3`.
- Experiment: native Pydantic union-form compatibility micro-bisect.
- Provider: local `llama_cpp`, model `qwen3.6-35b-a3b`.
- Production delta: zero.

EXP-TW-05 showed a complete structured-output collapse between historical
`SectionDraft` and its exact S1 discriminated track-union model. TW-06
decomposed that transition using only standard Pydantic declarations. The
provider input, system prompt, request settings, adapter, and Gate-A evaluator
were held constant.

## Micro-ladder

| Variant | Native response model | Representation introduced |
| --- | --- | --- |
| U0 | historical `SectionDraft` | control |
| U1 | `SectionDraftU1` | one historical track model with field-level `Literal[...]` union for `kind` |
| U2 | `SectionDraftU2` | ordinary union of `NormalTrackU`, `ReferenceTrackU`, and `ArrayTrackU` |
| U3 | `SectionDraftU3` | discriminator wrapper over the exact U2 branch classes |
| U4 | existing `SectionDraftS1` | exact TW-05 S1 control, not recreated |

All U1-U3 models preserve the historical role domain and mixed curve/raster
binding permissiveness. No role-to-kind policy was introduced. No JSON Schema
was manually edited, no custom grammar was used, and no provider adapter or
prior experiment model was changed.

## Native schema evidence

| Variant | Model | SHA-256 |
| --- | --- | --- |
| U0 | `SectionDraft` | `c19b81abe637e6d07c434a522ef01bd7e813bcbe16bb0e928044faa8217ab7e3` |
| U1 | `SectionDraftU1` | `c8cbb9737e2d048e6763d5f57990d42783e17a8b30fb649c83c6520192d62706` |
| U2 | `SectionDraftU2` | `b9e361f59c187995c1aae45087a854aabdc336d241f17e74759c4cc6d8bee412` |
| U3 | `SectionDraftU3` | `6f8cf97ae248738d3303ab156caeb1a0756c71fea68a991e974fb1cc8d08e297` |
| U4 | `SectionDraftS1` | `e189118a3e075e07d8ee1fbf7b53560ec4b834dbf2f7e7af8bbde5b5b8e5aeb3` |

U1 is genuinely separating: its track item contains native `anyOf` branches
for single-literal `const` values rather than the historical multi-value
literal representation. U2 and U3 prove normalized equivalence for the
`NormalTrackU`, `ReferenceTrackU`, and `ArrayTrackU` branch definitions. Their
difference is the surrounding union representation and discriminator metadata.

Adjacent native schema diff sizes were:

| Transition | Added | Removed | Changed | Track projection equivalent |
| --- | ---: | ---: | ---: | --- |
| U0 -> U1 | 32 | 30 | 3 | no |
| U1 -> U2 | 87 | 33 | 2 | no |
| U2 -> U3 | 7 | 3 | 2 | no |
| U3 -> U4 | 84 | 84 | 8 | no |

The complete native schemas and adjacent diff projections are in
`EXP-TW-06-schema-artifact.json`.

## Provider controls

Every executed variant used ten independent `main_pass` and ten independent
`repeat_pass` attempts with:

- exact TW-02I serialized provider input;
- exact historical TW-03 system prompt;
- temperature `1.0`;
- `max_tokens=16384`;
- timeout `900` seconds;
- llama.cpp `enable_thinking=false`;
- existing `OpenAICompatibleBackendV2` in JSON Schema mode.

Each attempt made one structured generation call. Results were flushed to the
raw JSONL immediately, provider failures remained terminal, and no repair,
retry, fallback, raw response parsing, or custom grammar was used.

## Live results

| Variant | Main structured | Repeat structured | Total structured | Gate-A successes | Provider failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| U0 | 10/10 | 10/10 | 20/20 | 6/20 | 0 |
| U1 | 10/10 | 10/10 | 20/20 | 4/20 | 0 |
| U2 | 10/10 | 10/10 | 20/20 | 3/20 | 0 |
| U3 | 10/10 | 10/10 | 20/20 | 4/20 | 0 |
| U4 | 0/10 | 0/10 | 0/20 | 0/20 | 0 |

All U4 attempts were classified as
`structured_output_failure / invalid_response`; no metric-bearing structured
outputs were retained for U4. The U0 control reproduced successfully, and U1,
U2, and U3 all remained structurally compatible.

## Interpretation

The first observed degradation and first complete collapse are both at
`U3 -> U4` in this run. The clean ordinary-union to discriminated-union
transition (`U2 -> U3`) did not collapse. The exact TW-05 S1 model (`U4`)
did collapse, so the remaining incompatibility is in the residual differences
between the clean U3 model and the exact S1 model. The U3-to-U4 native diff is
not small enough to attribute the result to the literal JSON Schema
`discriminator` keyword alone.

This result narrows the next question without selecting a remediation. It does
not prove a llama.cpp, Qwen, Pydantic, or single-keyword implementation bug.

## Hard stop

TW-06 added only experimental script/test/evidence artifacts. No files under
`src/wellplot` changed. No production provider, schema, parser, grammar,
repair, retry, orchestration, planner, enricher, compiler, rendering, or MCP
work began. Stop before remediation or the next micro-bisect; any eventual
representation change requires separate authorization.
