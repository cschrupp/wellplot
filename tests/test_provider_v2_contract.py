"""CM-30 tests for the provider-neutral asynchronous generation contract."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


class _SemanticPlan(BaseModel):
    """Recorded structured response used by the provider contract test."""

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1)


@dataclass
class _RecordedBackend:
    """Fake backend implementing the protocol without inheriting from it."""

    structured_payload: object = field(default_factory=lambda: {"objective": "make a plot"})
    program_text: str = "wp.report(title='Demo')"
    structured_requests: list[StructuredGenerationRequest] = field(default_factory=list)
    program_requests: list[ProgramGenerationRequest] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[_SemanticPlan],
    ) -> StructuredGenerationResult[_SemanticPlan]:
        """Validate the recorded payload through the supplied response model."""
        self.structured_requests.append(request)
        try:
            value = response_model.model_validate(self.structured_payload)
        except ValidationError as exc:
            raise ProviderRequestError(
                ProviderFailureCategory.VALIDATION,
                "The provider returned an invalid structured response.",
            ) from exc
        return StructuredGenerationResult(
            value=value,
            metrics=ProviderMetrics(input_tokens=8, output_tokens=4, total_tokens=12),
        )

    async def generate_program(
        self,
        request: ProgramGenerationRequest,
    ) -> ProgramGenerationResult:
        """Return recorded source text unchanged with per-call measurements."""
        self.program_requests.append(request)
        return ProgramGenerationResult(
            text=self.program_text,
            metrics=ProviderMetrics(latency_ms=12.5),
        )


async def _run_structured(backend: ModelBackendProtocol) -> StructuredGenerationResult:
    """Exercise structured generation through the protocol type only."""
    return await backend.generate_structured(
        StructuredGenerationRequest(
            system_prompt="You are a planner.",
            user_prompt="Plan a small plot.",
            timeout_seconds=3.0,
            temperature=0.0,
            max_output_tokens=100,
        ),
        response_model=_SemanticPlan,
    )


def test_fake_backend_validates_structured_payload_and_returns_metrics() -> None:
    """Structured generation returns the supplied model type and metrics."""
    backend = _RecordedBackend()
    result = asyncio.run(_run_structured(backend))

    assert isinstance(result.value, _SemanticPlan)
    assert result.value.objective == "make a plot"
    assert result.metrics.public_metadata() == {
        "input_tokens": 8,
        "output_tokens": 4,
        "total_tokens": 12,
        "latency_ms": None,
    }
    assert backend.structured_requests[0].user_prompt == "Plan a small plot."


def test_fake_backend_returns_plain_program_text_and_metrics() -> None:
    """Program generation returns source text unchanged and performs no parsing."""
    backend = _RecordedBackend(program_text="```python\nwp.report(title='Demo')\n```")
    request = ProgramGenerationRequest(
        system_prompt="Write a program.",
        user_prompt="Create a report.",
        timeout_seconds=4.0,
        max_output_tokens=200,
    )

    result = asyncio.run(backend.generate_program(request))

    assert result.text == "```python\nwp.report(title='Demo')\n```"
    assert result.metrics.public_metadata() == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "latency_ms": 12.5,
    }
    assert backend.program_requests == [request]


def test_invalid_structured_payload_uses_stable_validation_error() -> None:
    """A bad recorded object becomes a typed provider validation failure."""
    backend = _RecordedBackend(structured_payload={"objective": 42})

    with pytest.raises(ProviderRequestError) as caught:
        asyncio.run(_run_structured(backend))

    error = caught.value
    assert error.category is ProviderFailureCategory.VALIDATION
    assert error.retryable is False
    assert error.public_metadata() == {
        "category": "validation",
        "safe_message": "The provider returned an invalid structured response.",
        "retryable": False,
        "status_code": None,
    }


def test_provider_errors_are_redacted_and_retryability_is_deterministic() -> None:
    """Public error forms cannot expose an underlying secret-looking failure."""
    secret = "sk-provider-secret-value"
    error = ProviderRequestError(
        ProviderFailureCategory.TIMEOUT,
        "The provider request timed out.",
        status_code=504,
    )

    public_json = json.dumps(error.public_metadata(), sort_keys=True)
    assert error.retryable is True
    assert secret not in str(error)
    assert secret not in repr(error)
    assert secret not in public_json
    assert error.public_metadata() == {
        "category": "timeout",
        "safe_message": "The provider request timed out.",
        "retryable": True,
        "status_code": 504,
    }


def test_provider_request_models_reject_invalid_limits() -> None:
    """The provider-neutral request boundary rejects invalid timeout and limits."""
    with pytest.raises(ValueError, match="timeout_seconds"):
        StructuredGenerationRequest(
            system_prompt="planner",
            user_prompt="request",
            timeout_seconds=0,
        )
    with pytest.raises(ValueError, match="max_output_tokens"):
        ProgramGenerationRequest(
            system_prompt="writer",
            user_prompt="request",
            timeout_seconds=1,
            max_output_tokens=0,
        )


def test_provider_metrics_reject_negative_values() -> None:
    """Metrics accept unavailable values but reject impossible negatives."""
    with pytest.raises(ValueError, match="input_tokens"):
        ProviderMetrics(input_tokens=-1)
    with pytest.raises(ValueError, match="latency_ms"):
        ProviderMetrics(latency_ms=-0.1)
