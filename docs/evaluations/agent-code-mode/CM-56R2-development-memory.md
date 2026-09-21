# CM-56R2 Development Memory

## Status

- Slice: planner-only reliability and source-context diagnostic
- Baseline: `bfb539e`
- Implementation checkpoint: pre-live
- Production routing: unchanged; `ProgramSectionCompiler` remains active
- Typed worker: not invoked by this experiment

## Question

CM-56R improved planner information preservation but still produced terminal
planner failures and input losses. CM-56R2 separates three hypotheses without
changing production behavior:

```text
H1  planner sampling/reliability
H2  missing bounded source context
H3  capability-selection burden
```

The experiment is planner-only. It reuses the frozen ten-case CM-56 corpus,
the existing `SemanticPlanner`, and the existing deterministic
`SemanticEnricher`, then stops before any typed worker or compiler call.

## Fixed Variants

| Variant | Temperature | Bounded source summary |
|---|---:|---|
| A | 1.0 | no |
| B | 0.0 | no |
| C | 1.0 | yes |
| D | 0.0 | yes |

Each variant is intended to run three sequential attempts for each of the ten
frozen requests. The only experimental variables are temperature and inclusion
of the compact source summary.

The source summary contains only source labels and channel mnemonic/kind pairs.
It excludes candidate IDs, filenames, paths, source formats, parser objects,
and datasets. The planner continues to emit natural-language `source_hints`;
the existing enricher remains the resolver.

## Evidence Contract

Each redacted row records:

- variant and temperature;
- case and attempt index;
- planner call count;
- safe `SemanticPlan` projection, including source hints and requirements;
- planner failure type/code/provider category;
- enrichment failure type/code when applicable;
- bounded enrichment shape on successful enrichment;
- request and source-summary hashes.

No provider response content, exception text, canonical path, or host source
identity is retained. The harness never calls the typed worker, semantic
compiler, program worker, graph, routing, or persistence layers.

## Frozen Inputs

- CM-56 case corpus SHA-256:
  `4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e`
- CM-56 typed worker prompt, response schema, serializer, enricher, and
  evaluator remain unchanged.
- Primary provider remains the controlled local llama.cpp endpoint with the
  Qwen model and the existing CM-56 token/timeout controls.

## Decision Gate

The completed matrix will be evaluated in this order:

1. Terminal planner failures yield `STOP_PLANNER_RELIABILITY`.
2. Otherwise, missing source/scientific facts yield `STOP_INPUT_CONTRACT`.
3. Structured-output failures after sufficient planning yield
   `STOP_SCHEMA_COMPATIBILITY`.
4. The remaining outcomes distinguish enrichment and downstream typed-worker
   behavior without modifying those boundaries.

No production correction, planner prompt change, typed-worker call, repair,
fallback, routing change, or CM-57 work is authorized by this diagnostic alone.

## Validation

- `33 passed` focused diagnostic/planner tests
- Ruff check passed
- Ruff format check passed
- `git diff --check` passed
- Production-package delta: zero

Live result: pending.
