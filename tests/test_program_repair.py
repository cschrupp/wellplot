"""Tests for the bounded CM-34 program repair coordinator."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from wellplot.agent.code_mode.repair import (
    ProgramRepairCoordinator,
    ProgramRepairFormatFailure,
    ProgramRepairResult,
    ProgramRepairStopReason,
)
from wellplot.agent.providers.base import (
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
)
from wellplot.authoring_program.models import ProgramDiagnostic, ProgramMetrics


@dataclass
class _FakeBackend:
    """Sequence-backed provider-neutral backend for coordinator tests."""

    outcomes: list[object] = field(default_factory=list)
    requests: list[ProgramGenerationRequest] = field(default_factory=list)

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Record one request and return or raise its configured outcome."""
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _diagnostic(*, code: str = "program.policy_error", secret: str = "") -> ProgramDiagnostic:
    """Build one compact known failure diagnostic."""
    return ProgramDiagnostic(
        stage="policy",
        code=code,
        message=f"Use a normal track. {secret}".strip(),
        remediation_hint="Choose a compatible track.",
    )


def _result(text: str) -> ProgramGenerationResult:
    """Build one provider result without semantic validation."""
    return ProgramGenerationResult(text=text, metrics=ProviderMetrics(total_tokens=4))


def _run(coroutine: object) -> object:
    """Run one coordinator coroutine without an async pytest dependency."""
    return asyncio.run(coroutine)


def _repair(
    backend: _FakeBackend,
    diagnostic: ProgramDiagnostic | None,
    **overrides: object,
) -> object:
    """Run one coordinator request with compact fixture context."""
    values: dict[str, object] = {
        "semantic_task": "Add one compatible track.",
        "sdk_docs": "track.normal accepts width_mm.",
        "previous_program": "track = wp.section('main').track('gr')",
        "diagnostic": diagnostic,
        "timeout_seconds": 5.0,
    }
    values.update(overrides)
    return _run(ProgramRepairCoordinator(backend).repair(**values))


def test_no_diagnostic_means_no_repair_call() -> None:
    """A coordinator invoked without a known failure does nothing."""
    backend = _FakeBackend(outcomes=[_result("unused")])

    result = _repair(backend, None)

    assert result.stop_reason is ProgramRepairStopReason.NOT_REQUIRED
    assert result.repair_count == 0
    assert result.generation_call_count == 0
    assert result.metrics.program_repairs == 0
    assert backend.requests == []


def test_ordinary_diagnostic_gets_one_repair_and_returns_candidate() -> None:
    """A known kernel failure receives exactly one ordinary repair call."""
    backend = _FakeBackend(outcomes=[_result("candidate source")])

    result = _repair(backend, _diagnostic())

    assert result.stop_reason is ProgramRepairStopReason.REPAIRED
    assert result.source == "candidate source"
    assert result.repair_count == 1
    assert result.generation_call_count == 1
    assert result.metrics.program_repairs == 1


def test_repair_prompt_contains_only_the_compact_allowed_context() -> None:
    """Repair prompts exclude document state, raw errors, and conversation history."""
    backend = _FakeBackend(outcomes=[_result("candidate source")])
    diagnostic = _diagnostic(secret="diagnostic detail")

    _repair(backend, diagnostic)

    prompt = backend.requests[0].user_prompt
    assert "Semantic task:\nAdd one compatible track." in prompt
    assert "Relevant SDK documentation:\ntrack.normal accepts width_mm." in prompt
    assert "previous_program" in prompt
    assert '"code":"program.policy_error"' in prompt
    assert "UNRELATED_DOCUMENT_SECRET" not in prompt
    assert "raw provider exception" not in prompt
    assert "diagnostic detail" in prompt


def test_repaired_candidate_is_returned_without_semantic_revalidation() -> None:
    """CM-34 returns provider text and leaves policy/dry-run validation to workers."""
    backend = _FakeBackend(outcomes=[_result("not policy validated here")])

    result = _repair(backend, _diagnostic())

    assert result.stop_reason is ProgramRepairStopReason.REPAIRED
    assert result.source == "not policy validated here"


def test_first_format_failure_allows_exactly_one_second_call() -> None:
    """Only the explicit format signal can unlock the second repair pass."""
    format_diagnostic = _diagnostic(code="program.format_error")
    backend = _FakeBackend(
        outcomes=[
            ProgramRepairFormatFailure(format_diagnostic),
            _result("second candidate"),
        ]
    )

    result = _repair(backend, _diagnostic())

    assert result.stop_reason is ProgramRepairStopReason.SECOND_FORMAT_REPAIR_SUCCEEDED
    assert result.source == "second candidate"
    assert result.repair_count == 2
    assert result.generation_call_count == 2
    assert len(backend.requests) == 2


def test_second_format_failure_stops_at_two_calls() -> None:
    """A second format failure reaches the absolute repair limit."""
    first = ProgramRepairFormatFailure(_diagnostic(code="program.format_error"))
    second = ProgramRepairFormatFailure(_diagnostic(code="program.format_error_2"))
    backend = _FakeBackend(outcomes=[first, second, _result("must not run")])

    result = _repair(backend, _diagnostic())

    assert result.stop_reason is ProgramRepairStopReason.REPAIR_LIMIT_REACHED
    assert result.source is None
    assert result.repair_count == 2
    assert len(backend.requests) == 2


def test_format_second_pass_can_be_disabled() -> None:
    """The coordinator can enforce the ordinary one-repair limit."""
    backend = _FakeBackend(
        outcomes=[ProgramRepairFormatFailure(_diagnostic(code="program.format_error"))]
    )

    result = _run(
        ProgramRepairCoordinator(backend, allow_format_second_pass=False).repair(
            semantic_task="Add one compatible track.",
            sdk_docs="track.normal accepts width_mm.",
            previous_program="track = wp.section('main').track('gr')",
            diagnostic=_diagnostic(),
            timeout_seconds=5.0,
        )
    )

    assert result.stop_reason is ProgramRepairStopReason.REPAIR_LIMIT_REACHED
    assert result.repair_count == 1
    assert len(backend.requests) == 1


@pytest.mark.parametrize(
    "error",
    [
        ProviderRequestError(ProviderFailureCategory.TIMEOUT, "safe timeout"),
        ProviderRequestError(ProviderFailureCategory.TRANSPORT, "safe transport"),
        ProviderRequestError(ProviderFailureCategory.AUTHENTICATION, "safe auth"),
        ProviderRequestError(ProviderFailureCategory.RATE_LIMIT, "safe rate"),
        ProviderRequestError(ProviderFailureCategory.CONFIGURATION, "safe config"),
        ProviderRequestError(ProviderFailureCategory.PROVIDER_REJECTED, "safe refusal"),
        ProviderRequestError(ProviderFailureCategory.INVALID_RESPONSE, "safe invalid"),
    ],
)
def test_provider_failures_stop_after_one_call_without_retry(error: ProviderRequestError) -> None:
    """Provider failures are never treated as second-pass format failures."""
    backend = _FakeBackend(outcomes=[error, _result("must not run")])

    result = _repair(backend, _diagnostic())

    assert result.stop_reason is ProgramRepairStopReason.PROVIDER_FAILURE
    assert result.repair_count == 1
    assert len(backend.requests) == 1
    assert result.diagnostics[0].message == error.safe_message
    assert "safe" in result.diagnostics[0].message


def test_unexpected_generation_failure_is_redacted_and_not_retried() -> None:
    """Unexpected backend exceptions stop without exposing their contents."""
    backend = _FakeBackend(outcomes=[RuntimeError("secret backend detail")])

    result = _repair(backend, _diagnostic())

    assert result.stop_reason is ProgramRepairStopReason.NONREPAIRABLE_GENERATION_FAILURE
    assert len(backend.requests) == 1
    assert "secret backend detail" not in result.model_dump_json()


def test_result_serialization_is_stable_and_metrics_match_count() -> None:
    """Result JSON exposes enum values and aligned repair metrics."""
    backend = _FakeBackend(outcomes=[_result("candidate source")])

    result = _repair(backend, _diagnostic())
    payload = result.model_dump(mode="json")

    assert payload["stop_reason"] == "repaired"
    assert payload["repair_count"] == 1
    assert payload["generation_call_count"] == 1
    assert payload["metrics"]["program_repairs"] == 1


def test_result_rejects_inconsistent_repair_metrics() -> None:
    """The durable result cannot report counts that disagree with metrics."""
    with pytest.raises(ValueError, match="program_repairs"):
        ProgramRepairResult(
            repair_count=1,
            generation_call_count=1,
            stop_reason=ProgramRepairStopReason.REPAIRED,
            source="candidate source",
            metrics=ProgramMetrics(program_repairs=0),
        )
