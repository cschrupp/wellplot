# CM-54 Development Memory

## Slice

- Baseline: `5c98ad1`
- Slice: CM-54 Typed Section-Worker Architecture Contract
- Status: complete, documentation/design only
- Implementation begins: CM-55, separately authorized

CM-54 converts the EXP-TW-00 through EXP-TW-08 evidence into a production
design contract without copying the frozen CBL experiment into `src/wellplot`.
The contract is subordinate to the active Code Mode architecture document and
is authoritative for the future typed section-worker boundary.

## Sources reviewed

The design review covered:

- `docs/agent-code-mode-architecture.md`;
- `docs/wellplot_agentic_code_mode_migration_plan.md`;
- `docs/evaluations/agent-code-mode/EXP-TW-consolidated-development-memory.md`;
- `docs/evaluations/agent-code-mode/EXP-TW-08-development-memory.md`;
- `scripts/exp_tw02i_input.py`;
- `scripts/exp_tw02r_contract.py`;
- `scripts/exp_tw03s_schema.py`;
- `scripts/exp_tw08_required_strengthened_schema.py`;
- the v2 planner, enrichment, program worker, workflow, and state contracts;
- canonical authoring and intent models;
- capability declarations for `section.log_plot`, `track.normal`,
  `track.reference`, `track.array`, `binding.curve`, and `binding.raster`.

## Frozen production decisions

The future production flow is:

```text
SectionTask + ResolvedSectionContext
    -> provider-safe static semantic draft
    -> structural validation
    -> context/semantic validation
    -> deterministic section compiler
    -> section-local AuthoringDocumentIntent
```

The production model is static and request-independent, strict, immutable,
and path-free. Track discriminator tags are required fields. The proposed
production names are `SectionSemanticDraft`, `NormalTrackSemanticDraft`,
`ReferenceTrackSemanticDraft`, `ArrayTrackSemanticDraft`,
`CurveBindingSemanticDraft`, `RasterBindingSemanticDraft`, `SemanticScale`,
and `SemanticSampleAxis`.

The worker uses opaque host-issued source candidates and worker-local semantic
IDs. Repeated channel bindings retain independent semantic IDs and order. The
host owns canonical IDs, source paths, parser objects, renderer mechanics,
reconciliation, persistence, and provider/graph state.

## Evidence promoted from TW

The validated typed-worker core preserves:

```text
normal    -> curve only
reference -> curve only
array     -> raster only
array     -> x_scale required
```

Required track discriminators are promoted from TW-07/TW-08. The CBL role
literal (`combo`, `depth`, `cbl`, `vdl`) is not promoted to production. The
production semantic identity is generic and worker-local.

TW-specific scales, labels, colors, widths, line styles, colormap, colorbar,
grid suppression, and other presentation constants remain experimental
benchmark completion policy and are excluded from the production worker
contract.

## Generalizations and gaps

Canonical Wellplot supports linear, log, and tangential scales; generic, VDL,
and waveform raster profiles; optional sample-axis fields; annotation tracks;
fills; and curve overlays on array/image tracks. TW-08 directly validated only
the smaller CBL-shaped core. These capabilities are recorded in the normative
representability matrix rather than silently removed:

- scale/profile/sample-axis generalization requires CM-56 evidence;
- annotation, fill, reference-overlay, waveform, style, and grid coverage are
  deferred gaps;
- curve overlays on array tracks are an explicit compatibility gap because the
  canonical model supports them while the validated typed core does not;
- explicit width, subtitle, depth-window, and label requests remain gaps when
  they are not in the initial semantic draft.

The typed worker cannot replace the current section path for an unrepresented
capability without first adding and validating that capability.

## Remaining uncertainty

TW-08 used the richer typed input built by TW-02I. Production currently gives
the worker a looser `SectionTask` and `ResolvedSectionContext`. Free-text
requirements can mention title, channels, scales, repeated views, and sample
axes, but their presence is not guaranteed by the current type contract.
CM-56 must measure real planner/enricher input sufficiency. CM-56R is allowed
only if that evidence demonstrates a generic insufficiency.

TW evidence covers new-section reconstruction, not existing-section revision.
CM-47 remains the reference for opaque target selection and sparse preservation;
typed revision parity is deferred until production evidence exists.

## Integration constraints

`ReportProgramCompiler` remains unchanged. A future typed section result must
not fabricate `AuthoringProgram`, AST metrics, source text, or repair counts to
fit the current program result model. Initial typed validation is first-attempt
only; no repair, fallback, provider change, routing change, or graph topology
change is included.

## Files and delta

Changed in CM-54:

- `docs/typed-section-worker-contract.md`;
- `docs/evaluations/agent-code-mode/CM-54-development-memory.md`;
- `docs/agent-code-mode-architecture.md`;
- `docs/wellplot_agentic_code_mode_migration_plan.md`.

Production delta: `0`.

Test delta: `0`.

No provider calls, shadow execution, schema implementation, compiler
implementation, routing change, or prior TW/CM memory change occurred.

## Next boundary

CM-55 planning/implementation is the next separately authorized slice. CM-56
must validate the real planner/enricher boundary before CM-57 section-worker
cutover. CM-53 transition acceptance remains open and CM-60+ deletion remains
blocked.
