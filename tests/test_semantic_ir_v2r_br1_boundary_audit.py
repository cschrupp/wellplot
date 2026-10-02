"""Provider-free SI-V2R-BR1 boundary-audit tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.semantic_ir_v2r_br1_boundary_audit import (
    DEFAULT_EVIDENCE,
    analyze_evidence,
    authenticate_evidence,
    build_audit,
    invariant_inventory,
    validation_matrix,
)

from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

FIXTURE_DIR = Path("tests/fixtures/semantic_ir_v2r_br1")


@pytest.mark.skipif(not DEFAULT_EVIDENCE.exists(), reason="frozen live evidence is external")
def test_frozen_live_evidence_is_authenticated() -> None:
    """BR1 must use the exact immutable 48-row population."""
    evidence = authenticate_evidence()
    assert evidence["sha256"] == (
        "9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08"
    )
    assert evidence["rows"] == 48
    assert evidence["cases"] == 24
    assert evidence["attempts_per_case"] == 2


@pytest.mark.skipif(not DEFAULT_EVIDENCE.exists(), reason="frozen live evidence is external")
def test_committed_taxonomy_is_reproducible() -> None:
    """The committed residual artifact is derived from raw evidence, not prose."""
    committed = json.loads(
        (FIXTURE_DIR / "live_residual_mechanisms.json").read_text(encoding="utf-8")
    )
    actual = analyze_evidence()
    assert committed["evidence"] == actual["evidence"]
    assert committed["row_mechanism_counts"] == actual["row_mechanism_counts"]
    assert committed["allocation_audit"] == actual["allocation_audit"]


@pytest.mark.skipif(not DEFAULT_EVIDENCE.exists(), reason="frozen live evidence is external")
def test_allocation_family_does_not_imply_allocation_mechanism_failure() -> None:
    """Tamarind, Verde, and Willow preserve allocation despite family failure."""
    taxonomy = analyze_evidence()
    audit = taxonomy["allocation_audit"]
    for case_id in (
        "cm59-alloc-tamarind-17",
        "cm59-alloc-verde-19",
        "cm59-alloc-willow-20",
    ):
        assert audit[case_id]["section_count"] == [True, True]
        assert audit[case_id]["section_order"] == [True, True]
    assert audit["cm59-alloc-umber-18"]["section_count"] == [
        "NOT_EVALUABLE",
        "NOT_EVALUABLE",
    ]
    assert taxonomy["allocation_mechanism_status"] == "PARTIAL"


@pytest.mark.skipif(not DEFAULT_EVIDENCE.exists(), reason="frozen live evidence is external")
def test_garnet_does_not_establish_negative_reference_misunderstanding() -> None:
    """Garnet's evidence separates report and context ownership from negation."""
    garnet = next(
        case for case in analyze_evidence()["cases"] if case["case_id"] == "cm59-single-garnet-06"
    )
    assert garnet["primary_failure_mechanism"] == "REPORT_FALSE_POSITIVE"
    assert "REQUIRED_CONTEXT_OWNER_ERROR" in garnet["secondary_failure_mechanisms"]
    assert "REFERENCE_FALSE_POSITIVE" not in garnet["secondary_failure_mechanisms"]


def test_structurally_unavailable_dimensions_are_not_evaluable() -> None:
    """Terminal schema failures cannot be scored as semantic false values."""
    taxonomy = json.loads(
        (FIXTURE_DIR / "live_residual_mechanisms.json").read_text(encoding="utf-8")
    )
    rows = [row for row in taxonomy["rows"] if not row["structural_available"]]
    assert len(rows) == 6
    for row in rows:
        assert row["primary_failure_mechanism"] == "STRUCTURAL_UNAVAILABLE"
        assert row["section_count_correct"] == "NOT_EVALUABLE"
        assert row["reference_target_correct"] == "NOT_EVALUABLE"


def test_canonical_invariant_inventory_separates_schema_and_runtime_rules() -> None:
    """Relational model validators are not falsely reported as JSON Schema rules."""
    inventory = invariant_inventory(SemanticIRV2R.model_json_schema())
    by_id = {item["invariant_id"]: item for item in inventory}
    assert by_id["feature_discriminator"]["classification"] == "SCHEMA_EXPLICIT"
    assert by_id["reference_target_identifies_feature"]["classification"] == (
        "CANONICAL_VALIDATION_ONLY"
    )
    assert by_id["fill_target_identifies_curve"]["classification"] == ("CANONICAL_VALIDATION_ONLY")
    assert by_id["report_or_sections_required"]["classification"] == ("CANONICAL_VALIDATION_ONLY")


def test_malformed_matrix_exposes_schema_to_canonical_validation_gap() -> None:
    """Several relational invalid cases pass JSON Schema but fail Pydantic."""
    rows = validation_matrix()["rows"]
    by_name = {row["fixture"]: row for row in rows}
    for name in (
        "reference_track_without_target",
        "companion_with_target",
        "reference_target_missing_feature",
        "duplicate_semantic_id",
        "fill_target_missing",
        "fill_target_raster",
        "no_report_or_sections",
        "blank_required_string",
    ):
        assert by_name[name]["json_schema_accepts"] is True
        assert by_name[name]["canonical_model_accepts"] is False
    assert by_name["unknown_feature_kind"]["json_schema_accepts"] is False
    assert by_name["extra_field"]["json_schema_accepts"] is False


def test_exact_deployed_converter_is_not_invented() -> None:
    """Without authenticated build provenance, converter support stays unknown."""
    audit = build_audit()
    assert audit["deployed_converter"]["status"] == "DEPLOYED_CONVERTER_VERSION_UNRESOLVED"
    assert audit["deployed_converter"]["converter_calls"] == 0
    assert audit["decision"] == "SI_V2R_BR1_BOUNDARY_MECHANISM_UNRESOLVED"


def test_audit_is_deterministic_and_provider_free() -> None:
    """Repeated local audits produce identical decision-bearing output."""
    first = build_audit()
    second = build_audit()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["provider_calls"] == 0
    assert first["endpoint_calls"] == 0
    assert first["worker_program_calls"] == 0


def test_audit_source_has_no_endpoint_or_provider_execution_path() -> None:
    """The BR1 implementation cannot accidentally contact the live endpoint."""
    source = Path("scripts/semantic_ir_v2r_br1_boundary_audit.py").read_text(encoding="utf-8")
    assert "192.168.2.140" not in source
    assert "requests." not in source
    assert "httpx." not in source
