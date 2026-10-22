"""Provider-free tests for the D5-5I successor-runtime probe."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from scripts import d5_5i_runtime_build_drift_probe as probe
from scripts import d5_5i_runtime_pin_establishment as pin
from scripts import nlp_d5_live_semantic_qualification as d5

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_CONFIG = d5.load_project_config(REPO_ROOT)


def _props(*, build_info: str = "b11669-378a347ce") -> dict[str, object]:
    """Build a bounded response with the accepted projection shape."""
    return {
        "model_path": "/srv/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf",
        "default_generation_settings": {
            "n_ctx": 65536,
            "temperature": 0.0,
            "top_p": 1.0,
        },
        "build_info": build_info,
        "total_slots": 1,
        "chat_template": "qwen3-template",
    }


def _identity() -> dict[str, Any]:
    """Project the exact identity used by the provider-free response double."""
    projected = d5._project_props(_props(), "json_schema")
    return {
        "model_catalog": [probe.EXPECTED_MODEL],
        **{field: projected[field] for field in probe.SUCCESSOR_FIELDS if field != "model_catalog"},
    }


def _authorization(tmp_path: Path) -> probe.ProbeAuthorization:
    """Build an explicit test authority without deriving runtime identity."""
    return probe.ProbeAuthorization(
        scientific_executable_checkpoint=probe.TARGET_EXECUTABLE_CHECKPOINT,
        projection_baseline_checkpoint=probe.PROJECTION_BASELINE_CHECKPOINT,
        probe_tooling_checkpoint="probe-tooling-checkpoint",
        authorization_id="probe-auth",
        project_config_fingerprint_sha256=PROJECT_CONFIG.fingerprint_sha256,
        artifact_root=str(tmp_path / "probe-evidence"),
        historical_pin_artifact_root=str(tmp_path / "historical"),
        historical_pin_authorization_id=probe.HISTORICAL_AUTHORIZATION_ID,
        historical_pin_custody_digests={
            "state_sha256": "state",
            "journal_sha256": "journal",
            "terminal_sha256": "terminal",
        },
        successor_identity=_identity(),
        target_server_origin=probe.TARGET_SERVER_ORIGIN,
        target_openai_compat_base_url=probe.TARGET_OPENAI_COMPAT_BASE_URL,
        model=probe.EXPECTED_MODEL,
        credential_resolution=probe.EXPECTED_CREDENTIAL_RESOLUTION,
    )


def _static_pass(
    repo_root: Path,
    authorization: probe.ProbeAuthorization,
    paths: probe.ProbeEvidencePaths,
) -> dict[str, Any]:
    """Inject only static facts for provider-free transport tests."""
    del repo_root, authorization, paths
    return {"status": "PASS", "single_engine_attestation": {"status": "PASS"}}


def _run(
    authorization: probe.ProbeAuthorization,
    endpoint_request: Callable[[str, str, str, bytes | None], object],
    *,
    observation_clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Run the probe with injected transport and no provider construction."""
    return probe.establish_successor_compatibility(
        repo_root=REPO_ROOT,
        tooling_root=REPO_ROOT,
        authorization=authorization,
        endpoint_request=endpoint_request,
        api_key_loader=lambda: "secret-token",
        static_checker=_static_pass,
        observation_clock=observation_clock,
    )


def _endpoint_double(
    calls: list[tuple[str, str, bytes | None]],
    *,
    false_prompt: str = "formatted without reasoning",
    true_prompt: str = "formatted with reasoning",
    fail_at: int | None = None,
    build_info: str = "b11669-378a347ce",
) -> Callable[[str, str, str, bytes | None], object]:
    """Return a bounded endpoint double for all four allowed routes."""

    def endpoint_request(method: str, url: str, token: str, body: bytes | None) -> object:
        del token
        calls.append((method, url, body))
        if fail_at == len(calls):
            raise probe.ProbeEndpointError("endpoint_transport_error")
        if method == "GET" and url == PROJECT_CONFIG.model_catalog_url:
            return probe.ProbeEndpointResponse(
                {"data": [{"id": probe.EXPECTED_MODEL}]}, http_status=200
            )
        if method == "GET" and url == PROJECT_CONFIG.props_url:
            return probe.ProbeEndpointResponse(_props(build_info=build_info), http_status=200)
        if method == "POST":
            assert body is not None
            options = json.loads(body)["chat_template_kwargs"]
            return probe.ProbeEndpointResponse(
                {"prompt": false_prompt if options["enable_thinking"] is False else true_prompt},
                http_status=200,
            )
        raise AssertionError((method, url))

    return endpoint_request


def test_differing_prompt_hashes_seal_control_effect(tmp_path: Path) -> None:
    """A contemporaneously matching runtime can establish control sensitivity."""
    calls: list[tuple[str, str, bytes | None]] = []
    result = _run(
        _authorization(tmp_path),
        _endpoint_double(calls),
        observation_clock=lambda: datetime(2026, 10, 22, 12, tzinfo=UTC),
    )

    assert result["outcome"] == "CONTROL_EFFECT_OBSERVED"
    assert result["thinking_off_semantics"] == "NOT_ESTABLISHED_BY_THIS_PROBE"
    assert result["endpoint_attempts"] == 4
    assert [method for method, _, _ in calls] == ["GET", "GET", "POST", "POST"]
    assert calls[2][2] == probe._request_body(False)
    assert calls[3][2] == probe._request_body(True)
    assert result["successor_identity_comparison"] == "EXACT_MATCH"
    assert result["successor_identity_observed_at_utc"] == "2026-10-22T12:00:00Z"
    assert result["false_request_body_sha256"] == probe.FALSE_REQUEST_BODY_SHA256
    assert result["true_request_body_sha256"] == probe.TRUE_REQUEST_BODY_SHA256
    assert result["false_http_status"] == 200
    assert result["true_http_status"] == 200
    assert result["false_response_shape"] == "object_with_string_prompt"
    assert result["true_response_shape"] == "object_with_string_prompt"


def test_identity_drift_blocks_both_template_posts(tmp_path: Path) -> None:
    """A changed successor identity stops before either compatibility POST."""
    calls: list[tuple[str, str, bytes | None]] = []
    endpoint_request = _endpoint_double(calls, build_info="b11669-different")
    result = _run(_authorization(tmp_path), endpoint_request)

    assert result["outcome"] == "SUCCESSOR_IDENTITY_DRIFT"
    assert result["mismatched_fields"] == ["build_info"]
    assert result["endpoint_attempts"] == 2
    assert [method for method, _, _ in calls] == ["GET", "GET"]


def test_auth001_observed_successor_identity_cannot_be_substituted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valid AUTH-001 digests cannot authorize a different successor identity."""
    authorization = _authorization(tmp_path)
    historical_root = tmp_path / "historical"
    paths = pin.MetadataEvidencePaths(historical_root, probe.HISTORICAL_AUTHORIZATION_ID)
    paths.root.mkdir(parents=True)
    paths.terminal.write_text(
        json.dumps(
            {
                "outcome": "MISMATCH",
                "reason": "HISTORICAL_IDENTITY_MISMATCH",
                "mismatched_fields": ["build_info"],
                "observed_empirical_pins": _identity(),
            }
        ),
        encoding="utf-8",
    )
    digests = {"state_sha256": "state", "journal_sha256": "journal", "terminal_sha256": "terminal"}
    monkeypatch.setattr(probe.pin, "verify_metadata_custody", lambda _: digests)
    substituted = replace(
        authorization,
        historical_pin_artifact_root=str(historical_root),
        historical_pin_custody_digests=digests,
        successor_identity={**_identity(), "build_info": "b11669-substituted"},
    )

    with pytest.raises(probe.ProbeStaticPreflightError, match="not joined"):
        probe._verify_historical_pin_join(REPO_ROOT, substituted)


def test_first_identity_get_failure_consumes_one_attempt(tmp_path: Path) -> None:
    """A first identity transport failure is terminal before GET two."""
    calls: list[tuple[str, str, bytes | None]] = []
    result = _run(_authorization(tmp_path), _endpoint_double(calls, fail_at=1))

    assert result["outcome"] == "AUTHENTICATION_OR_TRANSPORT_FAILURE"
    assert result["reason"] == "FIRST_IDENTITY_GET_FAILED"
    assert result["endpoint_attempts"] == 1
    assert len(calls) == 1


def test_second_identity_get_failure_blocks_posts(tmp_path: Path) -> None:
    """A second identity transport failure is terminal before either POST."""
    calls: list[tuple[str, str, bytes | None]] = []
    result = _run(_authorization(tmp_path), _endpoint_double(calls, fail_at=2))

    assert result["outcome"] == "AUTHENTICATION_OR_TRANSPORT_FAILURE"
    assert result["reason"] == "SECOND_IDENTITY_GET_FAILED"
    assert result["endpoint_attempts"] == 2
    assert [method for method, _, _ in calls] == ["GET", "GET"]


def test_malformed_identity_response_blocks_posts(tmp_path: Path) -> None:
    """An unusable identity observation never reaches the template probe."""
    calls: list[tuple[str, str, bytes | None]] = []

    def endpoint_request(method: str, url: str, token: str, body: bytes | None) -> object:
        del token, body
        calls.append((method, url, None))
        if len(calls) == 1:
            return {"unexpected": "shape"}
        return _props()

    result = _run(_authorization(tmp_path), endpoint_request)
    assert result["outcome"] == "INCOMPLETE_SUCCESSOR_IDENTITY"
    assert result["reason"] == "MODEL_CATALOG_UNAVAILABLE"
    assert result["endpoint_attempts"] == 2
    assert [method for method, _, _ in calls] == ["GET", "GET"]


def test_false_arm_failure_is_terminal_at_attempt_three(tmp_path: Path) -> None:
    """A false-arm failure cannot fall through to the true arm."""
    calls: list[tuple[str, str, bytes | None]] = []
    result = _run(_authorization(tmp_path), _endpoint_double(calls, fail_at=3))

    assert result["outcome"] == "COMPATIBILITY_UNESTABLISHED"
    assert result["reason"] == "FALSE_ARM_FAILED"
    assert result["endpoint_attempts"] == 3
    assert [method for method, _, _ in calls] == ["GET", "GET", "POST"]


def test_true_arm_failure_is_terminal_at_attempt_four(tmp_path: Path) -> None:
    """A true-arm failure seals without retry or replay."""
    calls: list[tuple[str, str, bytes | None]] = []
    result = _run(_authorization(tmp_path), _endpoint_double(calls, fail_at=4))

    assert result["outcome"] == "COMPATIBILITY_UNESTABLISHED"
    assert result["reason"] == "TRUE_ARM_FAILED"
    assert result["endpoint_attempts"] == 4
    assert [method for method, _, _ in calls] == ["GET", "GET", "POST", "POST"]


def test_identical_prompt_hashes_do_not_establish_control_effect(tmp_path: Path) -> None:
    """Identical template projections are an explicit negative result."""
    calls: list[tuple[str, str, bytes | None]] = []
    result = _run(
        _authorization(tmp_path),
        _endpoint_double(calls, false_prompt="same", true_prompt="same"),
    )

    assert result["outcome"] == "CONTROL_NOT_OBSERVED"
    assert result["reason"] == "IDENTICAL_PROMPT_PROJECTIONS"
    assert result["endpoint_attempts"] == 4


def test_frozen_request_body_mutation_is_rejected() -> None:
    """A mutated request cannot pass the frozen body contract."""
    mutated = bytearray(probe._request_body(False))
    mutated[-2:] = b"  "
    with pytest.raises(probe.ProbeStaticPreflightError, match="mutation"):
        probe._validate_frozen_request_body(False, bytes(mutated))


def test_fifth_endpoint_attempt_is_rejected_before_transport(tmp_path: Path) -> None:
    """Custody prevents any request beyond the four-request ceiling."""
    authorization = _authorization(tmp_path)
    paths = probe.ProbeEvidencePaths(
        Path(authorization.artifact_root), authorization.authorization_id
    )
    custody = probe.ProbeCustody.create(paths, authorization, {"status": "PASS"})
    for index in range(4):
        assert custody.issue("GET", f"/probe/{index}") == index + 1
    with pytest.raises(probe.ProbeToolError, match="fifth"):
        custody.issue("GET", "/probe/fifth")


def test_generation_route_is_not_allowlisted() -> None:
    """The transport helper rejects chat-completions before network access."""
    with pytest.raises(probe.ProbeStaticPreflightError, match="forbidden"):
        probe._validate_route(
            "POST",
            f"{probe.TARGET_OPENAI_COMPAT_BASE_URL}/chat/completions",
            PROJECT_CONFIG,
        )


def test_probe_authorization_rejects_checkpoint_or_identity_drift() -> None:
    """Machine-readable authority cannot synthesize a different target."""
    payload = {
        "scientific_executable_checkpoint": probe.TARGET_EXECUTABLE_CHECKPOINT,
        "projection_baseline_checkpoint": probe.PROJECTION_BASELINE_CHECKPOINT,
        "probe_tooling_checkpoint": "probe-tooling-checkpoint",
        "authorization_id": "probe-auth",
        "project_config_fingerprint_sha256": PROJECT_CONFIG.fingerprint_sha256,
        "artifact_root": "workspace/probe",
        "historical_pin_artifact_root": "workspace/historical",
        "historical_pin_authorization_id": probe.HISTORICAL_AUTHORIZATION_ID,
        "historical_pin_custody_digests": {
            "state_sha256": "state",
            "journal_sha256": "journal",
            "terminal_sha256": "terminal",
        },
        "successor_identity": _identity(),
        "target_server_origin": probe.TARGET_SERVER_ORIGIN,
        "target_openai_compat_base_url": probe.TARGET_OPENAI_COMPAT_BASE_URL,
        "model": probe.EXPECTED_MODEL,
        "credential_resolution": probe.EXPECTED_CREDENTIAL_RESOLUTION,
    }
    with pytest.raises(probe.ProbeStaticPreflightError, match="checkpoint"):
        probe.ProbeAuthorization.from_mapping(
            {**payload, "scientific_executable_checkpoint": "wrong"}
        )
