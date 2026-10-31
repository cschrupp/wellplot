# D5 Worker Action Observability

Status: implementation candidate, pending independent review. This document
does not authorize a live smoke or a scientific campaign.

## Boundary

The canonical section worker observes an action after Pydantic schema
validation and before `validate_section_action_contract()`. Schema validity
does not imply contract acceptance. The existing `SECTION_ACTION_VALIDATED`
event remains an acceptance event. No new worker, provider, correction
protocol, retry, or semantic execution path is introduced.

An explicitly enabled observation emits `SECTION_ACTION_SCHEMA_VALIDATED`
followed by `SECTION_ACTION_CONTRACT_RESULT`. Events contain the worker role,
task index, generation attempt, logical call index, action schema, canonical
DTO SHA-256, byte size, and contract outcome. The canonical DTO digest hashes
sorted, compact, ASCII-escaped JSON from `model_dump(mode="json",
exclude_unset=True)`. It is not the raw provider-response hash. A schema-invalid
response has no schema-validated DTO and is handled by the existing provider
or schema failure path.

For `worker_contract_incomplete`, supplementary mismatch evidence distinguishes
track-handle from binding-handle set mismatches. It records bounded counts and
SHA-256 handle projections, not untrusted handle strings. A track mismatch
reports binding validation as `NOT_EVALUATED`. Existing public error codes,
field/ownership diagnostics, validation order, and generation ceilings remain
unchanged.

## Authorization And Storage

The binding-smoke authorization may explicitly include
`"section_action_capture_mode"` with one of:

- `off`: default; no pre-contract observation or DTO retention by D5 smoke
  custody. The worker still emits the historical post-contract-success callback
  for compatibility; D5 custody records only the event metadata in this mode.
- `diagnostics`: bounded observation metadata and mismatch projections only.
- `validated_dto`: diagnostics plus the complete schema-validated DTO, subject
  to screening and the 65,536-byte event limit.

No environment variable selects a mode. The authorization binds the mode;
missing fields default to `off`. An enabled capture campaign root must be under
the Git-ignored local `workspace/evaluations` tree, be an owned `0700`
directory, contain only `0600` pre-existing files, and run with process umask
`077`. Full DTOs are written under a dedicated owned `0700`
campaign subdirectory as `0600` files. The existing section-actions JSONL
contains bounded metadata and relative DTO paths; its file is `0600`. The
terminal attests both the JSONL and each DTO file. Existing sealed campaigns
are not modified.

Full capture is a Human-approved privacy exception. Secret and absolute-path
screening is best-effort and cannot guarantee that arbitrary model-generated
text is free of private information. Strong screening matches and oversized
events produce only safe metadata with `INCOMPLETE` capture and fail the
worker before lowering. DTOs are not raw HTTP bodies, and they must never be
committed to Git or uploaded as public CI artifacts. Restrict local access to
authorized operators. Do not silently redact or truncate a DTO while calling
it complete.

## Retention And Inspection

Full DTO metadata records capture time and a default 30-day retention
deadline. There is no background deletion service: an authorized local
operator must arrange deletion after expiry. `delete_expired_validated_dtos()`
requires a non-empty deletion authorization ID, verifies sealed custody and
expiry, writes a separate private authorization receipt, and removes the DTO
files while retaining the sealed metadata and hashes. The receipt is an
operator attestation, not a cryptographic signature. `verify_smoke_observability()`
checks the terminal/summary, artifact hashes, observation correlation, and any
authorized retention-deletion receipt. Keep an independently retained terminal
digest when external authenticity is required.

To inspect a retained rejected action, verify custody first, locate the
`SECTION_ACTION_SCHEMA_VALIDATED` row and its following
`SECTION_ACTION_CONTRACT_RESULT` row by logical call, task, attempt, and DTO
digest, then load the referenced private DTO. Rebuild the deterministic work
contract from the authorized request and host context and invoke
`validate_section_action_contract()` offline. Do not treat a reconstructed
contract as proof of a missing historical response.

The prior `d5-binding-smoke-113dcff6-001` remains immutable and its rejected
worker DTO was not retained. This change cannot recover it retroactively.

## Qualification

The development slice includes provider-free capture, mismatch, screening,
retention, failure, and correlation tests. A synthetic two-track case exercises
obligation validation, lowering, reconciliation, and in-memory execution while
preserving six existing tracks, an unrelated section, and report fields. The
candidate remains pending independent implementation review; no new live
qualification or scientific result is implied.

The implementation base is `113dcff6fd35b809bc4d3ce8d3a38e7a1b06c6e6`.
The combined provider-free planner, workflow, canonical-worker, binding-smoke,
capture, and single-engine suite reported `376 passed, 1 deselected`. The
separate D4/workflow regression run reported `96 passed, 2 deselected`. The
deselections are the previously known long nine-turn and rendering rehearsals;
they are not passing qualification evidence. Provider, endpoint, model,
scientific-turn, and C02 calls during this slice were all zero. The review
checkpoint is the commit containing this candidate document.
