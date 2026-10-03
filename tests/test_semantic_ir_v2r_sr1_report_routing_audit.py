"""Tests for the provider-free SI-V2R SR1 report-routing audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.semantic_ir_v2r_sr1_report_routing_audit import (
    BASELINE_SHA,
    DEFAULT_EVIDENCE,
    FALSE_POSITIVE_CASES,
    SECTION_ONLY_CONTROLS,
    _git_protected_paths_unchanged,
    authenticate_evidence,
    classify_report_mechanisms,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr1"


@pytest.mark.skipif(not DEFAULT_EVIDENCE.is_file(), reason="immutable LQ0 evidence is external")
def test_authenticate_frozen_lq0_population() -> None:
    """Authenticate the exact external raw population when available."""
    evidence = authenticate_evidence()
    assert evidence["sha256"] == "9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08"
    assert evidence["rows"] == 48
    assert evidence["cases"] == 24
    assert evidence["attempts"] == 2


def test_wrong_evidence_digest_fails_closed(tmp_path: Path) -> None:
    """Reject any source artifact other than the frozen SHA-256."""
    path = tmp_path / "evidence.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected SI-V2R evidence SHA-256"):
        authenticate_evidence(path)


def test_scope_matrix_and_false_positive_population_are_complete() -> None:
    """Keep all 24 cases and the ten decision-bearing rows in view."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["evidence"]["rows"] == 48
    assert result["evidence"]["cases"] == 24
    assert result["mechanism_summary"]["false_positive_rows"] == 10
    assert len(result["mechanism_summary"]["stable_false_positive_cases"]) == 5
    assert result["report_scope_matrix"]["total_correct"] == 24


def test_deterministic_classifier_matches_all_gold_scopes() -> None:
    """The existing classifier owns a complete, exact corpus scope matrix."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    matrix = result["report_scope_matrix"]
    assert matrix["REPORT_ONLY"] == {"correct": 4, "total": 4}
    assert matrix["SECTION_ONLY"] == {"correct": 16, "total": 16}
    assert matrix["MIXED"] == {"correct": 4, "total": 4}
    assert matrix["false_positive_rows_section_only"] == 10
    assert matrix["genuine_report_rows_report_or_mixed"] == 16


def test_cm58_reconciliation_is_complete_for_structurally_available_rows() -> None:
    """SR1 must agree with retained CM-58.2 evidence without rescoring LQ0."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["cm58_reconciliation"] == {
        "comparable_rows": 42,
        "matching_rows": 42,
        "mismatches": 0,
    }


def test_sanitized_rows_contain_no_provider_or_host_data() -> None:
    """The committed projection excludes raw envelopes, secrets, and host paths."""
    for path in ARTIFACT_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("Authorization", "api_key", "Bearer ", "/home/", "/tmp/"):
            assert forbidden not in text, f"{forbidden!r} leaked into {path.name}"


def test_mechanism_taxonomy_does_not_depend_on_case_identity() -> None:
    """Equivalent generated content receives equivalent labels for any case name."""
    model_template = {
        "report_work": {
            "goal": "Display alpha curve in one panel.",
            "requirements": [],
            "constraints": [],
        },
        "sections": [
            {
                "goal": "Display alpha curve.",
                "features": [{"requirements": [], "constraints": []}],
            }
        ],
    }
    first = classify_report_mechanisms(
        request="Show alpha curve in one panel.",
        model={**model_template, "case_id": "first"},
        gold_scope="SECTION_ONLY",
    )
    second = classify_report_mechanisms(
        request="Show beta curve in one panel.",
        model={
            **model_template,
            "case_id": "different",
            "report_work": {
                "goal": "Display beta curve in one panel.",
                "requirements": [],
                "constraints": [],
            },
            "sections": [
                {
                    "goal": "Display beta curve.",
                    "features": [{"requirements": [], "constraints": []}],
                }
            ],
        },
        gold_scope="SECTION_ONLY",
    )
    assert first == second
    assert "REQUEST_SUMMARY_PROMOTION" in first


def test_matched_controls_are_section_only_and_structurally_evaluable() -> None:
    """Control selection excludes false positives and unavailable cases."""
    result = json.loads((ARTIFACT_DIR / "mechanism_summary.json").read_text(encoding="utf-8"))
    for case_id, controls in result["mechanism_summary"]["matched_controls"].items():
        assert case_id in FALSE_POSITIVE_CASES
        assert set(controls).issubset(SECTION_ONLY_CONTROLS)
        assert not set(controls).intersection(FALSE_POSITIVE_CASES)
    assert result["mechanism_summary"]["matched_controls"]


def test_prompt_and_protected_production_artifacts_are_unchanged() -> None:
    """The SR1 branch cannot silently modify prompt, compiler, safety, or planner code."""
    assert BASELINE_SHA == "7a660d6f4efff7a6b3e54a09fa81a3e08e271de4"
    assert _git_protected_paths_unchanged()


def test_sr1_is_provider_free() -> None:
    """The result records no provider, endpoint, or worker/program activity."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["provider_calls"] == 0
    assert result["endpoint_calls"] == 0
    assert result["worker_program_calls"] == 0


def test_hypothesis_and_ownership_decision_are_frozen() -> None:
    """Keep the SR1 terminal decision distinct from any future implementation."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["decision"] == "SI_V2R_SR1_DETERMINISTIC_REPORT_OWNERSHIP_SUPPORTED"
    assert result["recommended_owner_of_report_presence"] == "DETERMINISTIC_BOUNDARY"
    assert result["hypotheses"]["H5_OPTIONAL_REPORT_FIELD_PRIOR"] == "NOT_EVALUABLE"
    assert result["hypotheses"]["H7_DETERMINISTIC_REPORT_PRESENCE_OWNERSHIP"] == "SUPPORTED"
