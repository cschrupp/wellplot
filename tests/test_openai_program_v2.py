"""Tests for the CM-32 native OpenAI program transport."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProgramGenerationRequest,
    ProviderFailureCategory,
    ProviderRequestError,
    StructuredGenerationRequest,
)
from wellplot.agent.providers.openai_program_v2 import (
    PROGRAM_MAX_SOURCE_CHARS,
    OpenAIProgramBackend,
)
from wellplot.agent.providers.openai_v2 import OpenAIBackendV2
from wellplot.authoring_program.grammar import DEFAULT_PROGRAM_POLICY_LIMITS


class _Plan(BaseModel):
    """Minimal model-like type used to exercise the combined protocol path."""

    title: str


class _FakeResponses:
    """Minimal async Responses resource for program transport tests."""

    def __init__(
        self,
        *,
        create_response: object = None,
        parse_response: object = None,
        error: Exception | None = None,
    ) -> None:
        self.create_response = create_response
        self.parse_response = parse_response
        self.error = error
        self.create_calls: list[dict[str, object]] = []
        self.parse_calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        """Record and return one fake ordinary Responses response."""
        self.create_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.create_response

    async def parse(self, **kwargs: object) -> object:
        """Record and return one fake structured Responses response."""
        self.parse_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.parse_response


class _FakeClient:
    """Injected client exposing one fake Responses resource."""

    def __init__(self, responses: _FakeResponses) -> None:
        self.responses = responses


def _request(**overrides: object) -> ProgramGenerationRequest:
    """Build a valid plain-program request with optional overrides."""
    values: dict[str, object] = {
        "system_prompt": "Return one Wellplot program.",
        "user_prompt": "Create the requested plot.",
        "timeout_seconds": 12.5,
    }
    values.update(overrides)
    return ProgramGenerationRequest(**values)


def _structured_request() -> StructuredGenerationRequest:
    """Build a valid structured request for the combined backend test."""
    return StructuredGenerationRequest(
        system_prompt="Return one plan.",
        user_prompt="Plan the plot.",
        timeout_seconds=12.5,
    )


def _response(
    text: object = None,
    *,
    output: object = None,
    status: str = "completed",
    incomplete_details: object = None,
    usage: object = None,
) -> SimpleNamespace:
    """Build the Responses fields consumed by the program adapter."""
    return SimpleNamespace(
        output_text=text,
        output=output or [],
        status=status,
        incomplete_details=incomplete_details,
        usage=usage,
    )


def _run(coroutine: object) -> object:
    """Run one adapter coroutine without an async pytest dependency."""
    return asyncio.run(coroutine)


def test_raw_program_uses_one_create_call_and_preserves_source() -> None:
    """Accept raw source through one tool-free Responses request."""
    responses = _FakeResponses(create_response=_response("wp.report()\n\nwp.report()"))
    backend = OpenAIProgramBackend(model="gpt-test", client=_FakeClient(responses))

    result = _run(backend.generate_program(_request()))

    assert result.text == "wp.report()\n\nwp.report()"
    assert len(responses.create_calls) == 1
    assert responses.create_calls[0]["model"] == "gpt-test"
    assert responses.create_calls[0]["instructions"] == "Return one Wellplot program."
    assert responses.create_calls[0]["input"] == "Create the requested plot."
    assert responses.create_calls[0]["timeout"] == 12.5
    assert "text_format" not in responses.create_calls[0]
    assert "tools" not in responses.create_calls[0]
    assert "temperature" not in responses.create_calls[0]
    assert "max_output_tokens" not in responses.create_calls[0]
    assert result.metrics.latency_ms is not None


def test_python_fence_is_removed_without_rewriting_program_content() -> None:
    """Accept exactly one Python fence and remove only its envelope."""
    responses = _FakeResponses(create_response=_response("```python\nwp.report()\n```"))
    backend = OpenAIProgramBackend(model="gpt-test", client=_FakeClient(responses))

    result = _run(backend.generate_program(_request()))

    assert result.text == "wp.report()"


def test_optional_generation_settings_are_forwarded_when_explicit() -> None:
    """Forward optional output controls only when the request supplies them."""
    responses = _FakeResponses(create_response=_response("wp.report()"))
    backend = OpenAIProgramBackend(model="gpt-test", client=_FakeClient(responses))

    _run(
        backend.generate_program(
            _request(temperature=0.0, max_output_tokens=80),
        )
    )

    assert responses.create_calls[0]["temperature"] == 0.0
    assert responses.create_calls[0]["max_output_tokens"] == 80


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n\t",
        "Here is the program.",
        "Here is the program.\nwp.report()",
        "Here is the program:\n```python\nwp.report()\n```",
        "```python\nwp.report()\n```\nHope this helps!",
        "```python\nwp.report()\n```\n```python\nwp.report()\n```",
        "```python\nwp.report()",
        "```\nwp.report()\n```",
        '{"action": "create"}',
        '["wp.report()"]',
        "wp.report(",
    ],
)
def test_ambiguous_or_invalid_program_envelopes_are_rejected(text: str) -> None:
    """Reject empty, prose, fenced, JSON, and syntax-invalid responses."""
    responses = _FakeResponses(create_response=_response(text))
    backend = OpenAIProgramBackend(model="gpt-test", client=_FakeClient(responses))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_program(_request()))

    assert caught.value.category is ProviderFailureCategory.INVALID_RESPONSE


@pytest.mark.parametrize(
    ("status", "incomplete_details", "finish_reason"),
    [
        ("incomplete", {"reason": "max_output_tokens"}, None),
        ("completed", None, "length"),
    ],
)
def test_completion_metadata_rejects_truncation_before_syntax_acceptance(
    status: str,
    incomplete_details: object,
    finish_reason: str | None,
) -> None:
    """Reject incomplete provider responses even if their text parses."""
    response = _response(
        "wp.report()",
        status=status,
        incomplete_details=incomplete_details,
    )
    if finish_reason is not None:
        response.finish_reason = finish_reason
    responses = _FakeResponses(create_response=response)
    backend = OpenAIProgramBackend(model="gpt-test", client=_FakeClient(responses))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_program(_request()))

    assert caught.value.category is ProviderFailureCategory.INVALID_RESPONSE
    assert caught.value.safe_message == "OpenAI returned incomplete program output."


def test_tool_call_output_is_rejected_without_dispatch() -> None:
    """Reject function/tool output even when the response also has text."""
    output = [SimpleNamespace(type="function_call", name="secret_tool")]
    responses = _FakeResponses(create_response=_response("wp.report()", output=output))
    backend = OpenAIProgramBackend(model="gpt-test", client=_FakeClient(responses))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_program(_request()))

    assert caught.value.category is ProviderFailureCategory.INVALID_RESPONSE
    assert "secret_tool" not in str(caught.value)


def test_refusal_remains_provider_rejected() -> None:
    """Preserve CM-31 refusal classification for program generation."""
    refusal = SimpleNamespace(type="refusal", refusal="secret refusal")
    output = [SimpleNamespace(type="message", content=[refusal])]
    responses = _FakeResponses(create_response=_response(output=output))
    backend = OpenAIProgramBackend(model="gpt-test", client=_FakeClient(responses))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_program(_request()))

    assert caught.value.category is ProviderFailureCategory.PROVIDER_REJECTED
    assert "secret" not in str(caught.value)


def test_program_length_boundary_matches_cm11_policy() -> None:
    """Allow exactly the shared source limit and reject one character more."""
    assert DEFAULT_PROGRAM_POLICY_LIMITS.max_source_chars == PROGRAM_MAX_SOURCE_CHARS
    exact = "#" * PROGRAM_MAX_SOURCE_CHARS
    responses = _FakeResponses(create_response=_response(exact))
    backend = OpenAIProgramBackend(model="gpt-test", client=_FakeClient(responses))

    result = _run(backend.generate_program(_request()))

    assert result.text == exact

    oversized = OpenAIProgramBackend(
        model="gpt-test",
        client=_FakeClient(
            _FakeResponses(create_response=_response("#" * (PROGRAM_MAX_SOURCE_CHARS + 1)))
        ),
    )
    with pytest.raises(ProviderRequestError) as caught:
        _run(oversized.generate_program(_request()))
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
    ],
)
def test_provider_failures_are_stable_and_redacted(
    error: Exception,
    category: ProviderFailureCategory,
    message: str,
) -> None:
    """Map program transport failures to the CM-30 redacted taxonomy."""
    responses = _FakeResponses(error=error)
    backend = OpenAIProgramBackend(model="gpt-test", client=_FakeClient(responses))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_program(_request()))

    assert caught.value.category is category
    assert caught.value.safe_message == message
    assert "secret" not in str(caught.value)
    assert "secret" not in repr(caught.value)


async def _use_protocol(backend: ModelBackendProtocol) -> tuple[object, str]:
    """Exercise both protocol operations without runtime protocol introspection."""
    structured = await backend.generate_structured(_structured_request(), response_model=_Plan)
    program = await backend.generate_program(_request())
    return structured.value, program.text


def test_combined_backend_supports_both_protocol_operations() -> None:
    """The composed backend provides the full v2 surface by delegation."""
    responses = _FakeResponses(
        parse_response=SimpleNamespace(output_parsed=_Plan(title="Quicklook")),
        create_response=_response("wp.report()"),
    )
    backend = OpenAIBackendV2(model="gpt-test", client=_FakeClient(responses))

    structured, program = _run(_use_protocol(backend))

    assert isinstance(structured, _Plan)
    assert program == "wp.report()"
    assert len(responses.parse_calls) == 1
    assert len(responses.create_calls) == 1
