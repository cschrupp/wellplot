"""Provider-free tests for the D5-5I first-GET diagnostic tooling."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, Never
from urllib import request as urllib_request

import pytest
from scripts import d5_5i_probe_first_get_failure_diagnostic as diagnostic


def _authorization(
    tmp_path: Path, *, authorization_id: str = "diagnostic-auth"
) -> diagnostic.DiagnosticAuthorization:
    """Build an explicit diagnostic authority for an isolated test namespace."""
    return diagnostic.DiagnosticAuthorization(
        scientific_checkpoint=diagnostic.SCIENTIFIC_CHECKPOINT,
        failed_probe_tooling_checkpoint=diagnostic.FAILED_PROBE_TOOLING_CHECKPOINT,
        diagnostic_tooling_checkpoint="diagnostic-tooling-checkpoint",
        authorization_id=authorization_id,
        artifact_root=str(tmp_path / "diagnostic-artifacts"),
        project_config_fingerprint_sha256=diagnostic.EXPECTED_PROJECT_CONFIG_FINGERPRINT,
        target_url=diagnostic.TARGET_URL,
        credential_resolution=diagnostic.EXPECTED_CREDENTIAL_RESOLUTION,
        failed_probe_authorization_id=diagnostic.FAILED_PROBE_AUTHORIZATION_ID,
        failed_probe_artifact_root=str(tmp_path / "failed-probe-artifacts"),
        failed_probe_custody_digests={
            "state_sha256": "a" * 64,
            "journal_sha256": "b" * 64,
            "terminal_sha256": "c" * 64,
        },
    )


def _static_pass(*args: object) -> dict[str, str]:
    """Inject only the already-reviewed static pass for provider-free tests."""
    del args
    return {"status": "PASS"}


def _run(
    authorization: diagnostic.DiagnosticAuthorization,
    endpoint_request: Callable[[str, str], diagnostic.DiagnosticHttpResponse],
    *,
    api_key_loader: Callable[[], str] = lambda: "secret-token",
) -> dict[str, Any]:
    """Run the state machine with no provider construction or network access."""
    return diagnostic.run_diagnostic(
        repo_root=Path("/scientific"),
        failed_probe_tooling_root=Path("/failed-probe-tooling"),
        diagnostic_tooling_root=Path("/diagnostic-tooling"),
        authorization=authorization,
        endpoint_request=endpoint_request,
        api_key_loader=api_key_loader,
        static_checker=_static_pass,
    )


def _catalog_response(status: int = 200) -> diagnostic.DiagnosticHttpResponse:
    """Return a bounded model-catalog response double."""
    return diagnostic.DiagnosticHttpResponse(
        payload={"data": [{"id": "qwen3.6-35b-a3b"}]},
        http_status=status,
    )


@pytest.mark.parametrize(
    ("response", "classification"),
    [
        (
            diagnostic.DiagnosticHttpResponse(None, 401),
            "HTTP_REACHABLE_AUTH_FAILURE",
        ),
        (
            diagnostic.DiagnosticHttpResponse(None, 500),
            "HTTP_REACHABLE_OTHER_FAILURE",
        ),
        (
            diagnostic.DiagnosticHttpResponse(None, 302),
            "HTTP_REACHABLE_OTHER_FAILURE",
        ),
        (
            diagnostic.DiagnosticHttpResponse(diagnostic.UnusableJson("invalid_json"), 200),
            "HTTP_REACHABLE_OTHER_FAILURE",
        ),
        (
            diagnostic.DiagnosticHttpResponse({"unexpected": "shape"}, 200),
            "HTTP_REACHABLE_OTHER_FAILURE",
        ),
        (_catalog_response(), "ENDPOINT_REACHABLE"),
    ],
)
def test_bounded_http_terminals_consume_one_request(
    tmp_path: Path, response: object, classification: str
) -> None:
    """HTTP status and observation failures stay inside the five-class taxonomy."""
    authorization = _authorization(tmp_path)
    calls: list[tuple[str, str]] = []

    def endpoint_request(url: str, token: str) -> diagnostic.DiagnosticHttpResponse:
        calls.append((url, token))
        return response

    result = _run(authorization, endpoint_request)

    assert result["classification"] == classification
    assert result["network_request_issued"] is True
    assert result["endpoint_attempts"] == 1
    assert result["authority_consumed"] is True
    assert len(calls) == 1
    assert calls[0] == (diagnostic.TARGET_URL, "secret-token")


def test_transport_failure_is_tcp_unreachable(tmp_path: Path) -> None:
    """A request without an HTTP response is normalized as TCP unreachable."""
    authorization = _authorization(tmp_path)
    calls: list[str] = []

    def endpoint_request(url: str, token: str) -> Never:
        del token
        calls.append(url)
        raise diagnostic.DiagnosticTransportError("raw transport detail must not escape")

    result = _run(authorization, endpoint_request)

    assert result["classification"] == "TCP_UNREACHABLE"
    assert result["reason"] == "NORMALIZED_TRANSPORT_FAILURE"
    assert result["http_status"] == "NOT_RECEIVED"
    assert calls == [diagnostic.TARGET_URL]
    terminal = Path(authorization.artifact_root) / (
        f"{authorization.authorization_id}.terminal.json"
    )
    assert "raw transport detail" not in terminal.read_text(encoding="utf-8")


def test_stage_one_preflight_failure_seals_local_zero_attempts(tmp_path: Path) -> None:
    """A contemporaneous static failure cannot consume the network authority."""
    authorization = _authorization(tmp_path)
    calls: list[str] = []

    def static_failure(*args: object) -> Never:
        del args
        raise diagnostic.DiagnosticPreflightError("failed-probe custody digest join failed")

    result = diagnostic.run_diagnostic(
        repo_root=Path("/scientific"),
        failed_probe_tooling_root=Path("/failed-probe-tooling"),
        diagnostic_tooling_root=Path("/diagnostic-tooling"),
        authorization=authorization,
        endpoint_request=lambda url, token: calls.append(url),
        api_key_loader=lambda: (_ for _ in ()).throw(AssertionError("loader called")),
        static_checker=static_failure,
    )

    assert result["classification"] == "LOCAL_PRECONDITION"
    assert result["network_request_issued"] is False
    assert result["endpoint_attempts"] == 0
    assert result["authority_consumed"] is False
    assert calls == []
    state = json.loads(
        (
            Path(authorization.artifact_root) / f"{authorization.authorization_id}.state.json"
        ).read_text(encoding="utf-8")
    )
    assert state["status"] == "TERMINAL"
    assert state["consumed"] is False


def test_missing_credential_is_local_precondition_with_zero_attempts(tmp_path: Path) -> None:
    """Credential resolution remains before one-shot consumption."""
    authorization = _authorization(tmp_path)
    calls: list[str] = []

    result = _run(
        authorization,
        lambda url, token: calls.append(url),
        api_key_loader=lambda: "",
    )

    assert result["classification"] == "LOCAL_PRECONDITION"
    assert result["reason"] == "CREDENTIAL_UNAVAILABLE"
    assert result["endpoint_attempts"] == 0
    assert calls == []


def test_redirect_is_not_followed_and_second_attempt_is_rejected(tmp_path: Path) -> None:
    """The transport disables redirects and custody rejects a second issue."""
    assert diagnostic._NoRedirect().redirect_request(None, None, 302, "", {}, "") is None
    authorization = _authorization(tmp_path)
    paths = diagnostic.DiagnosticEvidencePaths(
        Path(authorization.artifact_root), authorization.authorization_id
    )
    custody = diagnostic.DiagnosticCustody.create(paths, authorization)
    assert custody.issue() == 1
    with pytest.raises(diagnostic.DiagnosticToolError, match="second diagnostic request"):
        custody.issue()


def test_default_endpoint_request_marks_http_success_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real urllib JSON boundary preserves HTTP success semantics."""

    class FakeResponse:
        status = 200

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self, limit: int) -> bytes:
            assert limit == diagnostic.MAX_ENDPOINT_RESPONSE_BYTES + 1
            return b"{not-json"

    class FakeOpener:
        def open(self, request: urllib_request.Request, timeout: float) -> FakeResponse:
            assert request.full_url == diagnostic.TARGET_URL
            assert request.get_method() == "GET"
            assert timeout == 20.0
            return FakeResponse()

    monkeypatch.setattr(
        diagnostic.urllib.request,
        "build_opener",
        lambda handler: FakeOpener(),
    )
    response = diagnostic._default_endpoint_request(diagnostic.TARGET_URL, "secret-token")
    assert response.http_status == 200
    assert response.payload == diagnostic.UnusableJson("invalid_json")


@pytest.mark.parametrize(
    "payload",
    [
        diagnostic.UnusableJson("response_too_large"),
        diagnostic.UnusableJson("invalid_json"),
        {"data": []},
        {"data": [{"object": "model"}]},
    ],
)
def test_http_200_unusable_observations_are_not_endpoint_reachable(
    tmp_path: Path, payload: object
) -> None:
    """Oversized, invalid, and invalid-shape 200 responses fail closed."""
    result = _run(
        _authorization(tmp_path),
        lambda url, token: diagnostic.DiagnosticHttpResponse(payload, 200),
    )
    assert result["classification"] == "HTTP_REACHABLE_OTHER_FAILURE"
    assert result["endpoint_attempts"] == 1


def test_failed_probe_digest_mismatch_is_zero_request_local_failure(tmp_path: Path) -> None:
    """A failed-probe custody join failure is a zero-request precondition stop."""
    authorization = _authorization(tmp_path)
    calls: list[str] = []

    def mismatch(*args: object) -> Never:
        del args
        raise diagnostic.DiagnosticPreflightError("failed-probe custody digest join failed")

    result = diagnostic.run_diagnostic(
        repo_root=Path("/scientific"),
        failed_probe_tooling_root=Path("/failed-probe-tooling"),
        diagnostic_tooling_root=Path("/diagnostic-tooling"),
        authorization=authorization,
        endpoint_request=lambda url, token: calls.append(url),
        api_key_loader=lambda: "secret-token",
        static_checker=mismatch,
    )
    assert result["classification"] == "LOCAL_PRECONDITION"
    assert result["endpoint_attempts"] == 0
    assert calls == []


def test_generation_route_is_rejected_before_transport() -> None:
    """The default diagnostic transport cannot be redirected to generation routes."""
    with pytest.raises(diagnostic.DiagnosticPreflightError):
        diagnostic._default_endpoint_request(
            "http://192.168.2.141:8888/v1/chat/completions", "secret-token"
        )


def test_evidence_has_no_credential_or_raw_transport_details(tmp_path: Path) -> None:
    """Sealed terminal and summary evidence remain redacted."""
    authorization = _authorization(tmp_path)
    result = _run(
        authorization,
        lambda url, token: diagnostic.DiagnosticHttpResponse(None, 401),
    )
    root_text = "".join(
        path.read_text(encoding="utf-8") for path in Path(authorization.artifact_root).iterdir()
    )
    assert "secret-token" not in root_text
    assert "Authorization" not in root_text
    assert "raw transport" not in root_text
    assert result["provider_calls"] == 0
    assert result["model_calls"] == 0


def test_failed_probe_join_checks_actual_digest_files(tmp_path: Path) -> None:
    """The static join compares the authorization to real custody bytes."""
    root = tmp_path / "failed-probe"
    root.mkdir()
    auth_id = diagnostic.FAILED_PROBE_AUTHORIZATION_ID
    state = {
        "status": "TERMINAL",
        "consumed": True,
        "endpoint_attempts": 1,
    }
    terminal = {
        "outcome": "AUTHENTICATION_OR_TRANSPORT_FAILURE",
        "reason": "FIRST_IDENTITY_GET_FAILED",
        "endpoint_attempts": 1,
        "provider_calls": 0,
        "model_calls": 0,
    }
    journal = {"event": "probe_endpoint_issued", "endpoint": "/v1/models"}
    paths = diagnostic.DiagnosticEvidencePaths(root, auth_id)
    paths.state.write_text(json.dumps(state), encoding="utf-8")
    paths.terminal.write_text(json.dumps(terminal), encoding="utf-8")
    paths.journal.write_text(json.dumps(journal) + "\n", encoding="utf-8")
    digests = {
        "state_sha256": hashlib.sha256(paths.state.read_bytes()).hexdigest(),
        "journal_sha256": hashlib.sha256(paths.journal.read_bytes()).hexdigest(),
        "terminal_sha256": hashlib.sha256(paths.terminal.read_bytes()).hexdigest(),
    }
    summary = dict(digests)
    paths.summary.write_text(json.dumps(summary), encoding="utf-8")
    authorization = _authorization(tmp_path)
    authorization = replace(
        authorization,
        failed_probe_artifact_root=str(root),
        failed_probe_custody_digests=digests,
    )
    assert diagnostic._verify_failed_probe_join(Path("/scientific"), authorization) == digests
