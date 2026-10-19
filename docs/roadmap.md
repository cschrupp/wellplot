# wellplot Roadmap

Last updated: 2026-10-18

## Product Direction

WellPlot is an open-source Python toolkit for high-quality well-log visualization and an
emerging intelligent subsurface authoring platform.

The product direction is:

- renderer-first, with print-quality static output and interactive viewing
- typed well-data and document models instead of renderer-specific ad-hoc configuration
- YAML and Python as first-class authoring surfaces
- deterministic semantic execution for layout/edit operations
- learned models used for language interpretation, not as semantic authority
- gradual expansion from visualization into QC, processing, petrophysics, and richer applications

Decision history is tracked in `docs/decision-log.md`.

## Current Product Baseline

### Data and authoring

Implemented and part of the working baseline:

- `WellDataset` normalized data model
- LAS / DLIS adapters plus numpy and optional pandas workflows
- `LogDocument` typed layout/visualization model
- YAML logfile/template authoring and inheritance
- programmatic authoring through:
  - `wellplot.api.dataset`
  - `wellplot.api.builder`
  - `wellplot.api.render`
  - `wellplot.api.serialize`
- partial section/track/window rendering
- YAML round-trip helpers
- notebook-friendly PNG/SVG output
- section-first data source routing

### Rendering

The renderer-first core is mature enough to serve as the product foundation.

Implemented capabilities include:

- printable matplotlib output and continuous log strips
- Plotly interactive-viewing baseline
- explicit `reference`, `normal`, `array`, and `annotation` tracks
- multi-curve tracks with independent scales
- curve fills:
  - `between_curves`
  - `between_instances`
  - `to_lower_limit`
  - `to_upper_limit`
  - `baseline_split`
- VDL density and waveform array rendering
- DLIS-derived sample-axis metadata with user overrides
- reference-track scalar overlays and local events
- curve callouts and section-relative repetition
- typed annotation objects and dedicated label lanes
- structured track headers
- heading / remarks / tail report composition baseline

### Packaging and ecosystem

The library has passed the initial productization milestone:

- public package name: `wellplot`
- PyPI release flow established
- TestPyPI and installed-wheel smoke testing established
- CI covers lint, tests, optional extras, builds, and installed-wheel verification
- MkDocs / Read the Docs documentation foundation
- optional experimental MCP server through `wellplot[mcp]`

Production hardening remains ongoing maintenance rather than the primary roadmap bottleneck.

## Current Frontier: Natural-Language Authoring Runtime

The active R&D track is a reliable natural-language control layer over the existing deterministic
WellPlot model.

Target architecture:

```
raw English + projected workspace
            ↓
        decomposer
      (learned model)
            ↓
 ScopeNormalizedProgram
            ↓
 deterministic resolver /
 validator / effect projector
            ↓
 canonical WellPlot intent
            ↓
 existing document + renderer stack
```

The model is responsible for language decomposition. It does not own WellPlot semantics,
persistent identity, validation, or execution.

### Completed runtime foundations

Accepted/closed work now includes:

- WELL-IR / typed semantic editing direction
- D5 semantic inventory and evaluation corpus work
- SLM baseline/fine-tuning experiments
- deterministic semantic-gate analysis
- deterministic MB-02R adjudicator
- ordered multi-operation `ScopeNormalizedProgram`
- projected-workspace execution runtime
- English→program evaluation contract
- oracle-safe evaluation harness with candidate freeze before oracle access
- zero-shot decomposer-pilot design
- constraint-backend preflight work
- rejection of the unsuitable Outlines and XGrammar JSON-Schema routes
- engine-neutral `WELL-EBNF-1` design
- deterministic schema→`WELL-EBNF-1` generator with independent recognizer/parity evidence

Accepted generator artifact:

```
grammar_sha256:
f8cfd0c2b8a2cb2c708e464147080ebd7400e40e8060fa0426e423d70396d9d3
```

### Important scientific status

The current Qwen decomposer hypothesis has **not yet been tested cleanly**.

Earlier work discovered constraint-system defects before inference. Therefore:

- current Qwen capability is not established
- current Qwen failure is not established
- no model result should be inferred from the constraint-engine work

This separation is intentional: the measurement path must be correct before model capability is
judged.

## Immediate Roadmap

### 1. CFG-ENGINE-BAKEOFF-01 — completed

Human/SOL accepted `CFG-ENGINE-BAKEOFF-01R2` selected **XGrammar 0.2.8 / native EBNF**.
llguidance 1.9.1 was rejected at G7 because matcher construction exceeded its grammar-symbol-table bound.

The accepted bakeoff established:

- independent language-preserving WELL-EBNF-1 → XGrammar lowering audit
- pinned Qwen tokenizer compatibility
- hard token-mask replay with completion/stop semantics
- deterministic repeated mask traces
- bounded compile/resource behavior
- zero model calls / no model weights loaded

### 2. Selected-backend constrained-decoding preflight — completed

Human/SOL accepted `DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PREFLIGHT-01R2` with P1–P9 PASS.
The accepted preflight established:

- complete frozen Q6 pilot manifest
- exact XGrammar 0.2.8 / native-EBNF constraint construction
- hard-mask and completion parity on the pinned Qwen3-1.7B tokenizer
- exact HF `LogitsProcessor` progressive synthetic replay
- six-case pre-inference hash freeze with no sealed-case contamination
- adversarial fail-closed evidence
- concrete-model load / invocation / generate / non-local-download guards
- zero model calls, zero model forward/generate calls, and no model weights loaded

### 3. DECOMPOSER-PILOT-01 — next scientific slice, not yet authorized

The infrastructure is now ready for the frozen six-call pilot, but execution still requires a
separate explicit pilot authority. Once authorized:

- model: `Qwen/Qwen3-1.7B`
- instruction checkpoint
- thinking disabled
- zero-shot
- same frozen prompt/schema for all six cases
- one call per case
- no retries
- no repair
- no oracle/cross-case feedback

The purpose is to test English→`ScopeNormalizedProgram` decomposition, not to retest deterministic
runtime semantics.

### 4. Pilot decision gate

If the pilot is promising:

- expand to a broader held-out corpus
- classify failures by mechanism
- compare zero-shot / few-shot / supervised options only if evidence justifies them
- integrate the decomposer behind the deterministic semantic runtime

If the pilot is weak:

- compare alternative decomposers/models without reopening the deterministic WellPlot contract
- candidates may include larger Qwen models, supervised Qwen, T5-style seq2seq, or a frontier/cloud
  decomposition path

## Parallel Product Tracks

These remain important but are not the current architecture bottleneck.

### Rendering and report quality

Near-term:

- richer report front matter and parameter tables
- paginated mixed report/log mode
- commercial-style themes, borders, and table systems
- denser annotation packing
- additional visual regression coverage
- vendor-specific VDL calibration workflows

### Interactive viewer maturity

Planned:

- track visibility/edit controls
- synchronized depth cursor/crosshair
- persistent viewer state
- graphical editing surfaces
- audit/history support

### I/O and standardization

Ongoing:

- LAS/DLIS edge-case hardening
- template schema versioning/migration
- stronger section-aware binding diagnostics
- track-level defaults and strict empty/unbound-track validation where useful

### Packaging and documentation

Ongoing maintenance:

- keep release workflows healthy
- deepen API/schema/cookbook documentation
- keep public exports and examples aligned
- prune stale comments and development-only examples

## Later Product Layers

After natural-language authoring is technically proven, the next major differentiation should be
domain intelligence rather than chat surface area alone.

### Well-log QC

Target capabilities:

- curve inventory and mnemonic recognition
- unit/range validation
- depth continuity and gap checks
- duplicate/spike/outlier detection
- cross-log consistency checks
- structured QC findings with deterministic evidence

### Processing and petrophysics

Longer term:

- deterministic well-log processing operations
- assisted interpretation workflows
- petrophysical calculations
- physics-aware / ML modules where they add measurable value

### Application layer

Longer term:

- richer desktop/web UI
- natural-language + graphical editing
- project/workspace state
- audit/history
- reusable workflow composition

## Product Status Matrix

| Area | Status |
|---|---|
| Typed well-data model | Mature foundation |
| Static well-log rendering | Strong |
| LAS/DLIS ingestion | Functional; edge-case hardening continues |
| Array / VDL / waveform rendering | Strong |
| YAML authoring | Productized |
| Python API | Productized |
| PyPI / release pipeline | Productized |
| MCP surface | Experimental but functional |
| Report composition | Functional; commercial-parity work remains |
| Interactive viewer | Baseline / partial |
| Deterministic semantic editing runtime | Strong experimental foundation |
| English decomposer | Not yet cleanly evaluated; six-call pilot is next |
| Hard constrained decoding | Preflight accepted; infrastructure ready |
| QC platform | Future product layer |
| Petrophysics platform | Future product layer |
| Full graphical/web application | Longer term |

## Immediate Next Tasks

1. Keep this roadmap and decision log synchronized with accepted runtime work.
2. Keep `DECOMPOSER-PILOT-01` blocked until a separate explicit authority is issued.
3. When authorized, run exactly the frozen six-call Qwen3-1.7B decomposer pilot with no retries or repair.
4. Continue release/documentation maintenance without allowing it to dominate the active R&D track.
5. Revisit renderer/report polish in parallel where it improves real user workflows.

## Working Principles

- Treat visual and semantic operations as typed objects, not ad-hoc text.
- Preserve physically meaningful layout dimensions.
- Keep model decisions explicit, bounded, and test-backed.
- Prefer deterministic machinery for semantics, validation, and evidence.
- Treat learned models as interpreters over a deterministic domain runtime.
- Separate implementation, execution, verification, acceptance, and authorization.
- Prefer stable defaults, then add opt-in complexity.
