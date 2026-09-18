# EXP-TW-02I Development Memory

## Baseline and purpose

- Frozen baseline: `afc9f71` (EXP-TW-02R evidence-corrected).
- Purpose: close the typed-worker input sufficiency gap before provider
  generation.
- Scope: experimental typed input and provenance evidence only.
- Production delta: zero files under `src/wellplot`.

TW-00, TW-01, TW-02, and TW-02R remain unchanged. The corrected output
schema and golden fixture are also unchanged.

## Boundary

EXP-TW-02I adds `TypedWorkerTaskInput`, which complements the existing
path-free `WorkerSectionInput` from TW-02R:

```text
frozen benchmark evidence
        ↓
TypedWorkerTaskInput
        +
WorkerSectionInput
        ↓
future provider boundary
        ↓
SectionDraft
        ↓
corrected Gate A
        ↓
host completion
```

`TypedWorkerTaskInput` carries only semantic task identity, section title,
opaque source candidate selection, ordered track requirements, ordered binding
requirements, curve scales, repeated CBL view identity, and VDL scientific
semantics. `WorkerSectionInput` carries only the existing bounded candidate and
channel facts. The combined serialized input is deterministic and contains no
host paths or implementation details.

## Provenance audit

Every required worker-owned output field has a deterministic
`SemanticProvenance` record. The provider path is checked against the typed
task input; the evidence path identifies the frozen benchmark source. The
audit fails with explicit `SectionDraft...` paths when a required provider
value is removed. It does not consult the TW-02R golden output as a fallback.

| Worker-owned output | Typed input | Frozen evidence |
| --- | --- | --- |
| Section title | `task.title` | `merged_intent.sections[*].title` |
| Source candidate | `task.source_candidate` | TW-00 semantic-plan `source_hints` |
| Track role/kind/title | `task.tracks[*]` | reconstruction-plan components and canonical track titles |
| Curve channel/identity | `task.tracks[*].bindings[*]` | reconstruction-plan binding goal and channel |
| Curve scale and reverse | binding `scale` | frozen canonical binding scale |
| CBL `0-100` / `0-10` distinction | `cbl_0_100` / `cbl_0_10` | frozen binding goals and scales |
| VDL x-scale | `task.tracks[vdl].x_scale` | frozen canonical VDL track |
| VDL profile/sample axis | raster requirement | frozen canonical VDL binding |

Track widths, labels, colors, line styles, line widths, colormaps, colorbars,
filesystem paths, canonical IDs, provider metadata, and orchestration details
remain host-owned or implementation-owned under TW-02R and are excluded.

## Evidence

The input builder derives values from the frozen
`tests/fixtures/agentic_cbl/compile_contract.json` reconstruction plan and
merged artifact, and joins the existing TW-00 source/channel projection. It
does not read the TW-02R golden fixture. Tests cover both sections, exact
scales and reversal, distinct repeated CBL views, VDL profile and sample axis,
ordering, deterministic serialization, path-free leakage, and missing-value
provenance failure.

## Hard stop

No provider calls, prompt construction, adapters, credentials, retries,
repair, graph/orchestration, planner/enricher, or production integration were
added. EXP-TW-03 may now be planned as a first-attempt provider-generation
experiment, but it remains a separate authorization gate.

**PROCEED:** review and commit EXP-TW-02I only.
