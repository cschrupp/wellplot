# CM-57IB Development Memory

## Status

- Baseline: `8d065ce44cef9459aec2c2608a627356c3085725`
- Branch: `eval/mcp-stabilization`
- Experiment: CM-57IB
- Provider calls: `0`
- Production changes: `0`
- Pre-live status: `PRELIVE_READY` after deterministic validation
- CM-57B: blocked

## Purpose

CM-57IB isolates the contribution of the authoritative original request from
the contribution of capability-local semantic metadata before CM-57B exposes
either factor to the typed worker.

The future design is a 2x2 factorial matrix over one shared planner/enrichment
result:

```text
P  current typed payload
R  P + authoritative_request
S  P + production semantic_contracts
RS P + authoritative_request + production semantic_contracts
```

The five frozen CM-56/S1 representation cases are each repeated three times.
That creates 15 shared planner/enrichment rows and 60 future worker calls.
Live calls are not authorized by this slice.

## Input Boundary

`P` is built by the unchanged production
`build_typed_section_input()` and
`serialize_typed_section_input()` functions. `R` adds the path-redacted
`authoritative_request` field sourced directly from the same request passed to
the planner. `S` adds `semantic_contracts` projected directly from
`CapabilitySpec.semantic_metadata` in task order, omitting capabilities with no
metadata and deduplicating canonical capability IDs. `RS` composes both fields.

The production `binding.raster` declaration is the only initial metadata owner.
The historical S1 JSON is not used as runtime authority. The projection is
ordered JSON with target objects, not tuple representations or executable
rules. Scalar-only tasks collapse structurally: `S == P` and `RS == R` when no
selected capability owns semantic metadata.

## Prompt Factors

`P` uses the exact current `TYPED_SECTION_SYSTEM_PROMPT`. `R` appends one
bounded authoritative-request instruction. `S` appends one bounded semantic
metadata instruction only when selected metadata exists. `RS` appends the
request instruction followed by the semantic instruction. No prompt includes
evaluation outcomes, expected semantics, historical experiment names, or
benchmark answers.

## Frozen Provenance

- Corpus: `4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e`
- Response schema: `93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4`
- Evaluator: `cm56r8r.corrected-evaluator.v1`
- Evaluator source: `4bddc22e5a8267cd36e96624884eba8c8578fdd229c7d71c0bd7986bcab12e49`
- Evaluation contract: `3e6c3c36d967acb60e6bb7cda13db95d76ed7a754eb92c4bcf5688d76b0da4da`
- Future model: `qwen3.6-35b-a3b`
- Planner/worker temperature: `0.0`
- Maximum output tokens: `16384` using `max_tokens`
- Timeout: `900` seconds
- Attempts per case: `3`

The harness records exact source-byte, prompt, payload, evaluator, corpus,
schema, contract, and production metadata projection hashes. It rejects drift,
invalid live checkpoints, changed controls, and non-empty evidence files before
provider construction.

## Evaluation

The unchanged corrected evaluator reports `track_scale`, `binding_scale`,
`raster_profile`, and `sample_axis` leaves with the frozen `PASS`, `MISSING`,
`WRONG_VALUE`, and `UNREQUESTED_EXTRA` statuses. Pairwise accounting reports
`P->R`, `P->S`, `R->RS`, and `S->RS`. Protected scale regressions dominate the
future-contract decision. Input insufficiency in P/R/S is retained as factorial
evidence rather than invalidating the population; RS must be sufficient for all
15 rows before the future contract can validate. Request contribution combines
P->R and S->RS, while metadata contribution combines P->S and R->RS. Expected
leaves use the frozen case inventory, and right-only `UNREQUESTED_EXTRA` leaves
count as regressions, including protected scale extras.

Allowed future decisions are `FUTURE_TYPED_INPUT_VALIDATED`,
`FUTURE_TYPED_INPUT_PARTIAL`, `FUTURE_TYPED_INPUT_REGRESSION`, and
`INCONCLUSIVE_INPUT_BOUNDARY`. No live conclusion is recorded here.

## Hard Stop

This is an evaluation-only pre-live harness. It does not modify `src/wellplot`,
the typed worker, prompts under production code, planner/enricher behavior,
graph/routing, identity, or CM-57B. It does not run Qwen, a smoke request, or a
partial factorial. Separate authorization is required for the future 15-row /
60-worker-call live matrix.
