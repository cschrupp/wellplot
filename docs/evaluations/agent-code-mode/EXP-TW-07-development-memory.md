# EXP-TW-07 Development Memory

## Baseline and question

- Frozen baseline: `1f5da6e` (EXP-TW-06 final evidence).
- Implementation checkpoint: `d4c73d3`.
- Experiment: required-versus-defaulted discriminator compatibility bisect.
- Provider: local `llama_cpp`, model `qwen3.6-35b-a3b`.
- Production delta: zero.

EXP-TW-06 localized the TW-05 collapse to the residual difference between a
working discriminated union and the exact S1 model. TW-07 changed only the
Pydantic field default for the discriminator tag. D0 and D1 are built through
the same `create_model()` factory with identical native model names and field
definitions; D0 uses a required `kind: Literal[...]`, while D1 uses the same
literal with a default.

```text
working U3-style branch
        |
        | add only a Pydantic discriminator default
        v
D1 native response schema
        |
        | measure structured compatibility
        v
local llama.cpp/Qwen result
```

## Controlled variants

| Variant | Feature | Response model |
| --- | --- | --- |
| D0 | required literal discriminator tag | `SectionDraftTag` |
| D1 | defaulted literal discriminator tag | `SectionDraftTag` |

The factory uses the same `NormalTrackTag`, `ReferenceTrackTag`,
`ArrayTrackTag`, and `SectionDraftTag` names for both variants. The response
model, not the provider input, is the only request-boundary difference.

The native schema audit proves:

- branch names, branch count, `oneOf` order, discriminator property, and
  discriminator mapping are identical;
- all non-`kind` branch fields are equivalent;
- D1 adds only `properties.kind.default` for each branch;
- D1 removes only `kind` from each branch's `required` list.

The native branch-level Pydantic model accepts an omitted D1 tag, while the
full discriminated response model still requires the tag to select a union
branch. That behavior is recorded in the schema artifact rather than assumed
away. The artifact also links the native D0/D1 representation to the prior U3
and U4 representations.

## Provider controls

Every live variant used ten independent `main_pass` and ten independent
`repeat_pass` attempts with:

- exact TW-02I serialized provider input;
- exact historical TW-03 system prompt:
  `Return exactly one SectionDraft that matches the typed input bundle. Use no fields outside the SectionDraft schema.`;
- temperature `1.0`;
- `max_tokens=16384`;
- timeout `900` seconds;
- llama.cpp `enable_thinking=false`;
- existing `OpenAICompatibleBackendV2` in JSON Schema mode.

Each attempt made exactly one structured generation call. Provider and
structured-output failures were terminal. No repair, retry, fallback, raw
response parsing, custom grammar, or orchestration was introduced. The runner
flushed each completed attempt to redacted JSONL before starting the next
request and persisted each section and variant summary.

## Deterministic evidence

The focused and prior experiment regression suites passed with `118` tests.
Ruff, formatting, schema JSON serialization, and `git diff --check` passed.
The focused tests prove:

- D0 and D1 use one factory path and identical model names;
- native schema differences are limited to discriminator defaults and
  requiredness;
- both golden sections round-trip through both response models;
- provider input, prompt, and request settings are identical;
- typed provider failure is terminal and unexpected exceptions propagate;
- attempt evidence is flushed before the next request;
- schema hashes and the review artifact are deterministic.

## Live results

| Variant | Main structured | Repeat structured | Total structured | Gate-A successes | Provider failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| D0 | 10/10 | 10/10 | 20/20 | 4/20 | 0/20 |
| D1 | 0/10 | 0/10 | 0/20 | 0/20 | 0/20 |

D0 recorded `34,401` total tokens and `1,151,472.28` ms across 20
metric-bearing calls. D1 made 20 provider calls, all classified as
`structured_output_failure / invalid_response`; no provider transport failures
were observed and no structured-output metrics were retained for D1.

The raw redacted JSONL is retained under `/tmp` for audit during this run and
is not committed. The committed aggregate is
`EXP-TW-07-live-summary.json`; the native schema review artifact is
`EXP-TW-07-schema-artifact.json`.

## Interpretation

The result isolates the first complete structural collapse to the single
required-versus-defaulted discriminator change:

```text
D0 required discriminator       20/20 structured, 4/20 Gate-A
D1 defaulted discriminator       0/20 structured, 0/20 Gate-A
```

This is stronger than the TW-06 U3-to-U4 localization because D0 and D1 use
the same native factory and model names. The evidence supports the conclusion
that the defaulted discriminator representation is incompatible with this
local llama.cpp/Qwen structured-output path. It does not by itself establish
whether the root implementation defect is in llama.cpp, Qwen, Pydantic schema
handling, or another JSON Schema consumer.

No production remediation is selected by this experiment. In particular,
TW-07 does not authorize removing defaults from production models, replacing
discriminated unions, editing provider adapters, adding grammar workarounds,
or adding retries.

## Hard stop

No files under `src/wellplot` changed. TW-07 added only the experimental
runner, focused tests, schema artifact, live summary, and this development
memory. No prior TW-00 through TW-06 file changed. Stop before remediation or
the next schema/provider experiment; any representation change requires
separate authorization.
