"""Provider-free tests for the D5-4 live qualification boundary."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from scripts import nlp_d4_live_acceptance as d4
from scripts import nlp_d5_live_semantic_qualification as d5
from tests.test_nlp_d4_live_acceptance import _D4SessionHarness

REPO_ROOT = Path(__file__).resolve().parents[1]


def _props() -> dict[str, object]:
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
        "chat_template": "qwen3",
        "gguf_byte_identity": "NOT_AVAILABLE",
    }


def _authorization(
    *, thinking_off: bool = True, campaign_id: str = "campaign"
) -> d5.D5Authorization:
    """Build an external-style authorization for injected readiness tests."""
    props = _props()
    defaults = props["default_generation_settings"]
    assert isinstance(defaults, dict)
    return d5.D5Authorization(
        implementation_checkpoint="synthetic-checkpoint",
        authorization_id="auth-test-001",
        campaign_id=campaign_id,
        endpoint_identity={
            "model_catalog": [d5.EXPECTED_MODEL],
            "model_path_basename": "qwen3.6-35b-a3b.gguf",
            "model_path_fingerprint_sha256": d4.sha256_text("/srv/models/qwen3.6-35b-a3b.gguf"),
            "context_size": 32768,
            "build_info": "llama.cpp provider-free test build",
            "total_slots": 1,
            "chat_template": "qwen3",
            "runtime_defaults_sha256": d5._sha256_json(defaults),
            "structured_output_contract": "json_schema",
            "gguf_byte_identity": "NOT_AVAILABLE",
        },
        minimum_context_size=16384,
        runtime_defaults_sha256=d5._sha256_json(defaults),
        thinking_off=thinking_off,
    )


def _ready() -> d5.D5OperationalReadiness:
    """Build already-qualified readiness without endpoint activity."""
    projection = d5.D5ReadinessProjection(
        model_catalog=(d5.EXPECTED_MODEL,),
        model_path_basename="qwen3.6-35b-a3b.gguf",
        model_path_fingerprint_sha256="a" * 64,
        context_size=32768,
        build_info="test build",
        total_slots=1,
        chat_template="qwen3",
        runtime_defaults_sha256="b" * 64,
        thinking_off=True,
        structured_output_contract="json_schema",
    )
    return d5.D5OperationalReadiness(
        projection=projection,
        endpoint_calls=("/v1/models", "/props"),
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

    async def execute_turn(
        self,
        case: dict[str, object],
        expected: dict[str, object],
    ) -> dict[str, object]:
        del case, expected
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
            api_key_loader=lambda: "secret-token",
            endpoint_get=endpoint_get,
            static_preflight={"status": "FAIL"},
        )
    assert endpoint_calls == []


def test_two_get_readiness_order_and_sanitized_projection() -> None:
    """Readiness performs exactly two ordered observations and no probe."""
    calls: list[tuple[str, str]] = []

    def endpoint_get(url: str, token: str) -> object:
        calls.append((url, token))
        if url == d5.MODEL_CATALOG_URL:
            return {"data": [{"id": d5.EXPECTED_MODEL}]}
        return _props()

    result = d5.prepare_readiness(
        authorization=_authorization(),
        api_key_loader=lambda: "secret-token",
        endpoint_get=endpoint_get,
        static_preflight={"status": "PASS"},
    )
    assert [url for url, _ in calls] == [d5.MODEL_CATALOG_URL, d5.PROPS_URL]
    assert all(token == "secret-token" for _, token in calls)
    assert result.endpoint_calls == ("/v1/models", "/props")
    sanitized = json.dumps(result.projection.as_dict(), sort_keys=True)
    assert "secret-token" not in sanitized
    assert "/srv/models" not in sanitized
    assert result.provider_calls == result.model_calls == 0


def test_readiness_rejects_thinking_on_without_generation_probe() -> None:
    """Thinking-off is a runtime precondition, not a request-level probe."""
    calls: list[str] = []

    def endpoint_get(url: str, token: str) -> object:
        del token
        calls.append(url)
        if url == d5.MODEL_CATALOG_URL:
            return {"data": [{"id": d5.EXPECTED_MODEL}]}
        return _props()

    with pytest.raises(d5.D5ReadinessError, match="thinking_off_not_established") as raised:
        d5.prepare_readiness(
            authorization=_authorization(thinking_off=False),
            api_key_loader=lambda: "secret-token",
            endpoint_get=endpoint_get,
            static_preflight={"status": "PASS"},
        )
    assert raised.value.endpoint_calls == 2
    assert calls == [d5.MODEL_CATALOG_URL, d5.PROPS_URL]


def test_credential_failure_is_retryable_before_endpoint_observation() -> None:
    """Credential failure does not consume campaign custody or call an endpoint."""
    calls: list[str] = []

    with pytest.raises(d5.D5ReadinessError, match="credential_unavailable"):
        d5.prepare_readiness(
            authorization=_authorization(),
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
        if url == d5.MODEL_CATALOG_URL:
            return {"data": [{"id": "wrong-model"}]}
        return _props()

    with pytest.raises(d5.D5ReadinessError, match="endpoint_identity_mismatch") as raised:
        d5.prepare_readiness(
            authorization=_authorization(),
            api_key_loader=lambda: "secret-token",
            endpoint_get=endpoint_get,
            static_preflight={"status": "PASS"},
        )
    assert raised.value.endpoint_calls == 1
    assert calls == [d5.MODEL_CATALOG_URL]


def test_runtime_defaults_drift_is_not_ready() -> None:
    """Omitted decoder controls do not permit unapproved server-default drift."""
    authorization = _authorization()
    calls: list[str] = []

    def endpoint_get(url: str, token: str) -> object:
        del token
        calls.append(url)
        if url == d5.MODEL_CATALOG_URL:
            return {"data": [{"id": d5.EXPECTED_MODEL}]}
        payload = _props()
        generation = payload["default_generation_settings"]
        assert isinstance(generation, dict)
        generation["top_p"] = 0.9
        return payload

    with pytest.raises(d5.D5ReadinessError, match="runtime_defaults_mismatch"):
        d5.prepare_readiness(
            authorization=authorization,
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


def test_redaction_rejects_secrets_raw_payloads_and_absolute_paths() -> None:
    """Evidence rejects credentials and unbounded provider material."""
    assert not d5.evidence_is_redacted({"api_key": "secret"})
    assert not d5.evidence_is_redacted({"raw_structured_payload": {"x": 1}})
    assert not d5.evidence_is_redacted({"absolute_model_path": "/srv/model.gguf"})
    assert not d5.evidence_is_redacted({"diagnostic": "Authorization: Bearer secret"})
    assert d5.evidence_is_redacted({"model": d5.EXPECTED_MODEL, "sha256": "a" * 64})


def test_authorization_binds_campaign_across_runner_instances(tmp_path: Path) -> None:
    """A second runner cannot reuse or rename the consumed authorized campaign."""
    authorization = _authorization()
    paths = _paths(tmp_path)
    custody = d5.D5CampaignCustody.start(
        paths,
        authorization=authorization,
        provenance=_provenance(),
        readiness=_ready().projection,
    )
    custody.finish("INCONCLUSIVE", attribution="TEST", rows=[])
    second_paths = _paths(tmp_path, "different-campaign")
    with pytest.raises(d5.D5HarnessError, match="campaign path"):
        d5.D5CampaignCustody.start(
            second_paths,
            authorization=authorization,
            provenance=_provenance(),
            readiness=_ready().projection,
        )
    with pytest.raises(d5.D5StaticPreflightError, match="collision"):
        d5.D5CampaignCustody.start(
            paths,
            authorization=authorization,
            provenance=_provenance(),
            readiness=_ready().projection,
        )


def test_started_campaign_is_one_shot_and_terminal_is_written_once(tmp_path: Path) -> None:
    """STARTED consumes the campaign and terminal custody cannot be rewritten."""
    paths = _paths(tmp_path)
    custody = d5.D5CampaignCustody.start(
        paths,
        authorization=_authorization(),
        provenance=_provenance(),
        readiness=_ready().projection,
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
        if url == d5.MODEL_CATALOG_URL:
            return {"data": [{"id": d5.EXPECTED_MODEL}]}
        return _props()

    result = d5.execute_live_campaign(
        repo_root=REPO_ROOT,
        authorization=_authorization(),
        artifact_root=tmp_path / "evidence",
        endpoint_get=endpoint_get,
        api_key_loader=lambda: "secret-token",
        static_checker=lambda repo, auth, paths: {"status": "PASS"},
        provider_factory=lambda repo, root, token: (
            provider_calls.append(token) or _WrongSemanticAdapter()
        ),
    )
    assert endpoint_calls == [d5.MODEL_CATALOG_URL, d5.PROPS_URL]
    assert provider_calls == ["secret-token"]
    assert result["completed_turns"] == 9
    assert result["terminal"]["authorization_id"] == "auth-test-001"


def test_provider_free_nine_turn_rehearsal_uses_canonical_direct_notebook() -> None:
    """Rehearse all nine frozen turns through the accepted canonical adapter."""
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
