# EXP-TW-02R Development Memory

## Baseline and purpose

- EXP-TW-00 baseline: `a31ff70`
- EXP-TW-01 baseline: `6f9a2d6`
- EXP-TW-02 baseline: `c844a9f`
- Scope: corrective contract and evidence pass before provider generation.
- Production delta: zero files under `src/wellplot`.

TW-00, TW-01, and TW-02 remain immutable historical experiments. This slice
adds a separate corrected contract rather than changing their fixtures or
semantics.

## Corrected boundary

The provider-facing projection is a separate immutable model. It contains only
the same bounded facts exposed by the current section worker: target kind,
opaque candidate IDs, and channel mnemonic/kind/alias/unit data. It never
contains `canonical_path`, `source_path`, source format, host IDs, renderer
objects, or compiler-generated IDs. Host `ResolvedSectionContext` remains a
host-only model.

The corrected worker contract is:

```text
SectionDraft
  title
  source_candidate
  ordered tracks:
    role, kind, title
    ordered curve/raster semantic bindings
    scalar scales
    VDL profile and sample-axis semantics
```

Binding semantic IDs distinguish the two repeated CBL views:
`cbl_0_100` and `cbl_0_10`. The channel name remains `CBL` for both, but the
distinct scale is worker-owned semantic intent rather than an accidental
positional convention.

## Semantic ownership audit

| Field | Ownership | Rationale |
| --- | --- | --- |
| Section title | Worker-owned | It is part of the requested semantic section identity. |
| Track titles and kinds | Worker-owned | They define ordered semantic tracks and curve/raster compatibility. |
| Source candidate | Worker-owned selection | The worker selects an opaque host-approved candidate; the host resolves its path. |
| Curve scales and reverse flag | Worker-owned | Numeric views change the scientific information communicated by a curve. |
| Repeated CBL view identity | Worker-owned | `0-100` and `0-10` are distinct views of one channel. |
| VDL profile and sample axis | Worker-owned | They determine the meaning and horizontal interpretation of the waveform. |
| Track widths | Host defaulted | The frozen CBL layout policy provides widths by semantic track role: 50, 10, 44, and 48 mm. |
| Binding labels and line styling | Host defaulted | The frozen canonical artifact provides deterministic presentation policy by semantic binding role. |
| VDL colormap, colorbar, and grid visibility | Host defaulted | These are fixed presentation policy for the frozen VDL track. |
| Canonical source path/format | Host-derived | Only the selected host `SourceContext` may supply filesystem data. |
| Renderer classes, layout coordinates, provider fields | Renderer/provider-only | They are not worker semantic intent and remain outside the experiment schema. |

The host defaults are explicit constants in `scripts/exp_tw02r_contract.py`;
they are not model-generated guesses. No semantic value is repaired,
deduplicated, reordered, or inferred during compilation.

## Validation and completion

The corrected entry point always serializes and revalidates both mappings and
pre-existing `SectionDraft` instances before running the original TW-00 Gate A
checks. Corrected Gate A additionally validates exact section/track titles,
track order, binding roles, repeated-view scales, VDL semantics, source scope,
and scalar/array compatibility.

The two-source regression keeps a valid channel in source A while selecting a
source B that lacks it; Gate A rejects the draft rather than unioning channels
across candidates.

For the two frozen Gate-A-valid corrected golden drafts, deterministic host
completion supplies every required new-track width and presentation field.
Both golden sections then pass deterministic reconciliation and private
`AuthoringService` execution. This is completion evidence for the frozen CBL
contract, not an exhaustive proof over every structurally possible
`SectionDraft` value. The canonical intent contains host-resolved source
metadata only at this host-side boundary.

The private reconciliation harness scopes its available-channel inventory to
the source candidate selected by the compiled draft; unrelated candidates in
the host context cannot contribute channels during execution evidence.

## Hard stop

This slice adds no provider calls, prompts, compiler integration under
`src/wellplot`, retries, repair behavior, planner/enricher changes, graph
changes, or production registration. EXP-TW-03 provider generation remains
blocked pending separate authorization.

**PROCEED:** review and commit EXP-TW-02R only.
