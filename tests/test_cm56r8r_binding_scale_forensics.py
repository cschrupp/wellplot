"""Tests for the zero-call CM-56R8R binding-scale forensics."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.cm56r8r_binding_scale_forensics import (
    CONTRACT_EXAMPLE_ANCHORING_SIGNATURE,
    CROSS_CASE_VALUE_SIGNATURE,
    MINMAX_NAME_CONFLICT_SIGNATURE,
    OTHER_CONTRACT_INDUCED_ENDPOINT_CHANGE,
    RAW_EVIDENCE_PATH,
    TRACK_SCALE_COPY_SIGNATURE,
    build_forensic_summary,
    classify_endpoint_regression,
    extract_contract_numeric_literals,
)


def _scale(
    minimum: float,
    maximum: float,
    *,
    kind: str = "linear",
    reverse: bool = False,
) -> dict[str, object]:
    """Build a bounded synthetic scale projection."""
    return {
        "minimum": minimum,
        "maximum": maximum,
        "kind": kind,
        "reverse": reverse,
    }


def test_exact_swap_is_classified_without_case_id_knowledge() -> None:
    """A reversed endpoint pair with preserved kind/reverse gets the swap signature."""
    result = classify_endpoint_regression(
        expected=_scale(200, 0, reverse=True),
        generated_a=_scale(200, 0, reverse=True),
        generated_b=_scale(0, 200, reverse=True),
    )
    assert result["primary_signature"] == MINMAX_NAME_CONFLICT_SIGNATURE
    assert result["relationships"]["b_is_exact_swap"]


def test_contract_example_pair_is_classified() -> None:
    """A wrong pair matching a concrete contract example is reported."""
    result = classify_endpoint_regression(
        expected=_scale(0, 150),
        generated_a=_scale(0, 150),
        generated_b=_scale(-25, 75),
        contract_pairs=[(-25, 75)],
    )
    assert result["primary_signature"] == CONTRACT_EXAMPLE_ANCHORING_SIGNATURE


def test_track_scale_copy_is_classified() -> None:
    """A binding pair copied from the same output's track scale is reported."""
    result = classify_endpoint_regression(
        expected=_scale(0, 150),
        generated_a=_scale(0, 150),
        generated_b={**_scale(10, 90), "track_x_scale": _scale(10, 90)},
    )
    assert result["primary_signature"] == TRACK_SCALE_COPY_SIGNATURE


def test_cross_case_pair_is_classified() -> None:
    """A pair equal to another frozen case's expected pair is reported."""
    result = classify_endpoint_regression(
        expected=_scale(0, 150),
        generated_a=_scale(0, 150),
        generated_b=_scale(10, 90),
        other_case_pairs={"generic_raster": [(10, 90)]},
    )
    assert result["primary_signature"] == CROSS_CASE_VALUE_SIGNATURE


def test_unmatched_pair_is_other_contract_change() -> None:
    """An unmatched wrong pair remains explicitly unassigned to a mechanism."""
    result = classify_endpoint_regression(
        expected=_scale(0, 150),
        generated_a=_scale(0, 150),
        generated_b=_scale(17, 83),
    )
    assert result["primary_signature"] == OTHER_CONTRACT_INDUCED_ENDPOINT_CHANGE


def test_contract_numeric_extraction_is_deterministic() -> None:
    """Contract examples expose their numeric evidence without hidden fixture data."""
    literals, pairs = extract_contract_numeric_literals(
        {
            "contracts": [
                {
                    "examples": [
                        "CALX with a linear scale from -25 to 75.",
                        "Array x scale 10 to 90.",
                        "sample origin 12, step 2, and 5 ticks.",
                    ]
                }
            ]
        }
    )
    assert literals == ["-25", "75", "10", "90", "12", "2", "5"]
    assert pairs == [
        {"example": "CALX with a linear scale from -25 to 75.", "pair": [-25, 75]},
        {"example": "Array x scale 10 to 90.", "pair": [10, 90]},
    ]


def test_frozen_r8r_population_reproduces_f1_result() -> None:
    """The checked-in forensic artifact is derived from the frozen 15-row evidence."""
    if not Path(RAW_EVIDENCE_PATH).exists():
        pytest.skip("local frozen R8R evidence is unavailable")
    summary = build_forensic_summary()
    assert summary["raw_evidence"]["rows"] == 15
    assert summary["primary_signature"] == MINMAX_NAME_CONFLICT_SIGNATURE
    assert [(row["case_id"], row["attempt_index"]) for row in summary["regressed_rows"]] == [
        ("reverse_scale", 0),
        ("reverse_scale", 1),
        ("reverse_scale", 2),
    ]
    assert summary["regressed_leaves"] == 6
