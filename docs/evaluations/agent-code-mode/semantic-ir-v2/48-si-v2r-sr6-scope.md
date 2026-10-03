# SI-V2R-SR6 Scope

## Status

SR6 is a provider-free historical regrade of the frozen SI-V2R-LQ0 population.
It consumes the SR5 applicability map exactly as committed and does not
rediscover, broaden, or amend eligibility.

| Item | Frozen value |
| --- | --- |
| Baseline checkpoint | `d46b280bbe1326fa1664778c66377067beb2a557` |
| SR5 checkpoint | `d46b280bbe1326fa1664778c66377067beb2a557` |
| Raw evidence | `/tmp/si-v2r-live.jsonl` |
| Raw evidence SHA-256 | `9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08` |
| Population | 48 rows, 24 cases, 2 attempts |
| Provider inference | 0 |
| Endpoint calls | 0 |
| Production changes | 0 |

## Mission

SR6 asks what historical system-semantic status follows when deterministic
credit is applied only where the accepted SR5 row contains
`system_credit_eligibility_by_dimension[dimension] == true`.

The model result, SR2 result, SR3 roots, SR4 contract, and SR5 applicability
states remain historical inputs. SR6 adds a separate
`contract_bounded_system_status`; it does not rewrite the model score or the
original provider-boundary decision.

## Hard boundaries

SR6 does not run a provider, call an endpoint, change prompts or schemas,
invoke workers, modify CM58/V2R/compiler code, or introduce a new ownership or
safety rule. The six structural failures remain `NOT_EVALUABLE`; no semantic
object is reconstructed for them.

The implementation and committed artifacts are:

- `scripts/semantic_ir_v2r_sr6_contract_regrade.py`
- `tests/fixtures/semantic_ir_v2r_sr6/`
- `tests/test_semantic_ir_v2r_sr6_contract_regrade.py`

The derivation has a `--check` mode and writes no provider output.
