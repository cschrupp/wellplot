"""Tests for the provider-free SI-V2R SR2 historical regrade."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.semantic_ir_v2r_sr1_report_routing_audit import DEFAULT_EVIDENCE
from scripts.semantic_ir_v2r_sr2_historical_regrade import (
    BASELINE_SHA,
    EVIDENCE_SHA256,
    _protected_unchanged,
    authenticate_evidence,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr2"


@pytest.mark.skipif(not DEFAULT_EVIDENCE.is_file(), reason="immutable LQ0 evidence is external")
def test_authenticate_frozen_lq0_population() -> None:
    """Authenticate the exact raw population used for the regrade."""
    evidence = authenticate_evidence()
    assert evidence["sha256"] == EVIDENCE_SHA256
    assert evidence["rows"] == 48
    assert evidence["cases"] == 24
    assert evidence["attempts"] == 2


def test_historical_counts_are_preserved() -> None:
    """SR2 records the original LQ0 result without overwriting it."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["frozen_historical_facts"] == {
        "decision": "SI_V2R_PROVIDER_BOUNDARY_REJECTED",
        "semantic_passes": 28,
        "stable_semantic_passes": 14,
        "terminal_structural_failures": 6,
        "raw_evidence_sha256": EVIDENCE_SHA256,
    }


def test_ownership_adjusted_metrics_are_derived_and_complete() -> None:
    """The committed regrade exposes all required population transitions."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["metrics"] == {
        "raw_rows": 48,
        "structurally_evaluable_rows": 42,
        "frozen_semantic_passes": 28,
        "ownership_adjusted_semantic_passes": 34,
        "frozen_stable_semantic_passes": 14,
        "ownership_adjusted_stable_passes": 17,
        "newly_recovered_attempt_passes": 6,
        "newly_recovered_stable_cases": 3,
        "model_report_overreach_rows": 10,
        "cm58_reconciled_overreach_rows": 10,
        "rows_only_report_presence_failure": 6,
        "rows_report_presence_plus_additional_errors": 4,
        "remaining_system_report_scope_failures": 0,
        "report_content_failures": 0,
        "remaining_adjusted_semantic_failures": 8,
    }
    assert result["transitions"] == {
        "FROZEN_FAIL → ADJUSTED_FAIL": 8,
        "FROZEN_FAIL → ADJUSTED_PASS": 6,
        "FROZEN_PASS → ADJUSTED_PASS": 28,
        "NOT_EVALUABLE → NOT_EVALUABLE": 6,
    }


def test_no_frozen_pass_regresses_and_structural_rows_stay_unavailable() -> None:
    """Ownership adjustment cannot convert a frozen pass into a failure."""
    rows = json.loads((ARTIFACT_DIR / "adjusted_rows.json").read_text(encoding="utf-8"))
    for row in rows:
        if row["frozen_semantic_status"] == "SEMANTIC_PASS":
            assert row["ownership_adjusted_semantic_status"] == "PASS"
    unavailable = [
        row for row in rows if row["ownership_adjusted_semantic_status"] == "NOT_EVALUABLE"
    ]
    assert len(unavailable) == 6


def test_report_presence_and_content_are_separate() -> None:
    """Report overreach is diagnostic while report content remains graded."""
    rows = json.loads((ARTIFACT_DIR / "adjusted_rows.json").read_text(encoding="utf-8"))
    overreach = [row for row in rows if row["model_report_routing_overreach"]]
    assert len(overreach) == 10
    assert all(row["system_report_scope_correct"] for row in overreach)
    assert all(row["cm58_2_action"] for row in overreach)
    report_rows = [row for row in rows if isinstance(row["model_report_content_correct"], bool)]
    assert report_rows
    assert all(row["model_report_content_correct"] is True for row in report_rows)


def test_cm58_scope_reconciliation_and_safety_counts_are_frozen() -> None:
    """SR2 reuses CM-58.2 and preserves its action accounting."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["scope_reproduction"] == {
        "REPORT_ONLY": True,
        "SECTION_ONLY": True,
        "MIXED": True,
        "total": True,
    }
    assert result["cm58_reconciliation"] == {
        "comparable_rows": 42,
        "matching_rows": 42,
        "mismatches": 0,
    }
    assert result["report_safety_accounting"] == {
        "report_removals": 10,
        "report_additions": 0,
        "report_boundary_rejections": 6,
        "unchanged_report_scopes": 32,
    }


def test_residual_counts_remove_report_false_positive_from_system_taxonomy() -> None:
    """The model taxonomy retains overreach while system residuals do not."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["model_residual_counts"]["REPORT_FALSE_POSITIVE"] == 10
    assert "REPORT_FALSE_POSITIVE" not in result["ownership_adjusted_system_residual_counts"]
    assert result["ownership_adjusted_system_residual_counts"]["REQUIRED_CONTEXT_OWNER_ERROR"] == 6


def test_anchor_statuses_are_preserved_and_regraded() -> None:
    """Named historical anchors retain both frozen and adjusted statuses."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["anchor_metrics"] == {
        "Fig": {
            "case_id": "cm59-single-fig-05",
            "frozen_attempt_statuses": ["SEMANTIC_PASS", "SEMANTIC_PASS"],
            "adjusted_attempt_statuses": ["PASS", "PASS"],
            "adjusted_case_status": "STABLE_PASS",
        },
        "Kestrel": {
            "case_id": "cm59-report-kestrel-04",
            "frozen_attempt_statuses": ["SEMANTIC_PASS", "SEMANTIC_PASS"],
            "adjusted_attempt_statuses": ["PASS", "PASS"],
            "adjusted_case_status": "STABLE_PASS",
        },
        "Linden": {
            "case_id": "cm59-reference-linden-10",
            "frozen_attempt_statuses": ["NOT_RUN", "NOT_RUN"],
            "adjusted_attempt_statuses": ["NOT_EVALUABLE", "NOT_EVALUABLE"],
            "adjusted_case_status": "STRUCTURAL_UNAVAILABLE",
        },
        "Xenon": {
            "case_id": "cm59-mixed-xenon-21",
            "frozen_attempt_statuses": ["SEMANTIC_PASS", "SEMANTIC_PASS"],
            "adjusted_attempt_statuses": ["PASS", "PASS"],
            "adjusted_case_status": "STABLE_PASS",
        },
    }


def test_sr2_is_provider_free_and_production_isolated() -> None:
    """No provider activity or protected source changes are part of SR2."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["provider_inference_calls"] == 0
    assert result["endpoint_calls"] == 0
    assert result["worker_program_calls"] == 0
    assert _protected_unchanged()
    assert BASELINE_SHA == "e97ae4d53ed82c724a014d7fc5b52598f9ca201d"


def test_result_is_terminal_but_does_not_qualify_model_or_production() -> None:
    """SR2 closes only the report-presence interpretation question."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["decision"] == "SI_V2R_SR2_REPORT_PRESENCE_RESOLVED"
    assert result["frozen_historical_facts"]["decision"] == "SI_V2R_PROVIDER_BOUNDARY_REJECTED"
    serialized = json.dumps(result)
    assert "MODEL_QUALIFIED" not in serialized
    assert "PROVIDER_QUALIFIED" not in serialized
    assert "PRODUCTION_READY" not in serialized
