"""Provider-free SI-V2R evidence analysis tests."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.semantic_ir_v2r_analysis import analyze_evidence


def test_authenticated_taxonomy_covers_all_frozen_rows() -> None:
    """The derived taxonomy uses the authentic 48-row evidence only."""
    result = analyze_evidence()
    assert result["evidence"]["rows"] == 48
    assert result["evidence"]["cases"] == 24
    assert result["frozen_si_v2_2"] == {
        "stable_semantic_passes": "8/24",
        "historical_result_changed": False,
    }
    assert len(result["rows"]) == 48
    assert len(result["cases"]) == 24


def test_taxonomy_does_not_use_case_specific_classifier_rules() -> None:
    """Classification code remains generic rather than naming benchmark cases."""
    source = Path("scripts/semantic_ir_v2r_analysis.py").read_text(encoding="utf-8")
    assert "cm59-" not in source
    assert "Linden" not in source
    assert "Xenon" not in source


def test_committed_taxonomy_matches_provider_free_analysis() -> None:
    """The review artifact is reproducible from the immutable raw evidence."""
    committed = json.loads(
        Path("tests/fixtures/semantic_ir_v2r/si_v2_2_failure_taxonomy.json").read_text()
    )
    actual = analyze_evidence()
    assert committed["evidence"] == actual["evidence"]
    assert committed["row_category_counts"] == actual["row_category_counts"]
    assert committed["capability_equivalence"] == actual["capability_equivalence"]
    assert committed["offline_adjudication_counts"] == actual["offline_adjudication_counts"]
