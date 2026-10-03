"""Tests for the provider-free SI-V2R SR3 root decomposition."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.semantic_ir_v2r_br1_boundary_audit import EXPECTED_EVIDENCE_SHA256
from scripts.semantic_ir_v2r_sr3_root_mechanisms import (
    BASELINE_SHA,
    DEFAULT_EVIDENCE,
    TARGET_CASES,
    _protected_unchanged,
    authenticate_evidence,
    reclassify_annotation_requirement,
    remove_unrequested_references,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr3"


@pytest.mark.skipif(not DEFAULT_EVIDENCE.is_file(), reason="immutable LQ0 evidence is external")
def test_authenticate_exact_target_population() -> None:
    """Authenticate the complete raw population before selecting four cases."""
    evidence = authenticate_evidence()
    assert evidence["sha256"] == EXPECTED_EVIDENCE_SHA256
    assert evidence["rows"] == 48
    assert evidence["cases"] == 24
    assert evidence["attempts_per_case"] == 2


def test_result_preserves_frozen_and_sr2_scores() -> None:
    """SR3 does not rewrite either historical score layer."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["target_cases"] == 4
    assert result["target_attempts"] == 8
    assert result["frozen_historical_facts"] == {
        "decision": "SI_V2R_PROVIDER_BOUNDARY_REJECTED",
        "semantic_passes": 28,
        "stable_semantic_passes": 14,
        "terminal_structural_failures": 6,
    }
    assert result["sr2_adjusted_facts"] == {
        "semantic_passes": 34,
        "stable_semantic_passes": 17,
        "adjusted_failures": 8,
    }


def test_target_leaf_labels_are_frozen_and_classified() -> None:
    """Every SR2 residual in the four cases receives a root classification."""
    decompositions = json.loads(
        (ARTIFACT_DIR / "case_decompositions.json").read_text(encoding="utf-8")
    )
    assert {item["case_id"] for item in decompositions} == set(TARGET_CASES)
    for item in decompositions:
        assert item["root_stability"] == "ROOT_STABLE"
        assert item["leaves_unexplained"] == 0
        assert all(
            value["classification"] in {"ROOT", "CONSEQUENCE", "CO-ROOT", "INDEPENDENT"}
            for value in item["leaf_classification"].values()
        )


def test_root_taxonomy_is_generic_and_prevalence_is_case_based() -> None:
    """Mechanism names contain no case identity and report attempts plus cases."""
    payload = json.loads((ARTIFACT_DIR / "root_mechanisms.json").read_text(encoding="utf-8"))
    assert set(payload["root_mechanisms"]) == {
        "CONSTRAINT_OWNER_MISPLACEMENT",
        "UNREQUESTED_REFERENCE_INFERENCE",
        "ANNOTATION_WRONG_OWNER",
        "UNRESOLVED_PROMOTION",
    }
    assert all(
        case_id not in payload["root_mechanisms"][mechanism]
        for mechanism in payload["root_mechanisms"]
        for case_id in TARGET_CASES
    )
    assert payload["root_mechanisms"]["UNREQUESTED_REFERENCE_INFERENCE"]["cases"] == 2
    assert payload["root_mechanisms"]["ANNOTATION_WRONG_OWNER"]["cases"] == 2


def test_safety_layer_interaction_is_retained() -> None:
    """SR3 records CM58 actions without changing their implementation or score."""
    decompositions = json.loads(
        (ARTIFACT_DIR / "case_decompositions.json").read_text(encoding="utf-8")
    )
    by_case = {item["case_id"]: item for item in decompositions}
    verde_actions = by_case["cm59-alloc-verde-19"]["safety_interaction"]["cm58_1"]
    iris_actions = by_case["cm59-single-iris-08"]["safety_interaction"]["cm58_1"]
    assert all(action["status"] == "SAFE_REPAIR" for action in verde_actions)
    assert all(action["status"] == "SAFE_REPAIR" for action in iris_actions)
    assert all(
        action["kind"] == "remove_reference"
        for row in verde_actions + iris_actions
        for action in row["actions"]
    )


def test_counterfactuals_are_bounded_and_do_not_mutate_raw_evidence() -> None:
    """Diagnostic transforms operate on copies and do not use gold replacement."""
    before = hashlib.sha256(DEFAULT_EVIDENCE.read_bytes()).hexdigest()
    diagnostics = json.loads(
        (ARTIFACT_DIR / "counterfactual_diagnostics.json").read_text(encoding="utf-8")
    )
    assert diagnostics
    assert all(item["uses_gold_replacement"] is False for item in diagnostics)
    assert {item["operation"] for item in diagnostics} >= {
        "move_existing_textual_constraint",
        "remove_unrequested_references",
        "reclassify_existing_annotation_text",
    }
    after = hashlib.sha256(DEFAULT_EVIDENCE.read_bytes()).hexdigest()
    assert before == after == EXPECTED_EVIDENCE_SHA256


def test_counterfactual_helpers_use_structural_copies() -> None:
    """The three diagnostic helper shapes are independently testable."""
    projection = {
        "sections": [
            {
                "reference_intent": {"kind": "companion_depth_lane"},
                "features": [{"kind": "curve"}],
            }
        ]
    }
    removed = remove_unrequested_references(projection)
    assert projection["sections"][0]["reference_intent"] is not None
    assert removed["sections"][0]["reference_intent"] is None

    annotation_projection = {"sections": [{"features": [{"kind": "curve"}]}]}
    annotation_model = {"sections": [{"requirements": ["annotate the interval top with a marker"]}]}
    reclassified = reclassify_annotation_requirement(annotation_projection, annotation_model)
    assert annotation_projection["sections"][0]["features"] == [{"kind": "curve"}]
    assert reclassified["sections"][0]["features"][-1] == {"kind": "annotation"}


def test_terminal_result_and_production_isolation() -> None:
    """SR3 is diagnostic-only and provider-free."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["decision"] == "SI_V2R_SR3_ROOT_MECHANISMS_RESOLVED"
    assert result["provider_inference_calls"] == 0
    assert result["endpoint_calls"] == 0
    assert result["worker_program_calls"] == 0
    assert result["production_behavior_changed"] is False
    assert result["adr_cm57"] == "UNCHANGED"
    assert BASELINE_SHA == "6d79a9f0cea757b97509dbd42fb50cc309bbae77"
    assert _protected_unchanged()


def test_no_live_or_production_data_in_sr3_artifacts() -> None:
    """Derived artifacts exclude raw envelopes, endpoint data, and secrets."""
    payload = "\n".join(path.read_text(encoding="utf-8") for path in ARTIFACT_DIR.glob("*.json"))
    for forbidden in (
        "provider_response",
        "raw_response",
        "LLAMA_CPP_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        assert forbidden not in payload
