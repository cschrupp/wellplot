"""Tests for the provider-free SI-V2R SR6 historical regrade."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from scripts.semantic_ir_v2r_sr6_contract_regrade import build_artifacts

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr6"
RAW_EVIDENCE = Path("/tmp/si-v2r-live.jsonl")
RAW_EVIDENCE_SHA256 = "9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08"
BASELINE_SHA = "d46b280bbe1326fa1664778c66377067beb2a557"


def load_json(name: str) -> object:
    """Load one committed SR6 artifact."""
    return json.loads((ARTIFACT_DIR / name).read_text(encoding="utf-8"))


def test_authenticated_population_and_exact_regeneration() -> None:
    """All four artifacts derive from the authenticated raw population."""
    assert RAW_EVIDENCE.is_file()
    assert hashlib.sha256(RAW_EVIDENCE.read_bytes()).hexdigest() == RAW_EVIDENCE_SHA256
    generated = build_artifacts(RAW_EVIDENCE, REPO_ROOT)
    for filename, expected in generated.items():
        assert load_json(filename) == expected


def test_population_and_frozen_scores_are_preserved() -> None:
    """SR6 does not rewrite LQ0, SR2, or structural unavailability."""
    result = load_json("result.json")
    assert result["evidence"] == {
        "sha256": RAW_EVIDENCE_SHA256,
        "rows": 48,
        "cases": 24,
        "attempts": 2,
    }
    assert result["frozen_historical_facts"] == {
        "decision": "SI_V2R_PROVIDER_BOUNDARY_REJECTED",
        "semantic_passes": 28,
        "stable_semantic_passes": 14,
        "terminal_structural_failures": 6,
    }
    assert result["sr2_historical_facts"]["adjusted_semantic_passes"] == 34
    assert result["sr2_historical_facts"]["adjusted_stable_passes"] == 17
    rows = load_json("regraded_rows.json")
    assert len(rows) == 48
    assert sum(row["contract_bounded_system_status"] == "NOT_EVALUABLE" for row in rows) == 6
    assert sum(row["frozen_model_semantic_status"] == "SEMANTIC_PASS" for row in rows) == 28
    assert sum(row["sr2_status"] == "PASS" for row in rows) == 34


def test_sr5_eligibility_is_copied_without_rederivation() -> None:
    """Each regraded row carries the exact SR5 dimensions and flags."""
    sr5_rows = {
        (row["case_id"], row["attempt"]): row
        for row in json.loads(
            (REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr5/applicability_rows.json").read_text()
        )
    }
    for row in load_json("regraded_rows.json"):
        sr5 = sr5_rows[(row["case_id"], row["attempt"])]
        assert row["sr5_applicability_dimensions"] == sr5["applicability_dimensions"]
        assert row["sr5_blockers"] == sr5["applicability_blockers"]
        assert row["sr5_system_credit_eligibility"] == sr5["system_credit_eligibility_by_dimension"]


def test_blocked_and_model_owned_dimensions_never_receive_credit() -> None:
    """SR4 blockers and model-owned semantics remain system residuals."""
    rows = load_json("regraded_rows.json")
    for row in rows:
        eligibility = row["sr5_system_credit_eligibility"]
        for dimension in (
            "report_content",
            "reference_kind",
            "reference_target",
            "annotation_semantics",
            "constraint_scope",
            "unresolved_requirements",
        ):
            assert not eligibility[dimension]
    verde = [row for row in rows if row["case_id"] == "cm59-alloc-verde-19"]
    assert all(
        "REFERENCE_REPRESENTATION_CONFLICT" in row["remaining_system_residuals"]
        and "REFERENCE_UNSPECIFIED_POLICY_BLOCK" in row["remaining_system_residuals"]
        and "reference_admissibility" not in row["system_credit_applied_dimensions"]
        for row in verde
    )
    garnet = [row for row in rows if row["case_id"] == "cm59-single-garnet-06"]
    assert all(
        "CONSTRAINT_SCOPE_UNRESOLVED" in row["remaining_system_residuals"]
        and "constraint_scope" not in row["system_credit_applied_dimensions"]
        for row in garnet
    )
    amber = [row for row in rows if row["case_id"] == "cm59-mixed-amber-24"]
    assert all("ANNOTATION_ERROR" in row["remaining_system_residuals"] for row in amber)
    iris = [row for row in rows if row["case_id"] == "cm59-single-iris-08"]
    assert all(
        {
            "ANNOTATION_ERROR",
            "UNRESOLVED_REQUIREMENT_ERROR",
            "REFERENCE_REPRESENTATION_CONFLICT",
            "REFERENCE_UNSPECIFIED_POLICY_BLOCK",
        }
        <= set(row["remaining_system_residuals"])
        for row in iris
    )


def test_only_true_report_presence_flags_remove_report_residuals() -> None:
    """The six historical report-only recoveries use the frozen SR5 flag."""
    rows = load_json("regraded_rows.json")
    recovered = [
        row
        for row in rows
        if row["frozen_model_semantic_status"] == "SEMANTIC_FAIL"
        and row["contract_bounded_system_status"] == "PASS"
    ]
    assert len(recovered) == 6
    assert all(
        row["system_credit_applied_dimensions"] == ["report_presence"]
        and row["sr5_system_credit_eligibility"]["report_presence"] is True
        for row in recovered
    )


def test_transitions_are_fail_closed_and_no_pass_regresses() -> None:
    """The required transition matrix is preserved by the derivation."""
    rows = load_json("regraded_rows.json")
    assert all(
        not (
            row["frozen_model_semantic_status"] == "SEMANTIC_PASS"
            and row["contract_bounded_system_status"] != "PASS"
        )
        for row in rows
    )
    result = load_json("result.json")
    assert result["decision"] == "SI_V2R_SR6_NO_ADDITIONAL_SYSTEM_RECOVERY"
    assert result["metrics"]["additional_sr6_changes_vs_sr2"] == 0
    assert result["metrics"]["sr6_system_semantic_passes"] == 34
    assert result["metrics"]["sr6_system_stable_passes"] == 17
    assert result["regrade_completeness"] == "PARTIALLY_REGRADABLE"


def test_named_anchors_and_provider_boundaries() -> None:
    """Anchors retain their model/SR2/SR6 distinctions and zero-call boundary."""
    result = load_json("result.json")
    assert result["anchor_metrics"]["Linden"]["sr6_system_status"] == "STRUCTURAL_UNAVAILABLE"
    assert result["anchor_metrics"]["Kestrel"]["sr6_system_status"] == "STABLE_PASS"
    assert result["anchor_metrics"]["Xenon"]["sr6_system_status"] == "STABLE_PASS"
    assert result["provider_inference_calls"] == 0
    assert result["endpoint_calls"] == 0
    assert result["worker_program_calls"] == 0
    assert result["production_behavior_changed"] is False
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", BASELINE_SHA, "--", "src/wellplot"],
        cwd=REPO_ROOT,
        text=True,
    ).splitlines()
    assert changed == []


def test_sr6_check_mode_reproduces_committed_artifacts() -> None:
    """The public derivation entry point has a provider-free check mode."""
    subprocess.run(
        [
            "python",
            "scripts/semantic_ir_v2r_sr6_contract_regrade.py",
            "--raw-evidence",
            str(RAW_EVIDENCE),
            "--check",
        ],
        cwd=REPO_ROOT,
        check=True,
    )
