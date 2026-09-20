# Wellplot Agentic Architecture Migration Plan
## From schema-heavy structured generation to a constrained Wellplot Authoring SDK ("Code Mode")

- **Document status:** Proposed implementation plan
- **Repository:** `cschrupp/wellplot`
- **Baseline branch:** `mcp-stabilization`
- **Baseline commit:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Baseline commit message:** `Strengthen graph report requirement compilation`
- **Prepared:** 2026-09-13
- **Current architecture-revision evidence baseline:** `68232ee`
- **Current status:** CM-53 routing is implemented; public transition acceptance
  remains open pending the typed section-worker phase below.
- **Primary objective:** Make full natural-language well-log generation reliable while reducing agent/runtime complexity and removing legacy orchestration code.
- **Secondary objective:** Make new Wellplot capabilities extensible without adding graph branches or central request-specific schema logic.

---

# 1. Executive decision

The next Wellplot agent architecture will keep the parts of the current system that are working and replace the part that is producing repeated inference failures.

The migration decision is:

> **Keep LangGraph as a small orchestration layer. Keep the deterministic authoring stack as the only mutation authority. Replace request-specific dynamic structured-output compilation with a constrained, deterministic Wellplot Authoring SDK executed from model-generated programs. Then remove the old tool-loop/compiler architecture once the new path is proven.**

The target model-facing flow is:

```text
Natural-language request
        |
        v
Small semantic planner
        |
        +------------------------+
        |                        |
        v                        v
 optional report task      section tasks
        |                        |
        |                  parallel fan-out
        |                        |
        v                        v
program synthesizer       program synthesizer
        |                        |
        +------------+-----------+
                     |
                     v
          restricted program parser
                     |
                     v
          deterministic SDK interpreter
                     |
                     v
        AuthoringDocumentIntent fragments
                     |
                     v
          deterministic intent merge
                     |
                     v
              AuthoringService
                     |
          reconcile / validate / apply
                     |
                     v
                render / verify
                     |
                     v
       optional bounded visual correction
```

The model is no longer responsible for constructing an exact, deeply nested final document object with request-specific IDs and a dynamically generated Pydantic schema.

Instead, the model writes a short program against a stable domain API. The program is **not arbitrary Python** and is **never executed with `exec()` or `eval()`**. It is parsed as Python syntax, validated against a small allowed AST, and interpreted by Wellplot. All operations are converted deterministically into the existing canonical authoring intent and executed through the existing deterministic service layer.

This is a migration of the **model-facing instruction set**, not a rewrite of the Wellplot domain model or renderer.

## 2026-09-19 Post-CM-53R3 Architecture Revision

The original migration hypothesis was that section workers should write
restricted Wellplot SDK programs. That hypothesis supported the CM-10 through
CM-53 implementation sequence and remains the historical rationale for the
program kernel, report worker, graph, and cutover work.

Repeated public live failures at the program-based section-worker boundary,
followed by EXP-TW-00 through EXP-TW-08, now require a narrower section-worker
decision:

```text
section task
    -> static typed semantic section draft
    -> deterministic semantic compiler
    -> AuthoringDocumentIntent
```

The TW experiments validated this boundary for the frozen CBL corpus and
showed that required track discriminator tags preserve the strengthened
semantic invariants while restoring the tested local structured-output path.
They did not authorize unconditional production cutover. The report worker
remains program-based pending separate evidence, and the planner, enrichment,
LangGraph fan-out, deterministic merge, `AuthoringService`, and v2 routing
remain active.

The next high-level migration phase is intentionally separate from this
revision:

```text
CM-54  reconcile production architecture and define the promoted typed section contract
CM-55  add production static section models and deterministic semantic compiler
CM-56  exercise the real planner/enricher boundary with shadow/A-B evidence
CM-56R strengthen planner-to-section information only if evidence requires it
CM-57  replace ProgramSectionCompiler in the v2 graph after validation
CM-58  rerun unchanged public/default-route acceptance
CM-60+ resume reachability and legacy deletion only after CM-58 acceptance
```

These are high-level sequence markers only. Detailed contracts require
separate authorization for each slice.

---

# 2. Why this migration is necessary

## 2.1 Current architecture has moved the complexity into schemas

The current graph topology is broadly sound:

- planner;
- planned source resolution;
- parallel report/section workers;
- deterministic merge;
- deterministic execution and verification.

The instability comes from what the planner and workers must generate.

The current planner is required to reason about:

- section IDs;
- capability IDs;
- component IDs;
- canonical target IDs;
- parent component IDs;
- globally unique binding IDs;
- typed source routing;
- exact report slot IDs;
- track/binding/fill/annotation ownership;
- exact values used later to synthesize worker schemas.

The section compiler then receives a request-specific model created at runtime. `worker_contracts.py` uses `create_model()`, `Literal[...]`, request-specific IDs, nested constrained models, exact counts, and conditional fields to constrain the provider's response.

That design converts semantic uncertainty into a dynamically generated type system.

It improves rejection of invalid outputs, but it does not reduce the model's semantic burden. It creates a pattern in which every observed model mistake becomes another schema or planner rule. The output space becomes narrower and more brittle, and failures move rather than disappear.

## 2.2 Current capability registry is only partially plugin-oriented

The capability registry is a strong foundation and should remain.

However, leaf capabilities currently mostly describe canonical models that central code already knows how to assemble. The central worker contract builder still contains detailed knowledge of:

- track creation;
- track kinds;
- x-scales;
- grids;
- binding models;
- curve values;
- raster values;
- colorbars;
- sample axes;
- fills;
- annotations;
- child collection cardinality.

Therefore a genuinely new capability can be discoverable by the graph while still requiring edits to central compiler/schema code.

The target architecture will make the capability own the deterministic authoring behavior required to create or revise it.

## 2.3 The current graph still depends on legacy provider machinery

`ExistingProviderStructuredAdapter` imports `FunctionToolDefinition` and `ProviderAdapterError` from `agent/core.py` and reuses the old provider authoring loop.

This means the new graph is not actually independent of the legacy agent architecture.

A key migration invariant will therefore be:

> **No module under the new graph or program compiler may import `wellplot.agent.core`, old tool-contract modules, branch compilers, or legacy operation-loop code.**

## 2.4 The existing deterministic authoring stack is valuable

The migration must **not** discard:

- canonical authoring/document models;
- `AuthoringDocumentIntent`;
- `AuthoringService`;
- reconciliation;
- deterministic execution;
- defaults;
- validation;
- persistence controls;
- rollback;
- source inspection;
- renderer;
- end-state verification;
- the capability registry concept;
- LangGraph parallel orchestration;
- evaluation infrastructure.

Those are precisely the parts that make a constrained code-generation approach safe and useful.

---

# 3. Scope

## 3.1 In scope

This program covers:

1. introduction of a restricted Wellplot authoring program language;
2. deterministic interpreter and builder SDK;
3. refactoring capability plugins to own their model-facing authoring contract;
4. simplification of the semantic planner;
5. replacement of section/report structured artifact generation with program generation;
6. provider abstraction cleanup;
7. parallel LangGraph workflow migration;
8. reconstruction and revision support;
9. bounded program repair;
10. bounded visual-QA correction;
11. Python/notebook API cutover;
12. high-level MCP cutover;
13. deletion of unreachable legacy agent/compiler/tool-loop code;
14. evaluation and release hardening.

## 3.2 Explicitly out of scope during the migration

Do **not** mix the following product work into the migration unless it is required to prove architecture generality:

- a production `track.image` implementation;
- a well-diagram renderer;
- new petrophysical calculations;
- new DLIS decoding features;
- new vendor packet templates;
- new CBL interpretation ML;
- redesign of the renderer;
- a persistent conversational memory system;
- autonomous long-running agents;
- arbitrary Python execution;
- shell, filesystem, network, subprocess, or dynamic import access from generated programs.

A test-only or minimal demonstration capability may be added to prove extensibility, but it must not turn into a new product feature during this program.

---

# 4. Target architecture principles

The following are non-negotiable.

## 4.1 One mutation authority

`AuthoringService` and canonical Wellplot models remain the only authority that can mutate or persist the document.

Generated programs do not edit YAML directly.

Generated programs do not mutate renderer objects.

Generated programs do not call MCP tools internally.

Generated programs do not bypass reconciliation.

## 4.2 One canonical durable IR

The durable/provider-neutral desired-state IR remains:

```text
AuthoringDocumentIntent
```

Do not create another persistent "operation IR" or another canonical document representation.

The program language is transient model output.

The interpreter converts that transient program into `AuthoringDocumentIntent` fragments.

## 4.3 No arbitrary execution

The implementation must not use:

```python
exec(...)
eval(...)
compile(..., mode="exec")
```

for model-generated source.

The program is parsed with `ast.parse()` and interpreted by Wellplot-owned code.

## 4.4 No request-specific worker schema generation

The new worker path must not dynamically synthesize a Pydantic response schema from the current plan.

Specifically, runtime worker code must not depend on request-specific uses of:

```python
create_model(...)
Literal[current_target_id]
Union[tuple(runtime_models)]
```

to force exact document construction.

Static Pydantic models remain appropriate for:

- the small semantic planner;
- SDK command arguments;
- capability argument validation;
- provider configuration;
- deterministic result models.

## 4.5 The planner plans semantics, not document mechanics

The planner may decide:

- what semantic sections are required;
- what each section is intended to show;
- which registered capabilities are likely needed;
- source selection;
- explicitly requested presentation constraints;
- report-wide semantic changes;
- unresolved requests.

The planner must not be required to decide:

- globally unique binding IDs;
- nested component IDs;
- exact parent component identifiers;
- canonical header slot IDs when semantic resolution can be deterministic;
- every low-level object field;
- an exact final document AST.

## 4.6 The host owns identity

For newly created objects, the host generates canonical IDs.

The model may provide a human-readable `id_hint`, but correctness must never depend on the model inventing a globally unique canonical binding ID.

For existing objects, the worker receives inspected canonical identities or semantic selectors.

## 4.7 Capability extensions do not change the graph

Adding a supported capability may require changes to:

- canonical Wellplot models;
- rendering;
- deterministic capability plugin code;
- capability-specific tests.

It must not require changes to:

- LangGraph topology;
- planner branching code;
- central worker schema construction;
- central `if capability == ...` compilation routing.

## 4.8 Context is progressive

The planner gets only compact capability descriptors.

A section worker gets only:

- its section task;
- relevant current-document projection;
- relevant source manifest/channels;
- documentation for selected/relevant capabilities;
- a few high-quality examples.

It does not get every Wellplot schema.

## 4.9 Repair is bounded

A failed program may receive a compact diagnostic and one normal repair attempt.

A second repair may be allowed only for a clearly syntactic/argument-validation failure.

There is no unbounded "agent loop".

## 4.10 MCP remains an edge protocol

MCP exposes high-level external operations.

Internal graph nodes call Python services directly.

Notebook/Python users call the internal Python session directly.

No internal agent should launch Wellplot's own MCP server merely to use Wellplot.

---

# 5. Proposed package architecture

The desired end state is approximately:

```text
src/wellplot/
|
+-- authoring.py
+-- authoring_context.py
+-- authoring_defaults.py
+-- authoring_executor.py
+-- authoring_reconciler.py
+-- authoring_service.py
|
+-- model/
|   +-- authoring.py
|   +-- intent.py
|   +-- ...
|
+-- capabilities/
|   +-- __init__.py
|   +-- base.py
|   +-- registry.py
|   +-- report.py
|   +-- section_log_plot.py
|   +-- track_normal.py
|   +-- track_reference.py
|   +-- track_array.py
|   +-- track_annotation.py
|   +-- binding_curve.py
|   +-- binding_raster.py
|   +-- fill_curve.py
|   +-- annotation_typed.py
|   +-- builtins.py
|
+-- authoring_program/
|   +-- __init__.py
|   +-- models.py
|   +-- grammar.py
|   +-- validator.py
|   +-- interpreter.py
|   +-- runtime.py
|   +-- ids.py
|   +-- builders.py
|   +-- inspection.py
|   +-- errors.py
|
+-- agent/
|   +-- __init__.py
|   +-- session.py
|   +-- context.py
|   +-- execution_trace.py
|   +-- planner.py
|   +-- models.py
|   +-- program_worker.py
|   +-- qa.py
|   +-- workflow.py
|   +-- providers/
|       +-- __init__.py
|       +-- base.py
|       +-- openai.py
|       +-- openai_compat.py
|
+-- mcp/
    +-- server.py
    +-- service.py
    +-- agentic.py
    +-- agentic_server.py
    +-- ...
```

The important dependency direction is:

```text
render/domain models
        ^
        |
authoring service
        ^
        |
authoring_program + capabilities
        ^
        |
agent planner/workers/graph
        ^
        |
Python API / notebook / MCP edge
```

Forbidden reverse dependencies:

```text
authoring_program -> LangGraph          NO
authoring_program -> MCP                NO
capabilities -> LangGraph               NO
capabilities -> MCP                     NO
authoring_service -> agent              NO
graph -> legacy core.py                 NO
```

---

# 6. The Wellplot Authoring Program

## 6.1 Why a program rather than another JSON DSL

The program provides:

- variables;
- local names;
- composition;
- small loops;
- conditional logic;
- reuse of handles;
- readable repair diagnostics;
- compact output;
- a natural representation for ordered constructive work.

The language should look Pythonic because models are already highly competent at Python syntax, but its semantics are controlled completely by Wellplot.

## 6.2 Example

A future section worker could emit:

```python
section = wp.add_section(
    title="Main CBL Pass",
    id_hint="main_pass",
    source="cbl.dlis",
)

depth = section.add(
    "track.reference",
    title="Depth",
    width_mm=18,
)

gr = section.add(
    "track.normal",
    title="Gamma Ray",
    width_mm=28,
    id_hint="gamma_ray",
)

gr.add(
    "binding.curve",
    channel="GR",
    label="GR",
    scale={"minimum": 0, "maximum": 150},
    style={"color": "green"},
)

cbl = section.add(
    "track.normal",
    title="CBL",
    width_mm=28,
    id_hint="cbl",
)

cbl.add(
    "binding.curve",
    channel="CBL",
    label="Amplitude",
    scale={"minimum": 0, "maximum": 100, "unit": "mV"},
)

vdl = section.add(
    "track.array",
    title="VDL",
    width_mm=52,
    id_hint="vdl",
)

vdl.add(
    "binding.raster",
    channel="VDL",
    label="VDL",
)
```

A resistivity worker could use bounded local iteration:

```python
track = section.add(
    "track.normal",
    title="Resistivity",
    width_mm=36,
    id_hint="resistivity",
    x_scale={"minimum": 0.2, "maximum": 2000, "mode": "log"},
)

for channel, label in [
    ("ILD", "Deep"),
    ("ILM", "Medium"),
    ("SFL", "Shallow"),
]:
    track.add(
        "binding.curve",
        channel=channel,
        label=label,
    )
```

## 6.3 Initial allowed syntax

The first production grammar should allow only:

- module body;
- expression statements;
- simple assignment to local names;
- names;
- constants;
- lists;
- tuples;
- dictionaries;
- keyword arguments;
- attribute access on Wellplot handles;
- function/method calls;
- `for` loops over bounded local literal sequences;
- `if` statements over deterministic local values if needed.

Do not initially allow:

- imports;
- function definitions;
- classes;
- lambdas;
- `while`;
- `try`;
- context managers;
- generators;
- comprehensions;
- arbitrary operators unless explicitly required;
- arbitrary attribute mutation;
- subscript assignment;
- deletion;
- `global`;
- `nonlocal`;
- `yield`;
- async syntax;
- file operations;
- network operations;
- reflection;
- dunder access.

Additional syntax is added only when an evaluation demonstrates a need.

## 6.4 Interpreter budgets

Every execution must enforce:

- maximum source characters;
- maximum AST node count;
- maximum statements;
- maximum builder calls;
- maximum loop iterations;
- maximum nesting depth;
- maximum created objects;
- maximum diagnostics returned to a repair call;
- execution wall-clock budget.

Suggested initial limits:

```text
program source:       16,000 characters
AST nodes:             1,500
statements:              300
builder calls:           250
loop iterations:         100 total
nesting depth:             8
new sections:             32
new tracks:               96
new bindings:            256
```

These are guardrails, not product semantics. Tune them using evals.

## 6.5 No side effects during generation

Program execution initially produces an intent fragment in memory.

Only after:

1. program parsing;
2. AST validation;
3. SDK argument validation;
4. capability validation;
5. private dry-run against the current document;

may the fragment enter the graph merge.

Persistence occurs only after final deterministic verification.

---

# 7. Authoring SDK design

## 7.1 Root object

The interpreter exposes one root:

```python
wp
```

The root exposes stable operations such as:

```python
wp.report()
wp.section(section_id)
wp.add_section(...)
wp.find(...)
wp.source(...)
```

The exact surface should remain small.

## 7.2 Generic capability operation

The core extensibility primitive is:

```python
parent.add(capability_id, **arguments)
```

Examples:

```python
section.add("track.normal", ...)
track.add("binding.curve", ...)
track.add("fill.curve", ...)
track.add("annotation.typed", ...)
```

This is the operation that ensures a future capability does not require graph changes.

Convenience methods may exist for high-frequency operations, but the generic `add()` path must always remain functional.

## 7.3 Capability argument validation

Each capability owns a static arguments model.

Conceptually:

```python
class CurveBindingArguments(BaseModel):
    channel: str
    label: str | None = None
    scale: ScaleInput | None = None
    style: StyleInput | None = None
    id_hint: str | None = None
```

The registry maps:

```text
binding.curve
    ->
CurveBindingArguments
    ->
deterministic handler
```

No request-specific Pydantic model is generated.

## 7.4 Handles

SDK calls return typed internal handles:

```text
ReportHandle
SectionHandle
TrackHandle
BindingHandle
FillHandle
AnnotationHandle
```

The model sees normal variable assignment.

The interpreter internally controls which methods are legal on each handle.

## 7.5 Identity allocation

Introduce a deterministic `IdAllocator`.

Rules:

- existing objects always retain their canonical IDs;
- new track IDs are scoped to the section;
- new binding IDs are host-generated and globally unique;
- new IDs are deterministic for equivalent program order + hints where possible;
- `id_hint` is advisory and slugified;
- collisions are resolved deterministically;
- the model is never asked to manually construct a global binding ID.

For example:

```python
gr.add("binding.curve", channel="GR")
```

could deterministically allocate:

```text
main_pass.gamma_ray.gr.1
```

without requiring that value in model output.

## 7.6 Existing-object selection

Revision programs must prefer inspected identities.

Example:

```python
section = wp.section("main_pass")
track = section.track("gamma_ray")
track.update(width_mm=30)
```

For semantic requests where the user does not know the ID, deterministic inspection before program generation should resolve likely candidates and present them to the worker.

Ambiguous resolution must fail without mutation.

## 7.7 Intent accumulation

Builder calls do not directly mutate `AuthoringService`.

They write to a private `IntentBuilder`.

The final result is:

```python
AuthoringDocumentIntent
```

or an equivalent validated fragment that is immediately converted into that model.

No separate operation sequence becomes a durable product API.

---

# 8. Capability plugin v2

## 8.1 New capability responsibility

The current `CapabilitySpec` should evolve from:

```text
description + artifact_model + compiler
```

toward:

```text
semantic descriptor
+
static SDK argument model
+
allowed parent rules
+
deterministic SDK handler/compiler
+
worker documentation
+
examples
+
validation hooks
```

A possible shape:

```python
@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    capability_id: str
    category: CapabilityCategory
    description: str

    arguments_model: type[BaseModel]
    handler: CapabilityHandler

    aliases: tuple[str, ...] = ()
    allowed_parents: tuple[str, ...] = ()
    source_kinds: tuple[str, ...] = ()
    planning_hints: tuple[str, ...] = ()
    worker_hints: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()

    schema_version: str = "2"
```

The exact implementation may use a protocol rather than a dataclass. The important behavior matters more than the exact type.

## 8.2 Planner descriptor

Planner context remains compact:

```json
{
  "id": "binding.curve",
  "category": "binding",
  "description": "Bind one scalar source channel...",
  "aliases": ["curve", "scalar binding"],
  "allowed_parents": ["track.normal", "track.reference"],
  "source_kinds": ["LAS", "DLIS"]
}
```

No full JSON schema is needed by the planner.

## 8.3 Worker descriptor

Workers receive richer help only for selected capabilities:

- argument names;
- short types;
- defaults that are important;
- constraints;
- one or two examples;
- parent compatibility;
- source compatibility.

Do not dump full canonical document schemas.

## 8.4 Extensibility invariant

A test capability must be registrable without modifying:

```text
agent/workflow.py
agent/planner.py
agent/program_worker.py
authoring_program/interpreter.py
```

If a new capability requires modifications there, the plugin boundary has failed.

---

# 9. Semantic planner v2

## 9.1 New planner responsibility

The planner should answer:

- what work units are needed;
- what the work unit means;
- what source it should use;
- what capabilities are relevant;
- what explicit user constraints must be preserved;
- whether an existing object is being revised;
- what cannot be satisfied.

It should not produce the final object hierarchy.

## 9.2 Proposed models

Conceptually:

```python
class ReportTask(BaseModel):
    goal: str
    requirements: list[str]
    capability_ids: list[str] = ["report.standard"]


class SectionTask(BaseModel):
    task_id: str
    goal: str

    existing_section_id: str | None = None
    create_section_hint: str | None = None

    source_path: str | None = None
    source_format: Literal["auto", "las", "dlis"] = "auto"

    capability_ids: list[str]
    requirements: list[str]
    preserve: list[str] = []


class SemanticPlan(BaseModel):
    summary: str
    report: ReportTask | None = None
    sections: list[SectionTask]
    postconditions: list[str] = []
    unresolved_requirements: list[str] = []
```

This model is intentionally small.

## 9.3 What disappears

The planner no longer needs:

```text
SemanticComponentPlan.component_id
SemanticComponentPlan.target_id
SemanticComponentPlan.parent_component_id
globally unique binding target IDs
exact worker-owned object ordering
request-generated target Literals
```

## 9.4 Deterministic semantic resolution

Where possible, resolve these outside the model:

- source paths;
- source formats;
- existing section identities;
- header slot identities;
- available channels;
- current object inventories;
- default styles;
- capability parent legality.

The planner should not spend inference capacity rediscovering facts that deterministic code can determine.

---

# 10. Program worker v2

## 10.1 Worker input

A section worker receives:

```text
original natural-language request
section task
current section projection
relevant source manifest
available channels
selected capability docs
small SDK reference
few examples
```

It does **not** receive:

- full document schema;
- full defaults catalog;
- unrelated sections;
- all capabilities;
- runtime-generated tool schemas.

## 10.2 Worker output

The model returns one program source string.

The worker then performs:

```text
extract source
-> parse
-> validate AST
-> interpret against private SDK
-> validate capability arguments
-> create AuthoringDocumentIntent fragment
-> dry-run against private current document
-> accept or produce compact diagnostic
```

## 10.3 Repair

If rejected:

```text
diagnostic + previous program + same section task
    ->
one repair generation
```

Diagnostic example:

```text
Line 14: capability binding.raster cannot be added to track.normal.
Use a track.array parent for binding.raster.
Available array track IDs in this section: vdl.
```

This is much more actionable to a model than a deeply nested Pydantic validation trace.

## 10.4 Report worker

The report path should use the same mechanism.

Example:

```python
report = wp.report()
report.set("well_name", "X-12")
report.set("field_name", "Example Field")
report.add_remark(
    title="Interpretation Note",
    text="...",
)
```

The report capability deterministically resolves semantic report keys to canonical header slots where possible.

The current report-requirement planner and report-task decomposition should not survive unless a live evaluation proves a genuine need after the simple program worker exists.

---

# 11. Provider abstraction v2

## 11.1 New protocol

The graph should depend on a small provider-neutral interface.

Conceptually:

```python
class ModelBackendProtocol(Protocol):
    async def generate_structured(
        self,
        *,
        instructions: str,
        user_message: str,
        response_model: type[T],
    ) -> T:
        ...

    async def generate_program(
        self,
        *,
        instructions: str,
        user_message: str,
    ) -> str:
        ...
```

Provider-specific transport concerns remain in provider modules.

## 11.2 Structured generation

Use provider-native schema-constrained output when available.

Fallback mechanisms are acceptable for small planner models, but the graph must not rebuild the old general function-tool authoring loop.

## 11.3 Program generation

Program generation is ordinary text generation.

The worker may accept:

- raw Python-like source;
- exactly one fenced code block if a provider insists on fencing.

Normalization should reject:

- multiple programs;
- prose mixed with program content when ambiguous;
- tool calls;
- JSON pretending to be a program.

## 11.4 No `core.py` dependency

The new provider modules must define their own:

- provider error model;
- request metrics;
- retry classification;
- transport abstraction.

They must not import provider-loop types from `agent/core.py`.

---

# 12. LangGraph v2

## 12.1 Graph topology

Keep the graph simple:

```text
START
  |
  v
plan
  |
  v
resolve sources / deterministic context
  |
  v
dispatch report + section workers
  |
  +----> program worker(report)
  |
  +----> program worker(section 1)
  |
  +----> program worker(section 2)
  |
  +----> ...
  |
  v
merge intent fragments
  |
  v
END
```

Execution remains outside or immediately after compile graph using the existing deterministic reconstruction/revision execution functions.

## 12.2 No domain-specific branches

`workflow.py` remains capability-agnostic.

There must be no branches such as:

```python
if cbl:
    ...
elif resistivity:
    ...
```

## 12.3 State

Graph state should contain JSON-safe values:

```text
request
mode
current_document
source_manifest
semantic_plan
program_artifacts
merged_intent
diagnostics
```

Do not store live builder/interpreter objects in graph state.

---

# 13. Reconstruction and revision

## 13.1 Reconstruction

Reconstruction workers may create objects.

Host-generated IDs are allowed.

The deterministic merge must reject overlapping worker ownership.

## 13.2 Revision

Revision must preserve unrequested state.

The semantic planner should select only affected work units.

The worker receives the existing canonical object inventory for its scope.

Programs use handles to existing objects where possible.

Example:

```python
section = wp.section("main_pass")
gr = section.track("gamma_ray")
gr.update(width_mm=30)
gr.binding(channel="GR").update(
    style={"color": "green"},
)
```

## 13.3 No copy-the-world revisions

A revision worker should never reproduce the entire section simply to edit one curve.

The builder intent should contain only changed desired state plus required identity.

---

# 14. Bounded visual QA

Visual QA comes after semantic correctness.

The first migration milestone does not depend on visual QA.

When added, visual QA should return a small correction model:

```text
target scope
problem
requested semantic adjustment
```

The correction worker writes another constrained program for the affected section only.

Maximum correction cycles:

```text
1 normal correction
+ optionally 1 retry if the correction program itself is invalid
```

Do not create an open-ended screenshot-agent loop.

---

# 15. MCP boundary

The stable deterministic MCP server remains provider-free.

The agentic server exposes high-level tools:

```text
build_plot_from_request
revise_plot_from_request
```

Internally those tools call the same Python `AgentSession` / graph service used by notebook clients.

Do not make the graph call MCP.

Do not make the notebook API start the MCP server to reach local Wellplot logic.

MCP is for external interoperability, not internal layering.

---

# 16. Python and notebook API target

The desired Python-facing API is small.

Conceptually:

```python
from wellplot.agent import AgentSession

session = AgentSession.open(
    project_dir="...",
    provider="openai",
    model="...",
)

result = await session.build(
    logfile_path="draft.yaml",
    request="Build a CBL log...",
)

result = await session.revise(
    logfile_path="draft.yaml",
    request="Make the VDL track wider...",
)
```

The notebook helpers can wrap this session for display convenience.

Avoid exposing old internal plan/phase/tool-loop types as long-term public API.

---

# 17. Legacy cleanup strategy

Cleanup is staged.

The rule is:

> **First make legacy code unreachable from the new production path. Then prove it with import/reachability tests. Then delete it.**

Do not delete a module solely because it appears old.

## 17.1 Candidate legacy modules

The following modules are strong deletion candidates once v2 is live:

```text
src/wellplot/agent/core.py
src/wellplot/agent/branch_compiler.py
src/wellplot/agent/compilation.py
src/wellplot/agent/operation_executor.py
src/wellplot/agent/reconciliation_bridge.py
src/wellplot/agent/stable_fallback.py
src/wellplot/agent/tool_contract.py
```

They represent the old provider/tool/branch/operation architecture.

## 17.2 Current graph modules to replace/delete after cutover

Likely replaced by v2:

```text
src/wellplot/agent/graph/worker_contracts.py
src/wellplot/agent/graph/section_worker.py
src/wellplot/agent/graph/report_worker.py
src/wellplot/agent/graph/report_requirements.py
src/wellplot/agent/graph/report_tasks.py
src/wellplot/agent/graph/provider_adapter.py
```

The current `planner.py` and `models.py` should be rewritten around the v2 semantic plan rather than kept for compatibility indefinitely.

## 17.3 Graph modules likely worth preserving/refactoring

Potentially reusable:

```text
context_projection.py
executor.py
finalization.py
merge.py
source_context.py
state.py
verifier.py
workflow.py
reconstruction.py
reconstruction_execution.py
revision.py
revision_execution.py
```

Each must still be audited for v1 model assumptions.

## 17.4 Provider modules

Current transport code may contain useful HTTP/Responses/Chat behavior.

Do not delete it blindly.

Refactor reusable transport into the new backend interface, then remove:

- old `run_authoring()` loops;
- old tool replay;
- old `FunctionToolDefinition` dependencies;
- old provider-round semantics no longer required.

## 17.5 Public exports

Current `agent/__init__.py` exports many legacy types.

Final public exports should be deliberately small, likely centered on:

```text
AgentSession
AgentResult
AgentRunTrace / trace read helper
provider configuration types
```

Internal planner/worker/program objects should not become accidental public API.

---

# 18. Migration feature flag

During the proving period, support:

```text
WELLPLOT_AGENTIC_ENGINE=v1
WELLPLOT_AGENTIC_ENGINE=v2
```

or an equivalent explicit constructor option.

Rules:

1. v1 remains unchanged while v2 is incomplete.
2. v2 is opt-in initially.
3. after acceptance, v2 becomes default.
4. after one cleanup slice, v1 is deleted.
5. the feature flag itself is then deleted.

Do not maintain two engines indefinitely.

---

# 19. Evaluation strategy

## 19.1 Existing evaluation assets remain useful

Preserve the philosophy of the current evaluation program:

- grade persisted canonical state;
- verify prohibited unrelated mutations;
- validate render;
- measure real provider performance separately from deterministic tests.

## 19.2 Metrics added for Code Mode

Record per task:

```text
planner input characters/tokens
planner schema characters
planner rounds
worker input characters/tokens
generated program characters
AST nodes
SDK calls
program validation failures
program repair count
dry-run failures
provider latency
provider tokens
final canonical correctness
unrequested mutation count
render success
```

## 19.3 Architecture budgets

Suggested target state:

```text
dynamic request-specific worker schemas:        0
legacy agent core imports from v2 path:          0
internal MCP calls from graph/session:           0
planner provider calls per request:              1
normal program calls per work unit:              1
normal repair calls per work unit:               0
max repair calls per work unit:                  1-2
unbounded provider loops:                        0
```

## 19.4 Live acceptance target

Keep or exceed the previous release goals:

- deterministic suite: 100%;
- primary release provider: >= 90% aggregate task success over three runs per task;
- at least one OpenAI-compatible provider: >= 80%;
- no persistence on ambiguous/unsupported requests;
- full CBL reconstruction should succeed as one natural-language request, not only as manually split prompts.

## 19.5 The key A/B experiment

Before completing full migration, compare current structured section compiler with program worker on the same CBL section.

Measure:

- success rate;
- repair rate;
- provider tokens;
- latency;
- output size;
- code/schema complexity;
- semantic omissions;
- unrequested mutations.

If program mode does not show a clear reliability or simplicity advantage, stop before deleting v1.

---

# 20. Implementation rules for Codex

Every slice should:

1. have one dominant architectural purpose;
2. avoid unrelated formatting/refactoring;
3. include tests in the same commit;
4. update an evidence record;
5. leave the repository passing;
6. avoid weakening deterministic assertions;
7. avoid changing benchmark prompts merely to pass;
8. explicitly list files added/modified/deleted;
9. stop if an architectural invariant would be violated.

Recommended branch:

```text
agent-code-mode-v2
```

created from:

```text
f03f76bda097bf93e4c640e0fc1a6b82b372bd0c
```

Recommended evidence directory:

```text
docs/evaluations/agent-code-mode/
```

Recommended architecture document:

```text
docs/agent-code-mode-architecture.md
```

This plan itself can become that document after review.

---

# 21. Slice plan overview

The migration is divided into seven phases.

```text
Phase 0  Freeze, evidence, architecture guards
Phase 1  Deterministic Authoring Program kernel
Phase 2  Capability plugin v2
Phase 3  Provider and semantic planner v2
Phase 4  Program workers and LangGraph cutover
Phase 5  Public API + MCP cutover
Phase 6  Legacy deletion
Phase 7  Security, live evals, release hardening
```

The slices below are intentionally small enough to stop safely.

---

# 22. Detailed slices

## CM-00 — Freeze the baseline and create the migration scorecard

### Goal

Establish an immutable baseline at `f03f76b...` and prevent the migration from becoming another sequence of changes with no comparable evidence.

### Changes

Add:

```text
docs/evaluations/agent-code-mode/CM-00-baseline.json
docs/agent-code-mode-architecture.md
```

Record:

- commit SHA;
- production module inventory;
- agent package file sizes/line counts;
- current graph package file sizes/line counts;
- test count;
- live/deterministic eval results;
- current model-facing schema sizes;
- current provider rounds;
- current full CBL success/failure trace;
- current simple-section success;
- current report success;
- current revision success;
- current public agent exports.

### Tests

No product changes.

Run full existing suite and architecture checks.

### Exit gate

Baseline record exists and can be regenerated.

### Stop condition

Do not begin implementation if the baseline full CBL request cannot be replayed reproducibly enough to compare v1/v2.

---

## CM-01 — Adopt architecture invariants and dependency rules

### Goal

Turn this plan into enforceable architecture rules.

### Changes

Add architecture tests that fail if:

- `authoring_program` imports LangGraph;
- `authoring_program` imports MCP;
- `capabilities` imports LangGraph;
- `capabilities` imports MCP;
- new v2 graph imports `agent.core`;
- domain authoring modules import the agent package.

Add comments/docs defining the dependency direction.

### Tests

Create:

```text
tests/test_agent_v2_architecture.py
```

Use AST/import scanning rather than runtime monkey-patching.

### Exit gate

The tests pass on the new empty/skeleton packages.

---

## CM-02 — Build an explicit reachability and deletion inventory

### Goal

Know exactly what legacy modules remain reachable from public entry points before deleting anything.

### Changes

Create a script:

```text
scripts/check_agent_reachability.py
```

Seed entry points:

```text
wellplot.agent
wellplot.mcp.agentic
wellplot.mcp.agentic_server
wellplot.agent.notebook
project scripts
```

Produce a machine-readable import graph and classify modules:

```text
keep
refactor
replace
delete-after-cutover
test-only
historical-doc-only
```

### Required output

At minimum classify:

```text
core.py
branch_compiler.py
compilation.py
operation_executor.py
reconciliation_bridge.py
stable_fallback.py
tool_contract.py
graph/worker_contracts.py
graph/section_worker.py
graph/report_worker.py
graph/report_requirements.py
graph/report_tasks.py
graph/provider_adapter.py
```

### Exit gate

No deletion is authorized until this inventory is committed.

---

## CM-03 — Extend the eval harness for dual-engine A/B runs

### Goal

Allow identical prompts and starter state to run through v1 and v2.

### Changes

Extend eval runner with:

```text
--engine v1
--engine v2
```

Add result fields:

```text
program_chars
program_ast_nodes
program_calls
program_repairs
dynamic_schema_chars
legacy_core_reached
```

Initially v2 can return `not_implemented`.

### Exit gate

The same case IDs can produce comparable v1/v2 records.

---

# Phase 1 — Deterministic Authoring Program kernel

## CM-10 — Define program result models and error taxonomy

### Goal

Create the deterministic types before implementing syntax.

### Add

```text
src/wellplot/authoring_program/models.py
src/wellplot/authoring_program/errors.py
```

Suggested models:

```text
AuthoringProgram
ProgramDiagnostic
ProgramMetrics
ProgramExecutionResult
ProgramArtifact
```

Error classes:

```text
ProgramSyntaxError
ProgramPolicyError
ProgramNameError
ProgramTypeError
ProgramCapabilityError
ProgramLimitError
ProgramDryRunError
```

Diagnostics must include:

- stage;
- line/column if applicable;
- concise message;
- optional remediation hint;
- no enormous Python traceback in model-facing repair messages.

### Exit gate

Pure model/error tests pass.

---

## CM-11 — Implement AST policy validator

### Goal

Validate source without executing it.

### Add

```text
src/wellplot/authoring_program/grammar.py
src/wellplot/authoring_program/validator.py
```

### Required behavior

Allow the initial syntax defined in Section 6.

Reject:

```python
import os
open("file")
__import__("os")
wp.__class__
while True:
    ...
```

Reject any identifier/attribute beginning with `_` unless explicitly internal and impossible for model code to access.

### Tests

Include adversarial cases:

- dunder chains;
- lambda;
- comprehension;
- giant nested literals;
- recursive-looking constructs;
- invalid calls;
- excessive loops;
- excessive source size.

### Exit gate

No model source can invoke arbitrary Python behavior.

---

## CM-12 — Implement the restricted interpreter

### Goal

Interpret the allowed AST without `exec()`.

### Add

```text
src/wellplot/authoring_program/interpreter.py
src/wellplot/authoring_program/runtime.py
```

### Runtime values allowed

Only:

```text
None
bool
int
float
str
list/tuple/dict of allowed values
Wellplot SDK handles
small immutable helper values
```

### Runtime calls

A call is legal only when:

- callee is an approved root function or approved handle method;
- argument values are allowed runtime values;
- call budget is not exceeded.

### Loops

Only iterate over:

- local list/tuple values;
- approved immutable inspection collections if added later.

Count iterations globally.

### Exit gate

Interpreter can execute a synthetic builder object and produce a deterministic command journal, with all security tests passing.

---

## CM-13 — Implement deterministic ID allocation and handles

### Goal

Remove canonical identity generation from the LLM.

### Add

```text
src/wellplot/authoring_program/ids.py
src/wellplot/authoring_program/builders.py
```

### Implement

- `IdAllocator`;
- `ReportHandle`;
- `SectionHandle`;
- `TrackHandle`;
- leaf handles;
- parent ownership validation;
- deterministic collision behavior.

### Tests

Prove:

- repeated binding channels receive unique IDs;
- equivalent creation order produces stable IDs;
- two sections can use local track ID `combo`;
- bindings remain globally unique;
- revision of existing IDs does not allocate replacements.

### Exit gate

No test program is required to manually provide a binding ID.

---

## CM-14 — Compile SDK calls into AuthoringDocumentIntent

### Goal

Connect the program kernel to the existing canonical desired-state IR.

### Changes

Implement an `IntentBuilder` that accumulates validated desired-state fragments and emits:

```python
AuthoringDocumentIntent
```

### Important rule

Do not execute through `AuthoringService` yet.

This slice is compile-only.

### Tests

For representative programs, assert exact intent content for:

- report field;
- section;
- track;
- curve;
- raster;
- fill;
- annotation.

### Exit gate

Program -> intent is deterministic and independent of LangGraph/provider/MCP.

---

## CM-15 — Add private dry-run execution

### Goal

Reject semantically invalid programs before graph merge.

### Changes

Add:

```text
ProgramRuntime.dry_run(...)
```

The dry run:

1. clones current document;
2. runs existing deterministic authoring execution on the intent;
3. validates;
4. returns compact diagnostics;
5. never persists.

### Examples rejected

- missing channel;
- raster binding on incompatible track;
- illegal parent;
- invalid scale;
- ambiguous existing target.

### Exit gate

A semantically invalid program cannot enter `ProgramArtifact`.

---

## CM-16 — Add deterministic inspection facade

### Goal

Give program workers enough scoped facts without making the program perform arbitrary discovery.

### Add

```text
src/wellplot/authoring_program/inspection.py
```

Provide read-only projections such as:

```text
existing section IDs/titles
tracks in selected section
bindings in selected track
header semantic inventory
available source channels
source dimensions/kinds
```

### Important

Most inspection should happen before program generation and be supplied as worker context.

The runtime may expose a very small read-only API only when it materially reduces prompt complexity.

### Exit gate

No worker needs the entire canonical document dump.

---

# Phase 2 — Capability plugin v2

## CM-20 — Introduce CapabilitySpec v2 alongside v1

### Goal

Create the new plugin contract without breaking the current graph.

### Changes

Extend or version capability declarations with:

```text
arguments_model
handler
worker_hints
examples
```

Keep current `artifact_model/compiler` temporarily for v1.

### Important

Do not migrate every capability in this slice.

### Exit gate

One synthetic capability can register both v1 and v2 behavior.

---

## CM-21 — Migrate report.standard to SDK capability

### Goal

Prove report authoring without report worker schemas.

### Implement

Program operations:

```python
report = wp.report()
report.set(...)
report.add_remark(...)
report.update_page(...)
report.update_depth(...)
report.update_output(...)
```

Semantic header keys should resolve deterministically against inspected header archetype/aliases.

### Tests

Cover:

- well name;
- field;
- company;
- measured mud values;
- service titles;
- detail fields;
- remarks;
- page/depth/output settings.

### Exit gate

All existing deterministic report tests can be expressed through the SDK path.

---

## CM-22 — Migrate section.log_plot and track capabilities

### Goal

Create the main structural builder surface.

### Capabilities

```text
section.log_plot
track.normal
track.reference
track.array
track.annotation
```

### Required behavior

- create;
- select existing;
- update;
- preserve unspecified state;
- parent validation;
- host IDs.

### Exit gate

A complete empty section with all four track kinds can be generated from one deterministic program.

---

## CM-23 — Migrate curve and raster bindings

### Goal

Support the primary scientific content.

### Capabilities

```text
binding.curve
binding.raster
```

### Support

- channel;
- label;
- scale;
- style;
- raster profile;
- colorbar;
- sample axis;
- required source-kind checks.

### Exit gate

A CBL/VDL section can be constructed entirely through SDK calls.

---

## CM-24 — Migrate fills and annotations

### Goal

Complete current leaf capability parity.

### Capabilities

```text
fill.curve
annotation.typed
```

### Exit gate

The existing development tasks for mirrored curves/fills and annotations pass through deterministic SDK programs.

---

## CM-25 — Prove plugin extensibility with a test-only capability

### Goal

Prove the registry is now a real execution plugin boundary.

### Add

A deliberately small test-only capability or fixture plugin.

Requirement:

Adding it may change:

```text
capabilities test fixture
capability-specific test
```

It may **not** change:

```text
agent/workflow.py
agent/planner.py
agent/program_worker.py
authoring_program/interpreter.py
```

### Exit gate

Architecture test enforces this.

---

# Phase 3 — Provider and planner v2

## CM-30 — Introduce provider protocol v2 independent of core.py

### Goal

Break the graph's dependency on legacy provider-loop types.

### Add/refactor

```text
src/wellplot/agent/providers/base.py
```

Define:

```text
generate_structured
generate_program
ProviderRequestError
ProviderMetrics
```

### Exit gate

A fake/recorded v2 backend can run without importing `agent.core`.

---

## CM-31 — Add native structured planner transport for OpenAI provider

### Goal

Support the small semantic planner without the old general authoring loop.

### Requirements

- use provider-native structured output when available;
- one request/response abstraction;
- no internal tool execution;
- no MCP tool replay;
- explicit timeout;
- redacted telemetry.

### Exit gate

A small static `SemanticPlan` fixture is generated and validated using the v2 provider interface.

---

## CM-32 — Add plain program generation transport

### Goal

Generate program source as ordinary model output.

### Requirements

- raw text or one fenced code block;
- deterministic extraction;
- no function-tool submission requirement;
- output-length bound;
- provider metrics.

### Exit gate

Recorded provider fixtures cover raw, fenced, malformed, truncated, and mixed-prose responses.

---

## CM-33 — Add OpenAI-compatible provider v2

### Goal

Retain local/NVIDIA/OpenAI-compatible support.

### Requirements

- structured planner strategy selected by advertised/known capability;
- plain program generation;
- no silent fallback to OpenAI;
- explicit provider capability errors.

### Exit gate

Current compatible provider tests are represented in the v2 interface.

---

## CM-34 — Add compact bounded program repair

### Goal

Allow one correction when validation gives the model useful feedback.

### Repair input

Only:

- semantic task;
- relevant SDK docs;
- previous program;
- compact diagnostic.

Do not resend unrelated document context unless required.

### Limits

Default:

```text
initial generation + 1 repair
```

Optional second repair only for parser/transport formatting failure.

### Exit gate

Repair metrics are visible in traces/evals.

---

## CM-40 — Replace ReconstructionPlan with SemanticPlan v2

### Goal

Remove object-identity and hierarchy construction from planner inference.

### Changes

Introduce the models in Section 9.

Planner prompt must explicitly say:

- do not invent object IDs;
- do not describe operation sequences;
- do not emit component trees;
- identify semantic work units and constraints only.

### Migration

Keep v1 planner available behind engine v1.

### Exit gate

Planner schema is materially smaller than current reconstruction plan schema and contains no component/target parent tree.

---

## CM-41 — Deterministic source/target enrichment after planning

### Goal

Move facts from model reasoning into code.

### Implement

After `SemanticPlan`:

- normalize source paths;
- infer source formats;
- load selected source context;
- resolve existing section candidates;
- resolve report semantic slot inventory;
- prepare worker projections.

### Exit gate

The program worker receives canonical inspected IDs without requiring the planner to invent them.

---

# Phase 4 — Program workers and graph v2

## CM-42 — Implement ProgramSectionCompiler

### Goal

Replace dynamic `section_contract()` structured generation.

### Add

```text
src/wellplot/agent/program_worker.py
```

or a section-specific wrapper around a generic program worker.

### Behavior

```text
SectionTask
-> compact worker context
-> generate_program()
-> validate/interpret
-> dry-run
-> optional repair
-> ProgramArtifact(intent_fragment)
```

### Important

Do not delete v1 worker yet.

### Exit gate

Single scalar-section deterministic/live pilot succeeds.

---

## CM-43 — Run the CBL section A/B experiment

### Goal

Validate the architectural hypothesis before broad migration.

### Compare

Current:

```text
SectionCompiler + worker_contracts
```

against:

```text
ProgramSectionCompiler
```

using the same unchanged CBL section request/source/starter.

### Required evidence

At least:

- three live runs on primary provider;
- semantic outcome;
- omissions;
- repair count;
- prompt/schema characters;
- latency/tokens;
- source generated size.

### Decision gate

Proceed only if v2:

- is materially simpler, or
- materially more reliable, ideally both.

If it is worse, stop and review the SDK/context rather than layering more agents.

---

## CM-44 — Implement ProgramReportCompiler

### Goal

Replace report requirement/task/worker chain.

### Behavior

One report semantic task -> one program worker.

### Delete authorization

If parity is reached, mark these v1-only:

```text
report_requirements.py
report_tasks.py
report_worker.py
```

but do not delete until v2 cutover.

### Exit gate

Full report development set passes.

---

## CM-45 — Build v2 compile graph

### Goal

Wire semantic planner + program workers into the existing generic fan-out topology.

### Graph

```text
plan_v2
-> enrich_context
-> Send(report/sections)
-> compile_program_artifact
-> merge_intent
```

### State

Introduce v2 state models or cleanly replace current state.

### Exit gate

Multi-section deterministic program artifacts merge correctly regardless of worker completion order.

---

## CM-46 — Integrate existing deterministic reconstruction execution

### Goal

Use the current safe lower half unchanged where possible.

### Required

Merged intent goes through:

- `AuthoringService`;
- deterministic reconciliation/execution;
- semantic verifier;
- rollback behavior;
- persistence only on success.

### Exit gate

No direct SDK/program persistence path exists.

---

## CM-47 — Implement revision mode v2

### Goal

Support natural-language scoped changes without rebuilding the world.

### Cases

- width change;
- curve style;
- scale change;
- add curve to existing track;
- remove annotation;
- add remark;
- change report field;
- add new section.

### Exit gate

Prohibited unrelated mutations remain zero in revision evals.

---

## CM-48 — Add bounded visual correction

### Goal

Restore visual feedback only after semantic v2 is stable.

### Behavior

render -> visual evaluator -> semantic correction request -> scoped program worker -> one correction.

### Exit gate

Visual correction cannot change unrelated sections and cannot loop indefinitely.

---

# Phase 5 — Public API and MCP cutover

## CM-50 — Add AgentSession v2 direct Python API

### Goal

Make Python/notebook use internal services directly.

### Add

```text
src/wellplot/agent/session.py
```

Public methods:

```text
build
revise
inspect trace/result
```

### Exit gate

A notebook does not need to start an MCP subprocess for local authoring.

---

## CM-51 — Cut agentic MCP tools to AgentSession/graph v2

### Goal

Keep MCP as an external edge.

### Preserve tool names if practical

```text
build_plot_from_request
revise_plot_from_request
```

This minimizes client churn.

### Change internals

`mcp/agentic.py` calls v2 service/session.

Remove direct dependency on:

```text
agent.core.ProviderAdapterError
```

### Exit gate

MCP integration tests pass with v2 engine.

---

## CM-52 — Migrate notebook helpers

### Goal

Keep current notebook ergonomics without self-MCP coupling.

### Refactor

`ProjectSession` should wrap `AgentSession`, not `LocalStdioMcpRuntime` for normal local authoring.

MCP client helpers can remain only if they are explicitly useful for external-client testing.

### Exit gate

Published notebook examples use the direct v2 Python path.

---

## CM-53 — Make v2 default and freeze v1

### Goal

Stop feature work on old engine.

### Changes

- default engine = v2;
- v1 only via explicit compatibility flag;
- CI runs both for one final transition window;
- docs mark v1 deprecated/internal.

### Exit gate

Primary live acceptance meets target with v2 default.

## Phase 5A — Typed Section-Worker Adoption

CM-53 routing is implemented, but the public transition remains open because
the unchanged live acceptance gate has not passed reliably for the
program-based section worker. The following slices resume the CM lineage using
the EXP-TW evidence without changing routing until their designated gates:

### CM-54 — Reconcile production scope with typed-worker evidence

Complete as a documentation-only design slice at baseline `5c98ad1`. The
promoted contract is recorded in
[`docs/typed-section-worker-contract.md`](typed-section-worker-contract.md)
and its development memory. It freezes the static semantic response shape,
required track discriminators, worker/host ownership, repeated-binding and
ordering invariants, the EXP-TW representability matrix, planner/enricher
input-sufficiency boundary, reconstruction/revision limits, and graph/result
integration constraints.

CM-54 changes no production behavior, routing, provider, planner, enrichment,
graph, repair, MCP, notebook, persistence, rendering, or test behavior.
CM-55 is the separately authorized implementation slice; CM-56 through CM-58
remain gated by later evidence and acceptance.

### CM-55 — Add the production typed section contract

Add the production static semantic section models and deterministic semantic
compiler while preserving existing routing.

### CM-56 — Exercise the real planner/enricher boundary

Run the typed worker against real production task/context inputs with shadow or
A/B evidence while leaving the current route unchanged.

### CM-56R — Evidence-driven input strengthening, if required

Only if CM-56 demonstrates insufficient planner-to-section information,
strengthen that semantic boundary without introducing benchmark-specific rules.

### CM-57 — Cut over the validated section worker

Replace `ProgramSectionCompiler` in the v2 graph only after the preceding
evidence supports the change. The report worker remains program-based.

### CM-58 — Re-run unchanged public acceptance

Re-run the unchanged public/default-route acceptance contract and determine
whether the CM-53 transition can close.

---

# Phase 6 — Legacy deletion

## CM-60 — Prove v2 does not import core.py

### Goal

Create the hard deletion boundary.

### Architecture test

Import and execute:

```text
AgentSession
v2 graph
agentic MCP server
notebook v2
```

while deliberately blocking import of:

```text
wellplot.agent.core
```

### Exit gate

Everything v2 works.

Only v1 tests may still import core.

---

## CM-61 — Delete old provider/tool-loop compiler modules

### Delete once reachability permits

```text
src/wellplot/agent/core.py
src/wellplot/agent/branch_compiler.py
src/wellplot/agent/compilation.py
src/wellplot/agent/operation_executor.py
src/wellplot/agent/reconciliation_bridge.py
src/wellplot/agent/stable_fallback.py
src/wellplot/agent/tool_contract.py
```

### Also delete

Tests whose only purpose is validating deleted architecture.

Do not delete tests of deterministic authoring behavior; migrate those assertions to the new path where appropriate.

### Exit gate

Full suite passes with these files absent.

---

## CM-62 — Delete schema-cascade graph code

### Delete/replace

```text
graph/worker_contracts.py
graph/section_worker.py
graph/report_worker.py
graph/report_requirements.py
graph/report_tasks.py
graph/provider_adapter.py
```

Remove runtime dynamic model construction that existed only to constrain worker document artifacts.

### Architecture assertion

Search production v2 agent path for request-driven `create_model()` usage.

Expected: zero.

Static model creation elsewhere is not automatically forbidden; the specific dynamic worker pattern is.

### Exit gate

Full CBL and development evals pass.

---

## CM-63 — Remove v1 feature flag and compatibility engine

### Goal

End dual architecture.

### Changes

- remove engine v1;
- remove dual-run production routing;
- retain archived baseline eval records;
- remove dead configuration.

### Exit gate

One production authoring path exists.

---

## CM-64 — Clean public exports and notebook/MCP leftovers

### Goal

Shrink the public surface.

### `wellplot.agent` target exports

Keep only intentionally supported types.

Remove legacy:

```text
AuthoringPlanPhase
AuthoringPlanResult
AuthoringRunState
AuthoringToolCall
BranchOperationGroup
DirectBranchCompilationResult
StableToolProfile
...
```

unless a separate non-agent public use is proven.

### Exit gate

API tests match documented exports.

---

## CM-65 — Provider transport cleanup

### Goal

Remove old round/tool-replay implementation while preserving useful transport code.

### Review

```text
providers/_openai_chat.py
providers/_openai_responses.py
providers/openai.py
providers/openai_compat.py
```

Keep only code reachable from v2 provider protocol.

### Exit gate

No old `run_authoring` general tool-loop remains.

---

## CM-66 — Dependency and package cleanup

### Goal

Align optional extras with actual architecture.

Potential end state:

```text
graph = langgraph
agent = openai + graph
mcp = mcp
```

Do not force MCP into local Python agent usage unless required.

Update `all`.

Review console scripts:

```text
wellplot-mcp
wellplot-agentic-mcp
```

### Exit gate

Fresh environment matrix installs and smoke tests pass.

---

## CM-67 — Archive/supersede historical architecture documents

### Goal

Prevent future Codex sessions from following obsolete plans.

### Action

Mark old documents clearly as historical/superseded, including the earlier MCP recovery plan where its "no LangGraph" rule conflicts with the now-approved direction.

Do not erase history.

Add a top-level pointer to the active architecture document.

### Exit gate

There is exactly one document marked as the active agent architecture.

---

# Phase 7 — Security and release hardening

## CM-70 — Adversarial program security suite

### Goal

Prove code mode is not arbitrary code execution.

### Cases

Attempt:

```text
imports
filesystem
network
subprocess
reflection
dunder access
class construction
function definitions
infinite loops
huge loops
huge literals
attribute mutation
access to interpreter internals
exception abuse
```

### Exit gate

All are rejected before side effects.

---

## CM-71 — Full natural-language CBL acceptance

### Goal

Pass the product task that motivated the architecture change.

One unchanged natural-language request must be able to create a full CBL log including the requested mixture of:

- report/header;
- source;
- section(s);
- depth/reference track;
- scalar tracks;
- CBL amplitude;
- CCL/GR where requested;
- VDL raster;
- main/repeat layout if requested;
- remarks/settings.

### Required runs

At least three primary-provider runs from clean state.

### Exit gate

Meets primary live target with no manual decomposition.

---

## CM-72 — Cross-domain held-out acceptance

### Goal

Prove the architecture is not a CBL-specific workaround.

Use held-out cases such as:

- caliper/mirrored binding;
- generic custom scalar track;
- resistivity;
- mixed raster/annotation;
- report-heavy cased-hole request.

### Exit gate

No orchestration changes are required to pass a newly enabled supported capability.

---

## CM-73 — Context, latency, and complexity budget review

### Goal

Measure whether the architecture actually simplified the model-facing system.

### Compare v1 baseline vs final

- agent production LOC;
- graph LOC;
- dynamic schema chars;
- prompt chars;
- model calls;
- repair rate;
- latency;
- token usage;
- live success.

### Desired direction

At minimum:

```text
dynamic worker schema chars -> approximately zero
legacy core reachable -> zero
agent public surface -> smaller
normal provider rounds -> fewer
full CBL success -> higher
```

### Exit gate

If code mode increases complexity without improving reliability, do not call the migration complete.

---

## CM-74 — Final release gate and architecture freeze

### Goal

Close the migration.

### Required commands

At minimum:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mkdocs build --strict
```

plus deterministic and live agent eval suites.

### Required documentation

- architecture;
- SDK safety model;
- provider configuration;
- Python usage;
- MCP usage;
- capability authoring guide;
- evaluation evidence;
- migration notes.

### Final invariant checks

```text
one production agent engine
zero legacy core.py
zero request-specific worker schemas
zero internal self-MCP authoring
zero arbitrary code execution
one canonical desired-state IR
deterministic mutation authority intact
capability-agnostic graph intact
```

---

# 23. Legacy module disposition table

| Module | Disposition | Timing | Reason |
|---|---|---:|---|
| `agent/core.py` | Delete | CM-61 | Legacy provider/tool loop; current graph still reaches it through adapter |
| `agent/branch_compiler.py` | Delete | CM-61 | Old operation/branch compilation architecture |
| `agent/compilation.py` | Delete | CM-61 | Old compiler path superseded by program compiler |
| `agent/operation_executor.py` | Delete | CM-61 | Old agent-operation execution layer; deterministic authoring executor remains |
| `agent/reconciliation_bridge.py` | Delete | CM-61 | Transitional bridge from old agent architecture |
| `agent/stable_fallback.py` | Delete | CM-61 | Host fallback for old tool loop |
| `agent/tool_contract.py` | Delete | CM-61 | Old model-facing stable tool-profile architecture |
| `agent/execution_trace.py` | Keep/refactor | early | Useful observability independent of old engine |
| `agent/mcp.py` | Major refactor / maybe shrink | CM-52/64 | Self-MCP path should not be normal local execution |
| `agent/notebook.py` | Refactor | CM-52 | Preserve UX, replace underlying runtime |
| `graph/worker_contracts.py` | Delete | CM-62 | Central schema cascade being replaced |
| `graph/section_worker.py` | Replace | CM-42/62 | Program worker replaces artifact generation |
| `graph/report_worker.py` | Replace | CM-44/62 | Program worker replaces report artifact generation |
| `graph/report_requirements.py` | Delete if no eval need | CM-44/62 | Extra report planning boundary |
| `graph/report_tasks.py` | Delete if no eval need | CM-44/62 | Extra report decomposition boundary |
| `graph/provider_adapter.py` | Delete | CM-30/62 | Imports legacy core and old tool submission |
| `graph/models.py` | Rewrite | CM-40 | Replace component/target-heavy plan |
| `graph/planner.py` | Rewrite | CM-40 | Small semantic planner |
| `graph/workflow.py` | Keep/refactor | CM-45 | Generic fan-out is useful |
| `graph/source_context.py` | Keep/refactor | CM-41 | Deterministic source enrichment is useful |
| `graph/context_projection.py` | Keep/refactor | CM-41/42 | Context minimization remains useful |
| `graph/merge.py` | Keep/refactor | CM-45 | Deterministic intent merge remains useful |
| `graph/verifier.py` | Keep | CM-46 | End-state verification is core safety |
| `graph/reconstruction_execution.py` | Keep/refactor | CM-46 | Safe apply/rollback path |
| `graph/revision_execution.py` | Keep/refactor | CM-47 | Safe revision path |

---

# 24. Tests to retain versus tests to retire

## 24.1 Retain/migrate

Tests proving:

- canonical authoring models;
- reconciler;
- authoring service;
- deterministic execution;
- source validation;
- rendering;
- rollback;
- graph merge;
- semantic verification;
- MCP high-level behavior;
- source context;
- cross-domain outcome acceptance.

## 24.2 Retire after v1 deletion

Tests whose only contract is:

- old provider rounds;
- old tool replay;
- old request inventories;
- old branch operation compilation;
- old stable tool budget;
- old fallback guard;
- old dynamic worker Pydantic schema structure.

Before deletion, verify that no unique product behavior is only covered by those tests.

---

# 25. New test suites

Create focused suites:

```text
tests/test_authoring_program_validator.py
tests/test_authoring_program_interpreter.py
tests/test_authoring_program_limits.py
tests/test_authoring_program_ids.py
tests/test_authoring_program_builder.py
tests/test_authoring_program_dry_run.py
tests/test_capability_sdk_plugins.py
tests/test_agent_v2_planner.py
tests/test_agent_v2_program_worker.py
tests/test_agent_v2_program_repair.py
tests/test_agent_v2_graph.py
tests/test_agent_v2_revision.py
tests/test_agent_v2_mcp.py
tests/test_agent_v2_security.py
```

Prefer table-driven tests.

---

# 26. Trace model

Trace stages should become easy to read.

Suggested event sequence:

```text
run_started
context_ready

planner_started
planner_finished

source_context_ready

worker_started
program_generated
program_parse_ok
program_policy_ok
program_sdk_validation_ok
program_dry_run_ok
worker_finished

merge_started
merge_finished

execution_started
execution_finished

semantic_verification_started
semantic_verification_finished

render_started
render_finished

visual_qa_started
visual_qa_finished

run_finished
```

On repair:

```text
program_rejected
program_repair_started
program_repair_generated
...
```

Avoid exposing hidden chain-of-thought. Store only operational evidence.

---

# 27. Program diagnostics contract

A model-facing diagnostic should be short.

Good:

```text
Line 9: binding.raster cannot be added to track.normal.
Parent capability must be track.array.
Change the VDL parent track to track.array and resubmit the program.
```

Bad:

```text
Pydantic ValidationError: 17 validation errors for Union[...]
...
```

Keep the full technical exception in developer trace if useful, but not in the repair prompt.

---

# 28. Context construction rules

## Planner receives

- request;
- compact current document summary;
- compact source summary;
- planner capability catalog.

## Section worker receives

- request;
- `SectionTask`;
- one selected section projection or new-section scaffold;
- selected source facts;
- selected capability worker docs;
- SDK core reference;
- max 2-4 examples relevant to those capabilities.

## Report worker receives

- request;
- `ReportTask`;
- report/header semantic inventory;
- report capability docs;
- report examples.

## Never send by default

- unrelated section contents;
- entire canonical document JSON schema;
- every capability schema;
- renderer implementation details;
- entire defaults corpus;
- legacy tool catalog.

---

# 29. Capability documentation format

Prefer concise generated docs such as:

```text
CAPABILITY: binding.curve
PARENT: track.normal | track.reference

CALL:
track.add(
    "binding.curve",
    channel: str,
    label: str | None = None,
    scale: {minimum, maximum, mode?, unit?} | None = None,
    style: {color?, linewidth?, linestyle?} | None = None,
    id_hint: str | None = None,
)

RULES:
- channel must exist in selected source unless explicitly computed/derived
- scale minimum/maximum are physical left/right endpoints
- do not manually construct binding_id

EXAMPLE:
gr.add("binding.curve", channel="GR", scale={"minimum": 0, "maximum": 150})
```

This is more model-usable than a full JSON Schema dump.

---

> **Historical pre-TW planning note:** Sections 30 onward preserve the original
> pre-EXP-TW migration assumptions and review criteria. The dated architecture
> revision above and the CM-54 through CM-58 phase inserted after CM-53 govern
> current sequencing; these sections are retained so the original reasoning is
> not rewritten.

# 30. Handling defaults

Do not require the model to emit defaults.

SDK capability handlers should apply domain defaults deterministically where appropriate.

The worker should specify only:

- explicit user requirements;
- values required to construct the object;
- intentional overrides.

This prevents generated programs from becoming verbose copies of canonical state.

---

# 31. Handling unsupported requests

The system should fail semantically, not hallucinate.

Planner:

```text
unresolved_requirements
```

Worker:

```text
ProgramCapabilityError
```

Final result:

- no persistence;
- clear user-facing unsupported/ambiguous reason;
- trace evidence.

Do not map unknown scientific requests to the nearest capability silently.

---

# 32. Handling ambiguity

Example:

> "Make the GR track wider"

If two plausible GR tracks exist:

1. deterministic context resolver detects ambiguity;
2. planner/worker does not arbitrarily select one;
3. no mutation;
4. result reports candidate identities.

Where an unambiguous semantic resolver exists, use it deterministically before invoking the model.

---

# 33. Handling computed/derived data

The architecture should leave room for future computed channels without putting numerical computation into the LLM.

Future capability:

```text
derived.channel
```

would own deterministic computation configuration.

The model chooses/configures the capability.

Wellplot executes the calculation.

This keeps the same architecture useful as Wellplot becomes more scientific.

---

# 34. Handling future `track.image` / well diagram capabilities

A future image track should require:

- canonical model support;
- renderer support;
- a capability plugin;
- capability argument model;
- deterministic handler;
- tests;
- docs.

It should **not** require:

- a graph branch;
- a new planner type;
- edits to central worker schema construction;
- a new agent.

This is the concrete extensibility standard.

---

# 35. Expected end-state code reduction

The migration will add:

- restricted interpreter;
- SDK;
- v2 provider interface;
- simpler planner/worker.

But it should remove a substantially larger amount of legacy orchestration:

- 370 KB-scale `core.py`;
- branch compiler;
- old compilation layer;
- old operation executor;
- fallback;
- reconciliation bridge;
- tool contract;
- dynamic worker-contract compiler;
- report subplanner/task machinery;
- old provider tool loop.

The final agent package should be easier to understand by reading a small number of modules in dependency order.

A new contributor should be able to understand the production path roughly as:

```text
session.py
-> planner.py
-> workflow.py
-> program_worker.py
-> authoring_program/*
-> AuthoringService
```

If the final path still requires understanding several generations of old architecture, cleanup is incomplete.

---

# 36. Recommended PR/commit strategy

Default: one slice per commit/PR-sized checkpoint.

Do not combine:

- new engine implementation;
- legacy deletion;
- provider rewrite;
- notebook migration;

into one large change.

Recommended milestones:

```text
Milestone A: CM-00 through CM-16
Deterministic SDK exists; no provider changes yet.

Milestone B: CM-20 through CM-34
Capabilities + provider v2 exist.

Milestone C: CM-40 through CM-44
Semantic planner and single-worker code mode proven.

Milestone D: CM-45 through CM-48
Full graph reconstruction/revision parity.

Milestone E: CM-50 through CM-53
Public/MCP cutover.

Milestone F: CM-60 through CM-67
Legacy deletion and package cleanup.

Milestone G: CM-70 through CM-74
Security/live acceptance/release.
```

---

# 37. Hard stop gates

The program must stop for architecture review if any of these happen:

1. two consecutive slices add model-facing complexity without increasing task success;
2. a new runtime-generated schema system starts appearing around program generation;
3. a second general planner is proposed;
4. an unbounded repair/tool loop is proposed;
5. generated code requires arbitrary Python execution;
6. a capability addition requires a new graph branch;
7. v2 begins importing `core.py`;
8. full CBL success remains unchanged after the program-worker pilot;
9. deterministic safety assertions need to be weakened to make v2 pass;
10. the migration begins adding CBL-specific orchestration logic.

---

# 38. Definition of architecture-complete

The architecture migration is complete only when all of the following are true:

- natural-language requests enter one production agent path;
- one small semantic planner decomposes the request;
- pre-TW section/report workers emit constrained Wellplot programs;
- programs are interpreted, never arbitrarily executed;
- program operations compile to `AuthoringDocumentIntent`;
- `AuthoringService` remains mutation authority;
- deterministic reconciliation/validation/rollback remain intact;
- LangGraph handles only orchestration/state/fan-out;
- capabilities own static SDK arguments and deterministic behavior;
- adding a supported capability does not change graph topology;
- planner no longer emits component trees or global binding IDs;
- no request-specific dynamic worker schemas exist;
- no v2 runtime imports legacy `core.py`;
- no internal self-MCP authoring path exists;
- old provider/tool-loop/compiler code is deleted;
- full CBL reconstruction passes live acceptance;
- revision passes preservation/isolated-change acceptance;
- held-out cross-domain tasks pass;
- security suite proves no arbitrary code execution.

---

# 39. First implementation sequence to give Codex

If implementation starts immediately, the first authorized sequence should be:

```text
CM-00
CM-01
CM-02
CM-03
CM-10
CM-11
CM-12
CM-13
CM-14
CM-15
CM-16
```

Then stop.

Do **not** start provider or graph changes until the deterministic program kernel can:

1. parse a program;
2. reject unsafe syntax;
3. build a CBL-like section using deterministic SDK calls;
4. generate correct `AuthoringDocumentIntent`;
5. dry-run it through the existing authoring stack;
6. prove host-generated IDs;
7. prove no LangGraph/MCP dependency.

That checkpoint gives us the cleanest possible architectural proof before touching inference again.

The second authorized sequence should then be:

```text
CM-20
CM-21
CM-22
CM-23
CM-24
CM-25
CM-30
CM-31
CM-32
CM-33
CM-34
CM-40
CM-41
CM-42
CM-43
```

Then stop again for the CBL A/B decision.

Only after CM-43 shows evidence in favor of code mode should Codex be authorized to continue into the full graph cutover and legacy deletion.

---

# 40. Suggested Codex completion report for every slice

Codex should end each slice with:

```text
Slice:
Commit:

Implemented:
- ...

Files added:
- ...

Files modified:
- ...

Files deleted:
- ...

Architecture invariants checked:
- ...

Tests:
- command -> result
- command -> result

Eval:
- baseline:
- new:
- delta:

Production LOC:
- added:
- deleted:
- net:

Model-facing metrics:
- planner schema chars:
- worker schema chars:
- prompt chars:
- provider calls:
- repair calls:

Known limitations:
- ...

Proceed / stop recommendation:
- ...
```

This prevents "tests pass" from being confused with "agent capability improved."

---

# 41. Final recommendation

Do not attempt to rescue the current schema-heavy worker by adding more planner rules before this migration pilot.

The repository already contains a strong deterministic authoring system and a reasonable generic graph. The next value comes from simplifying the boundary between inference and deterministic software.

The architecture should make the model responsible for:

```text
understand
decompose
choose capabilities
write a short domain program
repair a bounded error
```

and make Wellplot responsible for:

```text
identity
types
defaults
ownership
validation
source applicability
reconciliation
mutation
rollback
rendering
verification
persistence
```

That split aligns the model with the work it is good at and puts scientific/document correctness back into deterministic software.

The migration succeeds not when the model can satisfy a more sophisticated schema, but when the schema machinery is no longer needed for the model to construct a complete well log.
