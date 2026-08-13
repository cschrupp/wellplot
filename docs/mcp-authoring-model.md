# MCP Authoring Model

Last updated: 2026-08-12

## Mission

`wellplot` should help scientists and technical users plot their data in an
easy and intuitive way with little or no knowledge of the application's
internal implementation details.

This applies equally to:

- the Python API
- YAML/savefile workflows
- MCP-driven natural-language authoring
- notebook-based agent workflows

The final-user mental model should be:

- "I want a section here."
- "Put these curves on this track."
- "Use this scale."
- "Style this curve like this."
- "Fill these header values."

The final-user mental model should not be:

- "I need to know hidden packet-blueprint rules."
- "I need to understand internal reconciliation passes."
- "I need to guess which internal artifact is authoritative."

## Product Direction

The MCP surface should remain:

- deterministic
- explicit
- inspectable
- previewable
- schema-backed

The agent should add convenience, not hidden authority.

That means:

- the agent interprets freeform intent
- MCP tools mutate explicit canonical objects through the deterministic
  authoring service
- defaults fill missing details only
- explicit user instructions override defaults

The MCP should not drift toward an example-reconstruction engine that only
works when a hidden packet specification is present.

## Canonical Authoring Model

The canonical source of truth is a strict in-memory authoring contract. YAML is
a first-class serialization format for that contract, not a separate object
model and not the authority for Python or MCP behavior.

The authoring contract will use Pydantic v2 models at the public
serialization/API boundary. Those models will generate the JSON Schema used by
YAML validation and MCP discovery. The `wellplot.authoring` compatibility
module now builds the existing render dataclasses, which remain
renderer-facing implementation objects. Legacy render-only fields remain in
an explicit compatibility extension until their canonical value objects are
implemented.

MCP, Python API, YAML, agent verification, and documentation must operate on or
be generated from the same canonical contract.

The field-level implementation inventory is maintained in
[docs/authoring-contract-inventory.md](authoring-contract-inventory.md).

### Contract Layers

- data contract: existing channel classes and `WellDataset`
- authoring contract: strict report, section, track, binding, and report-content
  models
- render contract: existing renderer-facing dataclasses
- service contract: deterministic object reads and mutations shared by Python
  API and MCP

This split preserves healthy lower layers while removing duplicate public
definitions.

### Form Objects

Form objects define structure, layout, and report organization.

Primary form objects:

- `report`
- `section`
- `track`
- `heading`
- `remarks`
- `tail`

Track subtypes are form specializations:

- `reference` track
- `normal` track
- `array` track
- `annotation` track

Representative form properties:

- object `id`
- title/subtitle text
- physical size such as `width_mm`
- order/position within a parent
- page/depth/layout settings
- track kind
- track grid configuration
- track x-scale configuration
- report/header/tail enablement and styling

### Content Objects

Content objects define what is displayed inside the form structure.

Primary content objects:

- `curve binding`
- `raster binding`
- `fill`
- `annotation object`
- reference-track local overlay/event objects when exposed publicly

Representative content properties:

- source channel
- label
- scale
- style
- binding identity such as `binding_id`
- fill kind and fill targets
- raster profile, colormap, colorbar, and sample-axis settings
- annotation type, geometry, lane placement, and local styling

### Parent / Child Relationships

The public authoring model should preserve a simple hierarchy:

- a `report` owns sections plus report-level heading/remarks/tail blocks
- a `section` owns ordered tracks and its own data-source routing
- a `track` owns layout settings and accepts only compatible content objects

Compatibility rules should stay explicit:

- `normal` tracks accept curve bindings and fills
- `array` tracks accept raster bindings and optionally supported overlays
- `reference` tracks accept reference-specific overlays/events
- `annotation` tracks accept annotation objects, not generic curve/raster
  bindings

### Natural Authoring Hierarchy

The provider and MCP discovery surfaces must expose the canonical document in
the same hierarchy that a user edits it. A provider should never receive
header mutations, section construction, raster configuration, and annotation
schemas in one undifferentiated authoring contract.

The public hierarchy is:

```text
authoring document
|-- document settings
|   |-- output
|   |-- page
|   `-- depth
|-- report content
|   |-- title and subtitle
|   |-- header
|   |   |-- general fields
|   |   |-- service titles
|   |   `-- detail rows and cells
|   |-- remarks
|   `-- tail
`-- sections (ordered)
    `-- section
        |-- title, subtitle, depth range, and data-source routing
        `-- tracks (ordered)
            `-- track
                |-- form, width, scale, grid, and header display
                |-- curve bindings and fills
                |-- raster bindings and supported overlays
                `-- annotation objects
```

Data-source inspection and channel discovery provide read-only context for
this hierarchy. Validation, preview, render, and save are lifecycle operations
over it; they are not additional authoring object families.

Each hierarchy node must publish, from the canonical typed contract:

- its stable identity and parent identity
- its allowed child object kinds
- supported `list`, `get`, `create`, `update`, `remove`, `move`, and `validate`
  operations
- required-on-create and mutable-on-update properties
- finite, constrained, contextual, and relational value rules
- applicable generic defaults and their precedence
- the canonical getter used for read-after-write verification

This metadata must be generated rather than copied into provider prompts or a
separately maintained vocabulary.

### Hierarchy-Aware Agent Exposure

Natural-language compilation should traverse the hierarchy instead of asking a
model to solve a partial YAML graph:

1. split the request into user clauses and classify only their top-level branch
2. inspect the smallest current parent context needed by each clause
3. compile one small typed object operation for that branch and parent
4. resolve human targets, omitted defaults, and contextual references
   deterministically
5. order parent operations before child operations
6. execute each operation through the canonical service and read it back
7. validate and preview only after the requested object outcomes pass

A mixed request may therefore create independent report-content and log-section
work units, but no individual provider stage receives both contracts. Preserve
and negative instructions become assertions or postconditions rather than
synthetic mutations.

The agent must compile canonical object operations, not raw YAML paths and not
large partial `AuthoringDocumentIntent` fragments. YAML assembly, identity
generation, defaults, compatibility checks, atomic persistence, and operation
ordering remain deterministic responsibilities.

## Values And Constraints

Defining every property does not mean every value is a finite enum. The
canonical contract distinguishes:

- finite values such as track, scale, fill, raster, and annotation kinds
- constrained values such as positive widths, opacity ranges, and color forms
- contextual values such as channel, section, track, and binding identifiers
- relational values such as fill targets and compatible child objects
- explicit extension mappings where vendor/plugin metadata must remain open

Arbitrary extra keys are not an extensibility mechanism. Standard models reject
them, and intentional extension data must use a named `extensions` field.

## Deterministic Object Operations

Every persisted authoring object must be inspectable and editable through the
same deterministic service used by the Python API and MCP.

The operation vocabulary is:

- `list`
- `get`
- `create`
- `update`
- `remove`
- `move` for ordered collections
- `validate` without persistence

This is the intended meaning of getters and setters. The project should prefer
typed create/update models and atomic validation over mutable property setters
that can temporarily leave an object invalid.

## Authoring Precedence

The precedence model should be explicit and stable:

1. explicit user instruction
2. explicit "keep/revise" preservation of existing draft state
3. defaults catalogs
4. starter scaffolds and examples

This rule exists to protect user intent.

If a user explicitly asks for:

- a different width
- a different scale
- a different line color
- a different line style

then that explicit instruction must win over any fallback convention.

## Defaults, Not Hidden Packet Authority

The long-term direction should favor defaults catalogs over authoritative packet
blueprints.

Defaults are fallback guidance. They are not hidden bosses.

Useful defaults catalogs include:

- track-family defaults
- curve-family defaults
- raster-family defaults
- header archetypes
- starter scaffolds

Examples:

- a resistivity family may suggest common log-scale conventions
- a caliper family may suggest common mirrored-pair styling
- a VDL family may suggest common raster presentation defaults

Those defaults should only fill fields that the user did not specify.

## Role of Examples and Scaffolds

Examples and starter scaffolds remain useful, but they should be framed
correctly.

They are for:

- starting points
- demonstrations
- regression fixtures
- reusable scaffolds

They are not meant to be a second authoritative object model.

## Role of the Agent

The agent should:

- classify user intent
- decompose multi-object requests into generic authoring phases
- inspect the current draft state
- choose deterministic MCP tools
- use defaults only for unspecified details
- verify that each phase produced a persisted change or a successful final
  validation/preview

The agent should not silently restore hidden packet rules that contradict the
user's explicit request.

The agent must not construct raw YAML-shaped dictionaries once the canonical
object service is available. Its role is intent interpretation, deterministic
tool selection, and read-after-write verification.

## Immediate Design Consequences

The next MCP/agent cleanup should move toward:

- one strict authoring contract before another authoring vocabulary is
  published
- generated schema, discovery, and reference documentation from that contract
- complete deterministic object read/write coverage
- defaults catalogs for reusable conventions
- clear compatibility rules between form and content objects
- explicit precedence enforcement
- packet/example assets that behave as scaffolds instead of hidden authority

## Transitional Note

The current packet-blueprint path was useful as an experiment because it helped
surface:

- phase planning needs
- verification gaps
- missing deterministic edit tools

But it also showed a product risk:

- overfitting the MCP/agent surface to a few examples
- hiding authority in packet-specific reconciliation rules
- making prompt-level user intent less reliable than it should be

Blueprint assets are now opt-in scaffolds. A freeform `run()` or `revise()` call
does not infer a blueprint from packet terminology, and the dry-run planning API
accepts an explicit `blueprint_id` only when a caller intentionally wants to
inspect a scaffold. This keeps examples and regression fixtures available
without making them hidden authoring authority.

Future refactors should use the lessons from that experiment while moving back
toward a user-first, object-first authoring model.
