"""Tests for the CM-33 OpenAI-compatible provider-v2 transport."""

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
from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2
from wellplot.agent.providers.response_diagnostics import (
    ProviderResponseFailureReason,
    StructuredResponseProviderError,
)
from wellplot.authoring_program.grammar import DEFAULT_PROGRAM_POLICY_LIMITS


class _Plan(BaseModel):
    """Small structured response model for compatible transport tests."""

    title: str


class _FakeCompletions:
    """Minimal async Chat Completions resource."""

    def __init__(
        self,
        response: object = None,
        error: Exception | None = None,
        responses: list[object] | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        """Record one call and return its configured response."""
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if self.responses is not None:
            return self.responses.pop(0)
        return self.response


class _FakeClient:
    """Injected client exposing one fake Chat Completions resource."""

    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


def _program_request(**overrides: object) -> ProgramGenerationRequest:
    """Build a valid plain-program request."""
    values: dict[str, object] = {
        "system_prompt": "Return one Wellplot program.",
        "user_prompt": "Create the requested plot.",
        "timeout_seconds": 12.5,
    }
    values.update(overrides)
    return ProgramGenerationRequest(**values)


def _structured_request(**overrides: object) -> StructuredGenerationRequest:
    """Build a valid structured request."""
    values: dict[str, object] = {
        "system_prompt": "Return one plan.",
        "user_prompt": "Plan the plot.",
        "timeout_seconds": 12.5,
    }
    values.update(overrides)
    return StructuredGenerationRequest(**values)


def _response(
    content: object,
    *,
    finish_reason: str | None = "stop",
    role: object = "assistant",
    refusal: object = None,
    tool_calls: object = None,
    usage: object = None,
) -> SimpleNamespace:
    """Build the Chat Completions fields consumed by the adapter."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    role=role,
                    content=content,
                    refusal=refusal,
                    tool_calls=tool_calls or [],
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
    )


def _run(coroutine: object) -> object:
    """Run one adapter coroutine without an async pytest dependency."""
    return asyncio.run(coroutine)


def test_structured_output_requires_explicit_capability_without_calling_provider() -> None:
    """Do not probe, downgrade, or fall back when JSON Schema is not configured."""
    completions = _FakeCompletions(response=_response('{"title": "unused"}'))
    backend = OpenAICompatibleBackendV2(
        model="local-test",
        client=_FakeClient(completions),
        structured_output=None,
    )

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_structured(_structured_request(), response_model=_Plan))

    assert caught.value.category is ProviderFailureCategory.CONFIGURATION
    assert len(completions.calls) == 0


def test_structured_output_sends_one_strict_schema_request_and_validates_result() -> None:
    """Use one explicit JSON Schema request and validate its JSON content."""
    completions = _FakeCompletions(
        response=_response(
            '{"title": "Quicklook"}',
            usage={"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        )
    )
    backend = OpenAICompatibleBackendV2(
        model="local-test",
        client=_FakeClient(completions),
        structured_output="json_schema",
    )

    result = _run(backend.generate_structured(_structured_request(), response_model=_Plan))

    assert result.value == _Plan(title="Quicklook")
    assert result.metrics.public_metadata()["input_tokens"] == 11
    assert result.metrics.public_metadata()["output_tokens"] == 7
    assert result.metrics.latency_ms is not None
    assert len(completions.calls) == 1
    call = completions.calls[0]
    assert call["model"] == "local-test"
    assert call["messages"] == [
        {"role": "system", "content": "Return one plan."},
        {"role": "user", "content": "Plan the plot."},
    ]
    assert call["timeout"] == 12.5
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["strict"] is True
    assert "title" in call["response_format"]["json_schema"]["schema"]["properties"]
    assert "tools" not in call
    assert "json_object" not in str(call)


def test_schema_name_is_sanitized_to_a_bounded_api_name() -> None:
    """Translate arbitrary Pydantic class names into API-compatible names."""
    model = type("Plan.Name With Spaces", (BaseModel,), {"__annotations__": {"title": str}})
    completions = _FakeCompletions(response=_response('{"title": "Quicklook"}'))
    backend = OpenAICompatibleBackendV2(
        model="local-test",
        client=_FakeClient(completions),
        structured_output="json_schema",
    )

    _run(backend.generate_structured(_structured_request(), response_model=model))

    name = completions.calls[0]["response_format"]["json_schema"]["name"]
    assert name == "Plan-Name-With-Spaces"
    assert len(name) <= 64


def test_program_uses_one_sparse_chat_call_and_shared_envelope_rules() -> None:
    """Generate raw program text without tools or structured-output fields."""
    completions = _FakeCompletions(
        response=_response(
            "```python\nwp.report()\n```",
            usage={"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
        )
    )
    backend = OpenAICompatibleBackendV2(model="local-test", client=_FakeClient(completions))

    result = _run(backend.generate_program(_program_request()))

    assert result.text == "wp.report()"
    assert result.metrics.public_metadata()["total_tokens"] == 7
    assert result.metrics.latency_ms is not None
    assert len(completions.calls) == 1
    call = completions.calls[0]
    assert call["model"] == "local-test"
    assert call["timeout"] == 12.5
    assert "response_format" not in call
    assert "tools" not in call
    assert "functions" not in call


def test_explicit_max_token_parameter_is_forwarded_without_probing() -> None:
    """Select exactly one compatible max-token spelling at construction time."""
    completions = _FakeCompletions(response=_response("wp.report()"))
    backend = OpenAICompatibleBackendV2(
        model="local-test",
        client=_FakeClient(completions),
        max_tokens_parameter="max_tokens",
    )

    _run(backend.generate_program(_program_request(max_output_tokens=80, temperature=0.0)))

    assert completions.calls[0]["max_tokens"] == 80
    assert "max_completion_tokens" not in completions.calls[0]
    assert completions.calls[0]["temperature"] == 0.0


@pytest.mark.parametrize(
    ("content", "finish_reason", "category"),
    [
        ("{bad", "stop", ProviderFailureCategory.INVALID_RESPONSE),
        ("wp.report()", "length", ProviderFailureCategory.INVALID_RESPONSE),
        ("wp.report()", "tool_calls", ProviderFailureCategory.INVALID_RESPONSE),
        ("wp.report()", "content_filter", ProviderFailureCategory.PROVIDER_REJECTED),
    ],
)
def test_completion_and_content_failures_are_classified_without_dispatch(
    content: str,
    finish_reason: str,
    category: ProviderFailureCategory,
) -> None:
    """Reject malformed or incomplete Chat Completions before interpretation."""
    completions = _FakeCompletions(response=_response(content, finish_reason=finish_reason))
    backend = OpenAICompatibleBackendV2(model="local-test", client=_FakeClient(completions))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_program(_program_request()))

    assert caught.value.category is category


def test_structured_response_failure_reasons_cover_each_adapter_boundary() -> None:
    """Classify each bounded completion-envelope failure without raw payloads."""
    missing_message = _response("{}")
    missing_message.choices[0].message = None
    cases = [
        (SimpleNamespace(choices=[]), ProviderResponseFailureReason.UNUSABLE_CHOICE),
        (missing_message, ProviderResponseFailureReason.MISSING_MESSAGE),
        (
            _response("{}", role="user"),
            ProviderResponseFailureReason.NON_ASSISTANT_MESSAGE,
        ),
        (
            _response("{}", finish_reason="length"),
            ProviderResponseFailureReason.INCOMPLETE_OUTPUT,
        ),
        (
            _response("{}", finish_reason="provider_specific_stop"),
            ProviderResponseFailureReason.UNEXPECTED_FINISH_REASON,
        ),
        (
            _response("{}", tool_calls=[SimpleNamespace(name="secret-tool")]),
            ProviderResponseFailureReason.TOOL_CALL,
        ),
        (_response(None), ProviderResponseFailureReason.MISSING_CONTENT),
    ]

    for response, reason in cases:
        completions = _FakeCompletions(response=response)
        backend = OpenAICompatibleBackendV2(model="local-test", client=_FakeClient(completions))

        with pytest.raises(ProviderRequestError) as caught:
            _run(backend.generate_program(_program_request()))

        assert caught.value.category is ProviderFailureCategory.INVALID_RESPONSE
        assert isinstance(caught.value, StructuredResponseProviderError)
        assert caught.value.response_reason is reason
        assert "secret" not in repr(caught.value)


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("{bad", ProviderResponseFailureReason.INVALID_JSON),
        ("{}", ProviderResponseFailureReason.SCHEMA_VALIDATION),
    ],
)
def test_structured_json_and_schema_failures_are_distinguished(
    content: str,
    reason: ProviderResponseFailureReason,
) -> None:
    """Separate JSON parsing failure from response-model validation failure."""
    completions = _FakeCompletions(response=_response(content))
    backend = OpenAICompatibleBackendV2(
        model="local-test",
        client=_FakeClient(completions),
        structured_output="json_schema",
    )

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_structured(_structured_request(), response_model=_Plan))

    assert caught.value.category is ProviderFailureCategory.INVALID_RESPONSE
    assert isinstance(caught.value, StructuredResponseProviderError)
    assert caught.value.response_reason is reason
    assert content not in repr(caught.value)


def test_incomplete_finish_reason_precedes_tool_call_reason() -> None:
    """An incomplete finish reason dominates later tool-call inspection."""
    response = _response("{}", finish_reason="tool_calls", tool_calls=[{"name": "secret"}])
    backend = OpenAICompatibleBackendV2(
        model="local-test",
        client=_FakeClient(_FakeCompletions(response=response)),
    )

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_program(_program_request()))

    assert caught.value.response_reason is ProviderResponseFailureReason.INCOMPLETE_OUTPUT


def test_stop_finish_reason_with_tool_call_is_tool_call_reason() -> None:
    """A completed response containing a tool call is classified separately."""
    response = _response("{}", finish_reason="stop", tool_calls=[{"name": "secret"}])
    backend = OpenAICompatibleBackendV2(
        model="local-test",
        client=_FakeClient(_FakeCompletions(response=response)),
    )

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_program(_program_request()))

    assert caught.value.response_reason is ProviderResponseFailureReason.TOOL_CALL


def test_tool_calls_are_rejected_and_never_executed() -> None:
    """Treat returned tool calls as invalid output rather than dispatching them."""
    response = _response("wp.report()", tool_calls=[SimpleNamespace(name="secret_tool")])
    completions = _FakeCompletions(response=response)
    backend = OpenAICompatibleBackendV2(model="local-test", client=_FakeClient(completions))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_program(_program_request()))

    assert caught.value.category is ProviderFailureCategory.INVALID_RESPONSE
    assert "secret_tool" not in str(caught.value)


def test_refusal_is_provider_rejected_without_exposing_content() -> None:
    """Map refusal metadata to the stable rejection category."""
    completions = _FakeCompletions(response=_response(None, refusal="secret refusal"))
    backend = OpenAICompatibleBackendV2(model="local-test", client=_FakeClient(completions))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_program(_program_request()))

    assert caught.value.category is ProviderFailureCategory.PROVIDER_REJECTED
    assert not hasattr(caught.value, "response_reason")
    assert "secret" not in str(caught.value)


def test_content_filter_finish_reason_is_provider_rejected_without_reason() -> None:
    """A refusal finish reason remains outside invalid-response diagnostics."""
    completions = _FakeCompletions(response=_response("{}", finish_reason="content_filter"))
    backend = OpenAICompatibleBackendV2(model="local-test", client=_FakeClient(completions))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_program(_program_request()))

    assert caught.value.category is ProviderFailureCategory.PROVIDER_REJECTED
    assert not hasattr(caught.value, "response_reason")


def test_oversized_program_uses_the_canonical_cm11_limit() -> None:
    """Reject one character beyond the shared authoring-program source limit."""
    source = "#" * (DEFAULT_PROGRAM_POLICY_LIMITS.max_source_chars + 1)
    completions = _FakeCompletions(response=_response(source))
    backend = OpenAICompatibleBackendV2(model="local-test", client=_FakeClient(completions))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_program(_program_request()))

    assert caught.value.category is ProviderFailureCategory.INVALID_RESPONSE


def test_server_json_schema_capability_error_is_configuration_and_redacted() -> None:
    """Classify explicit capability metadata without inspecting raw error text."""

    class UnsupportedSchemaError(Exception):
        status_code = 400
        code = "response_format_not_supported"

    completions = _FakeCompletions(error=UnsupportedSchemaError("secret body"))
    backend = OpenAICompatibleBackendV2(
        model="local-test",
        client=_FakeClient(completions),
        structured_output="json_schema",
    )

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_structured(_structured_request(), response_model=_Plan))

    assert caught.value.category is ProviderFailureCategory.CONFIGURATION
    assert caught.value.safe_message == "OpenAI-compatible JSON Schema output is not supported."
    assert "secret" not in repr(caught.value)


class APITimeoutError(Exception):
    """Fake timeout exception identified by its provider-style name."""


class RateLimitError(Exception):
    """Fake rate-limit exception with a safe status code."""

    status_code = 429


class AuthenticationError(Exception):
    """Fake authentication exception with a safe status code."""

    status_code = 401


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (APITimeoutError("secret timeout"), ProviderFailureCategory.TIMEOUT),
        (RateLimitError("secret rate"), ProviderFailureCategory.RATE_LIMIT),
        (AuthenticationError("secret auth"), ProviderFailureCategory.AUTHENTICATION),
        (ConnectionError("secret connection"), ProviderFailureCategory.TRANSPORT),
    ],
)
def test_provider_failures_are_redacted_and_stable(
    error: Exception,
    category: ProviderFailureCategory,
) -> None:
    """Map transport failures without exposing exception details."""
    completions = _FakeCompletions(error=error)
    backend = OpenAICompatibleBackendV2(model="local-test", client=_FakeClient(completions))

    with pytest.raises(ProviderRequestError) as caught:
        _run(backend.generate_program(_program_request()))

    assert caught.value.category is category
    assert not hasattr(caught.value, "response_reason")
    assert "secret" not in str(caught.value)
    assert "secret" not in repr(caught.value)


async def _use_protocol(backend: ModelBackendProtocol) -> tuple[object, str]:
    """Exercise both operations through the provider-neutral protocol shape."""
    structured = await backend.generate_structured(_structured_request(), response_model=_Plan)
    program = await backend.generate_program(_program_request())
    return structured.value, program.text


def test_backend_supports_both_protocol_operations() -> None:
    """The compatible adapter exposes the complete v2 protocol surface."""
    completions = _FakeCompletions(
        responses=[_response('{"title": "Quicklook"}'), _response("wp.report()")]
    )
    backend = OpenAICompatibleBackendV2(
        model="local-test",
        client=_FakeClient(completions),
        structured_output="json_schema",
    )
    structured, program = _run(_use_protocol(backend))

    assert isinstance(structured, _Plan)
    assert program == "wp.report()"
    assert len(completions.calls) == 2
