"""Provider-free tests for the SI-V2R SR7-C0 configuration probe."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.semantic_ir_v2r_sr7_c0_config_probe import (
    B_REQUESTED_MODEL,
    GOLD_SHA256,
    MAX_OUTPUT_TOKENS,
    RETRY_PROMPT_SHA256,
    SYSTEM_PROMPT_SHA256,
    V2R_SCHEMA_SHA256,
    _configuration_record,
    _probe_is_schema_incompatible,
    _response_result,
    _result,
    _schema_request,
    _synthetic_payload,
    _validate_trivial_probe,
    _validate_v2r,
    build_preflight_artifacts,
    canonical_json,
    sha256_text,
)

from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr7_c0"


def _identity(model: str) -> dict[str, object]:
    return {
        "endpoint": "https://example.invalid/v1",
        "requested_model": model,
        "observed_model_identifier": model,
        "available_model_ids": [model],
        "model_catalog_sha256": sha256_text(canonical_json([model])),
    }


def _record(
    configuration_id: str,
    *,
    structured_output_status: str = "PASS",
    full_schema_status: str = "PASS",
    reasoning_mode: str = "EXPLICIT_LOW",
    reasoning_control: object = "FROZEN",
    top_p: float | None = 0.95,
) -> dict[str, object]:
    return _configuration_record(
        configuration_id=configuration_id,
        role="CANDIDATE" if configuration_id == "B" else "CURRENT_BASELINE",
        provider="nvidia_cloud" if configuration_id == "B" else "openai_compat",
        base_url="https://example.invalid/v1",
        requested_model=B_REQUESTED_MODEL,
        identity=_identity(B_REQUESTED_MODEL),
        props={"backend": "NVIDIA hosted OpenAI-compatible"},
        structured_output_status=structured_output_status,
        full_schema_status=full_schema_status,
        reasoning_mode=reasoning_mode,
        reasoning_control=reasoning_control,
        temperature=1.0 if configuration_id == "B" else 0.0,
        top_p=top_p,
        probes=[],
    )


def test_preflight_hashes_bind_the_frozen_repository_inputs() -> None:
    """C0 cannot run against a changed schema, prompt, retry, or corpus."""
    preflight = build_preflight_artifacts(REPO_ROOT)
    assert (
        preflight["baseline"]
        == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip()
    )
    assert preflight["gold_sha256"] == GOLD_SHA256
    assert preflight["v2r_schema_sha256"] == V2R_SCHEMA_SHA256
    assert preflight["prompt_sha256"] == SYSTEM_PROMPT_SHA256
    assert preflight["retry_prompt_sha256"] == RETRY_PROMPT_SHA256


def test_a1_uses_the_exact_v2r_schema_and_no_retry() -> None:
    """A1 is one direct full-schema probe, not a qualification loop."""
    payload = _schema_request(
        model="qwen3.6-35b-a3b",
        system_prompt="system",
        user_prompt=_synthetic_payload(),
        schema_name="SemanticIRV2R",
        schema=SemanticIRV2R.model_json_schema(),
        temperature=0.0,
        top_p=None,
        reasoning_effort=None,
    )
    assert payload["max_tokens"] == MAX_OUTPUT_TOKENS
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "SemanticIRV2R",
            "schema": SemanticIRV2R.model_json_schema(),
            "strict": True,
        },
    }
    assert "retry" not in json.dumps(payload).lower()


def test_b1_validates_the_trivial_schema_before_b2() -> None:
    """B1 accepts exactly the probe object rather than arbitrary JSON."""
    assert _validate_trivial_probe({"ok": True}) is True
    assert _validate_trivial_probe({"ok": False}) is False
    assert _validate_trivial_probe({"ok": True, "extra": 1}) is False


def test_b2_validator_is_the_frozen_v2r_model() -> None:
    """The candidate full-schema probe uses canonical Pydantic validation."""
    assert callable(_validate_v2r)
    assert _validate_v2r({}) is False


def test_a_can_freeze_when_server_default_reasoning_is_unresolved() -> None:
    """A freezes its observed request/schema path without guessing server defaults."""
    a = _record(
        "A",
        reasoning_mode="UNRESOLVED",
        reasoning_control="UNRESOLVED",
        top_p=None,
    )
    b = _record("B")
    outcome = _result(
        a=a,
        b=b,
        probe_summary={"structured_calls_a": 1, "structured_calls_b": 2},
    )
    assert outcome["a_frozen"] is True
    assert outcome["b_frozen"] is True
    assert outcome["decision"] == "SI_V2R_SR7_C0_CONFIGURATIONS_FROZEN"


def test_candidate_transport_failure_is_unresolved_not_schema_incompatible() -> None:
    """Credential, timeout, and transport failures cannot become schema findings."""
    a = _record("A", reasoning_mode="UNRESOLVED", reasoning_control="UNRESOLVED", top_p=None)
    b_probe = {
        "label": "B1_JSON_SCHEMA_TRANSPORT",
        "provider_attempts": 1,
        "response_status_code": 0,
        "error": {"category": "transport"},
        "validation": "NOT_EVALUABLE",
    }
    b = _record("B", structured_output_status="UNRESOLVED", full_schema_status="UNRESOLVED")
    b["probes"] = [b_probe]
    outcome = _result(
        a=a,
        b=b,
        probe_summary={"structured_calls_a": 1, "structured_calls_b": 1},
    )
    assert outcome["decision"] == "SI_V2R_SR7_C0_CONFIGURATION_UNRESOLVED"


def test_candidate_http_schema_rejection_is_incompatible() -> None:
    """An actual bounded 400/422 schema rejection is decision-bearing."""
    a = _record("A", reasoning_mode="UNRESOLVED", reasoning_control="UNRESOLVED", top_p=None)
    b_probe = {
        "label": "B1_JSON_SCHEMA_TRANSPORT",
        "provider_attempts": 1,
        "response_status_code": 400,
        "error": {"category": "http_error", "status_code": 400},
        "validation": "NOT_EVALUABLE",
    }
    b = _record("B", structured_output_status="INCOMPATIBLE", full_schema_status="UNRESOLVED")
    b["probes"] = [b_probe]
    outcome = _result(
        a=a,
        b=b,
        probe_summary={"structured_calls_a": 1, "structured_calls_b": 1},
    )
    assert outcome["decision"] == "SI_V2R_SR7_C0_CANDIDATE_SCHEMA_INCOMPATIBLE"


def test_candidate_http_200_schema_validation_failure_is_unresolved() -> None:
    """A valid HTTP response cannot localize failure to the schema converter."""
    probe = {
        "provider_attempts": 1,
        "response_status_code": 200,
        "error": None,
        "validation": "SCHEMA_VALIDATION",
    }
    assert _probe_is_schema_incompatible(probe) is False


def test_response_result_does_not_persist_provider_content() -> None:
    """Probe diagnostics retain bounded metadata only."""
    body = {
        "model": "candidate",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": '{"ok": true}'},
            }
        ],
        "usage": {"total_tokens": 3},
    }
    result = _response_result(
        body,
        model="candidate",
        schema_validator=_validate_trivial_probe,
    )
    serialized = json.dumps(result)
    assert result["validation"] == "PASS"
    assert '{"ok": true}' not in serialized


def test_c0_source_has_no_qualification_corpus_or_cm59a_request_loop() -> None:
    """C0 cannot silently expand into the 24-case or CM-59A evaluation."""
    source = Path("scripts/semantic_ir_v2r_sr7_c0_config_probe.py").read_text(encoding="utf-8")
    assert "cm59a_system_reevaluation_cases" not in source
    assert "EXPECTED_CASE_COUNT" not in source
    assert "range(24)" not in source


def test_only_bounded_probe_counts_are_declared() -> None:
    """The C0 result explicitly records its bounded call budget."""
    a = _record("A", reasoning_mode="UNRESOLVED", reasoning_control="UNRESOLVED", top_p=None)
    b = _record("B")
    result = _result(
        a=a,
        b=b,
        probe_summary={"structured_calls_a": 1, "structured_calls_b": 2},
    )
    assert result["structured_calls_a"] == 1
    assert result["structured_calls_b"] == 2
    assert result["cm59a_requests_sent"] == 0
    assert result["sr7_p0_authorized"] is False


def test_committed_configuration_fingerprints_reproduce() -> None:
    """Machine records are self-authenticating canonical configuration data."""
    for name in ("configuration_a.json", "configuration_b.json"):
        record = json.loads((ARTIFACT_DIR / name).read_text(encoding="utf-8"))
        expected = record.pop("configuration_fingerprint_sha256")
        assert sha256_text(canonical_json(record)) == expected


def test_committed_c0_artifacts_are_sanitized_and_bounded() -> None:
    """Committed evidence cannot contain credentials or raw provider content."""
    forbidden = ("bearer", "nvidia_api_key", "openrouter_api_key", "sk-", "nvapi-")
    for path in ARTIFACT_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        assert not any(marker in lowered for marker in forbidden)
        assert "response_content" not in lowered
        assert "raw_response" not in lowered


def test_committed_c0_result_preserves_unresolved_b2_interpretation() -> None:
    """HTTP-200 schema validation failure does not become schema proof."""
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    summary = json.loads((ARTIFACT_DIR / "probe_summary.json").read_text(encoding="utf-8"))
    assert result["decision"] == "SI_V2R_SR7_C0_CONFIGURATION_UNRESOLVED"
    assert result["a_frozen"] is True
    assert result["b_frozen"] is False
    assert result["structured_calls_a"] == 1
    assert result["structured_calls_b"] == 2
    assert summary["probes"]["B2"]["response_status_code"] == 200
    assert summary["probes"]["B2"]["validation"] == "SCHEMA_VALIDATION"


def test_committed_result_matches_provider_free_decision_derivation() -> None:
    """The terminal decision is derived from sanitized evidence, not hand-set."""
    a = json.loads((ARTIFACT_DIR / "configuration_a.json").read_text(encoding="utf-8"))
    b = json.loads((ARTIFACT_DIR / "configuration_b.json").read_text(encoding="utf-8"))
    summary = json.loads((ARTIFACT_DIR / "probe_summary.json").read_text(encoding="utf-8"))
    result = json.loads((ARTIFACT_DIR / "result.json").read_text(encoding="utf-8"))
    assert _result(a=a, b=b, probe_summary=summary) == result
