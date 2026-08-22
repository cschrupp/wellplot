# Wellplot MCP Stabilization & Remediation Playbook

**Purpose:** Convert the 2026-08-20 MCP code review into an executable, gated remediation program that fixes every identified issue without re-introducing compensating complexity.

**Applies to:** Wellplot MCP server, stable tool contract, deterministic authoring service, MCP prompts/resources, host agent loop, tests/evals, packaging, security, observability, and protocol migration.

**Primary objective:** Make the deterministic Wellplot authoring system appear to an LLM exactly as intended: truthful schemas, compact results, reliable state transitions, deterministic validation, and minimal host-side semantic policing.

---

## 1. Executive Summary

The Wellplot codebase does not need a ground-up rewrite. The canonical domain model, the reduced 17-tool taxonomy, the authoring service as mutation authority, root-path confinement, and the use of deterministic validation are solid foundations.

The highest-risk failures are concentrated at the **MCP boundary** and the **agent compensation layer**:

1. The rich JSON Schemas designed in `stable_tool_contract.yaml` are not faithfully exposed on the real MCP wire surface.
2. Tool responses are so large that they recreate the context-pressure problem the tool-count reduction was meant to solve.
3. Some shipped example documents can be created but fail during the first unrelated mutation, violating round-trip invariants.
4. Structural editing is coupled to LAS/DLIS/render dependencies that should only be required for source- or render-level validation.
5. Several advertised parameters are ignored or misleading.
6. MCP prompt templates still instruct clients to call old tools that no longer exist.
7. Output schemas are designed but are not faithfully wired to real MCP responses, and some actual responses would violate the intended schemas.
8. The host controller performs too much natural-language interpretation, scope policing, fallback planning, and postcondition inference.
9. Existing tests validate the intended contract rather than the actual wire contract, allowing false-green results.
10. Live provider evaluation is not yet strong enough to justify additional recovery heuristics.
11. The implementation is still tied to the MCP Python SDK v1 / older protocol lifecycle.
12. Tool annotations misclassify read-only operations.
13. The MCP subprocess inherits a broader environment than necessary, including secrets it does not need.
14. MCP runtime observability is insufficient for reliable diagnosis.
15. Historical agent paths and large controller functions remain after the simplification effort.
16. Documentation and internal counts are drifting from the actual stable surface.

The remediation should proceed in **gated slices**. Later slices must not compensate for failures in earlier slices. In particular, no new agent heuristics should be added until the real wire contract, result budgets, and deterministic mutation invariants pass.

---

## 2. Non-Negotiable Engineering Principles

These principles govern every slice in this playbook.

### P1. One source of truth for each contract

The same typed model or canonical schema must drive:

- MCP `tools/list` input schema,
- server-side argument validation,
- agent-facing tool documentation,
- contract tests,
- and, where applicable, generated examples.

Do not maintain a “good schema” for tests and a separately inferred weaker schema for MCP.

### P2. Tool results are part of the context budget

Schema reduction is meaningless if normal tool calls return 40–70 KB payloads. Default tool results must be compact and targeted. Full document state belongs behind explicit inspection or resource retrieval.

### P3. Every exposed parameter must matter

If an argument is in the schema, it must alter behavior, constrain behavior, or be removed. No “decorative” arguments.

### P4. A created document must be immediately editable

Any starter/example accepted by `create_draft` must pass canonical load, validation, serialization, reload, and unrelated mutation tests.

### P5. Structural validity is not renderability

Editing a title, remark, page setting, or section property must not require LAS/DLIS parser dependencies or a full render pipeline unless the operation actually depends on source/render semantics.

### P6. The host is not a second planner

The LLM should reason from truthful tool contracts. The host should enforce bounded execution, deterministic safety rules, transactions, timeouts, and final validation—not duplicate natural-language reasoning with regexes and fallback planners.

### P7. Real-wire tests outrank profile tests

A contract is correct only if a real MCP client sees and exercises it successfully.

### P8. No feature work during stabilization

Until Slice 6 is complete, do not increase the tool count, add new recovery branches, or add new authoring capabilities unless required to fix a blocking defect.

---

## 3. Target Architecture

The target architecture is intentionally simple:

```text
User
  |
  v
LLM / MCP Client
  |
  | exact, typed MCP schemas
  v
MCP Server
  |  ~15–17 stable tools
  |  compact structured results
  v
AuthoringService
  |  sole mutation authority
  v
Canonical Wellplot Models
  |
  +--> structural validation
  +--> source adapters (LAS / DLIS)
  +--> renderer / preview
```

Large or infrequently needed state should be accessed separately:

```text
MCP Resources
  +--> full document representations
  +--> large catalogs / vocabularies
  +--> example source files
  +--> reconstruction examples
  +--> large diagnostics
```

The host agent loop should eventually be reduced to:

```text
bounded rounds
+ tool-call dispatch
+ timeout / error accounting
+ transaction / rollback mechanics
+ final deterministic validation
+ final response assembly
```

---

## 4. Stabilization Success Metrics

The remediation is complete only when the following are true.

### Contract correctness

- 100% equality between intended tool schemas and real `tools/list` schemas.
- 100% of tool results validate against their advertised output schema.
- 0 ignored or no-op public parameters.
- 0 stale tool names in shipped MCP prompts or user-facing docs.

### Result efficiency

For default tool calls:

- P50 serialized result size: **< 4 KB**.
- P95 serialized result size: **< 12 KB**.
- Hard default cap: **20 KB** unless the call explicitly requests full detail.
- `detail="summary"` must be materially smaller than `detail="full"`.
- Large state must be retrievable by resource or explicit full-detail call.

### Deterministic correctness

- Every packaged example passes create -> canonical load -> validate -> serialize -> reload.
- Every packaged example survives one unrelated mutation from every mutation family.
- Structural-only edits do not require LAS/DLIS packages.
- Render validation still fails clearly when required source/render dependencies are missing.

### Agent reliability

Before removing legacy recovery behavior, establish a live-provider baseline. Final release target:

- >= 90% Pass@1 on the stable core task suite across each supported frontier provider.
- No provider regresses by >5 percentage points from the best pre-cleanup baseline.
- Tool-call error rate <= 5% on valid tasks.
- Host fallback rate <= 10% and trending toward zero on happy-path tasks.
- No recovery heuristic is retained without an observed eval benefit.

### Operational quality

- Every MCP tool call has request ID, duration, result size, error type, and mutation status in structured logs.
- MCP subprocess receives only explicitly required environment variables.
- Current protocol/SDK integration uses only public APIs.

---

## 5. Issue Register and Traceability

| ID | Issue | Severity | Primary Slice(s) |
|---|---|---:|---|
| I01 | Intended input JSON Schema is not the real MCP wire schema | Critical | S1, S6 |
| I02 | Tool-result payloads recreate context bloat; summary/full ineffective | Critical | S2 |
| I03 | Packaged examples violate create/edit round-trip invariant | Critical | S3 |
| I04 | Structural mutations require LAS/DLIS/render validation | High | S4 |
| I05 | Advertised parameters are ignored or misleading | High | S1, S5 |
| I06 | MCP prompts reference removed tool names; prompt payload is bloated | High | S5 |
| I07 | Intended output schemas are not wired and actual outputs are not schema-safe | High | S1, S2, S6 |
| I08 | Host agent performs excessive semantic policing and fallback planning | High | S7 |
| I09 | Tests validate profile schemas rather than real MCP schemas; false-green condition | High | S0, S6 |
| I10 | Live-provider eval evidence is incomplete | High | S0, S6 |
| I11 | MCP Python SDK v1 / old lifecycle / private API usage | High | S9 |
| I12 | Tool annotations misclassify read-only/idempotent tools | Medium | S1 |
| I13 | MCP subprocess inherits unnecessary environment/secrets | Medium | S8 |
| I14 | Structured MCP observability is insufficient | Medium | S0, S8 |
| I15 | Large controller/service modules and historical paths remain | Medium | S7, S10 |
| I16 | README, prompt docs, tool-count comments, and recovery docs drift from reality | Medium | S5, S10 |

---

# 6. Remediation Sequence

The recommended dependency order is:

```text
S0 Baseline & Freeze
        |
        v
S1 Truthful Wire Contract
        |
        +---------> S2 Compact Results
        |                |
        |                v
        |           S5 Parameter/Prompt Cleanup
        |
        +---------> S3 Round-Trip Invariants
        |                |
        |                v
        |           S4 Validation Separation
        |
        +--------------------------+
                                   v
                          S6 Real-Wire + Live Evals
                                   |
                    +--------------+--------------+
                    v                             v
              S7 Agent Simplification      S8 Security/Observability
                    |                             |
                    +--------------+--------------+
                                   v
                            S9 MCP SDK v2
                                   |
                                   v
                           S10 Cleanup & Docs
```

Slices S2 and S3 can proceed in parallel after S1 if separate developers are available. S7 must not start before S6 provides real evidence.

---

# 7. Slice S0 — Baseline, Freeze, and Instrumentation

## Goal

Create a trustworthy before-state so every later simplification can be measured and rolled back safely.

## Issues addressed

I09, I10, I14; establishes evidence for all later slices.

## Scope

Do not change behavior in this slice except to add non-invasive instrumentation and missing fixtures.

## Procedure

### Step 1 — Freeze the stable surface

Record the exact current list of 17 tools and their order. Store it in a versioned baseline fixture.

Capture for every tool:

- name,
- description,
- real `inputSchema` returned by a real MCP client,
- real `outputSchema` if present,
- annotations,
- serialized schema size.

Store this as `tests/fixtures/mcp_contract_baseline_v1.json` or equivalent.

### Step 2 — Capture real MCP wire output

Add a small test utility that starts the server exactly as production does and executes:

```text
connect
list_tools
list_resources
list_prompts
```

Do not use `stable_tool_profile()` to synthesize the result.

### Step 3 — Add result-size instrumentation

Wrap tool dispatch to record:

- tool name,
- serialized argument bytes/chars,
- serialized result bytes/chars,
- elapsed milliseconds,
- success/error,
- changed/not changed,
- exception class.

Do not log the full document or source data.

### Step 4 — Repair missing test fixtures

The review bundle could not collect the MCP integration suite because `examples/cbl_main.log.yaml` was absent. Decide whether the repository itself is missing the fixture or only the review bundle omitted it. Ensure production CI can collect all MCP integration tests from a clean checkout/archive.

### Step 5 — Run the current deterministic and live baselines

Run:

- current contract tests,
- current MCP integration tests,
- all packaged example tests,
- the 12-task stable agent eval set,
- at least two live frontier providers if credentials are available.

Record:

- task success,
- tool calls,
- retries,
- host fallbacks,
- rollbacks,
- tool errors,
- input token estimate,
- tool-result character/token volume,
- total latency.

### Step 6 — Declare a stabilization freeze

Until S6 completes:

- no new tools,
- no new agent fallback branches,
- no new prompt heuristics,
- no new authoring feature families.

Bug fixes are allowed.

## Tests

- Clean checkout can collect the entire test suite.
- Real MCP server boots in the same way as production.
- Baseline contract fixture is generated from live MCP output.
- Instrumentation does not change tool result content.

## Acceptance criteria

- A versioned baseline exists.
- All current failing tests are enumerated rather than hidden.
- At least one end-to-end live MCP trace is captured with result sizes.
- No subsequent slice proceeds without this baseline committed.

## Suggested PR

`stabilization/S0-baseline-and-wire-capture`

---

# 8. Slice S1 — Make the MCP Wire Contract Truthful

## Goal

Ensure the schema the model sees is the same schema the repository intends and validates.

## Issues addressed

I01, I05, I07, I12.

## Core design decision

Make typed request/response models the **single source of truth**. Generate:

- server validation,
- `tools/list` schemas,
- test fixtures,
- documentation snippets,
- and contract metrics

from those same models.

Do not keep a separately handcrafted YAML contract if it can drift from runtime behavior. If the YAML must remain for packaging/review reasons, generate it from the typed models rather than the reverse.

## Procedure

### Step 1 — Inventory every field in the 17 tools

For each tool, classify each parameter as:

- always required,
- optional,
- required for a specific operation,
- enum/literal,
- constrained numeric,
- nested structured object,
- deprecated/dead.

Create an operation matrix before writing code.

Example for `edit_track`:

| Operation | Required | Optional | Forbidden/irrelevant |
|---|---|---|---|
| add | `track_id`, `title`, `kind`, `width_mm` | scales/layout options | `new_index` unless explicitly supported |
| update | `track_id` | mutable track fields | create-only fields if semantically invalid |
| remove | `track_id` | none/minimal | unrelated mutation fields |
| move | `track_id`, `new_index` | none/minimal | unrelated fields |
| clear_bindings | `track_id` | none/minimal | unrelated fields |
| set_scales | `track_id`, scale payload | scale-specific options | unrelated fields |

### Step 2 — Replace coarse annotations with precise models

Avoid signatures equivalent to:

```python
operation: str
kind: str
x_scale: dict[str, object]
```

Prefer:

```python
operation: Literal["add", "update", "remove", "move", ...]
kind: Literal["normal", "reference", "array", "annotation"]
```

For operation-dependent requests, use discriminated unions where practical.

Conceptual structure:

```python
class AddTrack(BaseModel):
    operation: Literal["add"]
    track_id: str
    title: str
    kind: TrackKind
    width_mm: Annotated[float, Field(gt=0)]

class UpdateTrack(BaseModel):
    operation: Literal["update"]
    track_id: str
    title: str | None = None
    width_mm: Annotated[float, Field(gt=0)] | None = None

TrackEditRequest = Annotated[
    AddTrack | UpdateTrack | RemoveTrack | MoveTrack | ...,
    Field(discriminator="operation"),
]
```

### Step 3 — Make MCP registration consume those exact models

`register_stable_tools()` must stop synthesizing lossy Python signatures from a handcrafted JSON schema.

The registration path must prove that enum, nested, minimum, and `additionalProperties` rules survive to `tools/list`.

### Step 4 — Define typed output models

Create explicit result families, for example:

```text
InspectionResult
MutationResult
ValidationResult
ArtifactResult
ErrorResult
```

But make them truthful. If `inspect_source` needs `source_format_detected`, include it in the result model. If `render_logfile` needs `page_count`, include it.

Do not attach a strict `additionalProperties: false` schema to a result object and then return undeclared fields.

### Step 5 — Correct tool annotations

At minimum:

- `inspect_authoring`: `readOnlyHint=true`, `idempotentHint=true`
- `inspect_source`: `readOnlyHint=true`, `idempotentHint=true`
- `inspect_vocab`: `readOnlyHint=true`, `idempotentHint=true`
- `validate_logfile`: usually read-only/idempotent
- `preview_logfile`: read-only but may create a temporary artifact; annotate according to actual behavior
- mutation tools: `readOnlyHint=false`

### Step 6 — Fail malformed calls before service dispatch

Tests must prove that the MCP layer rejects:

- invalid enum values,
- missing operation-specific required fields,
- illegal extra fields,
- wrong nested types,
- values below minimums,
- invalid discriminators.

The handler should not need to rediscover these errors manually.

## Tests

Add `tests/test_mcp_wire_contract.py` with real client assertions:

```text
actual tool names == intended names
actual inputSchema == canonical generated input schema
actual outputSchema == canonical generated output schema
actual annotations == expected annotations
```

Add one valid and several invalid calls per operation family.

## Acceptance criteria

- 100% schema equality on the real MCP wire surface.
- No coarse `dict[str, object]` where a stable structured schema exists.
- Invalid operation values never reach `AuthoringService`.
- All output results validate against advertised schemas.
- Read-only tools are annotated truthfully.

## Rollback rule

If typed schema generation materially increases context size, do not weaken the schema. Instead move large catalogs/examples to resources and simplify operation models while preserving constraints.

## Suggested PR

`stabilization/S1-truthful-mcp-contract`

---

# 9. Slice S2 — Compact, Deliberate Tool Results

## Goal

Prevent normal tool execution from flooding the model context.

## Issues addressed

I02, I07.

## Procedure

### Step 1 — Establish explicit payload budgets

Implement automated size assertions for every default result family.

Recommended budgets:

```text
ordinary default result:   target < 4 KB
P95 across stable suite:    < 12 KB
hard default cap:           20 KB
full-detail exceptions:     explicit only
```

### Step 2 — Redesign mutation envelopes

Current pattern:

```text
before = entire object/document
after  = entire object/document
```

Replace with minimal diffs.

Example:

```json
{
  "ok": true,
  "changed": true,
  "target": {
    "object_kind": "track",
    "section_id": "main",
    "track_id": "resistivity"
  },
  "changed_fields": ["title", "width_mm"],
  "before": {
    "title": "Res",
    "width_mm": 25
  },
  "after": {
    "title": "Resistivity",
    "width_mm": 30
  },
  "warnings": [],
  "next_steps": []
}
```

For destructive operations, include the minimal deleted-object identity and critical summary fields, not the entire document.

### Step 3 — Redesign `create_draft`

Default response should return a creation summary:

```json
{
  "ok": true,
  "changed": true,
  "logfile_path": "...",
  "starter": "forge16b_porosity_example",
  "section_ids": ["main", "lower_review"],
  "section_count": 2,
  "warnings": []
}
```

Do not return the full canonical document under `after`.

### Step 4 — Make inspection detail levels real

`inspect_authoring(detail="summary")` must return a concise structural projection.

Suggested semantics:

```text
summary
  IDs, titles, counts, key ranges, binding counts, validation state

normal
  summary + selected commonly needed properties

full
  complete canonical representation of selected objects
```

If only `summary` and `full` are needed, expose only those two.

### Step 5 — Make vocabulary inspection selective

`inspect_vocab(family="track")` must return only track vocabulary.

For large vocabularies:

- use pagination/filtering,
- or return an MCP resource URI,
- or expose narrow resource templates.

### Step 6 — Use MCP resources for large representations

Move large, mostly-read content out of routine tool results:

- full document YAML/JSON,
- reconstruction examples,
- large vocabularies,
- source metadata dumps,
- verbose validation reports.

Tools may return a compact summary plus a resource reference.

### Step 7 — Enforce size in CI

Instrument a representative suite and fail CI if a default result unexpectedly exceeds the budget.

## Tests

- `create_draft` default result < 12 KB for every packaged starter.
- `inspect_authoring(summary)` is significantly smaller than `full`.
- `inspect_vocab(family=...)` materially filters output.
- Mutation output contains only changed fields or targeted summaries.
- No default result exceeds 20 KB without an explicit exception.

## Acceptance criteria

- The packaged porosity example no longer injects ~70 KB on creation.
- Normal create + summary inspect sequence stays comfortably below 20 KB combined.
- Full state remains accessible on demand.

## Suggested PR

`stabilization/S2-result-budget-and-resources`

---

# 10. Slice S3 — Canonical Round-Trip and Mutation Invariants

## Goal

Guarantee that every starter/example accepted by creation is a valid member of the same canonical state space used by later mutations.

## Issues addressed

I03.

## Procedure

### Step 1 — Define one canonical acceptance pipeline

Any persisted logfile must pass the same canonical structural checks regardless of whether it was created, imported, or mutated.

Minimum invariant:

```text
mapping
  -> normalize/rebase
  -> canonical model
  -> canonical structural validate
  -> serialize
  -> reload
  -> canonical structural validate
```

### Step 2 — Remove divergent create-vs-edit acceptance rules

The current `create_draft` path and mutation persistence path apply different validation/normalization depth. Refactor them so creation cannot persist a document that later mutation immediately rejects.

### Step 3 — Fix between-instance fill reference normalization

Reproduce the identified Forge porosity case:

```text
NPHI / nphi_overlay
fill.kind = between_instances
other_element_id = rhob_overlay
```

Confirm why `_normalize_between_instance_fill_references()` or canonical validation loses/changes the relationship. Fix the canonical rule, not just the example.

### Step 4 — Parameterize every packaged starter

For each starter/example:

1. create draft,
2. load canonical model,
3. validate,
4. serialize,
5. reload,
6. validate again.

### Step 5 — Cross-family unrelated mutation test

For every starter, execute at least one valid mutation in each family that can be applied without changing the semantic essence of the example:

- header,
- report settings,
- remarks,
- section,
- track,
- curve binding,
- raster binding where applicable,
- fill where applicable,
- annotation where applicable.

After each mutation:

```text
persist -> reload -> structural validate
```

Use fresh copies per mutation so tests are independent.

### Step 6 — Add no-op/idempotence checks

Where operations claim idempotence, calling the same valid update twice should either:

- return `changed=false`, or
- produce an identical canonical hash.

### Step 7 — Add canonical hash/diff support for tests

Use a normalized deterministic representation to distinguish real state changes from serialization-order noise.

## Tests

Create a parameterized matrix such as:

```text
starter x mutation_family x structural_validation
```

CI must fail if any shipped example cannot survive an unrelated edit.

## Acceptance criteria

- 100% packaged starters round-trip.
- 100% applicable mutation-family smoke tests pass.
- The original Forge porosity remarks mutation succeeds.
- Creation and mutation use one structural acceptance standard.

## Suggested PR

`stabilization/S3-canonical-roundtrip-invariants`

---

# 11. Slice S4 — Separate Structural, Data, and Render Validation

## Goal

Make editing independent from optional source/render dependencies unless those dependencies are truly needed.

## Issues addressed

I04.

## Validation model

Define three levels explicitly.

### Level A — Structural

Checks only the canonical document:

- IDs and uniqueness,
- references between sections/tracks/bindings/fills,
- numeric/domain constraints,
- required fields,
- internal consistency.

No LAS/DLIS parser. No renderer.

### Level B — Data/source

Adds:

- source file existence,
- parser availability,
- channel existence,
- source metadata compatibility,
- binding-to-channel resolvability.

### Level C — Render

Adds:

- full document construction,
- backend availability,
- render-specific constraints,
- preview/render artifact generation.

## Procedure

### Step 1 — Split the current validation pipeline

Refactor `_persist_validated_logfile_mapping()` so structural persistence does not automatically call `_validate_logfile_spec_renderable()`.

### Step 2 — Map operations to required validation level

Suggested mapping:

| Operation | Minimum validation |
|---|---|
| edit_header | Structural |
| edit_report_settings | Structural |
| edit_remarks | Structural |
| edit_section layout-only fields | Structural |
| edit_track layout/style | Structural |
| add/update curve binding channel | Data |
| raster binding source-dependent change | Data |
| validate_logfile(level="structural") | Structural |
| validate_logfile(level="data") | Data |
| validate_logfile(level="render") | Render |
| preview_logfile | Render |
| render_logfile | Render |

### Step 3 — Decide public API shape

Either expose:

```text
validate_logfile(level="structural" | "data" | "render")
```

or separate tools only if client ergonomics clearly improve. Prefer one tool with a precise enum unless tool semantics become confusing.

### Step 4 — Make missing dependencies explicit and local

If `dlisio` is absent:

- structural edits must still work,
- data/render validation should return a clear dependency error,
- error should identify the extra package required.

### Step 5 — Align packaging extras

Decide whether `wellplot[mcp]` is intended to support:

- only structural MCP authoring, or
- full LAS/DLIS preview/render.

If full functionality is expected, ensure the appropriate extras install the parser dependencies. If optional behavior is intended, document capability boundaries clearly.

## Tests

Run a server environment without `lasio`/`dlisio`:

- create structurally valid draft: pass,
- edit remarks: pass,
- edit page setting: pass,
- structural validate: pass,
- data validate on LAS/DLIS: fail with dependency-specific tool error,
- render: fail with dependency-specific tool error.

## Acceptance criteria

- No structural-only mutation imports or executes LAS/DLIS readers.
- Missing optional parsers never block unrelated authoring.
- Validation level is explicit in result metadata.

## Suggested PR

`stabilization/S4-validation-tiers`

---

# 12. Slice S5 — Remove Fake Controls, Repair Prompts, and Reduce Prompt Bloat

## Goal

Ensure every advertised control is real and every shipped prompt describes the current stable tool surface.

## Issues addressed

I05, I06, I16.

## Procedure

### Step 1 — Audit every public parameter

Start with the confirmed cases:

- `inspect_authoring.detail`
- `inspect_vocab.family`
- `inspect_vocab.detail`
- `inspect_source.include_metadata`
- `validate_logfile.strict`
- `render_logfile.backend`
- `create_draft.source_data_file`

For each parameter choose exactly one outcome:

1. implement its documented semantics,
2. rename/redefine it to truthful semantics,
3. remove it from the public contract.

Do not preserve a parameter merely for compatibility unless there is a real compatibility requirement and a deprecation plan.

### Step 2 — Fix backend semantics

If `render_logfile.backend` is exposed, it must actually select or constrain the backend. If runtime backend selection is intentionally configuration-only, remove the argument and expose current backend in inspection/status instead.

### Step 3 — Regenerate all MCP prompts

Audit every prompt template and remove references to old tools, including confirmed stale names such as:

- `inspect_logfile`
- `preview_logfile_png`
- `inspect_data_source`
- `check_channel_availability`
- `set_section_data_source`
- `update_section`
- `set_section_view`
- `set_page_layout`
- `set_matplotlib_style`
- `set_depth_axis`
- `inspect_style_presets`
- `apply_style_preset`
- `inspect_track_bindings`
- `set_track_scales`

Generate prompt tool-name lists from the canonical registered profile wherever possible.

### Step 4 — Stop embedding large examples into prompts

`start_from_example_prompt()` should not inline README + base YAML + full reconstruction YAML when those artifacts already exist as MCP resources.

Replace with:

```text
short task-specific instructions
+ resource identifiers/URIs
+ when-to-read guidance
```

### Step 5 — Add prompt conformance tests

Parse shipped prompt text and fail CI if it references a token matching a removed tool name.

At minimum, maintain a set of valid stable tool names and check backticked/call-like tool references.

### Step 6 — Correct docs and counts

Update:

- README tool list,
- server comments saying “16-responsibility” when the actual surface is 17,
- recovery plan hard-limit text if 17 is now intentionally approved,
- installation extras/capability notes,
- examples using old tool names.

## Tests

- Every parameter has a behavioral test.
- `summary` and `full` differ.
- `family` filters.
- `backend` either changes behavior or no longer exists.
- No prompt references an unavailable tool.
- Prompt payload sizes are measured and bounded.

## Acceptance criteria

- Zero ignored public parameters.
- Zero stale tool names in shipped prompts/docs.
- Large examples are referenced as resources rather than duplicated in prompts.

## Suggested PR

`stabilization/S5-contract-semantics-and-prompts`

---

# 13. Slice S6 — Real-Wire Conformance and Live Provider Evaluation

## Goal

Replace false-green testing with evidence that real MCP clients and real models can use the server reliably.

## Issues addressed

I09, I10; validates S1–S5.

## Procedure

### Step 1 — Real MCP conformance suite

For each tool:

1. fetch tool descriptor through real `list_tools`,
2. compare schema to canonical generated schema,
3. execute a minimal valid request,
4. validate structured result against output schema,
5. execute invalid enum request,
6. execute missing-required-field request,
7. execute extra-field request,
8. verify failure occurs at the expected layer.

### Step 2 — Result-size regression suite

For every stable task/tool path, record serialized result sizes and assert budgets from S2.

### Step 3 — Resource and prompt integration tests

Verify:

- prompt tool references are valid,
- referenced resources resolve,
- resource content is accessible from a real MCP client,
- resources do not unexpectedly exceed documented limits.

### Step 4 — Expand the deterministic task suite

The prior 12-task suite contained many incomplete expected assertions. Complete expected final-state assertions for every task before using the suite to justify architecture decisions.

Each task should define:

- initial state,
- user request,
- allowed/expected semantic changes,
- prohibited changes,
- deterministic final-state verifier.

### Deterministic task contract

The task suite is a versioned product contract, not a list of prompts. Every
active task must declare all of the following in machine-readable form:

- a named starting fixture and canonical preconditions checked before execution;
- a `run` goal or `revise` feedback request;
- non-empty final-state assertions against the persisted canonical document;
- allowed JSON-pointer change paths and prohibited JSON-pointer change paths;
- an expected result outcome where no mutation is correct, such as an ambiguity
  clarification or an unavailable-channel rejection.

Assertions over sections, tracks, bindings, fills, and annotations must match
semantic object subsets by stable identity. They must not depend on provider-
chosen binding ids or list positions unless list order itself is the behavior
being tested. A live evaluator must copy the per-task baseline before every
request, check fixture preconditions against that baseline, and grade both the
final document and the observed result outcome. Tasks from different starting
fixtures run in separate invocations; they are never chained through one mutable
notebook draft.

### Step 5 — Run a provider matrix

At minimum:

- one strongest production model,
- one lower-cost/fast production model,
- one second vendor or materially different model family.

For each provider run the same task suite multiple times if budget permits.

The evaluator now requires an explicit fixture catalog at
`tests/evals/agent_fixture_catalog.json`. Each fixture directory contains the
declared starter, initial draft, and canonical baseline artifacts for its task
family. The live runner never falls back to a notebook draft: an absent fixture
is reported as `not_run` before provider creation.

Run one isolated fixture group per provider, for example:

```bash
WELLPLOT_RUN_LIVE_AGENT_EVALS=1 uv run python scripts/run_agent_evals.py \
  --suite development --mode live --provider openai_compat \
  --model z-ai/glm-5.2 --base-url https://integrate.api.nvidia.com/v1 \
  --api-key-file NVIDIA_API_KEY.txt \
  --task remarks_only --fixture-catalog tests/evals/agent_fixture_catalog.json \
  --output docs/evaluations/mcp-agent/nvidia-remarks.json
```

The runner creates an independent case directory and baseline for every task;
revision tasks are never chained through the previous task's mutated draft.
Aggregate redacted provider reports without contacting a model:

```bash
uv run python scripts/run_agent_evals.py --suite development --mode matrix \
  --matrix-evidence docs/evaluations/mcp-agent/nvidia-remarks.json \
  --matrix-evidence docs/evaluations/mcp-agent/nvidia-nemotron-remarks.json \
  --matrix-evidence docs/evaluations/mcp-agent/unsloth-backup-remarks.json
```

Matrix output reports `pass_at_1`, `not_run` cases, and one failure category
from the controlled remediation vocabulary. Missing credentials, missing
fixtures, and provider transport failures are not counted as successful cases.

### Step 6 — Track the right metrics

Per task/provider:

- Pass@1,
- final deterministic correctness,
- tool calls,
- tool errors,
- duplicate inspections,
- result-token volume,
- retries,
- host fallback invocations,
- rollback invocations,
- latency.

### Step 7 — Classify every failure

Every failure must be labeled as one of:

```text
contract/schema
server semantics
state invariant
missing capability
provider reasoning
host policy interference
resource/context overload
transient infrastructure
```

Do not add a heuristic until the failure has a category and repeatable reproduction.

## Acceptance criteria

Before S7 starts:

- Real-wire schema conformance = 100%.
- Output-schema conformance = 100%.
- Deterministic suite has complete expected assertions.
- Live baseline exists for at least two materially different providers.
- Remaining failures are categorized.

## Suggested PR / evidence package

`stabilization/S6-wire-and-provider-evals`

Store evaluation reports as versioned artifacts under the existing evidence structure.

---

# 14. Slice S7 — Simplify the Host Agent Loop

## Goal

Remove compensating logic made unnecessary by the repaired MCP boundary.

## Issues addressed

I08, I15.

## Rule

Remove one behavior at a time and keep it removed only if live evals stay within the S6 regression thresholds.

## Procedure

### Step 1 — Inventory host-side semantic behavior

Document every non-trivial transformation in `core.py`, including:

- regex tool-family scope detection,
- argument rewriting/aliasing,
- failure-specific corrective instructions,
- no-progress detection,
- deterministic catalog fallback,
- host-side fallback execution,
- natural-language desired-state extraction,
- postcondition parsing,
- automatic rollback logic.

Classify each as:

```text
safety invariant
transactional reliability
provider compensation
historical workaround
```

### Step 2 — Protect the mechanisms that are genuinely deterministic

Likely keep:

- maximum rounds,
- timeouts,
- transaction boundaries,
- rollback on deterministic validation failure,
- tool error accounting,
- final structural validation.

### Step 3 — Remove regex scope gating first

The current host rejects model-selected mutation tools based on regex-derived interpretation of the user request. With truthful schemas, this can block correct reasoning.

Replace broad regex gating with only hard authorization/safety constraints. If scope protection is still necessary, prefer explicit state/transaction policy over linguistic keyword matching.

### Step 4 — Remove failure-specific prompt patching

If a failure is now prevented by schema validation, delete the corresponding recovery instruction branch.

### Step 5 — Challenge catalog fallback

Run the live suite with catalog fallback disabled. Retain it only if it provides a measurable improvement that cannot be achieved by better tool descriptions/resources.

### Step 6 — Challenge host desired-state/postcondition parsing

Prefer deterministic state verification against expected task assertions in tests. In production, use canonical state comparisons where possible rather than regex interpretation of user prose.

### Step 7 — Reduce function size and split pure mechanics

Target a stable loop of roughly 500–800 lines or less, with small helpers for:

- call dispatch,
- transaction handling,
- telemetry,
- response normalization,
- deterministic validation.

Do not refactor merely to hit a line count; use the number as a complexity smell.

## Tests

For every removed heuristic:

1. run deterministic suite,
2. run live provider suite,
3. compare Pass@1, tool errors, fallback rate, and latency,
4. keep deletion if thresholds remain satisfied.

## Acceptance criteria

- No regex-based tool-family rejection on normal user semantics.
- Host fallback is rare and evidence-backed.
- Stable loop responsibilities are mechanical, not a parallel planner.
- Live reliability remains within S6 thresholds.

## Suggested PR strategy

Use several small PRs rather than one rewrite:

```text
S7a remove scope regex gating
S7b remove schema-redundant recovery branches
S7c reduce catalog fallback
S7d simplify postconditions and rollback interface
```

---

# 15. Slice S8 — Security Isolation and Structured Observability

## Goal

Make the MCP process least-privilege and make failures diagnosable without dumping user state.

## Issues addressed

I13, I14.

## Procedure

### Step 1 — Whitelist MCP subprocess environment

Replace:

```python
env = dict(os.environ)
```

with an allowlist of required variables.

Typical MCP subprocess needs may include:

- PATH or explicit executable path,
- Python/runtime environment variables,
- Wellplot-specific config variables,
- workspace/root path,
- logging level.

Provider API keys should remain in the host/provider process unless the MCP server itself directly needs them.

### Step 2 — Keep secrets outside the mutable workspace

Do not recommend storing `.env`, API-key text files, or credential files inside the MCP root if the MCP process can mutate that root.

### Step 3 — Preserve root-path confinement

Keep the existing path confinement behavior. Add explicit tests for:

- `..` traversal,
- absolute paths outside root,
- symlink escape if relevant,
- Windows path edge cases if supported.

### Step 4 — Add structured logs

Per call, emit a record similar to:

```json
{
  "request_id": "...",
  "tool": "edit_track",
  "operation": "update",
  "duration_ms": 41,
  "arg_chars": 280,
  "result_chars": 930,
  "ok": true,
  "changed": true,
  "error_type": null,
  "document_revision": "..."
}
```

Do not log full source data or full canonical documents by default.

### Step 5 — Add trace correlation

Use one correlation/request ID across:

```text
agent turn -> MCP call -> AuthoringService mutation -> validation -> artifact
```

### Step 6 — Add operational counters

Track at least:

- calls by tool,
- failures by exception type,
- P50/P95 latency,
- P50/P95 result size,
- rollback count,
- validation failures,
- optional dependency failures.

## Acceptance criteria

- MCP subprocess no longer receives unrelated provider secrets.
- Workspace contains no recommended credential files.
- Root confinement regression tests pass.
- Every tool failure can be correlated across agent/MCP/service layers by request ID.

## Suggested PR

`stabilization/S8-security-and-observability`

---

# 16. Slice S9 — Migrate to MCP Python SDK v2 / 2026-07-28 Protocol

## Goal

Move the now-stable contract onto the current public MCP SDK and lifecycle without mixing protocol migration with behavioral debugging.

## Issues addressed

I11.

## Preconditions

Do not start until S1–S8 are green. The migration must preserve the established wire contract and eval performance.

## Procedure

### Step 1 — Branch from a known green stabilization tag

Create a release candidate tag before migration.

### Step 2 — Upgrade dependencies deliberately

Move from the v1 pin to the supported v2 line. Record exact versions in lockfiles.

### Step 3 — Replace deprecated server imports

Migrate from old `FastMCP` import paths to the v2 public server API.

### Step 4 — Remove private server internals

Replace direct use of members such as:

```text
server._mcp_server.run(...)
server._mcp_server.create_initialization_options()
```

with documented public APIs.

### Step 5 — Update client lifecycle

Remove assumptions tied to the old initialize/session handshake where the v2 client API no longer requires them.

### Step 6 — Preserve compatibility intentionally

If older MCP clients are still supported, add explicit compatibility tests rather than relying on accidental behavior.

### Step 7 — Re-run full conformance and provider suites

The migration is successful only if:

- schemas remain equivalent,
- results remain equivalent,
- resource/prompt behavior remains valid,
- provider success does not regress beyond thresholds.

## Acceptance criteria

- No private MCP SDK API usage.
- Current protocol lifecycle passes integration tests.
- Stable provider metrics remain within pre-migration tolerance.
- Legacy-client support, if required, is explicitly tested.

## Suggested PR

`stabilization/S9-mcp-sdk-v2`

---

# 17. Slice S10 — Codebase Cleanup, Historical Path Removal, and Documentation Lock

## Goal

Remove obsolete architecture left behind by the recovery program and make documentation derive from reality where possible.

## Issues addressed

I15, I16.

## Procedure

### Step 1 — Build a reachability map

Identify whether these historical modules are still used:

- `branch_compiler.py`
- `compilation.py`
- `operation_executor.py`
- old tool registration paths
- old prompt-generation paths
- old fallback planner branches

Use import search plus runtime/test coverage.

### Step 2 — Delete unreachable code

Do not keep old architectures “just in case.” Tag the repository before deletion if historical recovery is desired.

### Step 3 — Split large modules by stable responsibility

Do not refactor `service.py` or `core.py` blindly. Split only around stable seams that emerged during S1–S9.

Potential boundaries:

```text
mcp/contracts.py
mcp/results.py
mcp/registration.py
mcp/resources.py
mcp/prompts.py
mcp/telemetry.py
agent/loop.py
agent/transactions.py
agent/evaluation_hooks.py
```

Keep `AuthoringService` as domain authority unless a clear internal domain seam is already proven.

### Step 4 — Generate documentation from contract metadata

Where possible, derive:

- stable tool list,
- tool descriptions,
- operation enums,
- result-family descriptions,
- resource names,

from the same source used by MCP registration.

### Step 5 — Add drift tests

Fail CI when:

- README tool list differs from `tools/list`,
- prompt references removed tool names,
- documented count differs from actual count,
- examples use unsupported parameters.

### Step 6 — Publish a stabilization architecture note

Document:

- why the 17-tool taxonomy was retained,
- why large state is resource-based,
- validation tiers,
- result budgets,
- host-loop responsibility boundaries,
- protocol version policy.

## Acceptance criteria

- Unused historical execution paths are removed.
- Documentation reflects actual 17-tool surface.
- Drift checks are automated.
- No architectural comment contradicts current behavior.

## Suggested PR

`stabilization/S10-cleanup-and-doc-lock`

---

# 18. Detailed Tool-by-Tool Remediation Checklist

Use this section during implementation reviews.

## `create_draft`

- [ ] Does not return full document by default.
- [ ] Any accepted starter passes canonical structural validation.
- [ ] Any accepted starter round-trips through serialization/reload.
- [ ] `source_data_file` is either truly supported or removed.
- [ ] Result validates against typed output schema.
- [ ] Missing LAS/DLIS parsers do not block structurally self-contained creation unless source ingestion is requested.

## `inspect_authoring`

- [ ] `detail` changes output materially.
- [ ] Summary is default.
- [ ] Full output is explicit and size-aware.
- [ ] Read-only/idempotent annotations are correct.
- [ ] Selection by object kind/id is precise.

## `inspect_source`

- [ ] `include_metadata` is implemented or removed.
- [ ] Source parser dependency errors are explicit.
- [ ] Read-only/idempotent annotations are correct.
- [ ] Large metadata is paginated, filtered, or resource-backed.

## `inspect_vocab`

- [ ] `family` actually filters.
- [ ] `detail` actually changes output or is removed.
- [ ] Large catalog data is resource-backed where appropriate.
- [ ] Read-only/idempotent annotations are correct.

## Mutation tools (`edit_*`)

- [ ] `operation` is a literal/discriminator, not a free string.
- [ ] Operation-specific required fields are expressed in schema.
- [ ] Illegal extra fields are rejected.
- [ ] Results return minimal diffs.
- [ ] Unrelated document state is not serialized into results.
- [ ] Structural-only changes do not trigger render validation.

## `replicate_section_structure`

- [ ] Schema clearly defines source/target semantics.
- [ ] Result summarizes created/changed IDs only.
- [ ] Canonical references remain valid after replication.
- [ ] Cross-section ID collision tests exist.

## `validate_logfile`

- [ ] `strict` is implemented or removed.
- [ ] Prefer explicit `level` enum for structural/data/render.
- [ ] Result indicates which level ran.
- [ ] Missing optional dependencies are tool errors only at relevant levels.
- [ ] Read-only/idempotent annotations are correct.

## `preview_logfile`

- [ ] Uses render-level validation.
- [ ] Returns compact artifact metadata.
- [ ] Large artifact bytes are not embedded in structured result.
- [ ] Temporary file lifecycle is documented.

## `render_logfile`

- [ ] `backend` truly selects/constrains backend or is removed.
- [ ] Result schema includes `output_path`, `backend`, `page_count` if returned.
- [ ] Artifact creation and overwrite behavior are explicit.
- [ ] Render dependency errors are specific.

---

# 19. Test Architecture After Stabilization

The final test pyramid should have four distinct layers.

## Layer 1 — Pure domain tests

Fast, no MCP, no provider:

- canonical models,
- AuthoringService mutations,
- normalization,
- structural validation,
- round-trip invariants.

## Layer 2 — Real MCP protocol tests

Real server/client transport:

- `tools/list` schema equality,
- output schema equality,
- annotations,
- invalid call rejection,
- resource retrieval,
- prompt retrieval,
- result-size budgets.

## Layer 3 — Deterministic end-to-end task tests

Agent-agnostic task fixtures:

- initial file tree,
- user request,
- expected canonical final state,
- prohibited changes,
- artifact expectations.

These tests should be executable with a scripted tool caller or deterministic harness.

## Layer 4 — Live provider evals

Real LLM clients:

- same task corpus,
- provider matrix,
- repeated runs where practical,
- Pass@1 and efficiency metrics,
- failure classification.

A profile-only fake MCP session is useful for unit isolation but must never be treated as proof of wire-contract correctness.

---

# 20. Release Gates

Use these gates to decide whether the next slice may begin.

## Gate A — Contract Gate (after S1)

- [ ] Real `tools/list` input schemas equal canonical schemas.
- [ ] Output schemas are truthful and enforced.
- [ ] Invalid enums/extra fields are rejected before service logic.
- [ ] Tool annotations are correct.

## Gate B — Context Gate (after S2)

- [ ] Default `create_draft` < 12 KB for all starters.
- [ ] No ordinary default tool result > 20 KB.
- [ ] Summary/full semantics are real.
- [ ] Large state is available through resources or explicit full inspection.

## Gate C — State Integrity Gate (after S3/S4)

- [ ] Every packaged starter round-trips.
- [ ] Every applicable mutation-family smoke test passes.
- [ ] Structural edits work without LAS/DLIS parser extras.
- [ ] Render checks still catch source/render failures.

## Gate D — Client Truth Gate (after S5/S6)

- [ ] No stale tool names in prompts/docs.
- [ ] No ignored public parameters.
- [ ] Real-client conformance suite is green.
- [ ] Live provider baseline exists and failures are categorized.

## Gate E — Simplification Gate (after S7)

- [ ] Removing host heuristics did not regress provider success beyond tolerance.
- [ ] Host loop is primarily mechanical/transactional.
- [ ] Fallback use is rare and evidence-backed.

## Gate F — Production Gate (after S8–S10)

- [ ] Least-privilege environment.
- [ ] Structured telemetry.
- [ ] MCP SDK v2/current lifecycle.
- [ ] No private SDK APIs.
- [ ] Historical dead paths removed.
- [ ] Docs generated/locked against drift.

---

# 21. Recommended Execution Cadence

A practical implementation sequence for one developer or a small team:

| Phase | Slices | Focus |
|---|---|---|
| Phase 1 | S0–S1 | Establish truth: baseline + real schemas |
| Phase 2 | S2–S4 | Fix payloads, state invariants, validation boundaries |
| Phase 3 | S5–S6 | Repair public semantics and prove via real clients/providers |
| Phase 4 | S7–S8 | Simplify host, secure and instrument runtime |
| Phase 5 | S9–S10 | Migrate protocol, delete old paths, lock docs |

Avoid scheduling protocol migration in parallel with contract redesign. The point of this order is to keep each failure domain isolated.

---

# 22. Pull Request Review Template

Use this checklist for each remediation PR.

## Contract

- [ ] Does this change alter `tools/list`?
- [ ] If yes, is the schema generated from the canonical typed model?
- [ ] Are operation-specific constraints represented structurally?
- [ ] Are output schemas truthful?

## Context

- [ ] What is the largest default result introduced/changed?
- [ ] Does it stay within the result budget?
- [ ] Could any large payload become a resource instead?

## State

- [ ] Does create/load/serialize/reload remain valid?
- [ ] Does the change preserve unrelated object families?
- [ ] Does validation run at the minimum required level?

## Agent

- [ ] Does this PR add a host heuristic?
- [ ] If yes, what repeatable live-provider failure proves it is needed?
- [ ] Could truthful schema/tool semantics solve the problem instead?

## Tests

- [ ] Pure domain test added/updated.
- [ ] Real MCP test added/updated.
- [ ] Result schema validated.
- [ ] Result size measured.
- [ ] Live eval impact recorded if agent behavior changes.

## Operations

- [ ] Structured telemetry preserved.
- [ ] No new secret/environment exposure.
- [ ] Docs/prompts remain synchronized.

---

# 23. Definition of Done for the Entire Stabilization Program

The program is complete when a new developer can perform the following without hidden knowledge or host-side magic:

1. Start the MCP server from a clean environment.
2. Connect with a standards-compliant MCP client.
3. Inspect `tools/list` and see precise enums, nested types, required fields, and correct annotations.
4. Create any shipped starter and receive a compact summary.
5. Inspect a summary without pulling the full document into context.
6. Perform an unrelated edit on any starter without triggering latent canonical errors.
7. Perform structural edits without LAS/DLIS parser packages.
8. Request source/render validation and receive clear dependency errors if optional packages are absent.
9. Use shipped MCP prompts without encountering removed tool names.
10. Execute the stable task suite with >=90% Pass@1 on supported frontier providers.
11. Trace any failure from agent turn through MCP call, service mutation, validation, and artifact by a request ID.
12. Run on the current MCP SDK using public APIs only.
13. Read documentation that exactly matches the actual stable tool surface.
14. Confirm that host-side recovery logic is small, deterministic, and justified by eval evidence.

The strongest architectural signal of success is not merely that tests pass. It is that **removing compensating host logic no longer makes the agent fall apart**, because the MCP boundary itself has become precise and predictable.

---

# 24. Immediate Next Actions

Start with these actions in order:

1. Create the S0 stabilization branch and freeze feature work.
2. Capture the real `tools/list` output from the current server into a fixture.
3. Add result-size telemetry and reproduce the ~70 KB `create_draft` result as a regression test.
4. Build the S1 typed request/output model skeleton for one representative complex tool, preferably `edit_track`.
5. Prove that the real MCP client sees the `operation` enum and operation-dependent fields.
6. Generalize the same source-of-truth pattern across all 17 tools.
7. Only after Gate A is green, begin result compaction and round-trip invariant work.

Do **not** start with the SDK v2 migration, agent-loop rewrite, or new tool decomposition. Those are later slices and should be performed only after the MCP façade is truthful.

---

## Appendix A — Original High-Value Findings Preserved as Regression Cases

The following observations from the review should become explicit regression tests so they cannot silently return:

1. `create_draft(forge16b_porosity_example)` previously returned roughly 71,000 serialized characters.
2. `inspect_authoring(section, detail="full")` previously returned roughly 40,000 characters.
3. `detail="summary"` and `detail="full"` previously had no meaningful behavioral distinction in key inspection paths.
4. `inspect_vocab()` and family/detail variants previously returned effectively the same payload.
5. A freshly created Forge porosity example previously failed an unrelated remarks mutation with a canonical between-instance fill-reference error.
6. Structural mutation of CBL/Forge examples previously could fail because `dlisio`/`lasio` was absent.
7. MCP prompt templates previously referenced removed tools such as `inspect_logfile` and `preview_logfile_png`.
8. Contract unit tests previously passed because they inspected the intended profile, while the real MCP registration used coarser inferred Python types.
9. Fake MCP sessions in tests previously supplied the intended schema directly, masking the real registration defect.
10. MCP subprocess creation previously inherited the complete host environment.

Each of these should have a named test with a clear failure message.

---

## Appendix B — Architectural Non-Goals

The stabilization program intentionally does **not** aim to:

- return to the old 58-tool architecture,
- rewrite the deterministic authoring domain model from scratch,
- make every domain object its own MCP tool,
- solve model reasoning failures with progressively larger system prompts,
- preserve every historical fallback path for compatibility,
- migrate protocol versions before the behavioral boundary is stable,
- inline full examples/catalogs into tool descriptions or prompts,
- treat passing fake-session tests as sufficient proof.

The existing 17-tool taxonomy should be retained unless live evidence demonstrates a specific semantic overlap or missing responsibility.

---

## Appendix C — Suggested Repository Artifacts to Add

```text
docs/
  mcp-stabilization-playbook.md
  mcp-architecture-after-stabilization.md

tests/
  test_mcp_wire_contract.py
  test_mcp_result_budgets.py
  test_packaged_example_roundtrip.py
  test_validation_tiers.py
  test_prompt_tool_references.py
  test_mcp_environment_isolation.py

  fixtures/
    mcp_contract_baseline_v1.json
    packaged_example_mutation_matrix.json

evals/
  stable_tasks/
  provider_reports/
  failure_taxonomy.md
```

This document itself can live at `docs/mcp-stabilization-playbook.md` and be maintained as the execution authority until all release gates are complete.
