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
- **Harness correction commit:** `bfada44` (`Correct CM-43 A/B evidence gate`).
- **Live runner commit:** `3864df2` (`Add CM-43 live experiment runner`).

## Harness Corrections

The deterministic harness now enforces the fairness conditions required before
live runs:

- `evaluate_gate()` requires v2 acceptance to be at least competitive with v1
  and also requires a material v2 complexity advantage. Simplicity cannot
  override a lower v2 acceptance count.
- Every row carries an experiment fingerprint derived from the frozen corpus
  hashes, section, provider/model, generation settings, timeout, and run count.
  Mixed fingerprints are not eligible for a decision.
- Legacy-core reachability is measured by an execution-frame probe, not by a
  `sys.modules` import delta, so the result is independent of prior imports.
- v2 SDK representability is classified from the published worker capability
  set (`section.log_plot`, `track.normal`, and `binding.curve`), not from a
  particular model's omitted tracks.
- The common acceptance contract requires exactly four tracks and exact
  binding shapes: four combo curves, three depth curves, two CBL curves, and
  one VDL raster. Extra tracks or bindings are rejected.
- The v1 evaluation boundary includes a redaction-safe legacy backend recorder
  for provider-call, repair, token, and latency aggregates when available.

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

- CM-43-focused tests: `10 passed`.
- Adjacent Code Mode/CBL regression selection: `65 passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.

The deterministic tests prove that three fake A/B pairs remain ineligible for
the live gate, all gate outcomes are bounded and explicit, mixed experiment
fingerprints are rejected, lower v2 acceptance stops even when v2 is simpler,
published SDK gaps are reported as `sdk_prompt_contract_insufficient`, exact
extra-binding mutations are rejected, and generated program text is retained
only as a length and SHA-256 hash in evidence rows.

## Live Gate Status

The six-run entry point is `scripts/run_cbl_section_ab.py`. It builds both
case-aware factories over one OpenAI-compatible client configuration, injects
the same temperature/token/timeout settings into the legacy Chat path, and
writes only redacted rows plus the gate summary. A live run is invoked with
explicit provider settings, for example:

```bash
uv run --extra agent python scripts/run_cbl_section_ab.py \
  --provider openai_compat \
  --model MODEL \
  --base-url https://provider.example/v1 \
  --api-key-file PROVIDER_API_KEY.txt \
  --temperature 0 \
  --max-output-tokens 16000 \
  --timeout 1800
```

The required three live runs per engine have not yet been collected in this
environment. No provider credentials, endpoint, model, or generation settings
were selected for execution, so no live claim is made and no
`CM-43-live-runs.jsonl` is created.

The live runner must use the same provider family, model, temperature, output
budget, timeout, and semantic case for both engines. It must record redacted
JSONL rows containing engine success, common acceptance, omissions, repairs,
provider calls/tokens, worker/provider latency, prompt/schema/source metrics,
legacy-core reachability, the shared experiment fingerprint, and failure codes.

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
