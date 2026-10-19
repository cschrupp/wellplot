"""Regression: max-token incomplete freeze → DECOMPOSITION_DECODE_FAILURE."""

from nlp_gate_modernbert.decomposer_pilot.pilot_01.run_pilot import (
    classify_incomplete_freeze_failure,
)


def test_max_new_tokens_incomplete_is_decode_failure_not_schema_invalid() -> None:
    failure, detail = classify_incomplete_freeze_failure(
        freeze_failure="DECOMPOSITION_SCHEMA_INVALID",
        freeze_detail="json.JSONDecodeError:Expecting value",
        n_generated_tokens=1024,
        max_new_tokens=1024,
    )
    assert failure == "DECOMPOSITION_DECODE_FAILURE"
    assert detail.startswith("max_new_tokens:1024;underlying_freeze:DECOMPOSITION_SCHEMA_INVALID:")


def test_non_max_incomplete_preserves_freeze_failure() -> None:
    failure, detail = classify_incomplete_freeze_failure(
        freeze_failure="DECOMPOSITION_SCHEMA_INVALID",
        freeze_detail="json.JSONDecodeError:Expecting value",
        n_generated_tokens=200,
        max_new_tokens=1024,
    )
    assert failure == "DECOMPOSITION_SCHEMA_INVALID"
    assert detail == "json.JSONDecodeError:Expecting value"
