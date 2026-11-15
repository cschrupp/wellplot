# A10-SEM-NL-CORRECTION-01 Qualification

Status: `A10_SEM_NL_CORRECTION_01R1_READY`

This record covers the bounded provider-free corrective based on the sealed
Smoke 002 forensic evidence. It does not authorize a live smoke, P8, holdout,
or scientific evaluation.

## Scope

The corrective changes only the existing schema-correction guidance and the
provider-neutral allowlist for two observed local validation reasons:

- `CLEAR field values cannot also provide a value.`
- `SET field values require an explicit value.`

The correction instruction now describes generation of a complete replacement
plan because the rejected candidate is unavailable at the provider error
boundary. It also states the bounded operation constraints without changing
the planner wire schema, operation validators, provider behavior, retry
ceiling, semantic ownership, or canonical execution path.

The historical forensic evidence remains immutable:

- forensic report SHA-256: `e0079f42e708135fd20ab338a2287e19de1938ad9769d19592fb299ef80787f1`
- operation comparison SHA-256: `4c3acbaa72bf1485dffffd82f0f82d5c342c5fcdbe7037f19cf143736d6d0f76`
- starting checkpoint: `5cc9fc5610a00a9660d25310978580f9b1d2907b`

## Contract identities

| Identity | Value |
| --- | --- |
| Planner system prompt SHA-256 | `4bb8005845dc8bd78ea5797e8887f35ea5afe085dace71ffcf31de0f1d2b9483` |
| Schema-correction instruction SHA-256 | `5cbabf8d6ebea3094a42705caf468f80e29a4cab9c5ed106cea719b76fdcc9a1` |
| Planner wire-schema SHA-256 (`_PlannerWirePlan`) | `b6b05fec2caabbc62708d17b1d752d8888e6cf7e2b91b4b67889eb583b080cbb` |
| Planner source SHA-256 | `790121ab7b75a0fd2bdd27bec83bb543d6926455297f0ae7a498c4543431f1ba` |
| Response diagnostics source SHA-256 | `e977816a85bfbce7038972dad4255ddc8a9a828216694f9120bb54725285de6e` |

The planner system prompt and wire-schema digest are unchanged. The new
correction-instruction digest is intentionally a new version and does not
rewrite historical evaluation evidence.

## Exact prompt delta

Previous correction instruction:

```text
Repair the supplied SemanticPlan candidate using the original request and the listed validation violations. Preserve already-valid requested work and change only what is needed to satisfy those violations. Do not create unrelated report or section work, add undeclared fields, or include prose. Return only one object matching the supplied structured response model.
```

Previous candidate correction instruction:

```text
Generate one complete replacement SemanticPlan from the original request, authoritative context, and the listed validation violations. No previous candidate is supplied, so do not assume or reconstruct unavailable candidate details. Preserve requested work supported by the request and context, and do not create unrelated report or section work, add undeclared fields, or include prose. Preserve established verb meanings; never change a verb merely to satisfy a validator. Field-value state=SET requires a non-null value; field-value state=CLEAR requires a null value. Operation verb=SET requires a target_clue and exactly one field_values entry, and may contain a field-value state=CLEAR. CREATE and ENSURE require semantic_ref; UPDATE and REMOVE require target_clue. Return only one object matching the supplied structured response model.
```

The production correction diagnostic preserves the existing generic
constraint and adds a `reason` only when the local validation message exactly
matches an allowlisted canonical rule. Unknown messages remain suppressed.

The canonical distinction is explicit: operation `verb=SET` may carry a
field-value entry with `state=CLEAR` and `value=null`; the nullability rule
applies to the field-value state, not to the operation verb.

Example of the bounded correction diagnostic passed to the existing correction
request builder:

```json
{
  "code": "schema_validation",
  "issues": [
    {
      "location": ["section_tasks", "*", "operations", "*"],
      "error_type": "value_error",
      "constraint": "satisfy the model's cross-field constraint",
      "reason": "ENSURE requires a request-local semantic_ref."
    }
  ],
  "previous_invalid_candidate": "unavailable_at_existing_provider_error_boundary"
}
```

## Provider-free validation

Command:

```text
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_code_mode_planner.py tests/test_cm59a_r2c_a_schema_validation_shape_diagnostic.py -k 'not historical_helper_drift_is_rejected_before_live_activity and not pre_live_report_is_provider_free'
```

Result: `134 passed, 2 deselected`.

The two deselected tests belong to the historical CM-59A frozen-contract
helper. They intentionally reject planner artifact drift against their old
checkpoint and remain unchanged; they are not rewritten to accept this new
corrective.

The focused tests cover replacement-plan wording, explicit SET/CLEAR and
semantic-reference guidance, exact allowlisted diagnostic projection,
arbitrary-message suppression, correction-request propagation, preservation
of `previous_invalid_candidate`, and the existing single-correction bound.

## Static qualification

The following checks passed at the candidate worktree:

- targeted Ruff lint;
- targeted Ruff format check;
- Python compilation for changed Python files;
- `git diff --check`;
- `scripts/d5_single_engine_attestation.py --check`.

No provider, endpoint, model, smoke, P8, holdout, C02, or scientific calls
were made.

## Review boundary

This is an implementation candidate for independent review. It must not be
interpreted as evidence that a model will repair the historical Smoke 002
responses. Any live smoke remains a separate, freshly authorized activity.
