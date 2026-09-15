# CM-43 Development Memory

## Scope

CM-43 adds a fair section-level A/B harness for the frozen CBL experiment. It
does not change either section worker, planner, provider, graph route, or
document mutation path.

- **Slice base SHA:** `f3ef056`
- **Implementation scope:** frozen-case loading, deterministic v1/v2 adapters,
  common canonical section acceptance, redacted JSONL evidence rows, and gate
  evaluation.
- **Primary case:** `main_pass` only. `repeat_pass` is intentionally not part
  of the CM-43 decision gate.

## Fairness Contract

Both engines receive the same immutable semantic case:

- `tests/fixtures/agentic_cbl/frozen_prompt.txt`
- `tests/fixtures/agentic_cbl/cased_hole_starter.log.yaml`
- `tests/fixtures/agentic_cbl/compile_contract.json`

The v1 adapter receives the frozen `SectionPlan` and uses the unchanged
`SectionCompiler`. The v2 adapter receives a deterministic `SectionTask` and
`EnrichedSemanticContext` derived from that same plan. Neither planner runs
during the A/B experiment.

Prompt and schema sizes are measured at each native worker boundary. The
harness does not force both engines through the same provider API: v1 uses its
structured-output interface and v2 uses plain program generation. Provider
metrics remain `not_available` when an adapter cannot measure them; measured
zero is not substituted.

## Common Acceptance

Engine-local success is not acceptance. Both outputs are normalized to
`AuthoringDocumentIntent` and evaluated by the same host-side contract:

- one section fragment;
- normal combo track;
- reference/depth track;
- normal CBL track;
- array VDL track;
- required scalar channels, CBL curve, and VDL raster;
- expected DLIS source association;
- no report-wide or unrelated-section mutations;
- successful private application through the canonical executor.

Legacy target-ID equality is recorded as informational evidence only. Host-owned
v2 identities are valid when the semantic roles and canonical application are
valid.

## Validation

- CM-43-focused tests: `4 passed`.
- Adjacent Code Mode/CBL regression selection: `59 passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.

The deterministic tests prove that three fake A/B pairs remain ineligible for
the live gate, that missing array/raster output is reported as
`sdk_prompt_contract_insufficient`, and that generated program text is retained
only as a length and SHA-256 hash in evidence rows.

## Live Gate Status

The required three live runs per engine have not been collected in this
environment. No provider credentials or provider factories were supplied, so
no live claim is made and no `CM-43-live-runs.jsonl` is created.

The live runner must use the same provider family, model, temperature, output
budget, timeout, and semantic case for both engines. It must record redacted
JSONL rows containing engine success, common acceptance, omissions, repairs,
provider calls/tokens, worker/provider latency, prompt/schema/source metrics,
legacy-core reachability, and failure codes.

If v2 omits the array/raster roles because the current scalar-only SDK
reference cannot express them, the decision is `STOP_SDK_CONTEXT_GAP`; do not
modify `ProgramSectionCompiler` during this slice. Otherwise the gate may
produce `PROCEED` or `STOP_V2_REGRESSION` according to the measured evidence.

## Boundaries

- `ProgramSectionCompiler` modifications: `0`.
- CBL-specific runtime branches: `0`.
- Provider fallback or retry changes: `0`.
- v1 worker modifications: `0`.
- Persistence, rendering, MCP, LangGraph routing, and legacy deletion: `0`.

## Decision

**PROCEED / STOP:** The deterministic A/B harness is implemented and tested,
but CM-43 remains open pending three live runs for each engine. Do not proceed
to CM-44 until the live evidence is collected and the A/B decision is recorded.
