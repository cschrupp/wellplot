# A10-SEM-NL-PLANNER-SMOKE-003 Qualification

Status: `A10_SEM_NL_PLANNER_SMOKE_003_INDEPENDENT_OPERATIONAL_ACCEPTANCE`

Smoke 003 is accepted as an operational planner-readiness result. It is not a
semantic-quality result, authoring qualification, rendering qualification, or
release decision.

## Execution identity

- Implementation checkpoint: `29bbcfe7c8ecbb9da49674240996499a20a5f183`
- Branch: `engineering-d5-binding-path-repair`
- Canonical checkout: `/home/user/projects/well_log_os`
- Request: `Plot Gamma Ray.`
- Case: `B01`
- Model: `qwen3.6-35b-a3b`
- Server build observed during readiness: `b12340-b8645ddda`
- Planner wire-schema SHA-256: `b6b05fec2caabbc62708d17b1d752d8888e6cf7e2b91b4b67889eb583b080cbb`
- Approved LAS source SHA-256: `7e6c69c65713dc33303362ab91b767eb06371fd24a31856add8650e6d3bee1a9`

## Result

- Initial generation: schema-invalid.
- Correction generation: schema-valid.
- Logical planner calls: `2`.
- Physical generation attempts: `2`.
- Native correction requests: `1`.
- Endpoint readiness calls: `2`.
- Final wire output: exact `GR`, semantic ref `binding.gr-curve`.
- Source revision and SHA-256: unchanged before, during and after the smoke.
- Numerical sample APIs: not invoked.
- Workers, reconciliation, persistence, rendering and preview: not reached.
- Scientific population and benchmark: not loaded.
- Provider retries: `0`.
- Wrapper exit code: `0`.

The initial response was rejected by the existing local/Pydantic cross-field
validation. The existing correction path supplied the accepted R1 guidance and
the bounded validation diagnostics; the corrected response then passed the
same production wire model. No semantic score or scientific interpretation was
performed.

## Evidence custody

Evidence namespace:

`workspace/evaluations/a10-sem-nl-correction-01r1-planner-smoke-20261115-003/`

The namespace retains complete system/user prompts, exact provider request and
response bodies, assistant content, validation diagnostics, the final parsed
wire response, stage trace, state, terminal and summary records, wrapper
stdout/stderr, static preflight, authorization and a SHA-256 manifest.

- `SHA256SUMS` SHA-256:
  `b16abbd24169ef7607a7f8c48969137d2b57c911de232704d93a229868f2b1b3`
- Provider/model calls: `2`.
- C02 access: `0`.

The independent review verified the supplied evidence files and their manifest.
The uploaded review package did not include the empty `runner.stderr` file,
although the local custody namespace retains it and records its empty-file
digest.

## Open semantic questions

The model output selected `binding.curve` and `track.normal` but did not emit
the `section.log_plot` ancestor. Whether host lowering accepts that capability
set remains unqualified. The output also specified a linear scale without an
explicit user scale request; whether that is an acceptable default remains
unqualified. These questions must be evaluated against the accepted host
contracts, not silently corrected in the smoke record.

## Boundary

Smoke 003 authorizes no workers, authoring mutation, YAML publication,
rendering, P8 benchmark, 53-case holdout, provider expansion, or scientific
execution. The next activity is a separately authorized frozen 53-case
evaluation-readiness review.
