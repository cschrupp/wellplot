# EXP-TW-03S Development Memory

## Baseline and question

- Baseline: `151efd0` (corrected EXP-TW-03 first-attempt experiment).
- Evidence inputs: local llama.cpp/Qwen and OpenRouter/Nemotron TW-03 JSONL
  artifacts, identified by their original artifact names in the experiment
  record. Raw provider evidence remains outside this commit.
- Question: can genuine semantic structural invariants become unrepresentable
  without encoding frozen CBL answers or adding repair behavior?

TW-03 provided the empirical motivation. The local Qwen run was structurally
  valid on every attempt but repeatedly selected a curve binding for the VDL
  array track. The OpenRouter/Nemotron run showed the same union-boundary
  failures among a broader set of semantic failures. This slice tests whether
  the former category belongs in the type system rather than in prompting or
  repair.

## Strengthened contract

`SectionDraftS` is a separate experimental schema. The historical TW-03
`SectionDraft` remains unchanged and remains the evidence response model.
Historical values cross into the strengthened schema through a serialized
mapping and are never copied by identity or transformed in place.

The only added invariants are:

- the historical track role domain remains `combo`, `depth`, `cbl`, or `vdl`;
- normal tracks contain curve bindings;
- reference tracks contain curve bindings;
- array tracks contain raster bindings;
- array tracks require an explicit track `x_scale`.

These are structural relationships in the semantic model: a track's declared
kind determines which binding family it can contain, and an array track cannot
express its array-axis semantics without an x scale. They do not depend on the
CBL title, source handle, channel mnemonic, exact scale, reversal, semantic ID,
track order, or any other frozen benchmark answer.

The schema does not add literals for `Main Pass`, `Repeat Pass`, `source-1`,
`source-2`, CBL ranges, TT/TENS values, VDL values, sample-axis values, or
specific ordering. It does not insert, reorder, infer, repair, replace, or
complete fields.

The distinction is explicit:

```text
schema-invalid
    = impossible according to the semantic type system

Gate-A-invalid
    = structurally representable, but wrong for this requested task
```

## Replay method and evidence

The replay reads only redacted TW-03 attempt rows. It performs no provider
calls. For each historical structurally valid draft it:

1. validates the serialized mapping as `SectionDraftS`;
2. compares the strengthened JSON projection with the original historical
   projection;
3. reruns the unchanged Gate-A scorer only for drafts accepted by `SectionDraftS`;
4. records aggregate structural rejection and redacted Pydantic
   type/location fingerprints.

The compact replay aggregate records, separately for Qwen and Nemotron and for
both section roles, historical structural/Gate-A counts, strengthened counts,
structural rejection counts, unchanged post-strengthening Gate-A counts, and
the number of prior Gate-A failures that were rejected structurally versus
remaining structurally valid. It contains no raw provider output, prompts,
paths, credentials, or hidden reasoning.

The replay aggregate is committed as
`EXP-TW-03S-replay-summary.json`. Its measured results are:

| Provider/model | Role | Historical structural | Historical Gate A | 03S structural | 03S rejected | Gate A after 03S | Prior Gate-A failures: structural / semantic |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| llama_cpp / `qwen3.6-35b-a3b` | `main_pass` | 10 | 1 | 1 | 9 | 1 | 9 / 0 |
| llama_cpp / `qwen3.6-35b-a3b` | `repeat_pass` | 10 | 3 | 3 | 7 | 3 | 7 / 0 |
| openrouter / `nvidia/nemotron-3-ultra-550b-a55b:free` | `main_pass` | 10 | 6 | 7 | 3 | 6 | 3 / 1 |
| openrouter / `nvidia/nemotron-3-ultra-550b-a55b:free` | `repeat_pass` | 9 | 4 | 6 | 3 | 4 | 3 / 2 |

The one Nemotron historical structured-output failure remains outside the 03S
schema replay because it had no historical `SectionDraft` value. Across the
replayed drafts, Gate-A success never increases. Qwen's observed VDL failures
move into structural rejection, while three Nemotron failures remain
structurally representable and therefore remain semantic Gate-A failures.

The final Gate-A success count is not allowed to increase during replay. An
accepted draft must have exactly the same semantic JSON projection as the
historical draft passed to the original Gate-A scorer.

## Scope and result boundary

- Production-package delta: zero.
- Historical TW-00/01/02/02R/02I/03 files: unchanged.
- Provider calls, prompts, adapters, retries, repair, critic, reflection,
  LangGraph, orchestration, and production integration: zero.
- EXP-TW-04: not started.

This slice answers only whether the selected impossible shapes can be rejected
structurally. Remaining title, source, scale, reversal, ordering, missing
track, and other task-specific errors remain Gate-A semantic failures.

**Hard stop:** review and commit EXP-TW-03S, then stop before EXP-TW-04.
