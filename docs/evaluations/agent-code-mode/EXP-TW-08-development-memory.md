# EXP-TW-08 Development Memory

## Baseline and question

- Frozen baseline: `79f3173` (EXP-TW-07 final evidence).
- Implementation checkpoint: `4fd71c3`.
- Experiment: remediation validation for the strengthened typed worker schema.
- Production delta: zero.

TW-07 isolated the local llama.cpp/Qwen structured-output collapse to the
Pydantic representation of defaulted discriminated track tags. EXP-TW-08
tested whether requiring those tags recovers compatibility without weakening
the structural guarantees established by TW-03S.

## Controlled variants

R0 reused the existing `SectionDraftS` from `scripts.exp_tw03s_schema`, whose
normal, reference, and array track tags have defaults. R1 used the same
semantic fields, branch names, branch order, discriminator property, and
discriminator mapping, but required:

```python
kind: Literal["normal"]
kind: Literal["reference"]
kind: Literal["array"]
```

R1 did not couple track roles to track kinds. It reused the existing leaf
types and changed no provider input, prompt, compiler, Gate-A rule, or host
completion behavior.

The native schema audit found only the intended representation change:

- R1 removes the three branch-level `properties.kind.default` values.
- R1 adds `kind` to each branch's `required` list.
- Branch names, branch count, `oneOf` ordering, discriminator property and
  mapping, references, and all non-tag fields remain identical.

## Deterministic evidence

Before live calls, the experiment verified:

- every TW-03S structural invariant remains true;
- both golden sections round-trip with equivalent semantic dumps under R0
  and R1;
- Gate-A results are equivalent for both frozen sections;
- compiler projections are equivalent;
- the full R1 discriminated union rejects an omitted `kind` tag.

The committed native schema artifact is
`EXP-TW-08-schema-artifact.json`.

## Provider controls

Each variant used ten independent `main_pass` and ten independent
`repeat_pass` attempts with:

- the exact TW-02I serialized provider input;
- the exact TW-04 system prompt used by the harness:
  `Return exactly one SectionDraftS matching the typed input bundle. Use no fields outside the SectionDraftS schema.`;
- local `llama_cpp`, model `qwen3.6-35b-a3b`;
- temperature `1.0`, `max_tokens=16384`, timeout `900` seconds;
- `enable_thinking=false`;
- the existing `OpenAICompatibleBackendV2` in JSON Schema mode.

Each attempt made exactly one structured generation call. Failures were
terminal. No retry, repair, fallback, grammar workaround, prompt tuning, or
orchestration was introduced. Every completed attempt was flushed to the
temporary redacted JSONL evidence before the next request.

## Live results

| Variant | Main structured | Repeat structured | Total structured | Gate-A successes | Provider failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| R0 | 0/10 | 1/10 | 1/20 | 0/20 | 0/20 |
| R1 | 10/10 | 10/10 | 20/20 | 20/20 | 0/20 |

R0 recorded `1,678` tokens and `55,652.99` ms for its one structurally
valid response. The other 19 calls were `structured_output_failure /
invalid_response`; no provider transport failures occurred.

R1 recorded `34,886` total tokens and `1,143,368.88` ms across 20
metric-bearing calls. All 20 responses were structurally valid and all 20
passed Gate A.

The raw redacted JSONL files remain under `/tmp` for this run and are not
committed. The committed aggregate is
`EXP-TW-08-live-summary.json`.

## Interpretation

The remediation recovered both stages measured by this experiment:

```text
R0 defaulted tags       1/20 structured, 0/20 Gate A
R1 required tags       20/20 structured, 20/20 Gate A
```

The result supports this experimental conclusion:

> For the local llama.cpp/Qwen structured-output path, requiring the
> discriminated track tags recovers compatibility while preserving the
> TW-03S structural contract.

The causal claim remains at the coupled native-schema level. Pydantic changes
the default and requiredness together, so this experiment does not separately
identify whether the lower-level trigger is the emitted `default` keyword,
the `required` list, or their interaction. The local provider/model is also
the only live environment tested.

This result does not authorize changing production schemas, providers, or
adapters. Any production adoption requires a separate review and explicit
authorization.

## Hard stop

No files under `src/wellplot` changed. No TW-00 through TW-07 file changed.
EXP-TW-08 added only its experimental runner, focused tests, schema artifact,
live summary, and this development memory. Stop before production adoption or
the next experiment without explicit authorization.
