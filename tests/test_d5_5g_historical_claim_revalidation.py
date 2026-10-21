"""Provider-free D5-5G historical-claim revalidation tests."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import d5_5g_historical_claim_revalidation as d5g
from scripts import nlp_d4_live_acceptance as d4

from wellplot.agent.providers.response_diagnostics import (
    ProviderResponseFailureReason,
    ProviderSchemaValidationIssue,
    ProviderSchemaValidationShape,
    StructuredResponseProviderError,
)

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
    """C0 deterministically reaches the canonical validator before correction."""
    result = d5g.observe_canonical_correction()
    assert result["condition"] == "C0"
    assert result["alternative_correction_paths"] == 0
    assert result["protected_subtrees"] == "REQUIRES_CORRECTED_PLAN"
    assert result["preservation_evidence"] == "REQUIRES_CANONICAL_CORRECTION_RESULT"
    assert result["validator_diagnostic"]["code"] == "unknown_capability"
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
    result = asyncio.run(runner.run())
    assert seen == [case["case_id"] for case in d5g.D5G_STUDY_CASES]
    assert [row["axis"] for row in result] == ["A", "A", "B", "B", "C"]
    assert all(row["case_id"] not in {"D4-C01", "D4-L01-T1"} for row in result)
    assert "execute_live_campaign" not in inspect.getsource(
        d5g.execute_authorized_live_revalidation
    )
    assert "_correction_request" in inspect.getsource(d5g._default_study_executor)


def test_study_runner_isolates_provider_failure_and_continues() -> None:
    """A failed arm is terminal evidence and cannot prevent later arms."""
    seen: list[str] = []

    class RecordingCustody:
        def __init__(self) -> None:
            self.turns: list[dict[str, object]] = []

        def begin_turn(self, case_id: str) -> None:
            del case_id

        def append_turn(self, row: dict[str, object]) -> None:
            self.turns.append(row)

    def executor(*, dependencies: object, case: dict[str, object]) -> dict[str, object]:
        del dependencies
        case_id = str(case["case_id"])
        seen.append(case_id)
        if case_id == "D5-5G-B0":
            raise d4.ProviderRequestError(
                d4.ProviderFailureCategory.PROVIDER_REJECTED,
                "structured output rejected",
            )
        return {"case_status": "PASS", "first_divergence": None}

    custody = RecordingCustody()
    rows = asyncio.run(
        d5g.D5GStudyRunner(
            dependencies=SimpleNamespace(),
            executor=executor,
            custody=custody,
        ).run()
    )

    assert seen == [case["case_id"] for case in d5g.D5G_STUDY_CASES]
    assert [row["case_id"] for row in rows] == seen
    failed = rows[2]
    assert failed["case_status"] == "INCONCLUSIVE"
    assert failed["first_divergence"] == "PROVIDER_OR_STRUCTURED"
    assert failed["failure_category"] == "provider_rejected"
    assert [row["case_id"] for row in custody.turns] == seen
    assert rows[3]["case_id"] == "D5-5G-B1"
    assert rows[4]["case_id"] == "D5-5G-C0"


def test_structured_failure_inspection_preserves_parse_boundary() -> None:
    """Provider diagnostics map to truthful JSON/schema boundary states."""
    case = d5g.D5G_STUDY_CASES[0]

    invalid_json = StructuredResponseProviderError(
        "provider returned invalid JSON",
        response_reason=ProviderResponseFailureReason.INVALID_JSON,
    )
    invalid_row = d5g._case_failure_result(
        dependencies=SimpleNamespace(), case=case, error=invalid_json
    )
    invalid_boundary = invalid_row["inspection_record"]["sections"]["structured_output_boundary"]
    assert invalid_boundary == {
        "json_decode": "FAIL",
        "schema_validation": "NOT_REACHED",
        "response_reason": "invalid_json",
    }

    schema_error = StructuredResponseProviderError(
        "provider response failed schema validation",
        response_reason=ProviderResponseFailureReason.SCHEMA_VALIDATION,
        validation_shape=ProviderSchemaValidationShape(
            issue_count=1,
            issues=(ProviderSchemaValidationIssue("missing", ("$root", "field")),),
            truncated=False,
        ),
    )
    schema_row = d5g._case_failure_result(
        dependencies=SimpleNamespace(), case=case, error=schema_error
    )
    schema_boundary = schema_row["inspection_record"]["sections"]["structured_output_boundary"]
    assert schema_boundary == {
        "json_decode": "PASS",
        "schema_validation": "FAIL",
        "response_reason": "schema_validation",
        "validation_shape": {
            "issue_count": 1,
            "issues": [{"error_type": "missing", "location": ["$root", "field"]}],
            "truncated": False,
        },
    }

    transport_error = d4.ProviderRequestError(
        d4.ProviderFailureCategory.TRANSPORT,
        "transport failed",
    )
    transport_row = d5g._case_failure_result(
        dependencies=SimpleNamespace(), case=case, error=transport_error
    )
    transport_boundary = transport_row["inspection_record"]["sections"][
        "structured_output_boundary"
    ]
    assert transport_boundary == {
        "json_decode": "NOT_REACHED",
        "schema_validation": "NOT_REACHED",
    }


@pytest.mark.parametrize("reason", list(ProviderResponseFailureReason))
def test_every_provider_response_reason_preserves_decode_progress(
    reason: ProviderResponseFailureReason,
) -> None:
    """Only JSON parsing and schema validation reasons establish decode progress."""
    error = StructuredResponseProviderError(
        "bounded provider response diagnostic",
        response_reason=reason,
        validation_shape=(
            ProviderSchemaValidationShape(
                issue_count=1,
                issues=(ProviderSchemaValidationIssue("missing", ("$root", "field")),),
                truncated=False,
            )
            if reason is ProviderResponseFailureReason.SCHEMA_VALIDATION
            else None
        ),
    )
    boundary = d5g._structured_failure_boundary(error)
    expected = {
        "json_decode": "NOT_REACHED",
        "schema_validation": "NOT_REACHED",
        "response_reason": reason.value,
    }
    if reason is ProviderResponseFailureReason.INVALID_JSON:
        expected["json_decode"] = "FAIL"
    elif reason is ProviderResponseFailureReason.SCHEMA_VALIDATION:
        expected["json_decode"] = "PASS"
        expected["schema_validation"] = "FAIL"
    assert boundary["json_decode"] == expected["json_decode"]
    assert boundary["schema_validation"] == expected["schema_validation"]
    assert boundary["response_reason"] == expected["response_reason"]


def test_live_qwen_backend_does_not_add_structured_output_extra_body() -> None:
    """The Qwen lane uses only the accepted backend response-format contract."""
    source = inspect.getsource(d5g._build_live_study_dependencies)
    assert "request_options=None" in source
    assert 'request_options={"structured_output"' not in source


def test_live_executor_consumes_a_b_c_variables_through_custody() -> None:
    """The provider-free live-shaped executor proves the actual controlled requests."""
    result = d5g._provider_free_live_executor_proof(REPO_ROOT)
    assert result["case_ids"] == [case["case_id"] for case in d5g.D5G_STUDY_CASES]
    assert result["inspection_records"] == 5
    assert result["a_request_difference_paths"] == ["$.response_schema.$defs.SectionTask.required"]
    assert result["b_request_difference_paths"] == ["$.user_payload"]
    assert result["c_validator_diagnostic"]["code"] == "unknown_capability"
    assert result["exact_wire_bodies_custodied"] is True
    assert result["logical_calls"] == 5
    assert result["physical_attempts"] == 5
    assert len(result["loop_ids"]) == 5
    assert len(set(result["loop_ids"])) == 1
    assert result["provider_model_calls"] == 0
    assert result["inspection_metadata"] == {
        "authorization_id": "d5-5g-provider-free-live-proof-auth",
        "campaign_id": "d5-5g-provider-free-live-proof",
        "implementation_checkpoint": d5g._git(REPO_ROOT, "rev-parse", "HEAD"),
        "provider": "openai_compat",
        "model": "provider-free-d5-5g",
        "terminal_status": "PASS",
        "logical_call_index": 1,
        "physical_attempt": 1,
        "request_sha256": result["inspection_metadata"]["request_sha256"],
        "response_sha256": result["inspection_metadata"]["response_sha256"],
        "wire_custody_artifact": "d5-5g-provider-free-live-proof.model-io.jsonl",
    }
    assert (
        result["inspection_metadata"]["response_sha256"]
        != result["inspection_metadata"]["request_sha256"]
    )


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
    assert result["axis_c"]["protected_subtrees"] == "REQUIRES_CORRECTED_PLAN"
    assert result["future_live_harness"]["authority_gated"] is True
    assert result["inspection_artifact"]["status"] == "PASS"
    assert result["study_population_wiring"]["case_ids"] == [
        "D5-5G-A0",
        "D5-5G-A1",
        "D5-5G-B0",
        "D5-5G-B1",
        "D5-5G-C0",
    ]
