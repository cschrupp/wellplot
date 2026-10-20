# D5-5 Qwen Model-I/O Custody Repair

## Authority

`WELLPLOT-D5-5-QWEN-MODEL-IO-CUSTODY-REPAIR-AUTH-001`

Parent implementation checkpoint:

`ca8a0311e229d6eb953f829e515dda24fa352c9e`

Branch:

`implementation/d5-5-comparative-model-qualification`

## Scope

This repair extends the existing D5 campaign custody without changing the
canonical WellPlot engine or any file under `src/wellplot/`.

The sixth append-only artifact is:

`<campaign-id>.model-io.jsonl`

It records the exact JSON request body at the existing OpenAI-compatible
generation transport and the matching response body when a response exists.
Headers, authorization material, credentials, and reasoning fields are not
stored or rendered. A transport failure still preserves the request event.

The existing state, journal, terminal, summary, and redacted evidence chain is
unchanged. Historical five-artifact campaigns remain valid when no model-I/O
artifact is present. The read-only inspection renderer consumes only local
sealed artifacts and frozen case/gold data; it makes no provider calls.

## Changes

- `scripts/nlp_d4_live_acceptance.py` preserves structured provider response
  reason and validation-shape diagnostics in canonical completion events.
- `scripts/nlp_d5_live_semantic_qualification.py` captures request/response
  JSON at the existing transport hook, seals the model-I/O digest, and keeps
  old five-artifact custody valid.
- `tests/test_d5_5_model_io_custody.py` covers exact-body capture, request-only
  transport failure custody, diagnostic distinctions, historical compatibility,
  and synthetic inspection output.
- `scripts/d5_5_inspection_report.py` renders local sealed model-I/O evidence
  without headers, credentials, or reasoning content.

## Validation

Provider/model calls: `0`

The provider-free model-I/O custody tests pass, and the existing D5 live
custody suite passes. Static compilation, Ruff, formatting, and
`git diff --check` are required to pass before publication.

No Qwen campaign was started, and no historical campaign was modified.

Status: `READY FOR INDEPENDENT REVIEW`
