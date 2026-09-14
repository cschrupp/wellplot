"""Tests for the CM-31 native OpenAI structured transport."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

from wellplot.agent.providers.base import (
    ProviderFailureCategory,
    ProviderRequestError,
    StructuredGenerationRequest,
)
from wellplot.agent.providers.openai_v2 import OpenAIStructuredBackend


class _Plan(BaseModel):
    """Structured response used by the fake native parser."""

    title: str


class _FakeResponses:
    """Minimal async Responses resource for transport tests."""

    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class _FakeClient:
    """Injected client exposing one fake Responses resource."""

    def __init__(self, responses: _FakeResponses) -> None:
        self.responses = responses


def _request(**overrides: object) -> StructuredGenerationRequest:
    """Build a valid request with optional test overrides."""
    values: dict[str, object] = {
        "system_prompt": "Return the semantic plan.",
        "user_prompt": "Build the plot.",
        "timeout_seconds": 17.5,
    }
    values.update(overrides)
    return StructuredGenerationRequest(**values)


def _response(
    parsed: object = None,
    usage: object = None,
    output: object = None,
) -> SimpleNamespace:
    """Build the response fields consumed by the adapter."""
    return SimpleNamespace(output_parsed=parsed, usage=usage, output=output or [])


def _run(coroutine: object) -> object:
    """Run one adapter coroutine without a pytest async dependency."""
    return asyncio.run(coroutine)


def test_structured_call_uses_native_parse_once_and_preserves_model_type() -> None:
    """Forward one native parse call and preserve the requested model type."""
    responses = _FakeResponses(
        response=_response(
            parsed=_Plan(title="Quicklook"),
            usage=SimpleNamespace(input_tokens=11, output_tokens=7, total_tokens=18),
        )
    )
    backend = OpenAIStructuredBackend(model="gpt-test", client=_FakeClient(responses))

    result = _run(backend.generate_structured(_request(), response_model=_Plan))

    assert isinstance(result.value, _Plan)
    assert result.value.title == "Quicklook"
    assert len(responses.calls) == 1
    assert responses.calls[0]["model"] == "gpt-test"
    assert responses.calls[0]["instructions"] == "Return the semantic plan."
    assert responses.calls[0]["input"] == "Build the plot."
    assert responses.calls[0]["text_format"] is _Plan
    assert responses.calls[0]["timeout"] == 17.5
    assert "tools" not in responses.calls[0]
    assert result.metrics.public_metadata()["input_tokens"] == 11
    assert result.metrics.public_metadata()["output_tokens"] == 7
    assert result.metrics.public_metadata()["total_tokens"] == 18
    assert result.metrics.latency_ms is not None


def test_optional_generation_settings_are_not_invented() -> None:
    """Omit optional SDK settings when the provider-neutral request omits them."""
    responses = _FakeResponses(response=_response(parsed=_Plan(title="Quicklook")))
    backend = OpenAIStructuredBackend(model="gpt-test", client=_FakeClient(responses))

    _run(backend.generate_structured(_request(), response_model=_Plan))

    assert "temperature" not in responses.calls[0]
    assert "max_output_tokens" not in responses.calls[0]


def test_reported_usage_fields_remain_unavailable_when_omitted() -> None:
    """Keep unreported usage fields as unavailable rather than inferred values."""
    responses = _FakeResponses(
        response=_response(
            parsed=_Plan(title="Quicklook"),
            usage=SimpleNamespace(input_tokens=11),
        )
    )
    backend = OpenAIStructuredBackend(model="gpt-test", client=_FakeClient(responses))

    result = _run(backend.generate_structured(_request(), response_model=_Plan))

    assert result.metrics.input_tokens == 11
    assert result.metrics.output_tokens is None
    assert result.metrics.total_tokens is None


def test_native_model_type_and_optional_settings_are_forwarded() -> None:
    """Forward explicitly requested optional generation settings."""
    responses = _FakeResponses(response=_response(parsed=_Plan(title="Quicklook")))
    backend = OpenAIStructuredBackend(model="gpt-test", client=_FakeClient(responses))

    _run(
        backend.generate_structured(
            _request(temperature=0.0, max_output_tokens=300),
            response_model=_Plan,
        )
    )

    assert responses.calls[0]["text_format"] is _Plan
    assert responses.calls[0]["temperature"] == 0.0
    assert responses.calls[0]["max_output_tokens"] == 300


def test_missing_parsed_output_is_invalid_response() -> None:
    """Classify a missing native parsed value as an invalid response."""
    responses = _FakeResponses(response=_response())
    backend = OpenAIStructuredBackend(model="gpt-test", client=_FakeClient(responses))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_structured(_request(), response_model=_Plan))

    assert caught.value.category is ProviderFailureCategory.INVALID_RESPONSE
    assert str(caught.value) == "invalid_response: OpenAI returned no valid structured result."


def test_refusal_is_provider_rejected_without_exposing_refusal_text() -> None:
    """Classify a provider refusal without exposing its explanation."""
    refusal = SimpleNamespace(type="refusal", refusal="secret refusal details")
    responses = _FakeResponses(response=_response(output=[SimpleNamespace(content=[refusal])]))
    backend = OpenAIStructuredBackend(model="gpt-test", client=_FakeClient(responses))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_structured(_request(), response_model=_Plan))

    assert caught.value.category is ProviderFailureCategory.PROVIDER_REJECTED
    assert "secret" not in str(caught.value)


def test_invalid_parsed_value_is_invalid_response() -> None:
    """Classify a parsed value that cannot validate as the requested model."""
    responses = _FakeResponses(response=_response(parsed=object()))
    backend = OpenAIStructuredBackend(model="gpt-test", client=_FakeClient(responses))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_structured(_request(), response_model=_Plan))

    assert caught.value.category is ProviderFailureCategory.INVALID_RESPONSE


def test_native_parse_validation_error_is_invalid_response() -> None:
    """Classify SDK parsing validation failures without exposing details."""
    parse_error = ValidationError.from_exception_data(
        "Response",
        [{"type": "missing", "loc": ("title",), "input": {}}],
    )
    responses = _FakeResponses(error=parse_error)
    backend = OpenAIStructuredBackend(model="gpt-test", client=_FakeClient(responses))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_structured(_request(), response_model=_Plan))

    assert caught.value.category is ProviderFailureCategory.INVALID_RESPONSE


class APITimeoutError(Exception):
    """Fake SDK timeout exception identified by its provider-style name."""

    pass


class APIConnectionError(Exception):
    """Fake SDK connection exception identified by its provider-style name."""

    pass


class RateLimitError(Exception):
    """Fake SDK rate-limit exception with a safe status code."""

    status_code = 429


class AuthenticationError(Exception):
    """Fake SDK authentication exception with a safe status code."""

    status_code = 401


class BadRequestError(Exception):
    """Fake SDK request rejection with a safe status code."""

    status_code = 400


@pytest.mark.parametrize(
    ("error", "category", "message"),
    [
        (
            APITimeoutError("secret timeout"),
            ProviderFailureCategory.TIMEOUT,
            "OpenAI request timed out.",
        ),
        (
            APIConnectionError("secret connection"),
            ProviderFailureCategory.TRANSPORT,
            "OpenAI transport request failed.",
        ),
        (
            RateLimitError("secret rate"),
            ProviderFailureCategory.RATE_LIMIT,
            "OpenAI rate limit reached.",
        ),
        (
            AuthenticationError("secret auth"),
            ProviderFailureCategory.AUTHENTICATION,
            "OpenAI authentication failed.",
        ),
        (
            BadRequestError("secret rejection"),
            ProviderFailureCategory.PROVIDER_REJECTED,
            "OpenAI rejected the structured request.",
        ),
    ],
)
def test_provider_failures_are_stable_and_redacted(
    error: Exception,
    category: ProviderFailureCategory,
    message: str,
) -> None:
    """Map provider failures to stable redacted categories and messages."""
    responses = _FakeResponses(error=error)
    backend = OpenAIStructuredBackend(model="gpt-test", client=_FakeClient(responses))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_structured(_request(), response_model=_Plan))

    assert caught.value.category is category
    assert caught.value.safe_message == message
    assert "secret" not in str(caught.value)
    assert "secret" not in repr(caught.value)


def test_missing_responses_parse_is_configuration_failure() -> None:
    """Reject a client that does not advertise native structured parsing."""
    backend = OpenAIStructuredBackend(model="gpt-test", client=SimpleNamespace(responses=object()))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_structured(_request(), response_model=_Plan))

    assert caught.value.category is ProviderFailureCategory.CONFIGURATION
    assert not hasattr(backend, "generate_program")


def test_timeout_is_passed_to_the_transport_call() -> None:
    """Pass the request timeout at the individual SDK call boundary."""
    responses = _FakeResponses(response=_response(parsed=_Plan(title="Quicklook")))
    backend = OpenAIStructuredBackend(model="gpt-test", client=_FakeClient(responses))

    _run(
        backend.generate_structured(
            _request(timeout_seconds=3.25),
            response_model=_Plan,
        )
    )

    assert responses.calls[0]["timeout"] == 3.25
