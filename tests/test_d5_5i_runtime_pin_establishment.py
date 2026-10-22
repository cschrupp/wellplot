"""Provider-free tests for the D5-5I runtime-pin metadata tool."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
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
        tooling_checkpoint="tooling-test-checkpoint",
        authorization_id=authorization_id,
        project_config_fingerprint_sha256=PROJECT_CONFIG.fingerprint_sha256,
        artifact_root=str(tmp_path / "runtime-pins"),
        historical_continuity=continuity,
        target_server_origin=tool.TARGET_SERVER_ORIGIN,
        target_openai_compat_base_url=tool.TARGET_OPENAI_COMPAT_BASE_URL,
        model=tool.EXPECTED_MODEL,
        credential_resolution=tool.EXPECTED_CREDENTIAL_RESOLUTION,
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
        tooling_root=REPO_ROOT,
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
    assert "structured_output_contract" not in result["empirical_pins"]
    assert "gguf_byte_identity" not in result["empirical_pins"]
    assert result["inherited_configuration"] == {"structured_output_contract": "json_schema"}
    assert result["gguf_byte_identity"] == "NOT_ESTABLISHED"
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
            tooling_root=REPO_ROOT,
            authorization=authorization,
            endpoint_get=lambda url, token: calls.append(url),
            api_key_loader=lambda: "secret-token",
            static_checker=static_failure,
        )
    assert calls == []
    assert not Path(authorization.artifact_root).exists()


def test_missing_credential_is_unconsumed_and_has_zero_gets(tmp_path: Path) -> None:
    """Credential failure occurs before namespace creation or one-shot use."""
    authorization = _authorization(tmp_path)
    calls: list[str] = []

    with pytest.raises(tool.MetadataToolError, match="CREDENTIAL_UNAVAILABLE"):
        tool.establish_runtime_pins(
            repo_root=REPO_ROOT,
            tooling_root=REPO_ROOT,
            authorization=authorization,
            endpoint_get=lambda url, token: calls.append(url),
            api_key_loader=lambda: "",
            static_checker=_static_pass,
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


def test_catalog_mismatch_still_issues_both_metadata_gets(tmp_path: Path) -> None:
    """A catalog mismatch does not suppress the required second observation."""
    authorization = _authorization(tmp_path)
    calls: list[str] = []

    def endpoint_get(url: str, token: str) -> object:
        del token
        calls.append(url)
        if url == PROJECT_CONFIG.model_catalog_url:
            return {"data": [{"id": "different-model"}]}
        return _props()

    result = _run(authorization, endpoint_get)
    assert result["outcome"] == "MISMATCH"
    assert result["reason"] == "HISTORICAL_IDENTITY_MISMATCH"
    assert result["mismatched_fields"] == ["model_catalog"]
    assert result["endpoint_attempts"] == 2
    assert calls == [PROJECT_CONFIG.model_catalog_url, PROJECT_CONFIG.props_url]


def test_malformed_catalog_still_issues_props_before_classification(tmp_path: Path) -> None:
    """A malformed successful first response still permits the second GET."""
    authorization = _authorization(tmp_path)
    calls: list[str] = []

    def endpoint_get(url: str, token: str) -> object:
        del token
        calls.append(url)
        if url == PROJECT_CONFIG.model_catalog_url:
            return {"unexpected": "shape"}
        return _props()

    result = _run(authorization, endpoint_get)
    assert result["outcome"] == "INCOMPLETE_PROPS"
    assert result["reason"] == "MODEL_CATALOG_UNAVAILABLE"
    assert result["endpoint_attempts"] == 2
    assert calls == [PROJECT_CONFIG.model_catalog_url, PROJECT_CONFIG.props_url]


def test_authorization_requires_explicit_target_and_credential_bindings(
    tmp_path: Path,
) -> None:
    """Target identity and credential resolution cannot be synthesized."""
    authorization = _authorization(tmp_path)
    payload = {
        "implementation_checkpoint": authorization.implementation_checkpoint,
        "tooling_checkpoint": authorization.tooling_checkpoint,
        "authorization_id": authorization.authorization_id,
        "project_config_fingerprint_sha256": authorization.project_config_fingerprint_sha256,
        "artifact_root": authorization.artifact_root,
        "historical_continuity": dict(authorization.historical_continuity),
    }
    for field in (
        "target_server_origin",
        "target_openai_compat_base_url",
        "model",
        "credential_resolution",
    ):
        with pytest.raises(tool.MetadataStaticPreflightError, match="missing"):
            tool.MetadataAuthorization.from_mapping(dict(payload))
        payload[field] = getattr(authorization, field)


def test_unsupported_continuity_fields_fail_before_gets(tmp_path: Path) -> None:
    """Continuity projection is closed before any endpoint activity."""
    authorization = _authorization(tmp_path)
    payload = {
        "implementation_checkpoint": authorization.implementation_checkpoint,
        "tooling_checkpoint": authorization.tooling_checkpoint,
        "authorization_id": authorization.authorization_id,
        "project_config_fingerprint_sha256": authorization.project_config_fingerprint_sha256,
        "artifact_root": authorization.artifact_root,
        "target_server_origin": authorization.target_server_origin,
        "target_openai_compat_base_url": authorization.target_openai_compat_base_url,
        "model": authorization.model,
        "credential_resolution": authorization.credential_resolution,
        "historical_continuity": {
            **authorization.historical_continuity,
            "unexpected": "value",
        },
    }
    with pytest.raises(tool.MetadataStaticPreflightError, match="unsupported fields"):
        tool.MetadataAuthorization.from_mapping(payload)


def test_static_preflight_binds_tooling_and_target_checkpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The metadata tool and scientific target identities are separate pins."""
    target_root = tmp_path / "target"
    tooling_root = tmp_path / "tooling"
    authorization = replace(_authorization(tmp_path), tooling_checkpoint="tooling-sha")
    paths = tool.MetadataEvidencePaths(tmp_path / "evidence", authorization.authorization_id)

    def fake_git(root: Path, *arguments: str) -> str:
        if arguments == ("status", "--porcelain"):
            return ""
        if root == target_root:
            return authorization.implementation_checkpoint
        if root == tooling_root:
            return authorization.tooling_checkpoint
        raise AssertionError(root)

    monkeypatch.setattr(tool, "_git", fake_git)
    monkeypatch.setattr(tool, "load_project_config", lambda root: PROJECT_CONFIG)
    monkeypatch.setattr(
        tool.d5,
        "_run_static_attestation",
        lambda root: {"status": "PASS"},
    )
    facts = tool._static_preflight(target_root, tooling_root, authorization, paths)
    assert facts["implementation_checkpoint"] == authorization.implementation_checkpoint
    assert facts["tooling_checkpoint"] == "tooling-sha"

    with pytest.raises(tool.MetadataStaticPreflightError, match="tooling checkpoint"):
        tool._static_preflight(
            target_root,
            tooling_root,
            replace(authorization, tooling_checkpoint="wrong-tooling-sha"),
            tool.MetadataEvidencePaths(tmp_path / "other-evidence", authorization.authorization_id),
        )


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
