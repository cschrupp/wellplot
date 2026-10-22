"""Provider-free tests for the D5-5I runtime-pin metadata tool."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from scripts import d5_5i_runtime_pin_establishment as tool
from scripts import nlp_d5_live_semantic_qualification as d5

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_CONFIG = d5.load_project_config(REPO_ROOT)


def _props() -> dict[str, object]:
    """Build a bounded llama.cpp properties response double."""
    return {
        "model_path": " /srv/models/qwen3.6-35b-a3b.gguf ",
        "default_generation_settings": {
            "n_ctx": 65536,
            "temperature": 0.0,
            "top_p": 1.0,
        },
        "build_info": "llama.cpp metadata test build",
        "total_slots": 1,
        "chat_template": "qwen3-template",
        "gguf_byte_identity": "NOT_AVAILABLE",
    }


def _authorization(
    tmp_path: Path, *, authorization_id: str = "pin-auth"
) -> tool.MetadataAuthorization:
    """Build an explicit metadata authority with matching historical values."""
    projected = d5._project_props(_props(), "json_schema")
    continuity = {
        "model_catalog": [tool.EXPECTED_MODEL],
        **{field: projected[field] for field in tool.CONTINUITY_FIELDS if field != "model_catalog"},
    }
    return tool.MetadataAuthorization(
        implementation_checkpoint=tool.TARGET_EXECUTABLE_CHECKPOINT,
        authorization_id=authorization_id,
        project_config_fingerprint_sha256=PROJECT_CONFIG.fingerprint_sha256,
        artifact_root=str(tmp_path / "runtime-pins"),
        historical_continuity=continuity,
    )


def _static_pass(
    repo_root: Path,
    authorization: tool.MetadataAuthorization,
    paths: tool.MetadataEvidencePaths,
) -> dict[str, Any]:
    """Inject only the already-reviewed static pass for provider-free tests."""
    del repo_root, authorization, paths
    return {"status": "PASS", "single_engine_attestation": {"status": "PASS"}}


def _run(
    authorization: tool.MetadataAuthorization,
    endpoint_get: Callable[[str, str], object],
) -> dict[str, Any]:
    """Run the tool with injected transport and no provider construction."""
    return tool.establish_runtime_pins(
        repo_root=REPO_ROOT,
        authorization=authorization,
        endpoint_get=endpoint_get,
        api_key_loader=lambda: "secret-token",
        static_checker=_static_pass,
    )


def test_successful_two_get_projection_and_custody_are_redacted(tmp_path: Path) -> None:
    """Two ordered GETs seal projected pins without retaining paths or credentials."""
    authorization = _authorization(tmp_path)
    calls: list[tuple[str, str]] = []

    def endpoint_get(url: str, token: str) -> object:
        calls.append((url, token))
        if url == PROJECT_CONFIG.model_catalog_url:
            return {"data": [{"id": tool.EXPECTED_MODEL}]}
        return _props()

    result = _run(authorization, endpoint_get)
    assert result["outcome"] == "SUCCESS"
    assert result["endpoint_attempts"] == 2
    assert result["generation_calls"] == 0
    assert [url for url, _ in calls] == [
        PROJECT_CONFIG.model_catalog_url,
        PROJECT_CONFIG.props_url,
    ]
    assert all(token == "secret-token" for _, token in calls)
    serialized = json.dumps(result, sort_keys=True)
    assert "secret-token" not in serialized
    assert "/srv/models" not in serialized
    paths = tool.MetadataEvidencePaths(
        Path(authorization.artifact_root), authorization.authorization_id
    )
    digests = tool.verify_metadata_custody(paths)
    assert set(digests) == {"state_sha256", "journal_sha256", "terminal_sha256"}
    assert json.loads(paths.state.read_text())["status"] == "TERMINAL"


def test_static_failure_has_zero_endpoint_calls_and_no_consumption(tmp_path: Path) -> None:
    """Static rejection occurs before custody consumption or endpoint access."""
    authorization = _authorization(tmp_path)
    calls: list[str] = []

    def static_failure(
        repo_root: Path,
        checked_authorization: tool.MetadataAuthorization,
        paths: tool.MetadataEvidencePaths,
    ) -> dict[str, Any]:
        del repo_root, checked_authorization, paths
        raise tool.MetadataStaticPreflightError("checkpoint mismatch")

    with pytest.raises(tool.MetadataStaticPreflightError, match="checkpoint mismatch"):
        tool.establish_runtime_pins(
            repo_root=REPO_ROOT,
            authorization=authorization,
            endpoint_get=lambda url, token: calls.append(url),
            api_key_loader=lambda: "secret-token",
            static_checker=static_failure,
        )
    assert calls == []
    assert not Path(authorization.artifact_root).exists()


def test_first_get_authentication_failure_consumes_authority_once(tmp_path: Path) -> None:
    """A failed first GET seals one-shot terminal custody and cannot replay."""
    authorization = _authorization(tmp_path)
    calls: list[str] = []

    def endpoint_get(url: str, token: str) -> object:
        del token
        calls.append(url)
        raise d5.D5ReadinessError("endpoint_authentication_failed", http_status=401)

    result = _run(authorization, endpoint_get)
    assert result["outcome"] == "AUTHENTICATION_FAILURE"
    assert result["endpoint_attempts"] == 1
    assert calls == [PROJECT_CONFIG.model_catalog_url]

    with pytest.raises(tool.MetadataStaticPreflightError, match="not fresh"):
        _run(authorization, endpoint_get)
    assert calls == [PROJECT_CONFIG.model_catalog_url]


def test_second_get_transport_failure_records_two_attempts(tmp_path: Path) -> None:
    """A second GET failure is terminal with truthful two-attempt custody."""
    authorization = _authorization(tmp_path)
    calls: list[str] = []

    def endpoint_get(url: str, token: str) -> object:
        del token
        calls.append(url)
        if len(calls) == 1:
            return {"data": [{"id": tool.EXPECTED_MODEL}]}
        raise d5.D5ReadinessError("endpoint_connection_refused")

    result = _run(authorization, endpoint_get)
    assert result["outcome"] == "TRANSPORT_FAILURE"
    assert result["endpoint_attempts"] == 2
    assert calls == [PROJECT_CONFIG.model_catalog_url, PROJECT_CONFIG.props_url]


def test_incomplete_props_is_not_a_successful_pin(tmp_path: Path) -> None:
    """Malformed properties terminate as unavailable extended identity."""
    authorization = _authorization(tmp_path)

    def endpoint_get(url: str, token: str) -> object:
        del token
        if url == PROJECT_CONFIG.model_catalog_url:
            return {"data": [{"id": tool.EXPECTED_MODEL}]}
        return {"default_generation_settings": {"n_ctx": 65536}}

    result = _run(authorization, endpoint_get)
    assert result["outcome"] == "INCOMPLETE_PROPS"
    assert result["reason"] == "EXTENDED_RUNTIME_IDENTITY_UNAVAILABLE"
    assert result["endpoint_attempts"] == 2


def test_historical_mismatch_stops_before_second_get(tmp_path: Path) -> None:
    """A continuity mismatch is not silently refreshed or followed by props."""
    authorization = _authorization(tmp_path)
    calls: list[str] = []

    def endpoint_get(url: str, token: str) -> object:
        del token
        calls.append(url)
        return {"data": [{"id": "different-model"}]}

    result = _run(authorization, endpoint_get)
    assert result["outcome"] == "MISMATCH"
    assert result["reason"] == "HISTORICAL_IDENTITY_MISMATCH"
    assert result["mismatched_fields"] == ["model_catalog"]
    assert result["endpoint_attempts"] == 1
    assert calls == [PROJECT_CONFIG.model_catalog_url]


def test_third_metadata_attempt_is_rejected_before_transport(tmp_path: Path) -> None:
    """The custody object refuses a third issued metadata request."""
    authorization = _authorization(tmp_path)
    root = Path(authorization.artifact_root)
    paths = tool.MetadataEvidencePaths(root, authorization.authorization_id)
    custody = tool.MetadataCustody.create(paths, authorization, {"status": "PASS"})
    assert custody.issue("/v1/models") == 1
    assert custody.issue("/props") == 2
    with pytest.raises(tool.MetadataToolError, match="third metadata endpoint attempt"):
        custody.issue("/v1/models")
