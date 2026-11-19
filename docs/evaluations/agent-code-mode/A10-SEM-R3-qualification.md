# A10 R3 Provider-Free Qualification

Candidate for review; no live inference, campaign, or benchmark execution.
Starting checkpoint: `2409d92de2e90f66b1f45eec48cac7da6a6bd2ec`.

**Decision (ADAPTED):** Add a compact scalar intent to the existing planner wire
contract. Independently compiled request facts authorize the scope, channel
spelling, and explicit scale. The existing conversion produces the canonical
operation inventory; the same worker contracts, lowerer, and authoring resolver
consume it. This follows the declarative compilation pattern reviewed for R3
(Vega-Lite and NL4DV). Rich report and section operation forms remain supported.

**Representative change:** F04 no longer needs seven wire operations, reference
declarations, or anchors. The section task can carry:

```json
{"action":"add_track","channel_kind":"physical","channel_clue":"CBL","scale":{"kind":"linear","minimum":0,"maximum":1,"unit":"mV"}}
```

The host authorizes one track operation and one curve binding. The lowerer uses
the existing generic width when width is omitted; it selects no scale preset
and performs no unit conversion. Explicit clears remain in the operation form,
distinct from absent settings.

**Observations:** Synthetic planner and worker responses exercised the actual
compile graph and read-only `reconcile_authoring()` disposition for A01, F04,
G02, and trusted Gamma Ray. Unapproved resistivity/porosity proposals and an
ambiguous source or section do not dispatch workers. Typed model abstention
keeps unresolved work without a plan, distinct from host rejection. Explicit
section, track, and source facts were tested in a two-section, two-source input.

**Boundary:** The live campaign stop remains `PLANNER_GENERATION_PASS` (validated
wire only). Authoring disposition is observable at `reconcile_authoring()`
after canonical workers and lowering, before apply. Provider-free disposition
does not imply live planner quality, deployed decoder compatibility, or
publication success. No launcher, runtime, resolver, or campaign changes.

**Verification:** 480 focused tests passed; 9 selected provider-free campaign
checks passed (135 deselected). Five broader graph-safety failures reproduced
unchanged on the starting checkpoint (110 passed in that separate group).
The mocked first-pass transport test timed out during asyncio teardown on both
the candidate and starting checkpoint; it is not counted as passing. Targeted
Ruff, format, compilation, diff check, and single-engine attestation passed.

Canonicalized R3 wire schema SHA-256:
`0b30e84626873a3c68ce8f12f50c52f96e17234b45b4a7ca0d74987c35512723`.
