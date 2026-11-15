# A10-SEM-NL-GATE-01R1 Qualification Record

Status: `A10_SEM_NL_GATE_01R1_COMPLETE — HA_REVIEW_REQUIRED`

## Scope and custody

This bounded corrective reconciles provider-free qualification expectations with
the accepted current implementation and performs one authenticated,
non-generative llama.cpp readiness check. No production semantic code, planner
wire schema, prompt, catalog, smoke, P8 run, holdout, or scientific execution
was changed or started.

- Starting checkpoint: `7c63a2b48412cf0b49ac98de4a9389fc6677c160`
- Branch: `engineering-d5-binding-path-repair`
- Canonical checkout: `/home/user/projects/well_log_os`
- Configured endpoint: `http://192.168.2.140:8888`
- Configured model: `qwen3.6-35b-a3b`
- Planner wire-schema SHA-256:
  `b6b05fec2caabbc62708d17b1d752d8888e6cf7e2b91b4b67889eb583b080cbb`
- Production source changes: none

The unrelated modified notebooks and untracked `examples/families/` directory
were preserved and excluded.

## Corrective changes

The existing CM-59A qualification script now distinguishes its historical E2
baseline identities from the accepted current implementation checkpoint. The
historical baseline and hashes remain recorded in the script; current pre-live
validation uses the accepted checkpoint and current prompt/schema identities.

The single-engine schema regression now includes the accepted `add_binding`
discriminator branch. The project-config regression now asserts the existing
authoritative `.140` LAN configuration rather than the stale `.141` value.

No production component or manifest digest changed.

## Provider-free qualification

Exact command:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_section_work_contract.py \
  tests/test_d5_single_engine_convergence.py \
  tests/test_project_config.py \
  tests/test_cm59a_r2c_a_schema_validation_shape_diagnostic.py
```

Result: `118 passed in 12.25s`, exit code `0`.

The section-work-contract subset independently reports `45 passed in 1.62s`.
The exact structured-schema adapter tests verify that the existing provider
adapter emits the same Pydantic JSON Schema used by local validation.

Additional checks:

- Ruff check: PASS
- Ruff format check: PASS
- Python compilation: PASS
- `git diff --check`: PASS
- D5 single-engine attestation: PASS

## Authenticated non-generative readiness

The existing canonical credential loader and endpoint fingerprint helper were
used. The API key was not printed, logged, hashed, persisted, or included in
this record.

- Request: one authenticated `GET /v1/models`
- Endpoint: `http://192.168.2.140:8888/v1`
- HTTP/model-list operation: PASS
- Configured model present: PASS, `qwen3.6-35b-a3b`
- Fingerprint helper: `cm57p9.endpoint-fingerprint.v2`
- Generation calls: `0`
- Structured-output calls: `0`
- Planner/worker execution: `0`

The first sandboxed attempt was blocked before socket creation by the local
execution policy (`Operation not permitted`). The authorized escalated retry
completed successfully; this is environment evidence, not provider or model
evidence.

## Gate disposition

- `STRUCTURAL_PARITY`: `PASS` for the qualified provider-free contract scope.
- `AUTHENTICATED_ENDPOINT_READINESS`: `PASS` for endpoint/model-list reachability.
- `PLANNER_SMOKE_ELIGIBILITY`: `READY_FOR_SEPARATE_AUTHORIZATION`.

This record does not authorize planner generation, A10 scientific evaluation,
P8, holdout access, or A12 execution. A future planner-only smoke must use a
fresh custody namespace, the canonical live harness, the current accepted
checkpoint, and the existing bounded correction limit, then stop after planner
validation.
