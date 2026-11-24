# S03 H1 provider-free implementation handoff

Beads: `well_log_os-bdn.4`, in progress. Planning parent:
`002815f7ebbfa50b2390d559f55854f17ca4c153`.
This checkpoint is not live authority, empirical evidence or product acceptance.

The [frozen panel](WELLPLOT_V2_H1_PANEL.json) carries only requests, expected
compiler dispositions, and explicitly synthetic inspection fixtures. The
scientific grading expectations remain in the [planning record](WELLPLOT_V2_S01_S02_H1.md)
and never enter model messages. Panel artifact SHA-256:
`967b3f670e4d5763b8aaa37cdbf9805ef76a8e7f831ea5106567895126391402`.

Actual system prompt:

> Describe the requested scientific outcomes using only the request and supplied inspection. Preserve physical versus semantic channel clues, sources, scope, quantities, units and restrictions. Report unavailable or ambiguous work without substitution; ask for consequential clarification. Do not produce implementation steps, operation IDs or prerequisites.

The user message is `USER REQUEST:\n{exact request}\n\nINSPECTED CONTEXT:\n`
followed by the sorted-key JSON representation of that case's context.
The advertised schema is `_H1ObservationResponse.model_json_schema()` in
`planner.py`, digest (D5 canonical JSON):
`a3ffbc58e61eb6cd1ca05f6801e47da1ec978cc646dbf79bc422c71f3fd3ada4`.
It admits only an object with required `outcomes` (minimum one item). Each
item requires nonempty `statement` and `disposition` in
`requested | already_satisfied | unavailable | needs_clarification`, with
optional `qualifiers` (string array, default empty). Both objects forbid
extra fields. No outcome can be converted into an executable plan.

The existing planner compiles the original request first and retains its
actual result. The internal H1 argument must match a frozen case's complete
digest, exact request and compiler disposition; dependency-bearing and C2
requests remain forbidden. H04/H05/H07 are the only pinned coverage failures
that can reach H1 capture. The same structured call and D4 accounting are
used, with no normal correction block reached. A valid response stops even
without the observer; an invalid response propagates without correction.
Notebook/MCP do not receive an experiment control.

The D5 selector admits only the complete ordered H1 panel under an H1
descriptor, in planner-only mode. It retains the actual prompt/schema,
raw bodies, compiler trace, typed outcome, request counts, timing and
tokens in existing custody. Synthetic contexts have no real source path,
format, source hash or numerical data. The measured limits are 10 logical
and 10 physical attempts, zero corrections or SDK retries, temperature 0,
thinking disabled, cap 4096, 900 s provider timeout and the existing 10800 s
watchdog with 10 s grace.

## Remaining operational gate

Before live use, freeze the reviewed implementation, descriptor, ordered
case IDs, panel and schema hashes, config/SDK identity, exact worktree and
private evidence namespace. Run non-generative model/build/template/defaults
readiness over approved LAN execution. Obtain and independently accept a
separately authorized operational smoke proving this exact response model,
transport, accounting, custody and orderly stop, without consuming the
ten measured H1 observations. The existing A10 smoke does not certify the
H1 DTO; the H1 campaign selector intentionally rejects subsets. An
H1-specific smoke descriptor uses the existing canonical planner smoke
entrypoint, not the measured panel or a weakened selector. Then obtain
separate live campaign authority.

The operational fixture `H1-SMOKE` asks: “Could you display the natural gamma
radiation measurement?” Its synthetic, complete inventory contains one
addressable scalar GR curve (gAPI), with no real file or numerical data. The
compiler returns `NO_SUPPORTED_SEMANTICS`, not a coverage failure. The smoke
mode binds the request, synthetic fixture, system prompt, existing H1 schema,
harness, executable checkpoint, reviewed worktree and runtime identity.
Use `scripts/run_d5_live_campaign.sh planner-smoke h1-development AUTH_JSON`
only with this separate smoke authority: one generation and one physical
attempt, no correction or SDK retry, same thinking-off and output controls.

No live call, scientific result, holdout execution, mutation, activation
or merge was authorized in this implementation slice.

## Provider-free qualification

Python 3.12, existing virtualenv, `PYTHONPATH=src`:

```bash
.venv/bin/python -m pytest -q tests/test_code_mode_planner.py \
  tests/test_code_mode_workflow.py tests/test_d5_single_engine_convergence.py \
  tests/test_d5_5_model_io_custody.py tests/test_nlp_d5_live_semantic_qualification.py \
  -k 'not (final_population or c02)'
.venv/bin/python -m pytest -q tests/test_nlp_d5_live_semantic_qualification.py \
  -k 'first_pass_campaign or h1_planner or first_pass_authority'
```

297 scoped and 6 focused tests passed, both exit 0. The second run included
the final advertised-schema equality and compiler-trace assertions. Mock
HTTP transport observed all ten ordered cases with one logical and physical
attempt each, nine valid fixture responses and one deliberately invalid fixture,
zero corrections and no wire conversion. A separate mock timeout stopped the
campaign. The tests also covered exhaustive H08 inventory, equally eligible
H09 sources, production rejection, C2 blocking, tampering and unconditional
termination without a trace callback. Mock validity counts are not model results.
Local tests ran outside the sandbox after a one-line asyncio executor reproducer
isolated sandbox teardown hangs. No inference endpoint was contacted. Scoped
Ruff/format, compilation, shell syntax, diff, manifest and reachability checks
passed. This was not a repository-wide run.
