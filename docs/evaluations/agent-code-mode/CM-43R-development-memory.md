# CM-43R Development Memory

## Scope

CM-43R generalizes the CM-42 section Code Mode worker enough to exercise the
already-supported generic section capability set from the unchanged CM-43 CBL
experiment. It adds the missing host-owned source bridge and publishes one
capability constant for the experiment harness. It does not add CBL/VDL
branches, provider logic, graph routing, persistence, rendering, or MCP
behavior.

- **Slice base SHA:** `021127b`
- **Implementation commit:** `c4fecb4` (`Generalize section Code Mode source and capabilities`)
- **Production files:** `builders.py`, `intent_builder.py`,
  `agent/code_mode/program_worker.py`
- **Harness file:** `scripts/cbl_section_ab.py`
- **Focused tests:** `test_authoring_program_intent_builder.py`,
  `test_code_mode_program_worker.py`, `test_cbl_section_ab.py`

## Contract

The restricted worker now exposes the generic section vocabulary already
implemented by the canonical intent builder:

```text
wp.report()
wp.source("candidate-id")
wp.section(report, ..., source=source)
wp.track(section, kind="normal" | "reference" | "array", ...)
wp.curve(track, channel=...)
wp.raster(track, channel=...)
```

`SECTION_PROGRAM_CAPABILITIES` is defined in the production worker and imported
by the CBL harness. The harness no longer maintains a smaller duplicate list.
The worker contains no CBL, VDL, or other document-specific orchestration.

Sources are host-registered as opaque `SourceHandle` values. A handle contains
only builder provenance and the candidate ID; it carries no path, format,
parser, channel data, or filesystem accessor. `IntentBuilder` resolves an exact
candidate ID to the canonical `AuthoringDataSource` only while constructing
the intent. Unknown/path-like IDs and handles from another builder fail
deterministically.

Each worker attempt creates a fresh identity builder and registers fresh source
handles from the bounded CM-41 `SourceContext`. A repaired program therefore
cannot reuse source-handle provenance from the failed attempt. Canonical source
paths remain host-owned and are not included in the provider prompt.

The section-only gate remains unchanged in principle: exactly one section is
allowed, section-local data-source association is allowed, and report-wide
fields, global child collections, removals, and multiple sections remain
rejected.

## Validation

- Focused implementation suite: `32 passed`.
- Architecture and adjacent suite: `41 passed`.
- Ruff check: passed.
- Ruff format check: passed.
- `git diff --check`: passed.

The focused tests cover opaque source handles, exact candidate lookup,
path-like and foreign-handle rejection, two-candidate selection, canonical
source association, fresh attempt provenance, generic reference/array/raster
construction, and the unchanged section safety gate.

## Live Rerun

The unchanged CM-43 case was rerun after `c4fecb4` with NVIDIA Nemotron
(`nvidia/nemotron-3-super-120b-a12b`) using the same provider, model,
temperature `1.0`, `top_p` `0.95`, `max_output_tokens` `16384`,
`max_tokens`, timeout `300`, starter document, source manifest, prompt, and
exact CBL acceptance contract. The six redacted rows are in
`CM-43-live-runs.jsonl` with fingerprint
`52deb03472c4939efa00cfda95c429850cdb0dd90735c910ca04ba9ad3910cc1`.

The generic capability expansion removed the prior SDK context gap:
`sdk_gap_capabilities` is empty and the successful v2 run reached complete
representability. The result is nevertheless not competitive:

| Engine | Engine success | Common acceptance | Notes |
| --- | ---: | ---: | --- |
| v1 | 2/3 | 2/3 | One worker failure |
| v2 | 1/3 | 1/3 | Two worker failures after one bounded repair; one accepted run |

The two failed v2 runs selected unavailable channel names (`CBL_0_100`,
`CBL_0_10`, and `VDL_WAVEFORM`) and were classified as worker execution
failures, not SDK capability gaps. The accepted v2 run used one provider call;
the failed runs used two calls each. Generated program sizes were `1092`,
`1103`, and `1236` characters with `227` AST nodes each.

The gate result is:

```text
STOP_V2_REGRESSION
```

This is a valid negative A/B result. The generic SDK/context boundary is now
representable, but the current v2 worker/provider combination is less reliable
than v1 on the frozen task. The CBL acceptance contract was not weakened.

## Boundaries and Decision

- CBL-specific branches: `0`.
- Provider/model changes: `0`.
- Planner, graph, LangGraph, MCP, persistence, and rendering changes: `0`.
- Legacy deletion or public cutover: `0`.

**STOP:** CM-43R implementation and evidence are complete, but CM-44 remains
blocked by `STOP_V2_REGRESSION`. The next slice requires a separately
authorized diagnosis of generic worker reliability/channel-selection behavior;
do not add a CBL-specific workaround or weaken the frozen acceptance contract.
