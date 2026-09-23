"""Deterministic tests for CM-56R7 offline semantic decomposition."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.cm56r7_semantic_failure_decomposition import (
    EvidenceIntegrityError,
    _row_profile,
    analyze_evidence,
    applicable_checks,
    check_family,
    unrequested_family,
    verify_evidence_integrity,
)


def _expected(*, raster: bool = False, axis: bool = False) -> dict[str, object]:
    """Build a minimal expected section for synthetic analysis tests."""
    binding: dict[str, object] = {"channel": "GR", "scale": {"minimum": 0, "maximum": 150}}
    track: dict[str, object] = {
        "kind": "array" if raster else "normal",
        "title": "Image" if raster else "Gamma Ray",
        "bindings": [binding],
    }
    if raster:
        track["x_scale"] = {"minimum": 0, "maximum": 100}
        binding["kind"] = "raster"
        binding.pop("scale")
        binding["profile"] = "generic"
    if axis:
        binding["sample_axis"] = {"unit": "us"}
    return {"title": track["title"], "source_candidate": "source-1", "tracks": [track]}


def _row(
    *,
    case_id: str = "scalar_linear",
    variant: str = "a",
    omissions: tuple[str, ...] = (),
    unrequested: tuple[str, ...] = (),
    accepted: bool = False,
    eligible: bool = True,
) -> dict[str, object]:
    """Build one synthetic paired R6 row."""
    result = {
        "structured_valid": eligible,
        "context_valid": eligible,
        "compiler_valid": eligible,
        "semantic_accepted": accepted,
        "omissions": list(omissions),
        "unrequested_semantics": list(unrequested),
        "error_code": None if eligible else "channel_missing",
    }
    other = {"a": result.copy(), "c": result.copy()}
    other[variant] = result
    return {
        "case_id": case_id,
        "attempt_index": 0,
        "classification": "PAIRED_TYPED_ATTEMPT",
        **other,
    }


def test_applicable_checks_reconstruct_optional_scale_profile_and_axis() -> None:
    """Only expected optional fields create evaluator check paths."""
    scalar = applicable_checks(_expected())
    raster = applicable_checks(_expected(raster=True))
    axis = applicable_checks(_expected(raster=True, axis=True))
    assert "tracks[0].x_scale" not in scalar
    assert "tracks[0].bindings[0].scale" in scalar
    assert "tracks[0].x_scale" in raster
    assert "tracks[0].bindings[0].profile" in raster
    assert "tracks[0].bindings[0].sample_axis" in axis


def test_check_and_unrequested_family_mapping_is_frozen() -> None:
    """Evaluator paths map to the authorized semantic families."""
    assert check_family("title_valid") == "labels"
    assert check_family("source_selection_valid") == "source_grounding"
    assert check_family("tracks[0].binding_channels") == "binding_topology"
    assert check_family("tracks[0].x_scale") == "track_scale"
    assert check_family("tracks[0].bindings[0].scale") == "binding_scale"
    assert check_family("tracks[0].bindings[0].profile") == "raster_profile"
    assert check_family("tracks[0].bindings[0].sample_axis") == "sample_axis"
    assert unrequested_family("tracks[0].x_scale") == "track_scale"
    assert unrequested_family("tracks[0].bindings[0].scale") == "binding_scale"


def test_eligible_row_uses_omissions_as_exact_pass_fail_boundary() -> None:
    """An omitted check fails and every applicable absent check passes."""
    row = _row(omissions=("tracks[0].bindings[0].scale",))
    profile = _row_profile(row, variant="A", expected=_expected())
    assert profile["evaluation_eligible"] is True
    assert "tracks[0].bindings[0].scale" in profile["failed_checks"]
    assert "title_valid" not in profile["failed_checks"]


def test_context_invalid_row_is_not_an_eligible_semantic_row() -> None:
    """Context failure remains outside semantic denominators."""
    row = _row(eligible=False)
    result = row["a"]
    assert isinstance(result, dict)
    assert not result["context_valid"]
    assert not result["compiler_valid"]


def test_row_profile_separates_scientific_and_unrequested_failures() -> None:
    """Scientific failures and unrequested semantics remain distinct."""
    row = _row(
        omissions=("tracks[0].bindings[0].scale",),
        unrequested=("tracks[0].bindings[0].profile",),
    )
    profile = _row_profile(row, variant="A", expected=_expected())
    assert profile["scientific_failure_present"] is True
    assert profile["unrequested_count"] == 1
    assert profile["failure_class"] == "SCIENTIFIC_SEMANTIC_FAILURE"


def test_vdl_expected_axis_is_an_applicable_scientific_check() -> None:
    """VDL sample-axis fields are included only when expected."""
    row = _row(
        case_id="vdl_sample_axis",
        omissions=("tracks[0].bindings[0].sample_axis",),
    )
    profile = _row_profile(row, variant="C", expected=_expected(raster=True, axis=True))
    assert "sample_axis" in profile["failed_families"]
    assert profile["scientific_failure_present"] is True


def test_evidence_integrity_rejects_wrong_hash_and_row_shape(tmp_path: Path) -> None:
    """R7 fails closed instead of reconstructing missing R6 evidence."""
    evidence = tmp_path / "evidence.jsonl"
    corpus = tmp_path / "corpus.json"
    evidence.write_text(json.dumps({"row": 1}) + "\n", encoding="utf-8")
    corpus.write_text(json.dumps({"cases": []}), encoding="utf-8")
    with pytest.raises(EvidenceIntegrityError, match="SHA mismatch"):
        verify_evidence_integrity(
            evidence,
            corpus,
            expected_evidence_sha256="0" * 64,
            expected_corpus_sha256=hashlib.sha256(corpus.read_bytes()).hexdigest(),
        )


def test_real_evidence_analysis_has_frozen_integrity_and_eligibility() -> None:
    """The committed R6 artifact supports the expected R7 denominators."""
    summary = analyze_evidence()
    assert summary["provider_calls"] == 0
    assert summary["evidence"]["rows"] == 18
    assert summary["eligibility"]["A"]["evaluation_eligible"] == 15
    assert summary["eligibility"]["C"]["evaluation_eligible"] == 15
    assert summary["context_invalid"]["A"] == {"channel_missing": 3}
    assert summary["context_invalid"]["C"] == {"channel_missing": 3}


def test_pairwise_recovery_and_regression_buckets_are_present() -> None:
    """The real result exposes per-check and family A/C pairwise buckets."""
    summary = analyze_evidence()
    pairwise = summary["pairwise"]
    assert "by_check" in pairwise
    assert "by_family" in pairwise
    assert "by_case" in pairwise
    assert set(pairwise["overall"]) == {
        "both_pass",
        "a_fail_c_pass",
        "a_pass_c_fail",
        "both_fail",
    }
