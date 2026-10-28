"""Provider-free tests for the D5-4 live qualification boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import urllib.error
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from pydantic import BaseModel
from scripts import nlp_d4_live_acceptance as d4
from scripts import nlp_d5_live_semantic_qualification as d5
from tests.test_nlp_d4_live_acceptance import (
    _D4PlannerBackend,
    _D4SessionBackend,
    _D4SessionHarness,
    _D4SessionPlanner,
    _D4SessionReportBackend,
    _D4SessionSectionBackend,
)

from wellplot.agent.code_mode.facade import (
    CodeModeCompileResult,
    CompileDiagnostic,
    CompileMetrics,
    CompileWorkerEvidence,
)
from wellplot.agent.providers.base import ProviderRequestError, StructuredGenerationRequest
from wellplot.model.intent import AuthoringDocumentIntent

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_CONFIG = d5.load_project_config(REPO_ROOT)


def _require_local_d5_sources() -> None:
    """Skip canonical-source tests when the isolated checkout lacks frozen assets."""
    missing = [
        relative for relative in d5.FROZEN_SOURCE_SHA256 if not (REPO_ROOT / relative).is_file()
    ]
    if missing:
        pytest.skip("LOCAL_ASSET_NOT_PROVISIONED_IN_THIS_CHECKOUT")


def _props(*, chat_template: str = "qwen3") -> dict[str, object]:
    """Build a sanitized llama.cpp property double."""
    return {
        "model_path": "/srv/models/qwen3.6-35b-a3b.gguf",
        "default_generation_settings": {
            "n_ctx": 32768,
            "temperature": 0.0,
            "top_p": 1.0,
        },
        "build_info": "llama.cpp provider-free test build",
        "total_slots": 1,
        "chat_template": chat_template,
        "gguf_byte_identity": "NOT_AVAILABLE",
    }


def _authorization(
    *,
    thinking_off: bool = True,
    campaign_id: str = "campaign",
    artifact_root: str = "workspace/evaluations/d5-4-live-qualification",
) -> d5.D5Authorization:
    """Build an external-style authorization for injected readiness tests."""
    props = _props()
    defaults = props["default_generation_settings"]
    assert isinstance(defaults, dict)
    return d5.D5Authorization(
        implementation_checkpoint="synthetic-checkpoint",
        authorization_id="auth-test-001",
        campaign_id=campaign_id,
        project_config_fingerprint_sha256=PROJECT_CONFIG.fingerprint_sha256,
        endpoint_identity={
            "model_catalog": [d5.EXPECTED_MODEL],
            "model_path_basename": "qwen3.6-35b-a3b.gguf",
            "model_path_fingerprint_sha256": d4.sha256_text("/srv/models/qwen3.6-35b-a3b.gguf"),
            "context_size": 32768,
            "build_info": "llama.cpp provider-free test build",
            "total_slots": 1,
            "chat_template_sha256": d4.sha256_text("qwen3"),
            "runtime_defaults_sha256": d5._sha256_json(defaults),
            "structured_output_contract": "json_schema",
            "gguf_byte_identity": "NOT_AVAILABLE",
        },
        minimum_context_size=16384,
        runtime_defaults_sha256=d5._sha256_json(defaults),
        thinking_off=thinking_off,
        artifact_root=artifact_root,
    )


def _authorization_payload() -> dict[str, object]:
    """Build the smallest JSON-shaped authorization payload for parser tests."""
    return {
        "implementation_checkpoint": "synthetic-checkpoint",
        "authorization_id": "auth-test-001",
        "campaign_id": "campaign",
        "project_config_fingerprint_sha256": PROJECT_CONFIG.fingerprint_sha256,
        "thinking_off": True,
        "thinking_control_options": d5._thinking_control_options(),
        "thinking_control_options_sha256": d5.THINKING_CONTROL_OPTIONS_SHA256,
    }


def _ready(*, live: bool = False) -> d5.D5OperationalReadiness:
    """Build already-qualified readiness without endpoint activity."""
    projection = d5.D5ReadinessProjection(
        model_catalog=(d5.EXPECTED_MODEL,),
        model_path_basename="qwen3.6-35b-a3b.gguf",
        model_path_fingerprint_sha256="a" * 64,
        context_size=32768,
        build_info="test build",
        total_slots=1,
        chat_template_sha256=d4.sha256_text("qwen3"),
        runtime_defaults_sha256="b" * 64,
        thinking_off=True,
        structured_output_contract="json_schema",
    )
    return d5.D5OperationalReadiness(
        projection=projection,
        endpoint_calls=("/v1/models", "/props"),
        live=live,
    )


def _paths(root: Path, name: str = "campaign") -> d5.EvidencePaths:
    """Build one fresh evidence namespace."""
    return d5.EvidencePaths(root / "evidence", name)


def _provenance() -> dict[str, object]:
    """Return bounded synthetic provenance for campaign-unit tests."""
    return {
        "implementation_checkpoint": "synthetic-checkpoint",
        "accepted_d5_engine_checkpoint": d5.D5_ENGINE_CHECKPOINT,
        "accepted_d5_design_checkpoint": d5.D5_DESIGN_CHECKPOINT,
    }


def test_authorization_requires_explicit_strict_thinking_control() -> None:
    """Missing or malformed external control fields fail before endpoint use."""
    cases: list[tuple[str, dict[str, object]]] = []
    for field in (
        "thinking_off",
        "thinking_control_options",
        "thinking_control_options_sha256",
    ):
        payload = _authorization_payload()
        payload.pop(field)
        cases.append((f"missing_{field}", payload))

    malformed = _authorization_payload()
    malformed["thinking_off"] = "false"
    cases.append(("string_false", malformed))
    malformed = _authorization_payload()
    malformed["thinking_off"] = None
    cases.append(("null_thinking_off", malformed))
    malformed = _authorization_payload()
    malformed["thinking_control_options_sha256"] = "0" * 64
    cases.append(("wrong_digest", malformed))
    malformed = _authorization_payload()
    malformed["thinking_control_options"] = {"chat_template_kwargs": {"enable_thinking": True}}
    cases.append(("changed_value", malformed))
    malformed = _authorization_payload()
    malformed["thinking_control_options"] = {
        "chat_template_kwargs": {"enable_thinking": False},
        "unexpected": True,
    }
    cases.append(("extra_option", malformed))

    for name, payload in cases:
        calls: list[str] = []
        with pytest.raises(d5.D5StaticPreflightError):
            authorization = d5.D5Authorization.from_mapping(payload)
            d5.prepare_readiness(
                authorization=authorization,
                project_config=PROJECT_CONFIG,
                api_key_loader=lambda: "secret-token",
                endpoint_get=lambda url, token, calls=calls: calls.append(url),
                static_preflight={"status": "PASS"},
            )
        assert calls == [], name


class _StructuredOutputRejectingAdapter:
    """Fail on the first measured generation without a retry."""

    logical_call_count = 0
    _call_started: Callable[[dict[str, object]], None] | None = None

    def bind_call_started(self, callback: Callable[[dict[str, object]], None]) -> None:
        """Expose the first measured logical call to campaign custody."""
        self._call_started = callback

    async def execute_turn(
        self,
        case: dict[str, object],
        expected: dict[str, object],
    ) -> object:
        del case, expected
        self.logical_call_count = 1
        if self._call_started is not None:
            self._call_started(
                {
                    "event": "logical_call_started",
                    "index": 1,
                    "generation_role": "planner",
                    "provider": d5.EXPECTED_PROVIDER,
                    "model": d5.EXPECTED_MODEL,
                }
            )
        raise d5.D5StructuredOutputRejected("response_format rejected")


class _WrongSemanticAdapter:
    """Return parsed but scientifically invalid output for every turn."""

    logical_call_count = 0
    _call_started: Callable[[dict[str, object]], None] | None = None

    def bind_call_started(self, callback: Callable[[dict[str, object]], None]) -> None:
        """Expose the canonical first-generation boundary to custody."""
        self._call_started = callback

    async def execute_turn(
        self,
        case: dict[str, object],
        expected: dict[str, object],
    ) -> dict[str, object]:
        del case, expected
        self.logical_call_count += 1
        if self._call_started is not None:
            self._call_started(
                {
                    "event": "logical_call_started",
                    "index": self.logical_call_count,
                    "generation_role": "planner",
                    "provider": d5.EXPECTED_PROVIDER,
                    "model": d5.EXPECTED_MODEL,
                }
            )
        return {
            "canonical_before": {},
            "canonical_after": {},
            "persisted": True,
            "rendered": True,
            "verifier": {"status": "PASS", "requirements": []},
        }


def test_population_and_decoder_policy_are_frozen() -> None:
    """The harness exposes exactly the accepted population and wire controls."""
    assert d5.FROZEN_TURN_IDS == (
        "D4-C01:C01",
        "D4-L01:T1",
        "D4-L01:T2",
        "D4-L01:T3",
        "D4-L01:T4",
        "D4-L02:T1",
        "D4-L02:T2",
        "D4-L03:C01",
        "D4-L04:C01",
    )
    assert d5.DECODER_POLICY["planner"] == {
        "temperature": 0.0,
        "max_output_tokens": None,
    }
    assert d5.DECODER_POLICY["all_roles"] == {
        "top_p": "ABSENT",
        "top_k": "ABSENT",
        "seed": "ABSENT",
        "max_tokens": "ABSENT",
        "max_completion_tokens": "ABSENT",
        "model_substitution": "FORBIDDEN",
    }


def test_provider_free_preflight_is_network_free_and_fail_closed() -> None:
    """Static failure occurs before any readiness endpoint operation."""
    endpoint_calls: list[str] = []
    paths = _paths(REPO_ROOT / "tmp", "static-preflight")

    def failing_checker(
        repo_root: Path,
        authorization: d5.D5Authorization,
        artifact_paths: d5.EvidencePaths,
    ) -> dict[str, Any]:
        del repo_root, authorization, artifact_paths
        raise d5.D5StaticPreflightError("checkpoint mismatch")

    with pytest.raises(d5.D5StaticPreflightError, match="checkpoint mismatch"):
        d5.provider_free_preflight(
            REPO_ROOT,
            _authorization(),
            paths,
            static_checker=failing_checker,
        )

    def endpoint_get(url: str, token: str) -> object:
        del token
        endpoint_calls.append(url)
        return {}

    with pytest.raises(d5.D5ReadinessError, match="static_preflight_failed"):
        d5.prepare_readiness(
            authorization=_authorization(),
            project_config=PROJECT_CONFIG,
            api_key_loader=lambda: "secret-token",
            endpoint_get=endpoint_get,
            static_preflight={"status": "FAIL"},
        )
    assert endpoint_calls == []


def test_provider_free_preflight_exposes_d5i_contract_without_calls(tmp_path: Path) -> None:
    """Provider-free preflight publishes the D5-5I contract and zero-call proof."""
    result = d5.provider_free_preflight(
        REPO_ROOT,
        _authorization(campaign_id="preflight-contract"),
        _paths(tmp_path, "preflight-contract"),
        static_checker=lambda repo, authorization, paths: {"status": "PASS"},
    )
    assert result["status"] == "PASS"
    assert result["logical_call_ceiling"] == 45
    assert result["physical_attempt_upper_bound"] == 135
    assert result["role_logical_call_limits"] == {
        "planner": 2,
        "report_worker": 2,
        "section_worker": 4,
    }
    assert result["accepted_h_implementation_checkpoint"] == (
        d5.D5I_ACCEPTED_H_IMPLEMENTATION_CHECKPOINT
    )
    assert set(result["scientific_terminals"]) == d5.D5I_SCIENTIFIC_TERMINALS
    assert result["provider_calls"] == result["endpoint_calls"] == result["model_calls"] == 0


def test_project_config_fingerprint_mismatch_fails_before_static_boundary() -> None:
    """A stale authorization cannot reach endpoint or provider readiness."""
    checker_called = False

    def checker(
        repo_root: Path,
        authorization: d5.D5Authorization,
        artifact_paths: d5.EvidencePaths,
    ) -> dict[str, Any]:
        nonlocal checker_called
        del repo_root, authorization, artifact_paths
        checker_called = True
        return {"status": "PASS"}

    authorization = _authorization()
    authorization = replace(authorization, project_config_fingerprint_sha256="0" * 64)
    with pytest.raises(d5.D5StaticPreflightError, match="configuration fingerprint"):
        d5.provider_free_preflight(
            REPO_ROOT,
            authorization,
            _paths(REPO_ROOT / "tmp", "fingerprint-mismatch"),
            static_checker=checker,
        )
    assert checker_called is False


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("provider", "name", "other_provider"),
        ("provider", "model", "other-model"),
        ("provider", "timeout_seconds", 901),
        ("provider", "max_retries", 3),
        ("runtime", "concurrency", 2),
        ("runtime", "structured_output", "text"),
    ],
)
def test_project_runtime_drift_fails_before_endpoint_access(
    section: str, field: str, value: object
) -> None:
    """Every frozen runtime invariant fails before credential or endpoint activity."""
    section_config = getattr(PROJECT_CONFIG, section)
    drifted_section = section_config.model_copy(update={field: value})
    drifted_config = PROJECT_CONFIG.model_copy(update={section: drifted_section})
    endpoint_calls: list[str] = []

    with pytest.raises(d5.D5StaticPreflightError):
        d5.prepare_readiness(
            authorization=_authorization(),
            project_config=drifted_config,
            api_key_loader=lambda: "secret-token",
            endpoint_get=lambda url, token: endpoint_calls.append(url),
            static_preflight={"status": "PASS"},
        )
    assert endpoint_calls == []


def test_two_get_readiness_order_and_sanitized_projection() -> None:
    """Readiness performs exactly two ordered observations and no probe."""
    calls: list[tuple[str, str]] = []

    def endpoint_get(url: str, token: str) -> object:
        calls.append((url, token))
        if url == PROJECT_CONFIG.model_catalog_url:
            return {"data": [{"id": d5.EXPECTED_MODEL}]}
        return _props()

    result = d5.prepare_readiness(
        authorization=_authorization(),
        project_config=PROJECT_CONFIG,
        api_key_loader=lambda: "secret-token",
        endpoint_get=endpoint_get,
        static_preflight={"status": "PASS"},
    )
    assert [url for url, _ in calls] == [PROJECT_CONFIG.model_catalog_url, PROJECT_CONFIG.props_url]
    assert all(token == "secret-token" for _, token in calls)
    assert result.endpoint_calls == ("/v1/models", "/props")
    sanitized = json.dumps(result.projection.as_dict(), sort_keys=True)
    assert "secret-token" not in sanitized
    assert "/srv/models" not in sanitized
    projection = result.projection.as_dict()
    assert "chat_template" not in projection
    assert len(projection["chat_template_sha256"]) == 64
    assert result.provider_calls == result.model_calls == 0


def test_chat_template_fingerprint_preserves_exact_utf8_bytes() -> None:
    """Whitespace changes in the returned template produce different hashes."""
    first = d5._project_props(_props(chat_template="qwen3\n"), "json_schema")
    second = d5._project_props(_props(chat_template="qwen3 "), "json_schema")

    assert first["chat_template_sha256"] == hashlib.sha256(b"qwen3\n").hexdigest()
    assert second["chat_template_sha256"] == hashlib.sha256(b"qwen3 ").hexdigest()
    assert first["chat_template_sha256"] != second["chat_template_sha256"]


def test_readiness_rejects_thinking_on_without_generation_probe() -> None:
    """Thinking-off is a runtime precondition, not a request-level probe."""
    calls: list[str] = []

    def endpoint_get(url: str, token: str) -> object:
        del token
        calls.append(url)
        if url == PROJECT_CONFIG.model_catalog_url:
            return {"data": [{"id": d5.EXPECTED_MODEL}]}
        return _props()

    with pytest.raises(d5.D5ReadinessError, match="thinking_off_not_established") as raised:
        d5.prepare_readiness(
            authorization=_authorization(thinking_off=False),
            project_config=PROJECT_CONFIG,
            api_key_loader=lambda: "secret-token",
            endpoint_get=endpoint_get,
            static_preflight={"status": "PASS"},
        )
    assert raised.value.endpoint_calls == 2
    assert calls == [PROJECT_CONFIG.model_catalog_url, PROJECT_CONFIG.props_url]


def test_credential_failure_is_retryable_before_endpoint_observation() -> None:
    """Credential failure does not consume campaign custody or call an endpoint."""
    calls: list[str] = []

    with pytest.raises(d5.D5ReadinessError, match="credential_unavailable"):
        d5.prepare_readiness(
            authorization=_authorization(),
            project_config=PROJECT_CONFIG,
            api_key_loader=lambda: "",
            endpoint_get=lambda url, token: calls.append(url),
            static_preflight={"status": "PASS"},
        )
    assert calls == []


def test_identity_mismatch_is_bounded_after_two_gets() -> None:
    """Wrong catalog identity is a readiness failure, not a model result."""
    calls: list[str] = []

    def endpoint_get(url: str, token: str) -> object:
        del token
        calls.append(url)
        if url == PROJECT_CONFIG.model_catalog_url:
            return {"data": [{"id": "wrong-model"}]}
        return _props()

    with pytest.raises(d5.D5ReadinessError, match="endpoint_identity_mismatch") as raised:
        d5.prepare_readiness(
            authorization=_authorization(),
            project_config=PROJECT_CONFIG,
            api_key_loader=lambda: "secret-token",
            endpoint_get=endpoint_get,
            static_preflight={"status": "PASS"},
        )
    assert raised.value.endpoint_calls == 2
    assert raised.value.mismatched_fields == ("model_catalog",)
    assert calls == [PROJECT_CONFIG.model_catalog_url, PROJECT_CONFIG.props_url]


def test_identity_mismatch_reports_only_safe_field_names() -> None:
    """Runtime drift identifies fields without exposing observed values."""
    authorization = _authorization()
    observed = dict(authorization.endpoint_identity)
    observed["build_info"] = "unexpected private build detail"

    with pytest.raises(d5.D5ReadinessError) as raised:
        d5.validate_readiness_projection(observed, authorization)

    assert raised.value.reason == "endpoint_identity_mismatch"
    assert raised.value.endpoint_calls == 2
    assert raised.value.mismatched_fields == ("build_info",)
    assert "unexpected private build detail" not in str(raised.value)


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (401, "endpoint_authentication_failed"),
        (403, "endpoint_authentication_failed"),
        (404, "endpoint_path_not_found"),
        (503, "endpoint_server_error"),
    ],
)
def test_readiness_http_failures_preserve_status_and_category(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    reason: str,
) -> None:
    """HTTP failures are not misreported as network unreachability."""

    def fail(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise urllib.error.HTTPError("https://endpoint.test", status, "failure", {}, None)

    monkeypatch.setattr(d5.urllib.request, "urlopen", fail)
    with pytest.raises(d5.D5ReadinessError) as raised:
        d5._credential_bearing_json_get("https://endpoint.test", "secret-token")

    assert raised.value.reason == reason
    assert raised.value.http_status == status


def test_readiness_transport_failure_is_distinct_from_http_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connection refusal remains a transport failure with no HTTP status."""

    def fail(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    monkeypatch.setattr(d5.urllib.request, "urlopen", fail)
    with pytest.raises(d5.D5ReadinessError) as raised:
        d5._credential_bearing_json_get("https://endpoint.test", "secret-token")

    assert raised.value.reason == "endpoint_connection_refused"
    assert raised.value.http_status is None


def test_prepare_readiness_preserves_failure_metadata_and_call_count() -> None:
    """Readiness wrapping keeps transport evidence and truthful call custody."""

    def endpoint_get(url: str, token: str) -> object:
        del url, token
        raise d5.D5ReadinessError(
            "endpoint_authentication_failed",
            http_status=401,
        )

    with pytest.raises(d5.D5ReadinessError) as raised:
        d5.prepare_readiness(
            authorization=_authorization(),
            project_config=PROJECT_CONFIG,
            api_key_loader=lambda: "secret-token",
            endpoint_get=endpoint_get,
            static_preflight={"status": "PASS"},
        )

    assert raised.value.reason == "endpoint_authentication_failed"
    assert raised.value.endpoint_calls == 1
    assert raised.value.http_status == 401


def test_cli_reports_bounded_not_ready_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """A pre-STARTED readiness failure produces structured terminal output."""
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(d5, "_load_authorization", lambda path: _authorization())

    def fail_live(**kwargs: object) -> dict[str, object]:
        del kwargs
        raise d5.D5ReadinessError(
            "endpoint_identity_mismatch",
            2,
            mismatched_fields=("build_info",),
        )

    monkeypatch.setattr(d5, "execute_live_campaign", fail_live)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nlp_d5_live_semantic_qualification.py",
            "--repo-root",
            str(REPO_ROOT),
            "--execute-live",
            "--authorization-json",
            str(authorization_path),
        ],
    )

    assert d5.main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "campaign_consumed": False,
        "endpoint_calls": 2,
        "experiment_version": d5.D5_EXPERIMENT_VERSION,
        "mismatched_fields": ["build_info"],
        "model_calls": 0,
        "provider_calls": 0,
        "reason": "endpoint_identity_mismatch",
        "started": False,
        "status": "NOT_READY",
    }


def test_runtime_defaults_drift_is_not_ready() -> None:
    """Omitted decoder controls do not permit unapproved server-default drift."""
    authorization = _authorization()
    calls: list[str] = []

    def endpoint_get(url: str, token: str) -> object:
        del token
        calls.append(url)
        if url == PROJECT_CONFIG.model_catalog_url:
            return {"data": [{"id": d5.EXPECTED_MODEL}]}
        payload = _props()
        generation = payload["default_generation_settings"]
        assert isinstance(generation, dict)
        generation["top_p"] = 0.9
        return payload

    with pytest.raises(d5.D5ReadinessError, match="runtime_defaults_mismatch"):
        d5.prepare_readiness(
            authorization=authorization,
            project_config=PROJECT_CONFIG,
            api_key_loader=lambda: "secret-token",
            endpoint_get=endpoint_get,
            static_preflight={"status": "PASS"},
        )
    assert len(calls) == 2


def test_call_ledger_rejects_call_46_and_keeps_retries_physical() -> None:
    """Retries add physical attempts but never logical calls."""
    ledger = d5.D5LogicalCallLedger()
    for _ in range(45):
        ledger.reserve("planner")
    with pytest.raises(d5.D5CallCapExceeded, match="call 46"):
        ledger.reserve("section_worker")

    retry_ledger = d5.D5LogicalCallLedger()
    index = retry_ledger.reserve("report_worker")
    retry_ledger.physical_attempt(index)
    retry_ledger.physical_attempt(index)
    retry_ledger.complete(index, "failed")
    assert retry_ledger.logical_calls == 1
    assert retry_ledger.physical_attempts == 2
    assert retry_ledger.calls[0]["physical_attempt_count"] == 2


@pytest.mark.parametrize(
    ("role", "limit"),
    [
        ("planner", 2),
        ("report_worker", 2),
        ("section_worker", 4),
    ],
)
def test_d5i_role_limits_fail_closed_at_role_specific_boundary(role: str, limit: int) -> None:
    """Each role admits its canonical per-turn envelope and rejects the next call."""
    ledger = d5.D5LogicalCallLedger()
    ledger.begin_turn("turn-1")
    for _ in range(limit):
        ledger.reserve(role)
    with pytest.raises(
        d5.D5CallCapExceeded,
        match=rf"{role} logical call limit {limit}",
    ):
        ledger.reserve(role)


def test_d5i_cbl_role_shape_and_per_turn_reset_are_provider_free() -> None:
    """A two-section CBL turn admits one initial/correction pair per section."""
    ledger = d5.D5LogicalCallLedger()
    for turn_id in ("turn-1", "turn-2"):
        ledger.begin_turn(turn_id)
        ledger.reserve("planner")
        ledger.reserve("report_worker")
        for _ in range(4):
            ledger.reserve("section_worker")
        assert ledger.turn_role_counts == {
            "planner": 1,
            "report_worker": 1,
            "section_worker": 4,
        }


def test_d5i_global_physical_136_fails_closed() -> None:
    """The physical-attempt ceiling remains independent of role-local limits."""
    physical_ledger = d5.D5LogicalCallLedger()
    index = physical_ledger.reserve("planner")
    for _ in range(d5.MAX_PHYSICAL_ATTEMPTS):
        physical_ledger.physical_attempt(index)
    with pytest.raises(d5.D5CallCapExceeded, match="physical attempt 136"):
        physical_ledger.physical_attempt(index)


@pytest.mark.parametrize(
    ("actual", "grade", "failure", "expected"),
    [
        ({}, {}, ("PROVIDER", "transport"), "PROVIDER_OR_STRUCTURED"),
        ({}, {"errors": ["schema invalid"]}, None, "PLANNER_STRUCTURAL"),
        ({}, {"errors": ["target mismatch"]}, None, "TARGET_GROUNDING"),
        ({}, {"errors": ["source channel unavailable"]}, None, "SOURCE_CHANNEL_GROUNDING"),
        ({}, {"errors": ["capability parent missing"]}, None, "CAPABILITY"),
        ({}, {"errors": ["canonical_change_outside"]}, None, "CORRECTION_PRESERVATION"),
        ({}, {"errors": ["owner diagnostic mismatch"]}, None, "HOST_EXECUTION"),
        ({}, {"errors": ["persistence_not_proven"]}, None, "PERSISTENCE_RELOAD_RENDER"),
        ({}, {"errors": ["semantic mismatch"]}, None, "SEMANTIC"),
        ({"first_divergence": "DETERMINISTIC_GRADING"}, {}, None, "DETERMINISTIC_GRADING"),
        ({"harness_failure": True}, {}, None, "HARNESS"),
        ({}, {}, None, "NONE"),
    ],
)
def test_d5i_first_divergence_is_bounded_and_earliest(
    actual: dict[str, object],
    grade: dict[str, object],
    failure: tuple[str, str] | None,
    expected: str,
) -> None:
    """Turn evidence uses only the accepted first-divergence vocabulary."""
    assert d5._first_divergence(actual, grade, failure) == expected


def test_d5i_dimension_and_correction_evidence_are_explicit() -> None:
    """Correction and safety evidence remain visible instead of inferred away."""
    actual = {
        "changed": False,
        "persisted": True,
        "rendered": True,
        "correction_occurred": True,
        "correction_preservation": {
            "status": "PASS",
            "diagnostic_code": "semantic_contract_incomplete",
            "authorized_paths": ["/sections/0"],
            "before_semantic_projection_sha256": "a" * 64,
            "after_semantic_projection_sha256": "b" * 64,
            "changed_paths": ["/sections/0"],
            "unauthorized_change": False,
            "final_status": "ACCEPTED",
        },
    }
    row = d5._bounded_turn_row(
        {"case_id": "D4-L04", "turn_id": "D4-L04:C01"},
        {"contract": {"kind": "safety"}},
        actual,
        {"status": "PASS", "errors": [], "verifier_requirements": []},
        execution_index=1,
        call_count=1,
        physical_attempt_count=1,
    )
    assert row["first_divergence"] == "NONE"
    assert row["evidence_dimensions"]["safe_negative"] == "PASS"
    assert row["evidence_dimensions"]["mutation"] == "PASS"
    assert row["correction_preservation"]["final_status"] == "ACCEPTED"


def test_d5i_positive_cbl_construction_marks_expected_mutation_as_pass() -> None:
    """A successful construction is an appropriate mutation, not a failure."""
    dimensions = d5._dimension_evidence(
        case={"turn_id": "D4-C01:C01"},
        expected={"contract": {"kind": "construction"}},
        actual={"changed": True, "persisted": True, "rendered": True},
        grade={"status": "PASS", "errors": []},
        first_divergence="NONE",
        observed_failure=None,
    )
    assert dimensions["mutation"] == "PASS"


def test_d5i_positive_las_revision_marks_expected_mutation_as_pass() -> None:
    """A successful revision is an appropriate mutation, not a failure."""
    dimensions = d5._dimension_evidence(
        case={"turn_id": "D4-L01:T1"},
        expected={"contract": {"kind": "revision"}},
        actual={"changed": True, "persisted": True, "rendered": True},
        grade={"status": "PASS", "errors": []},
        first_divergence="NONE",
        observed_failure=None,
    )
    assert dimensions["mutation"] == "PASS"


def test_d5i_safe_negative_without_change_marks_mutation_as_pass() -> None:
    """A safe-negative no-op remains an appropriate mutation result."""
    dimensions = d5._dimension_evidence(
        case={"turn_id": "D4-L03:C01"},
        expected={"contract": {"kind": "safety"}},
        actual={"changed": False, "persisted": True, "rendered": True},
        grade={"status": "PASS", "errors": []},
        first_divergence="NONE",
        observed_failure=None,
    )
    assert dimensions["mutation"] == "PASS"


def test_d5i_unauthorized_mutation_marks_mutation_as_fail() -> None:
    """An explicitly prohibited mutation fails even if other grading passes."""
    dimensions = d5._dimension_evidence(
        case={"turn_id": "D4-L01:T1"},
        expected={"contract": {"kind": "revision"}},
        actual={"changed": True, "persisted": True, "rendered": True},
        grade={
            "status": "FAIL",
            "errors": ["canonical_change_outside_allowed_paths"],
        },
        first_divergence="CORRECTION_PRESERVATION",
        observed_failure=None,
    )
    assert dimensions["mutation"] == "FAIL"


def test_d5i_correction_evidence_is_derived_from_canonical_adapter_observation(
    tmp_path: Path,
) -> None:
    """The reused D4 adapter produces observable G7 correction evidence."""

    class CorrectionSession:
        provider = "deterministic"
        model = "d5i-test-model"

        async def revise(self, *, feedback: str, logfile_path: Path) -> object:
            del feedback
            payload = d4.yaml.safe_load(logfile_path.read_text(encoding="utf-8"))
            payload["document"]["header"]["title"] = "Repaired title"
            logfile_path.write_text(d4.yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            return SimpleNamespace(
                submitted_intent={"correction": True},
                report_facts={
                    "success": True,
                    "changed": True,
                    "apply_status": "persisted",
                    "compilation": {
                        "diagnostics": [
                            {
                                "code": "semantic_contract_incomplete",
                                "stage": "contract",
                            }
                        ],
                        "metrics": {"total_repairs": 1},
                    },
                },
            )

        async def render_logfile_to_file(
            self,
            *,
            logfile_path: Path,
            output_path: Path,
            overwrite: bool,
        ) -> dict[str, object]:
            del logfile_path, overwrite
            output_path.write_bytes(b"deterministic render")
            return {"output_path": str(output_path)}

    harness = _D4SessionHarness.create(tmp_path)
    harness.adapter.session = CorrectionSession()
    case = next(item for item in d4.load_cases(REPO_ROOT) if item["turn_id"] == "D4-L01:T1")
    gold = next(item for item in d4.load_gold(REPO_ROOT)["cases"] if item["turn_id"] == "D4-L01:T1")
    actual = asyncio.run(harness.adapter.execute_turn(case, {}))
    row = d5._bounded_turn_row(
        case,
        {"contract": gold["contract"]},
        actual,
        {"status": "PASS", "errors": [], "verifier_requirements": []},
        execution_index=1,
        call_count=2,
        physical_attempt_count=2,
    )
    evidence = row["correction_preservation"]
    assert evidence["status"] == "OBSERVED"
    assert set(evidence["changed_paths"]) == {
        "/title",
        "/extensions/compatibility/legacy_document/header/title",
    }
    assert set(evidence["authorized_paths"]) == {
        "/title",
        "/extensions/compatibility/legacy_document/header/title",
    }
    assert evidence["unauthorized_change"] is False
    assert evidence["final_status"] == "ACCEPTED"
    assert (
        evidence["before_semantic_projection_sha256"]
        != evidence["after_semantic_projection_sha256"]
    )


def test_d5i_contract_input_and_residual_semantic_failures_are_distinct() -> None:
    """Observed contract diagnostics cannot collapse into residual semantics."""
    base = {
        "canonical_before": {},
        "canonical_after": {},
        "persisted": True,
        "rendered": True,
    }
    contract_row = d5._bounded_turn_row(
        {"case_id": "D4-L01", "turn_id": "D4-L01:T1"},
        {"contract": {"kind": "las"}},
        {
            **base,
            "diagnostics": [{"code": "semantic_contract_incomplete"}],
            "failure_owner": "contract",
        },
        {"status": "FAIL", "errors": ["semantic mismatch"], "verifier_requirements": []},
        execution_index=1,
        call_count=1,
        physical_attempt_count=1,
    )
    residual_row = d5._bounded_turn_row(
        {"case_id": "D4-L01", "turn_id": "D4-L01:T1"},
        {"contract": {"kind": "las"}},
        {**base, "diagnostics": [{"code": "semantic_mismatch"}]},
        {"status": "FAIL", "errors": ["semantic mismatch"], "verifier_requirements": []},
        execution_index=1,
        call_count=1,
        physical_attempt_count=1,
    )
    assert contract_row["scientific_terminal"] == "FAIL / CONTRACT_OR_INPUT"
    assert residual_row["scientific_terminal"] == "FAIL / RESIDUAL_SEMANTIC"


def test_d5i_provider_failure_preserves_provider_terminal_boundary(tmp_path: Path) -> None:
    """A structured provider refusal is inconclusive and never semantically graded."""
    runner = d5.D5CampaignRunner(
        repo_root=REPO_ROOT,
        authorization=_authorization(),
        paths=_paths(tmp_path),
        readiness=_ready(),
        provenance=_provenance(),
    )
    result = asyncio.run(runner.run(_StructuredOutputRejectingAdapter()))
    assert result["scientific_terminal"] == "INCONCLUSIVE / PROVIDER"
    assert result["first_divergence"] == "PROVIDER_OR_STRUCTURED"
    assert result["terminal"]["scientific_terminal"] == "INCONCLUSIVE / PROVIDER"


class _MissingAssetAdapter:
    """Raise a local source error without making a provider-shaped call."""

    async def execute_turn(
        self,
        case: dict[str, object],
        expected: dict[str, object],
    ) -> object:
        del case, expected
        raise OSError("local frozen asset is not provisioned")


def test_d5i_local_asset_failure_is_harness_inconclusive(tmp_path: Path) -> None:
    """Checkout-local asset failures cannot be misreported as provider evidence."""
    runner = d5.D5CampaignRunner(
        repo_root=REPO_ROOT,
        authorization=_authorization(),
        paths=_paths(tmp_path),
        readiness=_ready(),
        provenance=_provenance(),
    )
    result = asyncio.run(runner.run(_MissingAssetAdapter()))
    assert result["scientific_terminal"] == "INCONCLUSIVE / HARNESS"
    assert result["first_divergence"] == "HARNESS"


def test_redaction_rejects_secrets_raw_payloads_and_absolute_paths() -> None:
    """Evidence rejects credentials and unbounded provider material."""
    assert not d5.evidence_is_redacted({"api_key": "secret"})
    assert not d5.evidence_is_redacted({"raw_structured_payload": {"x": 1}})
    assert not d5.evidence_is_redacted({"absolute_model_path": "/srv/model.gguf"})
    assert not d5.evidence_is_redacted({"diagnostic": "Authorization: Bearer secret"})
    assert d5.evidence_is_redacted({"model": d5.EXPECTED_MODEL, "sha256": "a" * 64})


def test_physical_observer_seals_no_response_termination_without_raw_exception() -> None:
    """Five completed calls followed by no response preserve the forensic boundary."""
    observer = d5._PhysicalAttemptObserver()
    rows: list[dict[str, object]] = []
    observer.bind_model_io(rows.append)
    observer.callback = lambda _index: None
    observer.set_active_turn("D4-C01:C01")
    for index in range(1, 6):
        observer.logical_call_started(
            {
                "index": index,
                "generation_role": "section_worker",
                "model": d5.EXPECTED_MODEL,
            }
        )
        request = SimpleNamespace(
            url=SimpleNamespace(path="/v1/chat/completions"),
            content=f'{{"call":{index}}}'.encode(),
        )
        asyncio.run(observer.on_request(request))

        async def aread(body: bytes = b'{"ok":true}') -> bytes:
            return body

        response = SimpleNamespace(request=request, status_code=200, aread=aread)
        asyncio.run(observer.on_response(response))

    observer.logical_call_started(
        {
            "index": 6,
            "generation_role": "section_worker",
            "model": d5.EXPECTED_MODEL,
        }
    )
    request = SimpleNamespace(
        url=SimpleNamespace(path="/v1/chat/completions"),
        content=b'{"bounded":"request"}',
    )
    asyncio.run(observer.on_request(request))
    observer.logical_call_aborted(
        {
            "index": 6,
            "generation_role": "section_worker",
            "model": d5.EXPECTED_MODEL,
            "termination_kind": "provider_request_error",
            "exception_type": "ReadTimeout",
            "exception_module": "httpx",
            "status_code": None,
            "timeout": True,
        }
    )
    assert len([row for row in rows if row["event"] == "physical_response"]) == 5
    termination = next(row for row in rows if row["event"] == "physical_termination")
    assert termination["physical_attempt"] == 1
    assert termination["request_sha256"] == hashlib.sha256(request.content).hexdigest()
    assert termination["timeout"] is True
    assert "bounded" not in str(termination)
    assert all("headers" not in row for row in rows)


def test_campaign_exception_custody_records_primary_context_without_message(tmp_path: Path) -> None:
    """Top-level failure custody identifies outstanding calls without raw text."""
    paths = _paths(tmp_path, "campaign-exception")
    custody = d5.D5CampaignCustody.prepare(
        paths,
        authorization=_authorization(campaign_id="campaign-exception"),
        provenance=_provenance(),
        readiness=_ready().projection,
    )
    custody.record_call_started(
        {
            "event": "logical_call_started",
            "index": 1,
            "generation_role": "section_worker",
            "provider": d5.EXPECTED_PROVIDER,
            "model": d5.EXPECTED_MODEL,
        }
    )
    custody.record_campaign_exception(
        RuntimeError("do not persist this detail"),
        active_turn="D4-C01:C01",
        completed_worker_outcomes=[],
    )
    journal = paths.journal.read_text(encoding="utf-8")
    assert "campaign_exception" in journal
    assert "do not persist this detail" not in journal
    assert '"active_turn":"D4-C01:C01"' in journal
    assert '"outstanding_logical_calls":[{"index":1,"role":"section_worker"}]' in journal


def test_physical_observer_correlates_interleaved_logical_calls_by_context() -> None:
    """Overlapping backend tasks retain their own logical request identities."""
    observer = d5._PhysicalAttemptObserver()
    rows: list[dict[str, object]] = []
    observer.bind_model_io(rows.append)
    observer.callback = lambda _index: None
    observer.set_active_turn("D4-C01:C01")
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    class _InterleavedDelegate:
        async def generate_structured(
            self,
            request: d4.StructuredGenerationRequest,
            *,
            response_model: type[object],
        ) -> d4.StructuredGenerationResult[object]:
            del response_model
            if request.user_prompt == "first":
                first_started.set()
                await release_first.wait()
            else:
                await first_started.wait()
            request_object = SimpleNamespace(
                url=SimpleNamespace(path="/v1/chat/completions"),
                content=request.user_prompt.encode(),
            )
            await observer.on_request(request_object)

            async def aread(body: bytes = b'{"ok":true}') -> bytes:
                return body

            await observer.on_response(
                SimpleNamespace(request=request_object, status_code=200, aread=aread)
            )
            return d4.StructuredGenerationResult(
                value=d4.SemanticPlan(
                    summary=request.user_prompt,
                    report_task={"goal": "diagnostic report"},
                ),
                metrics=d4.ProviderMetrics(),
            )

    backend = d4.CountingBackend(delegate=_InterleavedDelegate())
    backend.call_started = observer.logical_call_started
    backend.call_completed = observer.logical_call_completed

    async def run() -> None:
        first = asyncio.create_task(
            backend.generate_structured(
                d4.StructuredGenerationRequest(
                    system_prompt="system",
                    user_prompt="first",
                    timeout_seconds=10.0,
                    temperature=0.0,
                ),
                response_model=d4.SemanticPlan,
            )
        )
        await first_started.wait()
        second = asyncio.create_task(
            backend.generate_structured(
                d4.StructuredGenerationRequest(
                    system_prompt="system",
                    user_prompt="second",
                    timeout_seconds=10.0,
                    temperature=0.0,
                ),
                response_model=d4.SemanticPlan,
            )
        )
        await second
        release_first.set()
        await first

    asyncio.run(run())
    requests = [row for row in rows if row["event"] == "physical_request"]
    assert [(row["logical_call_index"], row["request_body"]) for row in requests] == [
        (2, "second"),
        (1, "first"),
    ]


def test_secondary_cancellation_cannot_replace_primary_worker_failure(tmp_path: Path) -> None:
    """Both callback orders adjudicate worker failure over sibling cancellation."""
    for order in ("worker-first", "cancel-first"):
        campaign_id = f"secondary-cancellation-{order}"
        paths = _paths(tmp_path, campaign_id)
        custody = d5.D5CampaignCustody.prepare(
            paths,
            authorization=_authorization(campaign_id=campaign_id),
            provenance=_provenance(),
            readiness=_ready().projection,
        )
        custody.record_call_started(
            {
                "event": "logical_call_started",
                "index": 1,
                "generation_role": "section_worker",
                "provider": d5.EXPECTED_PROVIDER,
                "model": d5.EXPECTED_MODEL,
            }
        )
        worker_event = {
            "worker_kind": "section",
            "plan_order": 1,
            "stage": "compile_worker",
            "exception_type": "RuntimeError",
            "exception_module": "builtins",
            "provider_call_in_flight": None,
            "provider_call_state": "UNKNOWN",
        }
        cancellation_event = {
            "index": 1,
            "generation_role": "section_worker",
            "provider": d5.EXPECTED_PROVIDER,
            "model": d5.EXPECTED_MODEL,
            "termination_kind": "cancelled",
            "exception_type": "CancelledError",
            "exception_module": "asyncio.exceptions",
            "status_code": None,
            "timeout": False,
        }

        async def emit_concurrently(
            *,
            current_order: str = order,
            current_custody: d5.D5CampaignCustody = custody,
            current_worker_event: dict[str, object] = worker_event,
            current_cancellation_event: dict[str, object] = cancellation_event,
        ) -> None:
            ready = asyncio.Barrier(2)
            worker_done = asyncio.Event()
            cancellation_done = asyncio.Event()

            async def emit_worker() -> None:
                await ready.wait()
                if current_order == "cancel-first":
                    await cancellation_done.wait()
                current_custody.record_worker_diagnostic(current_worker_event)
                worker_done.set()

            async def emit_cancellation() -> None:
                await ready.wait()
                if current_order == "worker-first":
                    await worker_done.wait()
                current_custody.record_call_aborted(current_cancellation_event)
                cancellation_done.set()

            await asyncio.gather(emit_worker(), emit_cancellation())

        asyncio.run(emit_concurrently())
        custody.finish("INCONCLUSIVE", attribution="TEST", rows=[])
        events = [json.loads(line) for line in paths.journal.read_text().splitlines()]
        adjudication = next(event for event in events if event["event"] == "failure_adjudication")
        assert adjudication["primary"]["failure_kind"] == "worker_exception"
        assert adjudication["secondary"][0]["failure_kind"] == "cancellation"


def test_authorization_binds_campaign_across_runner_instances(tmp_path: Path) -> None:
    """A second runner cannot reuse or rename the consumed authorized campaign."""
    authorization = _authorization()
    paths = _paths(tmp_path)
    custody = d5.D5CampaignCustody.prepare(
        paths,
        authorization=authorization,
        provenance=_provenance(),
        readiness=_ready().projection,
    )
    custody.record_call_started(
        {
            "event": "logical_call_started",
            "index": 1,
            "generation_role": "planner",
            "provider": d5.EXPECTED_PROVIDER,
            "model": d5.EXPECTED_MODEL,
        }
    )
    custody.finish("INCONCLUSIVE", attribution="TEST", rows=[])
    second_paths = _paths(tmp_path, "different-campaign")
    with pytest.raises(d5.D5HarnessError, match="campaign path"):
        d5.D5CampaignCustody.prepare(
            second_paths,
            authorization=authorization,
            provenance=_provenance(),
            readiness=_ready().projection,
        )
    with pytest.raises(d5.D5StaticPreflightError, match="collision"):
        d5.D5CampaignCustody.prepare(
            paths,
            authorization=authorization,
            provenance=_provenance(),
            readiness=_ready().projection,
        )


def test_started_campaign_is_one_shot_and_terminal_is_written_once(tmp_path: Path) -> None:
    """STARTED consumes the campaign and terminal custody cannot be rewritten."""
    paths = _paths(tmp_path)
    custody = d5.D5CampaignCustody.prepare(
        paths,
        authorization=_authorization(),
        provenance=_provenance(),
        readiness=_ready().projection,
    )
    custody.record_call_started(
        {
            "event": "logical_call_started",
            "index": 1,
            "generation_role": "planner",
            "provider": d5.EXPECTED_PROVIDER,
            "model": d5.EXPECTED_MODEL,
        }
    )
    terminal = custody.finish("INCONCLUSIVE", attribution="TEST", rows=[])
    assert terminal["decision"] == "INCONCLUSIVE"
    assert json.loads(paths.terminal.read_text(encoding="utf-8"))["campaign_id"] == "campaign"
    digests = d5.verify_custody_artifacts(paths)
    terminal_payload = json.loads(paths.terminal.read_text(encoding="utf-8"))
    summary_payload = json.loads(paths.summary.read_text(encoding="utf-8"))
    assert terminal_payload["state_snapshot_sha256"] == digests["state_sha256"]
    assert terminal_payload["journal_sha256"] == digests["journal_sha256"]
    assert summary_payload["terminal_sha256"] == digests["terminal_sha256"]
    with pytest.raises(d5.D5HarnessError, match="terminal artifact"):
        custody.finish("PASS", attribution="TEST", rows=[])
    with pytest.raises(d5.D5StaticPreflightError, match="collision"):
        d5.ensure_fresh_namespace(paths)


def test_first_generation_structured_output_rejection_is_inconclusive(tmp_path: Path) -> None:
    """The first measured response-format failure is not semantic model FAIL."""
    runner = d5.D5CampaignRunner(
        repo_root=REPO_ROOT,
        authorization=_authorization(),
        paths=_paths(tmp_path),
        readiness=_ready(),
        provenance=_provenance(),
    )
    result = asyncio.run(runner.run(_StructuredOutputRejectingAdapter()))
    assert result["decision"] == "INCONCLUSIVE"
    assert result["attribution"] == "PROVIDER_BOUNDARY / STRUCTURED_OUTPUT"
    assert result["completed_turns"] == 0
    assert result["logical_generation_calls"] == 1
    assert result["provider_calls"] == result["endpoint_calls"] == result["model_calls"] == 0
    journal = next((_paths(tmp_path).root).glob("*.journal.jsonl"), None)
    assert journal is not None
    assert "replay" not in journal.read_text(encoding="utf-8").casefold()


def test_exhausted_schema_validation_is_provider_structured_failure() -> None:
    """An unrecovered invalid response cannot fall through to host execution."""
    calls = [
        {
            "outcome": "failed",
            "failure_category": "invalid_response",
            "response_reason": "schema_validation",
        }
    ]

    assert d5._classify_logical_call_failure(calls) == (
        "PROVIDER_BOUNDARY / STRUCTURED_OUTPUT",
        "invalid_response",
    )


def test_recovered_schema_validation_is_not_terminal_failure() -> None:
    """A failed attempt followed by success remains a recovered call."""
    calls = [
        {
            "outcome": "failed",
            "failure_category": "invalid_response",
            "response_reason": "schema_validation",
        },
        {"outcome": "completed", "failure_category": None},
    ]

    assert d5._classify_logical_call_failure(calls) is None


@pytest.mark.parametrize(
    ("calls", "expected"),
    [
        (
            [
                {
                    "outcome": "failed",
                    "failure_category": "invalid_response",
                    "response_reason": "schema_validation",
                },
                {"outcome": "failed", "failure_category": "invalid_response"},
            ],
            ("PROVIDER_BOUNDARY / STRUCTURED_OUTPUT", "invalid_response"),
        ),
        (
            [
                {
                    "outcome": "failed",
                    "failure_category": "invalid_response",
                },
                {"outcome": "completed", "failure_category": None},
                {"outcome": "failed", "failure_category": "timeout"},
            ],
            ("PROVIDER_OR_TRANSPORT_RUNTIME", "timeout"),
        ),
        (
            [
                {
                    "outcome": "failed",
                    "failure_category": "invalid_response",
                },
                {"outcome": "completed", "failure_category": None},
                {"outcome": "completed", "failure_category": None},
            ],
            None,
        ),
    ],
)
def test_recovered_structured_failures_do_not_poison_later_terminal_state(
    calls: list[dict[str, object]],
    expected: tuple[str, str] | None,
) -> None:
    """Only the latest unrecovered logical call owns terminal attribution."""
    assert d5._classify_logical_call_failure(calls) == expected


def test_recovered_structured_failure_does_not_override_host_failure() -> None:
    """A later host failure retains host ownership after recovered output errors."""
    calls = [
        {"outcome": "failed", "failure_category": "invalid_response"},
        {"outcome": "completed", "failure_category": None},
        {"outcome": "completed", "failure_category": None},
    ]
    actual = {
        "apply_status": "compile_failed",
        "persisted": False,
        "rendered": False,
        "host_stage_evidence": {"persistence": "NOT_REACHED"},
    }
    grade = {"errors": ["persistence_not_proven"]}
    observed_failure = d5._classify_logical_call_failure(calls)

    assert observed_failure is None
    assert d5.classify_grade_failure(actual, grade) == "HOST_SEMANTIC_APPLICATION"
    assert d5._first_divergence(actual, grade, observed_failure) == "HOST_EXECUTION"


def test_correction_scope_violation_is_semantic_not_host_infrastructure() -> None:
    """A correctly rejected correction remains a residual semantic failure."""
    actual = {
        "worker_diagnostic_code": "worker_correction_scope_violation",
        "normalization_status": "PASS",
        "worker_obligation_status": "FAIL",
        "lowering_status": "NOT_REACHED",
        "apply_status": "compile_failed",
        "persisted": False,
        "rendered": False,
    }
    grade = {"status": "FAIL", "errors": ["persistence_not_proven"]}

    assert d5.classify_grade_failure(actual, grade) is None
    assert d5._first_divergence(actual, grade, None) == "CORRECTION_PRESERVATION"
    row = d5._bounded_turn_row(
        {"case_id": "D4-C01", "turn_id": "D4-C01:C01"},
        {},
        actual,
        grade,
        execution_index=1,
        call_count=6,
        physical_attempt_count=6,
    )
    assert row["failure_category"] is None
    assert row["first_divergence"] == "CORRECTION_PRESERVATION"
    assert row["scientific_terminal"] == "FAIL / RESIDUAL_SEMANTIC"
    assert row["worker_diagnostic_code"] == "worker_correction_scope_violation"


def test_genuine_compile_failure_remains_host_inconclusive() -> None:
    """Unrelated compile failures retain the host/infrastructure boundary."""
    actual = {
        "apply_status": "compile_failed",
        "persisted": False,
        "rendered": False,
    }
    assert d5.classify_grade_failure(actual, {"errors": []}) == ("HOST_SEMANTIC_APPLICATION")
    assert d5._first_divergence(actual, {"errors": []}, None) == "HOST_EXECUTION"


def test_graded_safe_rejection_is_not_host_infrastructure() -> None:
    """A byte-preserving expected rejection does not stop the remaining population."""
    actual = {
        "observed_safe_rejection": True,
        "apply_status": "compile_failed",
        "lowering_status": "FAIL",
        "persisted": False,
        "rendered": False,
        "intent_applied": False,
        "pre_bytes_sha256": "same",
        "post_bytes_sha256": "same",
        "worker_diagnostic_code": "enrichment.section_hint_ambiguous",
    }
    grade = {"status": "PASS", "errors": []}

    assert d5.classify_grade_failure(actual, grade) is None
    assert d5._first_divergence(actual, grade, None) == "NONE"
    row = d5._bounded_turn_row(
        {"case_id": "D4-L02", "turn_id": "D4-L02:T1"},
        {"expected_outcome": "SAFE_ACTIONABLE_FAILURE"},
        actual,
        grade,
        execution_index=6,
        call_count=2,
        physical_attempt_count=2,
    )
    assert row["failure_category"] is None
    assert row["scientific_terminal"] == "PASS"


def test_scientifically_wrong_structured_result_is_fail(tmp_path: Path) -> None:
    """Validly returned but wrong canonical semantics classify as FAIL."""
    runner = d5.D5CampaignRunner(
        repo_root=REPO_ROOT,
        authorization=_authorization(),
        paths=_paths(tmp_path),
        readiness=_ready(),
        provenance=_provenance(),
    )
    result = asyncio.run(runner.run(_WrongSemanticAdapter()))
    assert result["decision"] == "FAIL"
    assert result["attribution"] == "SEMANTIC_CONTRACT"
    assert result["completed_turns"] == 9
    assert all(row["infrastructure_failure"] is False for row in result["rows"])


def test_exception_classification_is_fail_closed() -> None:
    """Production and transport faults cannot become architectural escalation."""
    assert d5._classify_exception(d5.D5ProductionFailure())[0] == "INCONCLUSIVE"
    assert d5._classify_exception(d5.D5TransportFailure())[0] == "INCONCLUSIVE"
    assert d5._classify_exception(d5.D5ProcessInterruption()) == (
        "INCONCLUSIVE",
        "PROCESS_INTERRUPTION",
    )
    assert d5._classify_exception(d5.D5CallCapExceeded())[1] == "CALL_CAP_EXCEEDED"
    assert d5._classify_exception(d5.D5HarnessError())[1] == "EVIDENCE_INTEGRITY"
    assert d5._classify_exception(ValueError("unexpected")) == (
        "INCONCLUSIVE",
        "EXECUTION_INTERNAL_ERROR",
    )


def test_persistence_and_render_failures_are_inconclusive_infrastructure() -> None:
    """D4 infrastructure diagnostics cannot be reported as model semantic FAIL."""
    accepted = {"execution_evidence": {"accepted": True}, "apply_status": "persisted"}
    assert (
        d5.classify_grade_failure(
            accepted,
            {"errors": ["persistence_not_proven"]},
        )
        == "PRODUCTION_OR_INFRASTRUCTURE"
    )
    assert (
        d5.classify_grade_failure(
            accepted,
            {"errors": ["render_not_proven"]},
        )
        == "PRODUCTION_OR_INFRASTRUCTURE"
    )
    rejected = {"execution_evidence": {"accepted": False}, "apply_status": "rejected"}
    assert (
        d5.classify_grade_failure(
            rejected,
            {"errors": ["persistence_not_proven", "render_not_proven"]},
        )
        is None
    )


def test_host_application_failure_precedes_persistence_attribution() -> None:
    """A compile/reconciliation rejection cannot be reported as model semantics."""
    actual = {
        "apply_status": "compile_failed",
        "persisted": False,
        "rendered": False,
        "host_stage_evidence": {"persistence": "NOT_REACHED"},
    }
    assert (
        d5.classify_grade_failure(actual, {"errors": ["persistence_not_proven"]})
        == "HOST_SEMANTIC_APPLICATION"
    )


def test_explicit_host_evidence_distinguishes_render_failure() -> None:
    """Persisted artifacts with a failed render retain the render boundary."""
    actual = {
        "apply_status": "persisted",
        "persisted": True,
        "rendered": False,
        "host_stage_evidence": {"persistence": "PASS", "render": "FAIL"},
    }
    assert d5.classify_grade_failure(actual, {"errors": ["render_not_proven"]}) == "RENDER"


def test_session_evidence_preserves_bounded_host_application_boundary() -> None:
    """D5 evidence retains application state without raw provider material."""
    actual: dict[str, object] = {}
    result = SimpleNamespace(
        submitted_intent=None,
        report_facts={
            "success": False,
            "changed": False,
            "apply_status": "compile_failed",
            "host_stage_evidence": {
                "reconciliation": "NOT_REACHED",
                "persistence": "NOT_REACHED",
                "render": "NOT_REACHED",
            },
            "compilation": {
                "diagnostics": [
                    {"stage": "semantic_worker", "code": "semantic_contract_incomplete"}
                ],
                "workers": [
                    {
                        "kind": "section",
                        "plan_order": 1,
                        "success": False,
                        "diagnostics": [{"code": "semantic_contract_incomplete"}],
                        "stage_evidence": {
                            "normalization": "NOT_REACHED",
                            "worker_obligation": "NOT_REACHED",
                            "semantic_lowering": "NOT_REACHED",
                        },
                    }
                ],
                "metrics": {},
            },
        },
    )

    d4._add_session_evidence(actual, result)

    assert actual["apply_status"] == "compile_failed"
    assert actual["failure_owner"] == "semantic_worker"
    assert actual["worker_diagnostic_code"] == "semantic_contract_incomplete"
    assert actual["normalization_status"] == "NOT_REACHED"
    assert actual["worker_obligation_status"] == "NOT_REACHED"
    assert actual["host_stage_evidence"]["persistence"] == "NOT_REACHED"
    assert d5.classify_grade_failure(actual, {"errors": ["persistence_not_proven"]}) == (
        "HOST_SEMANTIC_APPLICATION"
    )


class _RetryingAdapter:
    """Provider-free adapter exercising integrated logical/physical custody hooks."""

    logical_call_count = 0
    observes_physical_attempts = True

    def __init__(self, retry_count: int) -> None:
        self.retry_count = retry_count
        self._started: Callable[[dict[str, object]], None] | None = None
        self._completed: Callable[[dict[str, object]], None] | None = None
        self._physical: Callable[[int], None] | None = None

    def bind_call_started(self, callback: Callable[[dict[str, object]], None]) -> None:
        self._started = callback

    def bind_call_completed(self, callback: Callable[[dict[str, object]], None]) -> None:
        self._completed = callback

    def bind_physical_attempt(self, callback: Callable[[int], None]) -> None:
        self._physical = callback

    async def execute_turn(
        self,
        case: dict[str, object],
        expected: dict[str, object],
    ) -> dict[str, object]:
        del expected
        self.logical_call_count += 1
        index = self.logical_call_count
        event = {
            "event": "logical_call_started",
            "index": index,
            "generation_role": "planner",
            "provider": d5.EXPECTED_PROVIDER,
            "model": d5.EXPECTED_MODEL,
        }
        assert self._started is not None
        self._started(event)
        assert self._physical is not None
        for _ in range(self.retry_count + 1):
            self._physical(index)
        assert self._completed is not None
        self._completed({**event, "event": "logical_call_completed", "outcome": "completed"})
        return {
            "canonical_before": {},
            "canonical_after": {},
            "persisted": True,
            "rendered": True,
            "verifier": {"status": "PASS", "requirements": []},
            "execution_evidence": {"accepted": True},
            "apply_status": "persisted",
            "case_id": case["case_id"],
        }


def test_integrated_retry_observer_keeps_one_logical_id(tmp_path: Path) -> None:
    """Two SDK retries become three physical attempts on each logical call."""
    runner = d5.D5CampaignRunner(
        repo_root=REPO_ROOT,
        authorization=_authorization(),
        paths=_paths(tmp_path),
        readiness=_ready(),
        provenance=_provenance(),
    )
    result = asyncio.run(runner.run(_RetryingAdapter(retry_count=2)))
    assert result["logical_generation_calls"] == 9
    assert result["physical_generation_attempts"] == 27
    journal = result["custody_digests"]
    assert journal["journal_sha256"]


def test_execute_live_wiring_is_provider_free_with_injected_doubles(tmp_path: Path) -> None:
    """The explicit live command wires readiness and STARTED without network calls."""
    endpoint_calls: list[str] = []
    provider_calls: list[str] = []

    def endpoint_get(url: str, token: str) -> object:
        assert token == "secret-token"
        endpoint_calls.append(url)
        if url == PROJECT_CONFIG.model_catalog_url:
            return {"data": [{"id": d5.EXPECTED_MODEL}]}
        return _props()

    authorization = _authorization(artifact_root=str(tmp_path / "evidence"))
    result = d5.execute_live_campaign(
        repo_root=REPO_ROOT,
        authorization=authorization,
        artifact_root=tmp_path / "evidence",
        endpoint_get=endpoint_get,
        api_key_loader=lambda: "secret-token",
        static_checker=lambda repo, auth, paths: {"status": "PASS"},
        provider_factory=lambda repo, root, token: (
            provider_calls.append(token) or _RetryingAdapter(retry_count=0)
        ),
    )
    assert endpoint_calls == [PROJECT_CONFIG.model_catalog_url, PROJECT_CONFIG.props_url]
    assert provider_calls == ["secret-token"]
    assert result["completed_turns"] == 9
    assert result["terminal"]["authorization_id"] == "auth-test-001"
    assert result["provider_calls"] == result["model_calls"] == 9
    assert result["endpoint_calls"] == 2
    assert result["terminal"]["provider_calls"] == 9


def test_execute_live_rejects_artifact_root_relocation_before_readiness(tmp_path: Path) -> None:
    """One authorization cannot be replayed in a different artifact namespace."""
    authorization = _authorization(artifact_root=str(tmp_path / "authorized"))
    endpoint_calls: list[str] = []
    with pytest.raises(d5.D5StaticPreflightError, match="artifact root"):
        d5.execute_live_campaign(
            repo_root=REPO_ROOT,
            authorization=authorization,
            artifact_root=tmp_path / "different",
            endpoint_get=lambda url, token: endpoint_calls.append(url),
            api_key_loader=lambda: "secret-token",
            static_checker=lambda repo, auth, paths: {"status": "PASS"},
            provider_factory=lambda repo, root, token: _WrongSemanticAdapter(),
        )
    assert endpoint_calls == []


def test_provider_free_nine_turn_rehearsal_uses_canonical_direct_notebook() -> None:
    """Rehearse all nine frozen turns through the accepted canonical adapter."""
    _require_local_d5_sources()
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        root = Path(temporary)
        harness = _D4SessionHarness.create(root)
        runner = d5.D5CampaignRunner(
            repo_root=REPO_ROOT,
            authorization=_authorization(campaign_id="nine-turn"),
            paths=_paths(root, "nine-turn"),
            readiness=_ready(),
            provenance=_provenance(),
        )
        result = asyncio.run(runner.run(harness.adapter))
    assert result["decision"] == "PASS", result
    assert result["completed_turns"] == 9
    assert len(result["rows"]) == 9
    assert all(row["grader_status"] == "PASS" for row in result["rows"])
    assert result["logical_generation_calls"] == 18
    assert result["physical_generation_attempts"] == 18
    assert result["provider_calls"] == result["endpoint_calls"] == result["model_calls"] == 0
    terminal = result["terminal"]
    assert terminal["decision"] == "PASS"
    assert d5.evidence_is_redacted(terminal)


def _live_transport_response_model(name: str) -> type[BaseModel]:
    """Map the real request schema name to the accepted D4 response model."""
    models = {
        d4.SemanticPlan.__name__: d4.SemanticPlan,
        d4.DeliveryReportResponse.__name__: d4.DeliveryReportResponse,
        d4.DeliverySectionResponse.__name__: d4.DeliverySectionResponse,
    }
    return models[name]


def _live_transport_factory(
    *,
    retry_count: int,
    failure_mode: str = "success",
    clients: list[httpx.AsyncClient],
    requests: list[httpx.Request],
) -> Callable[[Callable[[object], Any]], object]:
    """Build an in-memory transport around the real D5 live adapter factory."""
    fixture_backend = _D4SessionBackend(
        planner=_D4PlannerBackend(_D4SessionPlanner(calls=[])),
        report=_D4SessionReportBackend(),
        section=_D4SessionSectionBackend(),
    )
    attempt_number = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_number
        requests.append(request)
        attempt_number += 1
        if failure_mode == "transport" or attempt_number <= retry_count:
            return httpx.Response(
                500,
                json={"error": {"message": "provider-free retry fixture"}},
                request=request,
            )
        if failure_mode == "provider_rejection":
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "refusal": "structured output is not supported",
                            },
                            "finish_reason": "stop",
                        }
                    ]
                },
                request=request,
            )
        payload = json.loads(request.content)
        messages = payload["messages"]
        response_model = _live_transport_response_model(
            payload["response_format"]["json_schema"]["name"]
        )
        generated = await fixture_backend.generate_structured(
            StructuredGenerationRequest(
                system_prompt=str(messages[0]["content"]),
                user_prompt=str(messages[1]["content"]),
                timeout_seconds=float(payload.get("timeout", 10.0)),
                temperature=payload.get("temperature"),
                max_output_tokens=payload.get("max_completion_tokens", payload.get("max_tokens")),
            ),
            response_model=response_model,
        )
        content = generated.value.model_dump_json()
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": content,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
            request=request,
        )

    def factory(observer: Callable[[object], Any]) -> object:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            event_hooks={"request": [observer]},
        )
        clients.append(client)
        return client

    return factory


def _live_planner_request() -> StructuredGenerationRequest:
    """Build the smallest real planner request accepted by the D4 backend."""
    return StructuredGenerationRequest(
        system_prompt="You are the WellPlot semantic planner.",
        user_prompt="Context:\n"
        + json.dumps(
            {
                "request": "Rename this report to Formation Integrity Review.",
                "mode": "revise",
                "current_document_summary": {},
                "source_summary": {},
            }
        ),
        timeout_seconds=10.0,
        temperature=0.0,
        max_output_tokens=None,
    )


@pytest.mark.parametrize("retry_count", [0, 1, 2])
def test_real_live_adapter_transport_retries_keep_one_logical_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, retry_count: int
) -> None:
    """The real OpenAI/client/backend/notebook path counts transport retries."""
    del tmp_path
    from openai import _base_client

    monkeypatch.setattr(_base_client, "get_platform", lambda: "Linux")
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        server_root = Path(temporary)
        clients: list[httpx.AsyncClient] = []
        requests: list[httpx.Request] = []
        adapter = d5.create_live_adapter(
            repo_root=server_root,
            artifact_root=server_root / "live",
            api_key="provider-free-test-token",
            project_config=PROJECT_CONFIG,
            require_thinking_control=True,
            request_options=d5._thinking_control_options(),
            http_client_factory=_live_transport_factory(
                retry_count=retry_count,
                clients=clients,
                requests=requests,
            ),
        )
        client = adapter.inner.session.session.compiler.dependencies.planner.backend.delegate.client
        client._platform = "Linux"
        started: list[dict[str, Any]] = []
        completed: list[dict[str, Any]] = []
        physical: list[int] = []
        adapter.bind_call_started(started.append)
        adapter.bind_call_completed(completed.append)
        adapter.bind_physical_attempt(physical.append)
        try:
            backend = adapter.inner.session.session.compiler.dependencies.planner.backend
            result = asyncio.run(
                backend.generate_structured(
                    _live_planner_request(),
                    response_model=d4.SemanticPlan,
                )
            )
        finally:
            asyncio.run(clients[0].aclose())
        assert result.value.report_task is not None
        assert started[0]["index"] == 1
        assert completed[0]["index"] == 1
        assert physical[: retry_count + 1] == [1] * (retry_count + 1)
        assert len(requests) == retry_count + 1
        assert str(requests[0].url).startswith(PROJECT_CONFIG.openai_compat_base_url)
        for request in requests:
            assert json.loads(request.content)["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.parametrize("generation_role", ["planner", "report_worker", "section_worker"])
def test_live_wire_control_is_exact_for_each_generation_role_and_retry(
    monkeypatch: pytest.MonkeyPatch,
    generation_role: str,
) -> None:
    """Every measured role and SDK retry carries the exact thinking control."""
    from openai import _base_client

    monkeypatch.setattr(_base_client, "get_platform", lambda: "Linux")
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        clients: list[httpx.AsyncClient] = []
        requests: list[httpx.Request] = []
        adapter = d5.create_live_adapter(
            repo_root=Path(temporary),
            artifact_root=Path(temporary) / "live",
            api_key="provider-free-test-token",
            project_config=PROJECT_CONFIG,
            require_thinking_control=True,
            request_options=d5._thinking_control_options(),
            http_client_factory=_live_transport_factory(
                retry_count=2,
                clients=clients,
                requests=requests,
            ),
        )
        client = adapter.inner.session.session.compiler.dependencies.planner.backend.delegate.client
        client._platform = "Linux"
        physical: list[int] = []
        adapter.bind_physical_attempt(physical.append)
        backend = adapter.inner.session.session.compiler.dependencies.planner.backend.delegate
        request = _live_planner_request()
        if generation_role != "planner":
            request = replace(request, temperature=None)
        adapter.observer.logical_call_started(
            {
                "index": 1,
                "generation_role": generation_role,
                "model": d5.EXPECTED_MODEL,
            }
        )
        try:
            asyncio.run(
                backend.generate_structured(
                    request,
                    response_model=d4.SemanticPlan,
                )
            )
        finally:
            asyncio.run(clients[0].aclose())
        assert len(requests) == 3
        assert physical == [1, 1, 1]
        assert all(
            json.loads(request.content)["chat_template_kwargs"] == {"enable_thinking": False}
            for request in requests
        )


def test_live_adapter_rejects_thinking_control_override() -> None:
    """A caller cannot silently replace the frozen request-level control."""
    with pytest.raises(d5.D5StaticPreflightError, match="request control drifted"):
        d5.create_live_adapter(
            repo_root=REPO_ROOT,
            artifact_root=REPO_ROOT / "workspace" / "test-live",
            api_key="provider-free-test-token",
            project_config=PROJECT_CONFIG,
            require_thinking_control=True,
            request_options={"chat_template_kwargs": {"enable_thinking": True}},
        )
    with pytest.raises(d5.D5StaticPreflightError, match="request control is missing"):
        d5.create_live_adapter(
            repo_root=REPO_ROOT,
            artifact_root=REPO_ROOT / "workspace" / "test-live",
            api_key="provider-free-test-token",
            project_config=PROJECT_CONFIG,
            require_thinking_control=True,
            request_options=None,
        )


def test_real_live_transport_physical_ceiling_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The integrated observer rejects a third attempt at a two-attempt cap."""
    del tmp_path
    from openai import _base_client

    monkeypatch.setattr(_base_client, "get_platform", lambda: "Linux")
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        server_root = Path(temporary)
        clients: list[httpx.AsyncClient] = []
        requests: list[httpx.Request] = []
        adapter = d5.create_live_adapter(
            repo_root=server_root,
            artifact_root=server_root / "live",
            api_key="provider-free-test-token",
            project_config=PROJECT_CONFIG,
            require_thinking_control=True,
            request_options=d5._thinking_control_options(),
            http_client_factory=_live_transport_factory(
                retry_count=2,
                clients=clients,
                requests=requests,
            ),
        )
        client = adapter.inner.session.session.compiler.dependencies.planner.backend.delegate.client
        client._platform = "Linux"
        ledger = d5.D5LogicalCallLedger(max_physical_attempts=2)
        observed: list[int] = []
        adapter.bind_call_started(ledger.record_d4_event)
        adapter.bind_call_completed(ledger.record_d4_event)

        def record_attempt(index: int) -> None:
            observed.append(index)
            ledger.physical_attempt(index)

        adapter.bind_physical_attempt(record_attempt)
        try:
            backend = adapter.inner.session.session.compiler.dependencies.planner.backend
            with pytest.raises(ProviderRequestError):
                asyncio.run(
                    backend.generate_structured(
                        _live_planner_request(),
                        response_model=d4.SemanticPlan,
                    )
                )
        finally:
            asyncio.run(clients[0].aclose())
        assert observed[:2] == [1, 1]
        assert observed[2:] == [1]
        assert ledger.physical_attempts == 2
        assert len(requests) == 2


def test_real_live_provider_rejection_is_inconclusive_without_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real provider refusal becomes structured-output INCONCLUSIVE evidence."""
    _require_local_d5_sources()
    from openai import _base_client

    monkeypatch.setattr(_base_client, "get_platform", lambda: "Linux")
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        root = Path(temporary)
        artifact_root = root / "live"
        clients: list[httpx.AsyncClient] = []
        requests: list[httpx.Request] = []
        adapter = d5.create_live_adapter(
            repo_root=REPO_ROOT,
            artifact_root=artifact_root,
            api_key="provider-free-test-token",
            project_config=PROJECT_CONFIG,
            require_thinking_control=True,
            request_options=d5._thinking_control_options(),
            http_client_factory=_live_transport_factory(
                retry_count=0,
                failure_mode="provider_rejection",
                clients=clients,
                requests=requests,
            ),
        )
        client = adapter.inner.session.session.compiler.dependencies.planner.backend.delegate.client
        client._platform = "Linux"
        authorization = _authorization(
            campaign_id="provider-rejection",
            artifact_root=str(artifact_root),
        )
        runner = d5.D5CampaignRunner(
            repo_root=REPO_ROOT,
            authorization=authorization,
            paths=d5.EvidencePaths(artifact_root, authorization.campaign_id),
            readiness=_ready(live=True),
            provenance=_provenance(),
        )
        try:
            result = asyncio.run(runner.run(adapter))
        finally:
            asyncio.run(clients[0].aclose())

        assert result["decision"] == "INCONCLUSIVE"
        assert result["attribution"] == "PROVIDER_BOUNDARY / STRUCTURED_OUTPUT"
        assert result["completed_turns"] == 1
        assert result["rows"][0]["failure_category"] == "provider_rejected"
        assert result["rows"][0]["grader_status"] == "INCONCLUSIVE"
        assert len(requests) == 1
        journal = next(artifact_root.glob("*.journal.jsonl"))
        assert "replay" not in journal.read_text(encoding="utf-8").casefold()


def test_real_live_transport_exhaustion_is_not_semantic_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exhausted real transport retries become provider-runtime INCONCLUSIVE."""
    _require_local_d5_sources()
    from openai import _base_client

    monkeypatch.setattr(_base_client, "get_platform", lambda: "Linux")
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        root = Path(temporary)
        artifact_root = root / "live"
        clients: list[httpx.AsyncClient] = []
        requests: list[httpx.Request] = []
        adapter = d5.create_live_adapter(
            repo_root=REPO_ROOT,
            artifact_root=artifact_root,
            api_key="provider-free-test-token",
            project_config=PROJECT_CONFIG,
            require_thinking_control=True,
            request_options=d5._thinking_control_options(),
            http_client_factory=_live_transport_factory(
                retry_count=0,
                failure_mode="transport",
                clients=clients,
                requests=requests,
            ),
        )
        client = adapter.inner.session.session.compiler.dependencies.planner.backend.delegate.client
        client._platform = "Linux"
        authorization = _authorization(
            campaign_id="transport-exhaustion",
            artifact_root=str(artifact_root),
        )
        runner = d5.D5CampaignRunner(
            repo_root=REPO_ROOT,
            authorization=authorization,
            paths=d5.EvidencePaths(artifact_root, authorization.campaign_id),
            readiness=_ready(live=True),
            provenance=_provenance(),
        )
        try:
            result = asyncio.run(runner.run(adapter))
        finally:
            asyncio.run(clients[0].aclose())

        assert result["decision"] == "INCONCLUSIVE"
        assert result["attribution"] == "PROVIDER_OR_TRANSPORT_RUNTIME"
        assert result["rows"][0]["failure_category"] == "transport"
        assert result["rows"][0]["grader_status"] == "INCONCLUSIVE"
        assert result["physical_generation_attempts"] == 3
        assert len(requests) == 3


def _smoke_provider_factory(
    *,
    response_mode: str = "ready",
    retry_count: int = 0,
    requests: list[httpx.Request] | None = None,
    clients: list[httpx.AsyncClient] | None = None,
) -> Callable[[Path, Path, str], object]:
    """Build the canonical adapter with an injected, non-network transport."""
    requests = requests if requests is not None else []
    clients = clients if clients is not None else []

    def factory(observer: object) -> httpx.AsyncClient:
        attempts = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            requests.append(request)
            assert request.url.path == "/v1/chat/completions"
            attempts += 1
            if attempts <= retry_count:
                return httpx.Response(500, request=request)
            content = (
                '{"status":"NOT_READY"}' if response_mode == "invalid" else '{"status":"READY"}'
            )
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {},
                },
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            event_hooks={
                "request": [observer.on_request],
                "response": [observer.on_response],
            },
        )
        client._platform = "Linux"
        clients.append(client)
        return client

    def build(repo_root: Path, artifact_root: Path, token: str) -> object:
        adapter = d5.create_live_adapter(
            repo_root=repo_root,
            artifact_root=artifact_root,
            api_key=token,
            project_config=PROJECT_CONFIG,
            request_options=d5._thinking_control_options(),
            require_thinking_control=True,
            http_client_factory=factory,
        )
        client = adapter.inner.session.session.compiler.dependencies.planner.backend.delegate.client
        client._platform = "Linux"
        return adapter

    return build


def _execute_provider_free_smoke(
    tmp_path: Path,
    *,
    response_mode: str = "ready",
    retry_count: int = 0,
) -> tuple[dict[str, Any], list[httpx.Request], list[httpx.AsyncClient]]:
    """Execute the dedicated smoke contract with all network activity injected."""
    artifact_root = tmp_path / "smoke"
    requests: list[httpx.Request] = []
    clients: list[httpx.AsyncClient] = []
    authorization = _authorization(
        campaign_id="d5-5j-smoke-provider-free",
        artifact_root=str(artifact_root),
    )

    def endpoint_get(url: str, token: str) -> object:
        assert token == "provider-free-token"
        if url == PROJECT_CONFIG.model_catalog_url:
            return {"data": [{"id": d5.EXPECTED_MODEL}]}
        assert url == PROJECT_CONFIG.props_url
        return _props()

    result = d5.execute_live_smoke(
        repo_root=REPO_ROOT,
        authorization=authorization,
        artifact_root=artifact_root,
        endpoint_get=endpoint_get,
        api_key_loader=lambda: "provider-free-token",
        static_checker=lambda repo, checked, paths: {
            "status": "PASS",
            "scientific_population_loaded": False,
            "scientific_campaign_started": False,
        },
        provider_factory=_smoke_provider_factory(
            response_mode=response_mode,
            retry_count=retry_count,
            requests=requests,
            clients=clients,
        ),
    )
    return result, requests, clients


def test_provider_free_smoke_uses_canonical_adapter_without_scientific_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One smoke call uses existing provider wiring and never starts D5 cases."""
    monkeypatch.setattr(
        d5.D5CampaignRunner,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("scientific campaign runner must not execute in smoke mode")
        ),
    )
    monkeypatch.setattr(
        d4,
        "load_cases",
        lambda *args: (_ for _ in ()).throw(AssertionError("scientific cases loaded")),
    )
    monkeypatch.setattr(
        d4,
        "load_gold",
        lambda *args: (_ for _ in ()).throw(AssertionError("scientific gold loaded")),
    )
    result, requests, clients = _execute_provider_free_smoke(tmp_path)
    try:
        assert result["status"] == "SMOKE_PASS"
        assert result["terminal"]["logical_generation_calls"] == 1
        assert result["terminal"]["physical_generation_attempts"] == 1
        assert result["terminal"]["scientific_population_loaded"] is False
        assert result["terminal"]["scientific_campaign_started"] is False
        assert len(requests) == 1
        body = json.loads(requests[0].content)
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        assert body["response_format"]["type"] == "json_schema"
        assert body["messages"][0]["content"] == d5.SMOKE_SYSTEM_PROMPT
        assert body["messages"][1]["content"] == d5.SMOKE_USER_PROMPT
        model_io_path = tmp_path / "smoke" / "d5-5j-smoke-provider-free.model-io.jsonl"
        rows = [json.loads(line) for line in model_io_path.read_text(encoding="utf-8").splitlines()]
        assert len([row for row in rows if row["event"] == "physical_request"]) == 1
        assert len([row for row in rows if row["event"] == "physical_response"]) == 1
        assert len([row for row in rows if row["event"] == "logical_call_result"]) == 1
    finally:
        for client in clients:
            asyncio.run(client.aclose())


def test_provider_free_smoke_counts_sdk_retries_as_physical_attempts(tmp_path: Path) -> None:
    """One logical smoke call permits three physical attempts and then passes."""
    result, requests, clients = _execute_provider_free_smoke(tmp_path, retry_count=2)
    try:
        assert result["status"] == "SMOKE_PASS"
        assert result["terminal"]["logical_generation_calls"] == 1
        assert result["terminal"]["physical_generation_attempts"] == 3
        assert len(requests) == 3
    finally:
        for client in clients:
            asyncio.run(client.aclose())


def test_provider_free_smoke_invalid_structured_response_is_inconclusive(tmp_path: Path) -> None:
    """A bounded provider response failure is not reported as harness success."""
    result, requests, clients = _execute_provider_free_smoke(tmp_path, response_mode="invalid")
    try:
        assert result["status"] == "SMOKE_PROVIDER_INCONCLUSIVE"
        assert result["terminal"]["logical_generation_calls"] == 1
        assert result["terminal"]["physical_generation_attempts"] == 1
        assert len(requests) == 1
    finally:
        for client in clients:
            asyncio.run(client.aclose())


@pytest.mark.parametrize(
    ("endpoint_failure", "expected_calls"),
    [("credential", 0), ("first_get", 1), ("second_get", 2)],
)
def test_smoke_readiness_failure_is_pre_start_and_truthful(
    tmp_path: Path,
    endpoint_failure: str,
    expected_calls: int,
) -> None:
    """Readiness failures seal without creating SMOKE_STARTED custody."""
    artifact_root = tmp_path / f"pre-smoke-{endpoint_failure}"
    authorization = _authorization(
        campaign_id=f"d5-5j-smoke-{endpoint_failure}",
        artifact_root=str(artifact_root),
    )

    def endpoint_get(url: str, token: str) -> object:
        del token
        if endpoint_failure == "first_get":
            raise d5.D5ReadinessError("endpoint_authentication_failed", 1)
        if endpoint_failure == "second_get" and url == PROJECT_CONFIG.props_url:
            raise d5.D5ReadinessError("endpoint_server_error", 2)
        if url == PROJECT_CONFIG.model_catalog_url:
            return {"data": [{"id": d5.EXPECTED_MODEL}]}
        return _props()

    result = d5.execute_live_smoke(
        repo_root=REPO_ROOT,
        authorization=authorization,
        artifact_root=artifact_root,
        endpoint_get=endpoint_get,
        api_key_loader=(lambda: "") if endpoint_failure == "credential" else (lambda: "token"),
        static_checker=lambda repo, checked, paths: {"status": "PASS"},
        provider_factory=lambda repo, root, token: _WrongSemanticAdapter(),
    )
    assert result["status"] == "SMOKE_NOT_READY"
    assert result["terminal"]["endpoint_calls"] == expected_calls
    state = json.loads(
        (artifact_root / f"{authorization.campaign_id}.state.json").read_text(encoding="utf-8")
    )
    journal = (artifact_root / f"{authorization.campaign_id}.journal.jsonl").read_text(
        encoding="utf-8"
    )
    assert state["status"] == "SMOKE_TERMINAL"
    assert "SMOKE_STARTED" not in journal
    assert "smoke_not_started" in journal


def test_smoke_provider_construction_failure_is_pre_start(tmp_path: Path) -> None:
    """Provider construction failure cannot create SMOKE_STARTED custody."""
    artifact_root = tmp_path / "provider-construction"
    authorization = _authorization(
        campaign_id="d5-5j-smoke-provider-construction",
        artifact_root=str(artifact_root),
    )

    def fail_provider(repo: Path, root: Path, token: str) -> object:
        del repo, root, token
        raise RuntimeError("provider unavailable")

    result = d5.execute_live_smoke(
        repo_root=REPO_ROOT,
        authorization=authorization,
        artifact_root=artifact_root,
        endpoint_get=lambda url, token: (
            {"data": [{"id": d5.EXPECTED_MODEL}]}
            if url == PROJECT_CONFIG.model_catalog_url
            else _props()
        ),
        api_key_loader=lambda: "provider-free-token",
        static_checker=lambda repo, checked, paths: {"status": "PASS"},
        provider_factory=fail_provider,
    )

    assert result["status"] == "SMOKE_NOT_READY"
    assert result["terminal"]["endpoint_calls"] == 2
    journal = (artifact_root / f"{authorization.campaign_id}.journal.jsonl").read_text(
        encoding="utf-8"
    )
    assert "SMOKE_STARTED" not in journal


def test_smoke_custody_captures_planner_replay_and_zero_worker_diagnostics(
    tmp_path: Path,
) -> None:
    """Opt-in capture retains replay inputs and graph diagnostics without raw I/O."""
    authorization = _authorization(
        campaign_id="planner-observability",
        artifact_root=str(tmp_path / "observability"),
    )
    paths = d5.EvidencePaths(tmp_path / "observability", authorization.campaign_id)
    custody = d5.D5SmokeCustody.start(
        paths,
        authorization=authorization,
        static_preflight={"status": "PASS"},
        readiness=_ready().projection,
        endpoint_calls=2,
        smoke_kind="planner_observability",
        source_asset_identities=({"asset_id": "fixture-source", "sha256": "a" * 64},),
    )

    custody.record_planner_observability(
        {
            "event": "PLANNER_GENERATION_PASS",
            "attempt": 1,
            "response_schema": "_PlannerWirePlan",
            "validated_response": {"summary": "Bounded plan", "section_tasks": []},
        }
    )
    custody.record_planner_observability(
        {
            "event": "REQUEST_COMPILATION_PASS",
            "result": {"status": "EXTRACTION_COMPLETE", "requirements": []},
        }
    )
    custody.record_planner_observability(
        {
            "event": "PLANNER_CONTEXT",
            "context": {
                "request": "Build the requested section.",
                "source_summary": {"sources": [{"path": "/private/assets/demo.dlis"}]},
            },
        }
    )
    custody.record_planner_observability(
        {
            "event": "COMPILED_REQUIREMENT_ATTACHMENT_FAIL",
            "exception_type": "PlannerSemanticError",
            "code": "unexpected_scope_assignment",
            "safe_message": "Planner assigned an undeclared scope.",
        }
    )
    custody.record_bounded_model_io(
        {
            "event": "physical_request",
            "logical_call_index": 1,
            "role": "planner",
            "request_sha256": "b" * 64,
            "request_body": "raw request body must not be retained",
        }
    )
    result = CodeModeCompileResult(
        success=False,
        diagnostics=(
            CompileDiagnostic(
                stage="planner",
                code="planner_semantic_failure",
                message="Bounded planner failure.",
            ),
        ),
        workers=(),
        metrics=CompileMetrics(
            worker_count=0,
            successful_workers=0,
            failed_workers=0,
            total_program_chars=0,
            total_ast_nodes=0,
            total_statements=0,
            total_calls=0,
            total_repairs=0,
            total_loop_iterations=0,
            total_created_objects=0,
            max_nesting_depth=0,
        ),
    )
    custody.record_compile_result(result)

    wire = json.loads(paths.planner_wire.read_text(encoding="utf-8").splitlines()[0])
    compilation = json.loads(paths.request_compilation.read_text(encoding="utf-8"))
    context = json.loads(paths.planner_context.read_text(encoding="utf-8"))
    trace = [
        json.loads(line) for line in paths.stage_trace.read_text(encoding="utf-8").splitlines()
    ]
    compile_result = json.loads(paths.compile_result.read_text(encoding="utf-8"))

    assert wire["validated_response"]["summary"] == "Bounded plan"
    assert compilation["result"]["status"] == "EXTRACTION_COMPLETE"
    assert context["source_summary"]["sources"][0]["path"] == "demo.dlis"
    assert context["source_asset_identities"][0]["sha256"] == "a" * 64
    assert trace[0]["event"] == "COMPILED_REQUIREMENT_ATTACHMENT_FAIL"
    assert compile_result["diagnostics"][0]["code"] == "planner_semantic_failure"
    assert compile_result["workers"] == []
    assert compile_result["metrics"]["worker_count"] == 0
    assert compile_result["merged_intent_present"] is False
    model_io = paths.model_io.read_text(encoding="utf-8")
    assert "request_sha256" in model_io
    assert "raw request body" not in model_io
    serialized = "".join(
        path.read_text(encoding="utf-8") for path in paths.all_paths() if path.is_file()
    )
    assert "/private/assets" not in serialized
    assert "raw_provider_response" not in serialized
    terminal = custody.finish("SMOKE_HARNESS_FAIL", reason="provider-free-custody-test")
    assert terminal["observability_artifacts"][paths.planner_wire.name] == d5._sha256_file(
        paths.planner_wire
    )


def test_smoke_compile_result_records_successful_merged_intent_presence(tmp_path: Path) -> None:
    """Compile custody reports the public merged-intent field without storing it."""
    authorization = _authorization(
        campaign_id="compile-success-observability",
        artifact_root=str(tmp_path / "compile-success"),
    )
    paths = d5.EvidencePaths(tmp_path / "compile-success", authorization.campaign_id)
    custody = d5.D5SmokeCustody.start(
        paths,
        authorization=authorization,
        static_preflight={"status": "PASS"},
        readiness=_ready().projection,
        endpoint_calls=2,
        smoke_kind="planner_observability",
    )
    result = CodeModeCompileResult(
        success=True,
        merged_intent=AuthoringDocumentIntent(),
        workers=(CompileWorkerEvidence(kind="section", plan_order=0, success=True),),
        metrics=CompileMetrics(
            worker_count=1,
            successful_workers=1,
            failed_workers=0,
            total_program_chars=0,
            total_ast_nodes=0,
            total_statements=0,
            total_calls=0,
            total_repairs=0,
            total_loop_iterations=0,
            total_created_objects=0,
            max_nesting_depth=0,
        ),
    )

    custody.record_compile_result(result)

    payload = json.loads(paths.compile_result.read_text(encoding="utf-8"))
    assert payload["merged_intent_present"] is True
    assert "merged_intent" not in payload
    assert "intent" not in payload
    custody.finish("SMOKE_HARNESS_FAIL", reason="provider-free-custody-test")


def test_binding_smoke_wires_canonical_calls_and_bounded_model_io(tmp_path: Path) -> None:
    """Binding custody records canonical roles and cannot retain raw model I/O."""
    authorization = _authorization(
        campaign_id="binding-smoke-observability",
        artifact_root=str(tmp_path / "binding-smoke"),
    )
    paths = d5.EvidencePaths(tmp_path / "binding-smoke", authorization.campaign_id)
    custody = d5.D5SmokeCustody.start(
        paths,
        authorization=authorization,
        static_preflight={"status": "PASS"},
        readiness=_ready().projection,
        endpoint_calls=2,
        smoke_kind=d5.SMOKE_BINDING_KIND,
    )

    class CallbackAdapter:
        def bind_call_started(self, callback: Callable[[dict[str, Any]], None]) -> None:
            self.started = callback

        def bind_call_completed(self, callback: Callable[[dict[str, Any]], None]) -> None:
            self.completed = callback

        def bind_call_aborted(self, callback: Callable[[dict[str, Any]], None]) -> None:
            self.aborted = callback

        def bind_physical_attempt(self, callback: Callable[[int], None]) -> None:
            self.physical_attempt = callback

        def bind_model_io(self, callback: Callable[[dict[str, Any]], None]) -> None:
            self.model_io = callback

        def set_active_turn(self, turn_id: str) -> None:
            self.turn_id = turn_id

    inner = CallbackAdapter()
    observer = d5._PhysicalAttemptObserver()
    adapter = d5._ObservedLiveAdapter(inner, observer)
    custody.bind_binding_smoke_observability(adapter)

    for index, role in ((1, "planner"), (2, "section_worker")):
        inner.started(
            {
                "event": "logical_call_started",
                "index": index,
                "generation_role": role,
                "provider": d5.EXPECTED_PROVIDER,
                "model": d5.EXPECTED_MODEL,
            }
        )
        observer.callback(index)
        inner.completed(
            {
                "event": "logical_call_completed",
                "index": index,
                "generation_role": role,
                "outcome": "success",
                "provider": d5.EXPECTED_PROVIDER,
                "model": d5.EXPECTED_MODEL,
            }
        )

    observer.model_io_callback(
        {
            "event": "physical_request",
            "turn_id": observer.active_turn_id,
            "logical_call_index": 1,
            "role": "planner",
            "physical_attempt": 1,
            "request_sha256": "a" * 64,
            "request_body": "private request body",
            "request_json": {"prompt": "private request"},
            "response_body": "private response body",
            "response_json": {"token": "private response"},
            "headers": {"Authorization": "Bearer private-secret"},
            "authorization": "Bearer private-secret",
            "api_key": "private-secret",
        }
    )
    terminal = custody.finish("SMOKE_PASS")

    journal = [json.loads(line) for line in paths.journal.read_text(encoding="utf-8").splitlines()]
    calls = [row for row in journal if row["event"] == "logical_call_started"]
    assert [(row["logical_call_index"], row["generation_role"]) for row in calls] == [
        (1, "planner"),
        (2, "section_worker"),
    ]
    assert observer.active_turn_id == d5.SMOKE_BINDING_TURN_ID
    assert terminal["logical_generation_calls"] == 2
    assert terminal["provider_calls"] == terminal["model_calls"] == 2
    assert terminal["physical_generation_attempts"] == 2
    assert terminal["logical_calls_by_role"] == {"planner": 1, "section_worker": 1}

    model_io = paths.model_io.read_text(encoding="utf-8")
    assert '"request_sha256"' in model_io
    for forbidden in (
        "request_body",
        "request_json",
        "response_body",
        "response_json",
        "Authorization",
        '"authorization"',
        '"api_key"',
        "private-secret",
        "private request",
        "private response",
    ):
        assert forbidden not in model_io
    serialized = "".join(
        path.read_text(encoding="utf-8") for path in paths.all_paths() if path.is_file()
    )
    for forbidden in (
        '"request_body"',
        '"request_json"',
        '"response_body"',
        '"response_json"',
        '"Authorization"',
        '"authorization"',
        '"api_key"',
        "private-secret",
    ):
        assert forbidden not in serialized


def test_binding_smoke_ledger_enforces_role_and_per_call_attempt_caps() -> None:
    """Binding mode permits planner/section calls but rejects other roles/caps."""
    ledger = d5.D5SmokeCallLedger(mode="binding_compile")
    calls = (
        (1, "planner"),
        (2, "planner"),
        (3, "section_worker"),
        (4, "section_worker"),
    )
    for index, role in calls:
        ledger.record_canonical_call_started(index, role)
    with pytest.raises(d5.D5CallCapExceeded):
        ledger.record_canonical_call_started(5, "section_worker")

    report_ledger = d5.D5SmokeCallLedger(mode="binding_compile")
    with pytest.raises(d5.D5CallCapExceeded):
        report_ledger.record_canonical_call_started(1, "report_worker")

    planner_ledger = d5.D5SmokeCallLedger(mode="binding_compile")
    planner_ledger.record_canonical_call_started(1, "planner")
    planner_ledger.record_canonical_call_started(2, "planner")
    with pytest.raises(d5.D5CallCapExceeded):
        planner_ledger.record_canonical_call_started(3, "planner")

    section_ledger = d5.D5SmokeCallLedger(mode="binding_compile")
    section_ledger.record_canonical_call_started(1, "section_worker")
    section_ledger.record_canonical_call_started(2, "section_worker")
    with pytest.raises(d5.D5CallCapExceeded):
        section_ledger.record_canonical_call_started(3, "section_worker")

    for index in range(1, 5):
        for _ in range(3):
            ledger.physical_attempt(index)
    assert ledger.physical_attempts == 12
    with pytest.raises(d5.D5CallCapExceeded, match="attempt 4"):
        ledger.physical_attempt(1)


def test_smoke_ledger_rejects_second_logical_and_fourth_physical_call() -> None:
    """Smoke caps fail before a second logical or fourth physical delegation."""
    ledger = d5.D5SmokeCallLedger()
    assert ledger.reserve() == 1
    with pytest.raises(d5.D5CallCapExceeded, match="logical call 2"):
        ledger.reserve()
    for _ in range(3):
        ledger.physical_attempt(1)
    with pytest.raises(d5.D5CallCapExceeded, match="physical attempt 4"):
        ledger.physical_attempt(1)
