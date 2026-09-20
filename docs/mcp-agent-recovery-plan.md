# MCP Agent Simplification And Recovery Plan

> **Historical supersession notice (2026-09-19):** This document records the
> August `0.6-L` recovery program and is no longer the active agent-architecture
> authority. Later Code Mode migration work adopted LangGraph and progressed
> through CM-53. EXP-TW-00 through EXP-TW-08 subsequently revised the
> section-worker boundary toward a static typed semantic worker and
> deterministic compiler. Read
> [`agent-code-mode-architecture.md`](agent-code-mode-architecture.md),
> [`wellplot_agentic_code_mode_migration_plan.md`](wellplot_agentic_code_mode_migration_plan.md),
> and the [consolidated typed-worker memory](evaluations/agent-code-mode/EXP-TW-consolidated-development-memory.md)
> for active guidance. The L0–L* body below is preserved as historical
> evidence.

Last updated: 2026-08-14

Status: historical implementation record; L1, L2, and L3 implemented, L4
evidence preserved

## Purpose

This plan replaces the unsuccessful provider-compiler direction with an
evaluation-driven, minimal MCP agent architecture. It exists to prevent another
cycle in which a notebook failure produces a new compiler layer, a large code
increase, and no measurable improvement in user task completion.

The deterministic authoring contract is not being discarded. Canonical
Pydantic models, `AuthoringService`, defaults, validation, rendering, and safe
persistence remain the product foundation. The correction is focused on the
model-facing tool surface and `wellplot.agent` orchestration.

This document records the historical `0.6-L` release-recovery sequence. It
superseded the
provider-facing compilation architecture described by `0.6-G`, `0.6-J`, and
`0.6-K`, including request inventories, scoped intent submissions, generated
branch-operation submission tools, and automatic compatibility routing. Those
sections remain in the implementation plan as historical records only.

## Reference Diagnostic

The unchanged initial LAS notebook request currently follows this sequence:

1. the provider successfully calls `submit_request_inventory`;
2. preserved clauses are still treated as provider compilation work;
3. a second provider call is forced to call a generated tool such as
   `submit_report_operations`;
4. the provider returns prose instead of the required function call;
5. the adapter blocks before any deterministic mutation;
6. the result reports preserved or uncompiled request items as skipped.

Measured repository state at the diagnostic commit:

- changes since the compact inventory baseline: 10,980 insertions and 607
  deletions across 37 files
- new runtime additions under `wellplot.agent` in that interval: approximately
  4,523 lines
- `src/wellplot/agent/core.py`: 7,155 lines
- registered MCP tools: 58
- provider branch static input: approximately 121,000 characters of operation
  definitions and defaults
- generated provider tool schemas: approximately 18,000 to 59,000 characters
  per branch
- effective provider contract before request-specific state: approximately
  145,000 to 180,000 characters

The acceptance suite primarily uses recorded backends that submit exact valid
payloads. Those tests prove deterministic validation and execution, but they do
not prove that a real model can discover, select, and call the tools.

## Research-Based Requirements

The recovery program follows these external design recommendations:

- start with simple, composable agent loops and add complexity only after an
  evaluation demonstrates a need
- expose a few clear, distinct, high-impact tools rather than overlapping API
  wrappers
- keep model context to the smallest high-signal subset needed for the current
  action
- use stable model-controlled MCP tools rather than generated per-request tool
  languages
- evaluate verifiable end states, tool errors, tool calls, latency, and token
  use with real providers
- preserve one way to solve a problem and degrade gracefully across models of
  different sophistication

Primary references:

- [Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [MCP design principles](https://modelcontextprotocol.io/community/design-principles)
- [MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)

## Non-Negotiable Architecture Rules

1. There is one provider-backed natural-language authoring path.
2. The model invokes stable MCP tools; it does not emit an intermediate
   `submit_*` inventory, intent, plan, or operation language.
3. `AuthoringService` and canonical Pydantic requests remain the only mutation
   authority behind those tools.
4. The model never receives the complete canonical document schema, operation
   union, hierarchy catalog, or defaults catalog in one request.
5. Tools load only the current object, relevant source-channel facts, and
   applicable defaults.
6. Tool results contain canonical before/after evidence and actionable errors;
   provider prose is never authoritative completion evidence.
7. Preserve instructions do not become synthetic mutation work; scoped tools
   and canonical diffs must expose any unrelated change.
8. No packet, CBL, resistivity, porosity, caliper, or vendor-specific routing is
   permitted in agent orchestration. Scientific defaults remain optional data.
9. No LangGraph, persistent memory, second planner, or new framework is added
   in this program.
10. A slice cannot close unless its predefined metric moves in the expected
    direction without regressing the existing deterministic contract.

## Accountability Contract

### Required Slice Record

Each slice must add a short evidence record under
`docs/evaluations/mcp-agent/` containing:

- slice id and commit id
- user-visible problem addressed
- baseline and post-change evaluation results
- production lines added, deleted, and net change
- model-facing tool count and combined JSON Schema characters
- static provider-context characters for each evaluated request
- provider rounds, tool calls, tool errors, latency, and tokens when available
- deterministic test, adapter test, live-eval, Ruff, and docs results
- known failures and an explicit proceed/stop decision

An implementation note or passing recorded backend is not evidence of model
capability. Live provider results must be labelled separately from deterministic
and adapter tests.

### Change Budgets

- default maximum per slice: 300 net new production lines
- default maximum per focused ergonomic correction: 200 net new production
  lines
- any larger increase requires stopping before commit and obtaining explicit
  approval with a simpler alternative documented
- test data must be table-driven; do not add a new bespoke fake provider class
  for every prompt
- the completed `0.6-L` program must be at least 2,500 production lines smaller
  than the diagnostic baseline
- deletion targets never justify deleting deterministic validation or
  weakening an assertion

### Context And Tool Budgets

- model-facing authoring tools: target 12, hard limit 16 without new evaluation
  evidence and approval
- combined loaded tool JSON Schema: target at most 40,000 characters
- any individual model-facing tool schema: at most 8,000 characters
- static instructions plus loaded tools: target at most 50,000 characters
- no provider request may contain the complete authoring document schema or
  complete canonical operation union
- context growth greater than 5 percent in any slice is a stop condition unless
  task success also improves and the tradeoff is approved

### Progress Rules

- implement and commit one slice at a time
- do not begin the next slice while the current slice has a failed exit gate
- do not change notebook prompts to make an implementation pass
- do not claim a slice is implemented until its evidence record exists
- if a change does not improve its named task outcome or simplify the measured
  architecture, revert it within the slice rather than carrying it forward
- if two consecutive slices fail to improve the live task pass rate, stop the
  program and review the architecture before further implementation

### Read-Only Stall Recovery

The stable loop now has one bounded host-side recovery guard for a specific
failure mode: after three successful read-only inspections with no persisted
mutation, it may resolve an explicit `add` or `create` track request from the
asset-backed track, form, and style catalogs. The guard executes the existing
stable MCP mutations in dependency order, reads back the track and bindings,
and stops only after validation and canonical postconditions pass.

The guard is not a second provider loop and contains no CBL, resistivity, or
other family-specific Python logic. It refuses an uncatalogued or ambiguous
family, reports the reason, and leaves ordinary provider authoring available
for requests outside this narrow recovery shape. Acceptance tests cover a
catalog-resolved resistivity request, unknown-family refusal, persisted
scale/channel postconditions, and the stalled-loop diagnostic path.

### Standard Compliance Commands

Slice `0.6-L0` must implement the first two commands below. Later slices must
use the same interfaces so measurements remain comparable:

```bash
uv run python scripts/run_agent_evals.py --suite development --mode deterministic
uv run python scripts/check_agent_architecture.py --baseline docs/evaluations/mcp-agent/0.6-L0.json
uv run pytest -q tests/test_authoring_service.py tests/test_mcp_service.py tests/test_mcp_server.py
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mkdocs build --strict
```

Live capability runs require an explicit opt-in and provider name. The runner
must load credentials through the existing ignored credential mechanism and
must redact endpoint query values, authorization headers, and tool arguments
that could contain secrets:

```bash
WELLPLOT_RUN_LIVE_AGENT_EVALS=1 uv run python scripts/run_agent_evals.py \
  --suite development --mode live --provider openai
```

Every evidence record must list the exact commands run. A skipped live command
is reported as `not_run`, not as passing acceptance.

## Evaluation Model

### Outcome Grading

Evaluations grade the persisted canonical document and rendered output, not an
expected tool-call sequence. Every task defines:

- unchanged input prompt
- clean starter document and source data
- required canonical postconditions
- prohibited unrelated mutations
- expected ambiguity or unsupported result, when applicable
- final validation and render expectation

Tool traces remain diagnostic metrics. A task may use any valid sequence as
long as its persisted end state is correct and isolated.

### Development Task Set

1. create the initial open-hole draft while preserving section and track state
2. add one isolated remarks block
3. fill natural-language open-hole header values, including measured mud values
4. add and style SP on an existing overview track
5. create a logarithmic resistivity track with deep, medium, and shallow curves
6. create an uncatalogued scalar track using generic form defaults
7. create duplicate/mirrored scalar bindings and a fill
8. create and configure an array/raster track
9. add, update, and remove annotation objects
10. apply page, output, depth, and section-view settings
11. build flexible main/repeat sections without packet-specific routing
12. reject an unavailable channel and an ambiguous target without persistence

### Held-Out Generalization Set

The held-out set must not be used to shape prompts or tool descriptions before
the final slice:

- a caliper workflow with mirrored bindings
- a custom project-specific scalar track and unknown channel mnemonic
- cased-hole header ingestion with extra irrelevant source text
- a mixed section, raster, and annotation request

### Provider Matrix

- one release-grade OpenAI provider/model
- one NVIDIA Cloud OpenAI-compatible provider/model
- one local Unsloth/OpenAI-compatible provider/model

Deterministic MCP tests must pass at 100 percent. Release-grade live acceptance
requires at least 90 percent aggregate task success across three runs per task
on the primary provider and at least 80 percent on one OpenAI-compatible
provider. Every provider must report unsupported tool calling truthfully and
without mutation; a local model's lower capability is not hidden by fallback to
another provider.

## Slice 0.6-L0: Freeze And Baseline

Goal:

- stop speculative production changes and establish a reproducible capability
  baseline

Work:

- capture the current LAS failures as end-state evaluation tasks
- add a data-driven evaluation runner that can execute deterministic, adapter,
  and opt-in live-provider modes
- record task outcome, canonical diff, tool trace, rounds, errors, latency,
  context size, and token usage where available
- record current production-line, tool-count, and schema-size measurements
- separate capability evals from regression tests in naming and reports

Production budget: zero behavior changes; instrumentation only must stay below
150 production lines.

Compliance tests:

- the initial-draft and remarks failures reproduce from clean drafts
- a deliberately wrong final document fails even when a recorded backend claims
  success
- a correct final document passes regardless of valid tool-call ordering
- live mode cannot run without an explicit environment flag and never records
  credentials

Exit gate:

- baseline evidence exists for all development tasks that currently reach the
  agent, with unimplemented tasks explicitly marked rather than omitted
- no user notebook or prompt is modified
- no new route, tool, default, or provider retry is introduced

Expected metric movement: none. This slice establishes trustworthy measurement.

L0 implementation evidence:

- scripts/run_agent_evals.py provides deterministic, persisted-document adapter,
  and explicitly gated live modes.
- scripts/check_agent_architecture.py records line, tool-count, and schema-size
  deltas against the baseline.
- tests/evals/agent_tasks.json contains all twelve development tasks with named
  starting fixtures, canonical preconditions, expected final-state assertions,
  allowed changes, and prohibited changes.
- The baseline and architecture-check reports are stored under
  docs/evaluations/mcp-agent/0.6-L0.json and
  docs/evaluations/mcp-agent/0.6-L0-architecture-check.json.

## Slice 0.6-L1: Stable Model-Facing Tool Contract

Goal:

- define the smallest stable MCP tool profile that can express the development
  task set without exposing internal compiler artifacts

Candidate responsibilities:

- draft lifecycle
- scoped authoring inspection
- source inspection and channel availability
- header editing
- remarks editing
- section editing
- track editing
- curve-binding editing
- raster-binding editing
- fill editing
- annotation editing
- page/output/depth editing
- validation
- preview/render

Create, update, remove, move, and clear variants should remain inside their
object-family tool schema rather than becoming separate overlapping tool names.
The exact names are finalized by the schema-budget and tool-selection eval, not
by preserving the current 58-tool roster.

Work:

- map every development task to one or more stable tool responsibilities
- generate input and output schemas from existing canonical service requests
- specify concise and detailed response modes for inspections
- define standard mutation results with target identity, changed flag,
  before/after state, warnings, and actionable next steps
- mark read-only, idempotent, and destructive behavior with MCP annotations
- produce a machine-checkable tool/context budget report

Production budget: 250 net new production lines. Prefer schema adapters and
deletions over new domain models.

Compliance tests:

- no candidate schema contains `AuthoringDocumentIntent`, the complete document
  schema, or the complete canonical operation union
- every tool has one distinct user-facing purpose
- every development task is expressible, while held-out scientific families do
  not require new tool names
- combined tool and static-context budgets pass
- at least two evaluated models select the correct tool family for isolated
  header, remarks, track, curve, raster, and page requests

Exit gate:

- the profile has at most 16 tools and at most 40,000 combined schema
  characters
- adding a seventeenth tool requires a demonstrated task failure that cannot be
  solved by an existing distinct responsibility
- the contract is reviewed before server or agent routing changes

Expected metric movement: provider contract size falls by at least 70 percent
from the diagnostic branch contract.

L1 implementation evidence:

- `src/wellplot/mcp/assets/defaults/stable_tool_contract.yaml` defines the
  approved 16-responsibility catalog without CBL-, caliper-, or other
  family-specific tool names.
- `src/wellplot/agent/tool_contract.py` projects that catalog into compact
  schemas derived from existing canonical request models. It is 249 production
  lines and does not register tools or change routing.
- `tests/test_agent_tool_contract.py` verifies distinct responsibilities,
  standard mutation envelopes, MCP annotations, task coverage, and exclusion
  of internal compiler unions.
- `docs/evaluations/mcp-agent/0.6-L1.json` records 16 tools and 18,308 combined
  schema characters versus the 104,728-character diagnostic contract, an
  82.5% reduction. The deterministic controls and architecture gate pass.
- Provider/model selection tests are intentionally not claimed in this slice;
  they require the L2 MCP projection and an explicit live-provider budget.

## Slice 0.6-L2: Thin MCP Projection

Goal:

- make the stable profile a thin projection of the existing deterministic
  service without creating another mutation implementation

Work:

- implement or consolidate the approved model-facing tools directly over
  `AuthoringService`
- remove superseded overlapping MCP wrappers in the same slice; do not leave a
  second public tool profile as fallback
- keep granular canonical request models and service methods available to the
  Python API
- return canonical read-after-write evidence from every mutation
- return only relevant context and defaults from inspections
- make omitted values, explicit null/clear, and supplied values distinguishable

Production budget: net zero or negative production lines. Any positive net
change requires approval before commit.

Compliance tests:

- MCP and direct `AuthoringService` calls produce identical canonical results
- invalid operations fail before persistence
- each mutation returns an exact before/after object and validation status
- tool list, schema, annotation, and response budgets pass
- no MCP tool contains provider logic, model prompts, or long-lived memory

Exit gate:

- deterministic service/MCP parity is 100 percent for every approved tool
- old overlapping tools are removed or explicitly retained as non-authoring
  lifecycle tools with a documented distinct purpose
- no test requires a provider

Expected metric movement: fewer model-facing tools, smaller combined schemas,
and no deterministic capability regression.

L2 implementation evidence:

- `src/wellplot/mcp/server.py` now registers only the stable profile through
  `register_stable_tools`; the previous overlapping wrapper roster is no
  longer exposed by the MCP server. The granular service functions remain
  available to the Python API.
- `src/wellplot/mcp/stable.py` is a thin dispatch/projection layer. Mutations
  return `ok`, `changed`, target identity, canonical before/after snapshots,
  warnings, and next steps. Persistence remains delegated to the existing
  deterministic service and typed authoring models.
- The model-facing profile is 16 tools with 16,529 combined schema
  characters. The L2 architecture check records a reduction from the L1
  baseline of 58 registered tools to 16, with no provider logic in the MCP
  layer.
- `tests/test_mcp_stable.py` covers profile registration, typed parity for a
  section mutation, invalid-operation non-persistence, and validation. The
  stdio integration test also exercises source inspection, draft cloning,
  canonical inspection, section/track/curve/remarks mutations, validation,
  preview, rendering, resources, prompts, and resource templates.
- Deterministic evidence: `582 passed, 2 skipped`; the development eval
  controls and architecture check pass. No live-provider result is claimed.
- L3 remains required before notebook acceptance: `wellplot.agent` still
  routes through the superseded request-inventory/compiler path and has not
  yet been switched to invoke these stable MCP tools directly.

## Slice 0.6-L3: Simple MCP Agent Loop

Goal:

- replace request inventory and generated submission compilers with a direct
  model/MCP tool loop

Flow:

1. create or open the draft deterministically
2. expose the stable MCP authoring profile
3. let the provider inspect and invoke actual MCP tools
4. feed concise tool results back to the provider
5. stop on provider completion, deterministic error, or bounded round limit
6. build `AuthoringResult` only from persisted tool outcomes and final
   validation

Work:

- implement the loop without LangGraph or another orchestration framework
- use provider-native automatic tool selection; do not require a generated
  final submission tool
- keep `run()` and `revise()` on the same loop
- make `plan()` an inspectable dry-run over the same stable tool requests or
  temporarily report it unsupported; do not keep a second planning language
- enforce preserve constraints through mutation isolation and final diff checks
- fail truthfully when the provider does not support tool calling

Production budget: at most 300 new lines, and the route-switch commit must be
net negative after removing replaced normal-path orchestration.

Compliance tests:

- production traces contain actual MCP tool names and no `submit_*` calls
- remarks-only work cannot mutate headings, tracks, or bindings
- a provider prose response without any mutation cannot complete an authoring
  request; after verified mutations it may end the loop but cannot add to the
  authoritative completed list
- no automatic fallback enters desired-state or provider-to-MCP mutation code
- initial draft and remarks tasks improve over the L0 live baseline

Exit gate:

- `run()` and `revise()` have one provider-backed route
- initial draft and remarks pass on the primary provider in at least two of
  three runs
- deterministic failures contain the exact failed tool and unchanged document
  evidence

Expected metric movement: first real increase in end-state task pass rate,
fewer provider stages, and lower rounds/tokens than L0.

## Slice 0.6-L3: Simple MCP Agent Loop

Status: implemented and passed deterministic acceptance gates.

The host agent now detects the complete stable MCP catalog and routes ordinary
`run()` and `revise()` requests through the existing bounded provider tool loop.
The stable route creates or clones the draft once, exposes only the compact
stable tool profile, records each tool payload and error, and finalizes from
stable validation, inspection, and preview reads. Legacy runtimes and explicit
typed workflows retain their existing route for compatibility.

Compliance evidence:

- `tests/test_agent_stable_loop.py` proves exact stable-tool selection, round
  propagation, mutation path injection, persisted change evidence, validation,
  previews, and absence of legacy draft verbs.
- Stable route implementation adds 297 net production lines against the L2
  architecture baseline, below the 300-line slice budget.
- Stable model-facing surface remains 16 tools and 16,529 combined schema
  characters; no generated submit tool or schema growth was introduced.
- Targeted suite: `79 passed, 2 skipped` across stable-loop, agent, stable MCP,
  and stdio-server tests.
- Live provider capability was not claimed; provider rounds, latency, and token
  use remain pending the L6 matrix.

Exit decision: proceed to L4. Do not add another planner, compiler, or provider
specific route to address failures; classify the next failure against the
stable tool contract and add one held-out deterministic evaluation first.

## Slice 0.6-L4: Evidence-Driven Ergonomic Corrections

Goal:

- correct only deterministic tool or default behavior proven inadequate by the
  task matrix

### L4.1 Remarks Operation Guidance

Status: deterministic contract correction implemented; live capability gate
pending.

The `remarks_only` task exposed a generic operation-shape gap: the stable
`edit_remarks` tool advertised its operation enum but not the payload required
by each operation. Its description now states the compact mapping for add,
update, remove, move, and clear. The request prompt and routing are unchanged.

Evidence:

- Named evaluation: `remarks_only`.
- `tests/test_agent_tool_contract.py` asserts every operation-shape cue.
- Focused contract/MCP/agent tests: `11 passed`.
- Tool count and input/output schema sizes are unchanged: 16 tools and 16,529
  combined schema characters.
- Description context increased from 845 to 880 characters, a 4.1 percent
  increase and below the five percent budget.
- No production Python lines were added and no domain-specific routing was
  introduced.
- Live provider confirmation is not available in this deterministic run;
  `remarks_only` remains ungraded for real-model task completion.

Decision: hold L4 exit until the unchanged `remarks_only` prompt is exercised
with a configured provider. Do not add another correction until that result is
known.

Allowed correction classes:

- natural header aliases and human-readable ambiguity
- generic form completion for sections and tracks
- source-channel resolution and compatibility
- explicit scale, style, width, ordering, and fill precedence
- concise tool descriptions and actionable validation responses

Each correction is a separately committed sub-slice and must name the failed
evaluation ids it addresses. A catalogued and an uncatalogued or held-out-style
case must exercise the same generic behavior.

Production budget: 200 net new lines per sub-slice.

Compliance tests:

- the named failed eval becomes correct without changing its prompt
- at least one unrelated domain task remains unchanged
- no scientific family name appears in agent routing conditions
- explicit user values override defaults exactly
- unknown but source-confirmed channels remain constructible
- context and schema budgets do not regress by more than 5 percent

Exit gate:

- SP, resistivity, custom scalar, raster, annotation, and page/output tasks meet
  their canonical postconditions
- every correction has a generic deterministic test and live evidence
- no request-specific shortcut or blueprint authority is introduced

Expected metric movement: task pass rate increases for the named failure class
with no mutation-isolation or held-out regression.

## Slice 0.6-L5: Delete Superseded Compiler Architecture

Goal:

- remove the architecture that made the model reconstruct internal operations
  instead of using MCP tools

Removal scope:

- provider request inventory and work-unit compilation
- generated `submit_*_intent` and `submit_*_operations` contracts
- branch compiler and reconciliation bridge used only by natural-language
  provider compilation
- automatic desired-state compatibility routing
- prompt text, diagnostics, and recorded-provider fixtures that exist only for
  those paths

Explicit caller-supplied deterministic request objects may remain as Python API
functionality, but they must not be reachable as an automatic natural-language
fallback.

Production budget: deletion slice. The primary gate is removal of all named
paths; expected deletion is 2,500 to 4,500 production lines.

Compliance tests:

- architecture checks find no production `submit_request_inventory`,
  `submit_*_intent`, or `submit_*_operations` provider tools
- natural-language `run()` and `revise()` cannot import the old compiler modules
- canonical service, YAML, Python API, renderer, and MCP parity suites still
  pass
- development task success is no worse than L4

Exit gate:

- one provider-backed route remains
- cumulative production code is at least 2,500 lines below L0
- obsolete tests are removed only after equivalent end-state coverage exists

Expected metric movement: major production-line and maintenance-surface
reduction with unchanged or improved task success.

## Slice 0.6-L6: Provider Portability And Graceful Failure

Goal:

- prove that the stable tools work across provider adapters without assuming
  identical function-calling behavior

Work:

- run the full development matrix against the provider matrix
- record provider capability, tool selection, malformed calls, truncation,
  latency, rounds, and token use
- add a small capability diagnostic for models that cannot call tools reliably
- ensure configured provider identity is visible and no silent provider
  fallback exists
- adjust adapter normalization only for protocol-level differences demonstrated
  by transcripts

Production budget: 250 net new production lines.

Compliance tests:

- provider identity and endpoint are reported without exposing credentials
- a missing or malformed tool call cannot be reported as a completed mutation
- connection closure, timeout, truncation, and unsupported tools have distinct
  diagnostics
- no adapter contains well-log-domain routing
- context and tool schemas are identical across compatible providers

Exit gate:

- primary and one compatible provider meet the release thresholds
- local-provider failures are truthful, isolated, and reproducible
- no provider-specific branch exists above the transport/response adapter

Expected metric movement: higher cross-provider completion and zero silent
fallback or false-success outcomes.

## Slice 0.6-L7: Held-Out, Notebook, And Release Closure

Goal:

- prove generalization and close `0.6.0` only after user-visible workflows work

Work:

- reveal and run the held-out generalization set
- run the canonical LAS notebook from a clean project with unchanged prompts
- run the CBL/VDL notebook as a stress test, not as authority
- run full deterministic, MCP, adapter, agent, docs, package, and installed-wheel
  checks
- publish the final evidence and architecture metrics
- update user documentation and release notes to the actual shipped surface

Production budget: zero new production behavior. Any failure returns to the
smallest responsible earlier slice.

Compliance tests:

- held-out tasks meet the same canonical and isolation graders
- notebook outputs contain requested headers, remarks, structures, scales,
  styles, arrays, and annotations
- no user prompt requires internal ids, YAML paths, or deterministic keys
- code, tool, schema, context, provider, and task metrics satisfy all budgets

Exit gate:

- deterministic tests pass at 100 percent
- live provider thresholds pass
- canonical notebook completes without prompt edits or manual YAML repair
- cumulative production code is at least 2,500 lines smaller than L0
- `0.6.0` release documentation accurately states provider limitations

Expected metric movement: held-out evidence confirms that improvements
generalize beyond the development notebooks.

## Recommendation Traceability

| Recommendation | Enforced by | Compliance evidence |
| --- | --- | --- |
| Start simple | L3, L5 | one loop, one route, compiler symbols absent |
| Use a few distinct tools | L1, L2 | tool count, schema budget, selection eval |
| Keep context high-signal | L1-L4 | captured static/context characters and tokens |
| Let models control stable MCP tools | L2, L3 | traces contain actual MCP names, no `submit_*` |
| Keep mutations deterministic | L2 | service parity and exact before/after evidence |
| Evaluate outcomes, not scripted behavior | L0, L7 | canonical end-state and render graders |
| Avoid overfitting | L4, L7 | uncatalogued and held-out tasks |
| Degrade across providers | L6 | provider matrix and truthful failure tests |
| Keep one solution path | L3, L5 | architecture guard and deleted fallbacks |
| Control maintenance growth | all slices | per-slice line budgets and cumulative deletion |

## Release Rule

`0.6.0` must not be published because unit tests pass while the canonical
notebook fails. Release requires the complete `0.6-L` evidence chain. A failed
gate blocks the next slice and the release; it does not authorize another
parallel compiler, request-specific shortcut, retry increase, or hidden
blueprint.
