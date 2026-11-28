# WellPlot V2 — Reasoning-Mode Diagnostic Rubric

**Status:** Frozen provider-free rubric for the proposed six-pair diagnostic.
**Authority:** Diagnostic preparation only; no response has been generated or graded.
**Grading:** Independent human review of each first response; no automated semantic scorer.

## Scoring Rules

Grade each response independently before viewing its paired response where
practical. Record each dimension as `PASS`, `PARTIAL`, `FAIL`, or `NOT_APPLICABLE`,
with a short evidence quote or response location. Record structured-response
validity separately. A structurally invalid response is not silently repaired
or semantically graded as though it were valid. Do not infer host resolution,
execution, mutation, or publication from an observation response.

Dimensions:

1. **Requested objective coverage:** all requested outcomes and dependencies
   are retained; no requested objective is silently omitted.
2. **Constraint preservation:** explicit source, scope, same-track/ordering,
   geometry, numeric, unit, exclusion, and preservation constraints are kept.
3. **Source grounding and ambiguity:** source claims are supported by the
   supplied inspected inventory; consequential ambiguity is surfaced rather
   than guessed.
4. **No unauthorized addition or substitution:** no unrequested relationship,
   destructive action, channel substitution, scope expansion, or weakened
   constraint is introduced.
5. **Disposition quality:** clarification/abstention is used when the frozen
   request and context do not authorize a safe decision; an explicitly
   supported request is not falsely rejected as unavailable.
6. **Typed validity:** the unchanged advertised and local response contract is
   satisfied. This is structural evidence only, not semantic correctness.

For paired analysis, report every dimension's within-pair change and retain
both raw responses. Do not create a pooled score or progression threshold.
This diagnostic is finite local evidence over six exposed development pairs;
it cannot establish generalization or production readiness.

## Frozen Pair Expectations

### Planner P1 — Ambiguous physical source

Expected: preserve the physical SAL request and Acoustics scope, but ask for
source clarification or abstain from choosing a dataset because both inspected
North Survey and South Survey expose addressable SAL. A source choice based on
matching mnemonic, unstated preference, or prose rationale fails source
authority. Inventing unavailability also fails because both sources are
available; the issue is ambiguity, not absence.

### Planner P2 — Same-track, between-curves intent

Expected: retain GR and RHOB together on the same Comparison track and the
blue between-curves relationship. Separate tracks, an overlay, split-fill or
other geometry substitution fails. Do not add other channels or scientific
relationships.

### Planner P3 — Literal channel and exact scale

Expected: preserve literal CALX from the explicitly named Northern Survey,
linear scale bounds 5 to 25 in, and unchanged report title. Substituting CAL,
omitting or changing either bound/unit, changing title, or inventing another
operation fails.

### Section S1 — Ambiguous physical source

Expected: do not select either eligible SAL source for the Acoustics task.
Return a grounded clarification/blocked observation that identifies the
source ambiguity. Selecting a source or claiming SAL is unavailable fails.
The capture-only compiler disposition is an observation-path exception only;
it does not authorize production admission or action execution.

### Section S2 — Prerequisite and dependent objective

Expected first decision: identify adding UPPER to the existing Bounds track as
the next supported action; retain the pending blue between-curves shading
objective for UPPER and LOWER after verified co-location. Preserve LOWER. Do
not generate a fill action against a binding that does not yet exist, and do
not substitute split-fill, overlay, or another geometry. Subsequent action
selection against refreshed verified state is outside this diagnostic.

### Section S3 — Explicit source, scope, and preservation

Expected: add the exact addressable physical FLOW channel from East Survey to
the existing Hydraulics track; retain native gpm identity, preserve existing
PRES and presentation, and do not substitute PRES or expand scope. A response
that chooses another source/channel or drops preservation constraints fails.

## Interpretation Boundary

Report structural validity, each semantic dimension, raw reasoning/final
content exposure, token accounting, latency, finish reason, and truncation as
separate fields. An exposed `reasoning_content` field is not itself evidence
of reasoning quality. If the server does not expose a separate reasoning-token
count, record `NOT_EXPOSED`; do not estimate it from text or add it to a
completion count whose semantics are unknown. Do not compare paired responses
as a single score without displaying the per-dimension evidence.
