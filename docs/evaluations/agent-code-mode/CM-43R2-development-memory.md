# CM-43R2 Development Memory

## Scope

CM-43R2 fixes the grounded-context defect exposed by the first CM-43R live
batch. It preserves the existing `SectionTask` planner contract and changes
only the frozen A/B adapter's semantic projection plus the generic section
worker's initial/repair context. It does not modify the planner schema,
`ProgramRepairCoordinator`, SDK surface, provider adapters, graph routing,
MCP, persistence, or rendering.

- **Slice base SHA:** `72e2a02`
- **Implementation commit:** `b95b58b` (`Ground section repair with exact channel facts`)
- **A/B case:** unchanged CM-43 `main_pass` CBL section
- **Evidence file:** `CM-43-live-runs.jsonl`

## Semantic Parity

`scripts/cbl_section_ab.py::_section_task()` now projects legacy component
values into ordinary `SectionTask.requirements` strings. The projection keeps
semantic facts such as track kind, parent role, exact channel mnemonic, and
scalar/array source kind while excluding component IDs, target IDs, binding
IDs, filesystem paths, and execution structure.

The planner models remain unchanged. No component tree or new semantic
requirement model was added.

## Grounded Repair Context

The worker now uses one bounded source/channel projection for both initial and
repair prompts. It contains only:

```text
candidate_id
channel mnemonic
channel kind
channel aliases
channel unit
```

Canonical paths, parser objects, document state, and source filesystem details
are excluded. Both prompts explicitly require exact supplied mnemonics or
aliases and state that multiple bindings may reference the same source
channel. `ProgramRepairCoordinator` remains unchanged and provider-neutral.

## Validation

- Focused and adjacent suite: `41 passed`.
- Ruff check: passed.
- Ruff format check: passed.
- `git diff --check`: passed.

The deterministic regression uses an intentionally invalid first program with
`CBL_0_100` and `VDL_WAVEFORM`, then verifies that the repair request contains
the authoritative scalar `CBL` and array `VDL` facts, excludes canonical paths,
and accepts two `CBL` bindings plus one `VDL` raster after repair.

## Live Evidence

The unchanged CM-43 3+3 experiment was rerun with the same provider, model,
temperature, top-p, token budget, timeout, prompt, starter document, source
manifest, acceptance contract, and experiment fingerprint:

```text
fingerprint = 52deb03472c4939efa00cfda95c429850cdb0dd90735c910ca04ba9ad3910cc1
provider    = nvidia_cloud
model       = nvidia/nemotron-3-super-120b-a12b
```

The six redacted rows in `CM-43-live-runs.jsonl` show:

| Engine | Engine success | Common acceptance | Legacy core | Dynamic schema |
| --- | ---: | ---: | ---: | ---: |
| v1 | 2/3 | 2/3 | reached on successful/failed worker paths | 30,842 chars |
| v2 | 3/3 | 3/3 | 0/3 | 0 chars |

All v2 runs have complete representability and no semantic omissions. The v2
provider generation calls were `2`, `2`, and `1`; repair counts were `1`, `1`,
and `0`; generated programs were `1083`, `1047`, and `1074` characters, each
with `227` AST nodes. The first two runs required one bounded repair and still
passed the unchanged acceptance contract.

The gate result is:

```text
PROCEED
```

The result is competitive on acceptance and materially simpler: v2 achieved
`3/3` acceptance versus v1 `2/3`, with no dynamic schema and no legacy-core
reachability.

## Decision

**PROCEED to CM-44 planning.** CM-43R2 closes the context-grounding and A/B
semantic-parity defect without broadening the SDK or adding document-specific
logic. CM-44 implementation remains separately gated; this slice does not
start the report worker or public v2 routing.
