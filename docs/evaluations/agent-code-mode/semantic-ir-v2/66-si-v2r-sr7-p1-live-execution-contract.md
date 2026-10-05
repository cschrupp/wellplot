# SI-V2R SR7-P1A — Live Execution Harness Contract

## Status

This record describes the provider-free P1A harness checkpoint descended from
the accepted P0 freeze at `8f30a33c9bcf5fbbce179996a6ea6b0f9a9da78f`.

P1A constructs the runner and deterministic transport tests only. It does not
authorize provider, endpoint, worker, or program calls. A separate P1B review
and authorization is required before live execution.

## Invariants

- The 96-row P0 schedule, prompts, schema, gold, mask, grader, retry limits,
  and configuration fingerprints are authenticated before provider creation.
- The live interlock requires `--execute-live` and an exact authorized
  checkpoint. A mismatch or dirty checkout fails before credentials are read.
- Each logical attempt permits at most one infrastructure retry and one
  structural retry, with a maximum of three physical calls.
- A crash-safe JSONL journal is written after each completed logical attempt.
  The canonical evidence file is written only after all 96 rows validate.
- Configuration drift and infrastructure exhaustion preserve the partial
  journal and stop without automatic resume or replay.
- Evidence retains canonical semantic output and bounded provider metadata only;
  credentials, authorization headers, hidden reasoning, and environment dumps
  are not serialized.

## P1B terminal labels

The only study-level labels are:

- `CONFIGURATION_B_DIRECTIONALLY_BETTER`
- `CONFIGURATION_A_DIRECTIONALLY_BETTER`
- `NO_CLEAR_DIRECTIONAL_DIFFERENCE`
- `INCONCLUSIVE_INFRASTRUCTURE`
- `INCONCLUSIVE_CONFIGURATION_DRIFT`
- `INCONCLUSIVE_EVIDENCE`

The claim remains a comparison of complete model-plus-serving configurations,
not isolated model superiority, production readiness, or generalization.

## Boundary

No P0 fixture or source is regenerated or modified by P1A. The P1A branch adds
only this runner, provider-free fixtures/tests, and this contract record.
