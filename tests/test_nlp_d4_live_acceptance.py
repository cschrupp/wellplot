"""Provider-free tests for the D4 live-acceptance harness."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pydantic import BaseModel
from scripts import nlp_d4_live_acceptance as d4
from tests._mcp_fixtures import REPO_ROOT

from wellplot.agent.providers.base import (
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


class _Value(BaseModel):
    value: str = "ok"


class _Backend:
    """Provider-free backend that records delegation without raw payloads."""

    def __init__(self, *, program_text: str = "report = wp.report()") -> None:
        self.calls = 0
        self.program_text = program_text

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[_Value],
    ) -> StructuredGenerationResult[_Value]:
        del request, response_model
        self.calls += 1
        return StructuredGenerationResult(
            value=_Value(),
            metrics=ProviderMetrics(input_tokens=2, output_tokens=3, total_tokens=5),
        )

    async def generate_program(
        self,
        request: ProgramGenerationRequest,
    ) -> ProgramGenerationResult:
        del request
        self.calls += 1
        return ProgramGenerationResult(
            text=self.program_text,
            metrics=ProviderMetrics(input_tokens=2, output_tokens=3, total_tokens=5),
        )


def _structured_request() -> StructuredGenerationRequest:
    return StructuredGenerationRequest(
        system_prompt="system",
        user_prompt="user",
        timeout_seconds=120.0,
        temperature=0.0,
        max_output_tokens=None,
    )


def _program_request() -> ProgramGenerationRequest:
    return ProgramGenerationRequest(
        system_prompt="system",
        user_prompt="user",
        timeout_seconds=120.0,
        temperature=None,
        max_output_tokens=None,
    )


def test_population_hashes_and_canonical_seed_are_frozen() -> None:
    """Require the exact nine-turn schedule and canonical seed."""
    cases = d4.load_cases(REPO_ROOT)
    gold = d4.load_gold(REPO_ROOT)
    assert len(cases) == 9
    assert gold["canonical_las_seed"]["name"] == "D4 LAS Acceptance Seed"
    assert [case["turn_id"] for case in cases] == [
        "D4-C01:C01",
        "D4-L01:T1",
        "D4-L01:T2",
        "D4-L01:T3",
        "D4-L01:T4",
        "D4-L02:T1",
        "D4-L02:T2",
        "D4-L03:C01",
        "D4-L04:C01",
    ]
    assert all(case["request_sha256"] == d4.sha256_text(case["request"]) for case in cases)


def test_d4_requests_are_not_the_d3_request() -> None:
    """Reject reuse of the accepted D3 request text."""
    cases = d4.load_cases(REPO_ROOT)
    d3_request = (REPO_ROOT / "tests/fixtures/agentic_cbl/frozen_prompt.txt").read_text()
    d3_request = d3_request.replace(
        "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis",
        "CBL_Main.dlis",
    ).replace(
        "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis",
        "CBL_Repeat.dlis",
    )
    d3_hash = d4.sha256_text(d3_request)
    assert all(case["request_sha256"] != d3_hash for case in cases)


def test_source_preflight_authenticates_real_las() -> None:
    """Authenticate the external LAS source when it is available locally."""
    try:
        result = d4.preflight_las_source(REPO_ROOT)
    except d4.PreflightError as error:
        pytest.skip(str(error))
    assert result.size == d4.SOURCE_SIZE
    assert result.sha256 == d4.SOURCE_SHA256
    assert result.required_channels_present is True
    assert result.forbidden_channels_absent is True
    assert {"GR", "CALI", "ILD", "ILM", "MSFL", "NPHI"}.issubset(result.channel_inventory)
    assert "RT" not in result.channel_inventory


def test_openai_retry_policy_is_provider_free() -> None:
    """Inspect the SDK retry contract without constructing a client."""
    evidence = d4.inspect_openai_retry_policy()
    assert evidence["version"] == "2.34.0"
    assert evidence["max_retries"] == 2
    assert evidence["physical_http_attempt_upper_bound"] == 135


def test_counting_backend_preserves_controls_and_records_bounded_metadata() -> None:
    """Record logical calls without retaining provider payloads."""
    delegate = _Backend()
    backend = d4.CountingBackend(delegate=delegate)

    async def run() -> None:
        await backend.generate_structured(_structured_request(), response_model=_Value)
        await backend.generate_program(_program_request())

    asyncio.run(run())
    assert delegate.calls == 2
    assert [call.operation for call in backend.calls] == ["structured", "program"]
    assert backend.calls[0].metrics == {
        "input_tokens": 2,
        "output_tokens": 3,
        "total_tokens": 5,
        "latency_ms": None,
    }
    assert not hasattr(backend.calls[0], "raw_provider_response")
    assert not hasattr(backend.calls[1], "raw_generated_program")


def test_call_46_is_rejected_before_delegation() -> None:
    """Reject the first call beyond the frozen logical-call ceiling."""
    delegate = _Backend()
    backend = d4.CountingBackend(delegate=delegate)

    async def run() -> None:
        for _ in range(d4.MAX_LOGICAL_CALLS):
            await backend.generate_structured(_structured_request(), response_model=_Value)
        with pytest.raises(d4.CallCapExceeded):
            await backend.generate_structured(_structured_request(), response_model=_Value)

    asyncio.run(run())
    assert delegate.calls == d4.MAX_LOGICAL_CALLS
    assert len(backend.calls) == d4.MAX_LOGICAL_CALLS


def test_campaign_state_is_durable_before_credentials() -> None:
    """Write STARTED state before invoking credential construction."""
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        state_path = directory / "state.json"
        journal_path = directory / "journal.jsonl"
        events: list[str] = []

        def preflight() -> dict[str, str]:
            events.append("preflight")
            return {"current_checkout": "a" * 40}

        def credentials() -> object:
            events.append("credentials")
            assert state_path.is_file()
            return object()

        state, _ = d4.start_campaign(
            state_path=state_path,
            journal_path=journal_path,
            preflight=preflight,
            credential_factory=credentials,
        )
        assert events == ["preflight", "credentials"]
        assert state["status"] == "STARTED"
        assert json.loads(state_path.read_text())["status"] == "STARTED"


def test_existing_campaign_artifacts_block_resume() -> None:
    """Reject both empty and non-empty previous campaign artifacts."""
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        state_path = directory / "state.json"
        journal_path = directory / "journal.jsonl"
        state_path.write_text("", encoding="utf-8")
        with pytest.raises(d4.PreflightError, match="already exist"):
            d4.start_campaign(
                state_path=state_path,
                journal_path=journal_path,
                preflight=lambda: {"current_checkout": "a" * 40},
                credential_factory=lambda: pytest.fail("credentials accessed"),
            )


def test_evidence_redaction_rejects_secrets_and_raw_material() -> None:
    """Reject credentials and raw generation content in evidence."""
    assert d4.evidence_is_redacted({"case_id": "D4-L01", "metrics": {"total": 3}})
    assert not d4.evidence_is_redacted({"api_key": "secret"})
    assert not d4.evidence_is_redacted({"text": "Authorization: Bearer secret"})
    assert not d4.evidence_is_redacted({"raw_generated_program": "report = wp.report()"})


def test_terminal_decision_precedence_is_frozen() -> None:
    """Keep incomplete infrastructure separate from semantic failure."""
    passed = [{"grader_status": "PASS"} for _ in range(9)]
    assert d4.derive_terminal_decision(passed) == "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_PASSED"
    failed = [*passed[:-1], {"grader_status": "FAIL"}]
    assert d4.derive_terminal_decision(failed) == "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_FAILED"
    incomplete = passed[:-1]
    assert d4.derive_terminal_decision(incomplete) == "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_INCONCLUSIVE"
    infra = [*passed[:-1], {"grader_status": "PASS", "infrastructure_failure": True}]
    assert d4.derive_terminal_decision(infra) == "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_INCONCLUSIVE"


def test_turn_grader_requires_zero_mutation_for_safe_failures() -> None:
    """Require byte identity and actionable diagnostics for safe failure."""
    expected = {
        "turn_id": "D4-L03:C01",
        "expected_outcome": "SAFE_ACTIONABLE_FAILURE",
    }
    safe = {
        "outcome": "SAFE_ACTIONABLE_FAILURE",
        "changed": False,
        "pre_bytes_sha256": "a",
        "post_bytes_sha256": "a",
        "diagnostic_code": "enrichment.source_missing",
    }
    assert d4.grade_turn(safe, expected)["status"] == "PASS"
    unsafe = {**safe, "post_bytes_sha256": "b"}
    assert d4.grade_turn(unsafe, expected)["status"] == "FAIL"
