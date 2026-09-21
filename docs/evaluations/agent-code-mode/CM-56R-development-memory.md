# CM-56R Development Memory

## Status

- Slice: planner-to-worker semantic preservation
- Baseline: `728e652`
- Implementation checkpoint: pre-live
- State: deterministic remediation complete; live causal rerun pending
- Production routing: unchanged; `ProgramSectionCompiler` remains active

## Causal Question

CM-56 stopped at `STOP_INPUT_CONTRACT`. The real planner/enricher boundary
lost worker-relevant information before the unchanged typed section worker:

```text
natural-language request
    -> SemanticPlanner
    -> SemanticEnricher
    -> SectionTask + ResolvedSectionContext
    -> unchanged typed worker
```

The dominant loss was source grounding. Secondary losses included explicit
scale semantics, repeated-view facts, and sample-axis values. CM-56R changes
only the planner information contract to test whether those facts can survive
the existing semantic boundary.

## Contract Changes

- `SectionTask.source_hints` now has an explicit planner obligation: preserve
  ordered natural-language source-selection clues for later host resolution.
- Source hints remain semantic clues, not host candidate IDs, paths, formats, or
  generated identities.
- The planner prompt now requires explicit scientific requirements to retain
  channel names, multiplicity, track kinds, scale types and numeric bounds,
  units, reverse direction, raster profiles, and sample-axis values.
- Semantic correction context now preserves section `source_hints`.
- Semantic correction context now includes a path-redacted copy of the original
  request so omitted facts can be recovered without exposing host paths.
- Report-task correction context does not gain `source_hints`.

No deterministic source parser, scientific regex extractor, candidate inventory,
typed worker prompt, response-schema field, or enrichment rule was added.

## Frozen Artifacts

The pre-live contract artifact is `CM-56R-planner-contract.json`.

```text
SemanticPlan schema SHA: 3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3
SectionTask schema SHA:  f81e80b2bf7f4967cfc7f105a4a8a487a8a3352beefe057b6f6814c33a45fa3e
Planner prompt before:   cb704977d2e167cbc6c6cce18e92c6df17cea0bfe9f31fa4c2d966d041ee2c72
Planner prompt after:    f32d9ec68dc1aaee291ae6a14cd589ae49757c3bb42cbeea0a35b908e8bd3a98
Typed worker prompt:     19b0e289d2fa8ea362840aa94d90ad43cdea5b2ebdc866363df1ef28a38f2d49
Response schema:         93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4
Case corpus:             4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e
```

The typed worker, semantic models, compiler, enricher, shadow harness, and
case corpus are unchanged from CM-56. The primary rerun must use the same local
Qwen/llama.cpp configuration and the same frozen harness.

## Deterministic Validation

- `29 passed` in `tests/test_code_mode_planner.py`
- Ruff check passed for the changed Python files
- Ruff format check passed for the changed Python files
- `git diff --check` passed
- No production routing, worker, schema, compiler, enricher, provider, MCP,
  notebook, or graph changes

## Live Gate

The unchanged CM-56 matrix is required after the implementation checkpoint:

- provider: OpenAI-compatible local llama.cpp
- model: `qwen3.6-35b-a3b`
- temperature: `1.0`
- max output tokens: `16384`
- timeout: `900` seconds
- thinking: disabled
- sequential attempts

Stage 1 must have zero terminal planner failures and preserve source grounding,
scale semantics, repeated-view facts, and sample-axis facts for every frozen
case. Only if that gate passes may the confirmation attempts run.

The final decision is pending. It must be one of `INPUT_CONTRACT_FIXED`,
`STOP_INPUT_CONTRACT`, `STOP_PLANNER_RELIABILITY`,
`STOP_SCHEMA_COMPATIBILITY`, `STOP_TYPED_CONTEXT_GROUNDING`,
`STOP_TYPED_WORKER_SEMANTICS`, or `INCONCLUSIVE_PROVIDER_INFRA`.

## Hard Stop

CM-56R does not begin CM-57. The typed section worker remains shadow-only, the
production section route remains `ProgramSectionCompiler`, and no fallback,
repair, routing, or worker prompt change is permitted before live evidence is
reviewed.
