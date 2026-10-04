"""Provider-free tests for SI-V2R SR7-C1 diagnostics."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import scripts.semantic_ir_v2r_sr7_c0_config_probe as c0_probe
from scripts.semantic_ir_v2r_sr7_c0_config_probe import (
    _configuration_record,
    canonical_json,
    sha256_text,
)
from scripts.semantic_ir_v2r_sr7_c1_failure_localization import (
    BASELINE_SHA,
    ROOT_MECHANISMS,
    _json_schema_errors,
    _pydantic_errors,
    _rule_inventory,
    _structural_projection,
    analyze_sanitized_evidence,
    build_artifacts,
)

from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

REPO_ROOT = Path(__file__).resolve().parents[1]
C0_ARTIFACT_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr7_c0"
C1_ARTIFACT_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr7_c1"
C0_FILES = (
    "docs/evaluations/agent-code-mode/semantic-ir-v2/52-si-v2r-sr7-c0-scope.md",
    "docs/evaluations/agent-code-mode/semantic-ir-v2/53-si-v2r-sr7-c0-configuration-a.md",
    "docs/evaluations/agent-code-mode/semantic-ir-v2/54-si-v2r-sr7-c0-configuration-b.md",
    "docs/evaluations/agent-code-mode/semantic-ir-v2/55-si-v2r-sr7-c0-result.md",
    "tests/fixtures/semantic_ir_v2r_sr7_c0/configuration_a.json",
    "tests/fixtures/semantic_ir_v2r_sr7_c0/configuration_b.json",
    "tests/fixtures/semantic_ir_v2r_sr7_c0/probe_summary.json",
    "tests/fixtures/semantic_ir_v2r_sr7_c0/result.json",
)


def _artifact(name: str) -> dict[str, object]:
    return json.loads((C1_ARTIFACT_DIR / name).read_text(encoding="utf-8"))


def test_baseline_and_frozen_inputs_are_unchanged() -> None:
    """C1 preserves the accepted C0 records and canonical schema."""
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", BASELINE_SHA, "HEAD"],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        == 0
    )
    assert (
        sha256_text(canonical_json(SemanticIRV2R.model_json_schema()))
        == "d84cdef165ba6d060addd3ed73b018a1f10a3e70ef4a674b5d1a06352c0d58d8"
    )
    for relative_path in C0_FILES:
        current = (REPO_ROOT / relative_path).read_bytes()
        baseline = subprocess.check_output(
            ["git", "show", f"{BASELINE_SHA}:{relative_path}"], cwd=REPO_ROOT
        )
        assert current == baseline


def test_identity_match_uses_the_normalized_identity_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The metadata comparison uses the canonical identity projection hash."""
    identity = {
        "endpoint": "https://example.invalid/v1",
        "requested_model": "qwen3.6-35b-a3b",
        "observed_model_identifier": "qwen3.6-35b-a3b",
        "available_model_ids": ["qwen3.6-35b-a3b"],
        "model_catalog_sha256": "catalog",
    }
    expected = sha256_text(canonical_json(identity))
    record = _configuration_record(
        configuration_id="A",
        role="CURRENT_BASELINE",
        provider="openai_compat",
        base_url="https://example.invalid/v1",
        requested_model="qwen3.6-35b-a3b",
        identity=identity,
        props={"backend": "llama.cpp"},
        structured_output_status="PASS",
        full_schema_status="PASS",
        reasoning_mode="UNRESOLVED",
        reasoning_control="UNRESOLVED",
        temperature=0.0,
        top_p=None,
        probes=[],
    )
    assert record["historical_identity_match"] is False
    monkeypatch.setattr(c0_probe, "HISTORICAL_A_ENDPOINT_SHA256", expected)
    matching_record = _configuration_record(
        configuration_id="A",
        role="CURRENT_BASELINE",
        provider="openai_compat",
        base_url="https://example.invalid/v1",
        requested_model="qwen3.6-35b-a3b",
        identity=identity,
        props={"backend": "llama.cpp"},
        structured_output_status="PASS",
        full_schema_status="PASS",
        reasoning_mode="UNRESOLVED",
        reasoning_control="UNRESOLVED",
        temperature=0.0,
        top_p=None,
        probes=[],
    )
    assert matching_record["historical_identity_match"] is True


def test_pydantic_errors_are_structurally_preserved() -> None:
    """C1 retains locations and categories without input values."""
    payload = {
        "summary": "probe",
        "sections": [
            {
                "kind": "log_plot",
                "goal": "plot",
                "features": [
                    {"kind": "curve", "semantic_id": "curve"},
                ],
                "reference_intent": {
                    "kind": "reference_track",
                },
            }
        ],
    }
    errors = _pydantic_errors(payload)
    assert errors["status"] == "FAIL"
    assert errors["errors"]
    assert {"loc", "type", "msg_category", "ctx_keys"} <= set(errors["errors"][0])
    assert "input" not in json.dumps(errors)


def test_schema_expressibility_is_checked_against_the_actual_schema() -> None:
    """C1 distinguishes schema keywords from Python-only model validators."""
    payload = {"summary": "probe", "sections": []}
    result = _json_schema_errors(payload)
    assert result["status"] == "PASS"
    rules = {rule["rule_id"]: rule for rule in _rule_inventory()}
    assert rules["reference_track_target_required"]["json_schema_explicit"] == "NO_PYTHON_ONLY"
    assert rules["semantic_id_nonempty"]["json_schema_explicit"] == "YES_EXPLICIT"


def test_structural_projection_excludes_generated_prose() -> None:
    """The persisted shape projection omits free-form generated text."""
    projection = _structural_projection({"summary": "private prose", "kind": "curve"})
    serialized = json.dumps(projection)
    assert "private prose" not in serialized
    assert '"value": "curve"' in serialized


def test_python_only_relational_failure_allows_candidate_freeze() -> None:
    """A schema-valid relational failure can use the local canonical boundary."""
    evidence = {
        "transport_status": "PASS",
        "json_parse_status": "PASS",
        "json_schema_conformance": "PASS",
        "pydantic_canonical_status": "FAIL",
        "pydantic_errors": [{"loc": ["sections", 0], "msg_category": "reference_target_missing"}],
    }
    result = analyze_sanitized_evidence(evidence)
    assert result["root_mechanism"] == "PYDANTIC_ONLY_RELATIONAL_VIOLATION"
    assert result["b_freeze"] == "B_FREEZE_ALLOWED"
    assert result["decision"] == "SI_V2R_SR7_C1_B_FREEZE_ALLOWED"


def test_explicit_schema_failure_forbids_candidate_freeze() -> None:
    """An explicit schema violation blocks candidate configuration freeze."""
    evidence = {
        "transport_status": "PASS",
        "json_parse_status": "PASS",
        "json_schema_conformance": "FAIL",
        "pydantic_canonical_status": "FAIL",
        "pydantic_errors": [{"loc": [], "msg_category": "pydantic_validation_error"}],
    }
    result = analyze_sanitized_evidence(evidence)
    assert result["root_mechanism"] == "PROVIDER_CONSTRAINT_ENFORCEMENT_GAP"
    assert result["b_freeze"] == "B_FREEZE_FORBIDDEN"


def test_unlocalized_failure_remains_unresolved() -> None:
    """Transport or parse failure cannot be promoted to a root mechanism."""
    result = analyze_sanitized_evidence(
        {
            "transport_status": "FAIL",
            "json_parse_status": "NOT_EVALUABLE",
            "json_schema_conformance": "NOT_EVALUABLE",
            "pydantic_canonical_status": "NOT_EVALUABLE",
            "pydantic_errors": [],
        }
    )
    assert result["root_mechanism"] == "FAILURE_CAUSE_UNRESOLVED"
    assert result["decision"] == "SI_V2R_SR7_C1_FAILURE_CAUSE_UNRESOLVED"


@pytest.mark.skipif(not C1_ARTIFACT_DIR.exists(), reason="live C1 artifacts not generated yet")
def test_live_artifacts_are_reproducible_from_sanitized_fixture() -> None:
    """Derived diagnostics reproduce exactly from sanitized evidence."""
    evidence = _artifact("probe_summary.json")["probe"]
    preflight = _artifact("probe_summary.json")["preflight"]
    generated = build_artifacts(evidence, preflight)
    for name, value in generated.items():
        assert value == _artifact(name)


@pytest.mark.skipif(not C1_ARTIFACT_DIR.exists(), reason="live C1 artifacts not generated yet")
def test_c1_result_has_one_allowed_root_and_no_score() -> None:
    """C1 records a mechanism decision, never semantic benchmark scoring."""
    result = _artifact("result.json")
    assert result["root_mechanism"] in ROOT_MECHANISMS
    assert "score" not in result
    assert "pass_rate" not in result
    assert result["cm59a_requests_sent"] == 0
    assert result["a_inference_calls"] == 0
    assert result["worker_program_calls"] == 0


@pytest.mark.skipif(not C1_ARTIFACT_DIR.exists(), reason="live C1 artifacts not generated yet")
def test_c1_artifacts_contain_no_credentials_or_raw_content() -> None:
    """C1 artifacts contain no credentials or assistant response text."""
    forbidden = ("bearer", "nvidia_api_key", "openrouter_api_key", "sk-", "nvapi-")
    for path in C1_ARTIFACT_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        assert not any(marker in text for marker in forbidden)
        assert "response_content" not in text
        assert "raw_response" not in text


def test_c1_source_does_not_expand_into_benchmark_evaluation() -> None:
    """The C1 source cannot silently become a 24-case evaluation."""
    source = Path("scripts/semantic_ir_v2r_sr7_c1_failure_localization.py").read_text(
        encoding="utf-8"
    )
    assert "cm59a_system_reevaluation_cases" not in source
    assert "range(24)" not in source
    assert "generate_structured" not in source
