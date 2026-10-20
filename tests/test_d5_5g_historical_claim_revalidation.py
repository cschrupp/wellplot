"""Provider-free D5-5G historical-claim revalidation tests."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import d5_5g_historical_claim_revalidation as d5g

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_axis_a_uses_one_canonical_model_and_one_schema_requiredness_delta() -> None:
    """A0/A1 differ only at the provider-facing requiredness path."""
    result = d5g.compare_requiredness_arms()
    assert result["schema_difference_paths"] == ["$.$defs.SectionTask.required"]
    assert result["canonical_model"] == "wellplot.agent.code_mode.planner.SemanticPlan"
    assert result["downstream_validation"] == "SHARED"
    assert result["identical_model_input"] is True
    assert result["plausible_target_count"] == 2
    assert result["request_difference_paths"] == ["$.response_schema.$defs.SectionTask.required"]
    assert d5g.canonical_provider_schema(False) != d5g.canonical_provider_schema(True)


def test_axis_b_contract_is_generic_and_field_local() -> None:
    """B1 adds generic capability-local text without qualification answers."""
    result = d5g.compare_capability_contract_arms()
    assert result["changed_surface"] == "capability_local_contract_text"
    assert result["synthetic_examples"] == "GENERIC"
    assert d5g.capability_contract("B0") is None
    assert len(d5g.capability_contract("B1")["mappings"]) == 2
    assert result["families"] == ["revision_target_mapping", "source_channel_closure"]
    assert all(path.startswith("$.user_payload") for path in result["request_difference_paths"])
    request = d5g._planning_context()["request"]
    examples = json.dumps(d5g.capability_contract("B1"), sort_keys=True)
    assert "Revise Copper Ridge" in request
    assert "source-ember" in request
    assert "Copper Ridge" not in examples
    assert "source-ember" not in examples


def test_axis_c_observes_only_canonical_correction_and_preserves_projection() -> None:
    """C0 proves request mechanics without fabricating corrected output."""
    result = d5g.observe_canonical_correction()
    assert result["condition"] == "C0"
    assert result["alternative_correction_paths"] == 0
    assert result["protected_subtrees"] == "NOT_OBSERVED_PROVIDER_FREE"
    assert result["preservation_evidence"] == "REQUIRES_ACTUAL_CANONICAL_CORRECTION_RESULT"
    assert result["canonical_model"] == "wellplot.agent.code_mode.planner.SemanticPlan"


def test_classifier_does_not_infer_reresolution_from_equal_list_lengths() -> None:
    """Same-sized changed clues remain ambiguous without host identity evidence."""
    before = {
        "target_identity": "Copper Ridge",
        "source_clue": ["source-ember"],
        "scale": ["linear 5-125"],
        "presentation": ["solid blue"],
    }
    after = {
        "target_identity": "Copper Ridge",
        "source_clue": ["source-flint"],
        "scale": ["logarithmic 0.2-2000"],
        "presentation": ["solid orange"],
    }
    result = d5g.classify_protected_subtrees(before, after)
    assert result == {
        "target_identity": "PRESERVED",
        "source_clue": "AMBIGUOUS",
        "scale": "CHANGED",
        "presentation": "CHANGED",
    }
    evidence = {
        "source_clue": {"same_canonical_identity": True},
    }
    assert (
        d5g.classify_protected_subtrees(before, after, resolution_evidence=evidence)["source_clue"]
        == "RE_RESOLVED"
    )


def test_study_runner_executes_the_frozen_d5g_population() -> None:
    """The future path enumerates A/B/C, not the inherited nine-turn campaign."""
    seen: list[str] = []

    def executor(*, dependencies: object, case: dict[str, object]) -> dict[str, object]:
        assert dependencies is not None
        seen.append(str(case["case_id"]))
        return {"first_divergence": None, "canonical_plan_sha256": "synthetic"}

    runner = d5g.D5GStudyRunner(
        dependencies=SimpleNamespace(planner=object()),
        executor=executor,
    )
    result = runner.run()
    assert seen == [case["case_id"] for case in d5g.D5G_STUDY_CASES]
    assert [row["axis"] for row in result] == ["A", "A", "B", "B", "C"]
    assert all(row["case_id"] not in {"D4-C01", "D4-L01-T1"} for row in result)
    assert "execute_live_campaign" not in inspect.getsource(
        d5g.execute_authorized_live_revalidation
    )
    assert "_correction_request" in inspect.getsource(d5g._default_study_executor)


def test_first_divergence_selects_only_the_earliest_failed_boundary() -> None:
    """Later failures cannot replace the first failed canonical boundary."""
    boundaries = dict.fromkeys(d5g.FIRST_DIVERGENCE_ORDER, "PASS")
    boundaries["SEMANTIC_FIELD"] = "SEMANTIC_FIELD"
    boundaries["HARNESS"] = "HARNESS"
    assert d5g.classify_first_divergence(boundaries) == "SEMANTIC_FIELD"
    assert (
        d5g.classify_first_divergence(
            {boundary: boundary for boundary in d5g.FIRST_DIVERGENCE_ORDER}
        )
        == "PROVIDER_OR_STRUCTURED"
    )


def test_future_live_entrypoint_requires_explicit_authority(tmp_path: Path) -> None:
    """The future live path is fail-closed before any executor can be called."""
    with pytest.raises(PermissionError):
        d5g.execute_authorized_live_revalidation(
            REPO_ROOT,
            {
                "authorization_id": "not-live-authority",
                "live_execution": False,
                "implementation_checkpoint": "wrong",
                "campaign_id": "future",
                "artifact_root": str(tmp_path),
                "model": "future-model",
            },
        )


def test_synthetic_inspection_artifact_has_all_ordered_sections(tmp_path: Path) -> None:
    """Provider-free inspection evidence contains the complete visibility contract."""
    output = tmp_path / "inspection.json"
    d5g.write_synthetic_inspection_artifact(output)
    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert artifact["provider_model_calls"] == 0
    assert artifact["sections"] == list(d5g.INSPECTION_SECTIONS)
    assert len(artifact["records"]) == 1
    assert artifact["records"][0]["sections"]["first_divergence"] is None
    committed = REPO_ROOT / "docs/architecture/D5_5G_SYNTHETIC_INSPECTION_ARTIFACT.json"
    assert output.read_text(encoding="utf-8") == committed.read_text(encoding="utf-8")


def test_model_io_custody_reuses_wire_observer_without_headers_or_credentials(
    tmp_path: Path,
) -> None:
    """The accepted wire observer captures bodies and excludes auth material."""
    result = d5g.capture_wire_custody_probe(REPO_ROOT, tmp_path)
    assert result["request_sha256_present"] is True
    assert result["response_sha256_present"] is True
    assert result["headers_captured"] is False
    assert result["credentials_captured"] is False
    assert result["model_io_sha256"] == result["terminal_model_io_sha256"]


def test_provider_free_d5g_proof_is_zero_call_and_single_engine() -> None:
    """The complete implementation proof remains provider-free."""
    result = d5g.verify_provider_free(REPO_ROOT)
    assert result["single_engine_attestation"] == "PASS"
    assert result["canonical_engine"] == d5g.D5_5G_SINGLE_ENGINE_ENTRYPOINT
    assert result["provider_model_calls"] == 0
    assert result["source_changes"] == 0
    assert result["production_changes"] == 0
    assert result["axis_c"]["protected_subtrees"] == "NOT_OBSERVED_PROVIDER_FREE"
    assert result["future_live_harness"]["authority_gated"] is True
    assert result["inspection_artifact"]["status"] == "PASS"
    assert result["study_population_wiring"]["case_ids"] == [
        "D5-5G-A0",
        "D5-5G-A1",
        "D5-5G-B0",
        "D5-5G-B1",
        "D5-5G-C0",
    ]
