# SI-V2R-SR1 Report-Routing Residual Audit

## Authority

- Baseline: `7a660d6f4efff7a6b3e54a09fa81a3e08e271de4`
- Raw population: `/tmp/si-v2r-live.jsonl`
- Raw SHA-256: `9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08`
- Provider, endpoint, and worker/program calls: `0`

SR1 is a finite, provider-free audit of the immutable SI-V2R-LQ0 population. It
does not modify the V2R prompt, IR, compiler, planner, graph, providers, CM-58,
ADR-CM57, or qualification thresholds. It does not rescore LQ0 and does not
run inference.

The question is whether the model should continue owning **report presence**
when the accepted deterministic CM-58.2 boundary already distinguishes report,
section, and mixed request scope. Report content remains a separate question:
when report work is actually requested, its goal, requirements, and constraints
remain semantic model output.

The audit authenticates all 48 rows, retains the generated report-work content
for structurally available rows in a sanitized projection, compares all 24
requests with the unchanged `classify_report_boundary_intent()` function, and
recomputes CM-58.2 for available generated models. Unavailable structural rows
remain non-evaluable.

This is diagnostic evidence, not a production change. Any ownership change
requires a later design slice and independent review.
