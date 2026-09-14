"""OpenAI-compatible Chat Completions transport for Code Mode v2."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Literal, TypeVar

from pydantic import BaseModel, ValidationError

from ._program_output import PROGRAM_MAX_SOURCE_CHARS, extract_program_source
from .base import (
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)

TModel = TypeVar("TModel", bound=BaseModel)
StructuredOutputCapability = Literal["json_schema"]
MaxTokensParameter = Literal["max_completion_tokens", "max_tokens"]
_SCHEMA_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")
_NORMAL_FINISH_REASON = "stop"
_INCOMPLETE_FINISH_REASONS = frozenset({"length", "tool_calls"})
_REFUSAL_FINISH_REASONS = frozenset({"content_filter"})
_JSON_SCHEMA_CAPABILITY_CODES = frozenset(
    {
        "json_schema_not_supported",
        "response_format_not_supported",
        "unsupported_response_format",
    }
)


@dataclass(frozen=True, slots=True)
class OpenAICompatibleBackendV2:
    """Expose both v2 operations over one explicit Chat Completions client."""

    model: str
    client: object
    structured_output: StructuredOutputCapability | None = None
    max_tokens_parameter: MaxTokensParameter = "max_completion_tokens"

    def __post_init__(self) -> None:
        """Validate explicit transport capabilities before provider dispatch."""
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model must be a non-empty string.")
        if self.structured_output not in (None, "json_schema"):
            raise ValueError("structured_output must be 'json_schema' or None.")
        if self.max_tokens_parameter not in {"max_completion_tokens", "max_tokens"}:
            raise ValueError(
                "max_tokens_parameter must be 'max_completion_tokens' or 'max_tokens'."
            )

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[TModel],
    ) -> StructuredGenerationResult[TModel]:
        """Generate one Pydantic value through explicit JSON Schema support."""
        if self.structured_output != "json_schema":
            raise ProviderRequestError(
                ProviderFailureCategory.CONFIGURATION,
                "OpenAI-compatible JSON Schema output is not configured.",
            )
        if not isinstance(response_model, type) or not issubclass(response_model, BaseModel):
            raise ProviderRequestError(
                ProviderFailureCategory.CONFIGURATION,
                "OpenAI-compatible structured output requires a Pydantic response model.",
            )
        try:
            schema = response_model.model_json_schema()
        except (TypeError, ValueError):
            raise ProviderRequestError(
                ProviderFailureCategory.CONFIGURATION,
                "OpenAI-compatible structured output schema is invalid.",
            ) from None

        arguments = self._request_arguments(request)
        arguments["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": _schema_name(response_model),
                "schema": schema,
                "strict": True,
            },
        }
        started = perf_counter()
        response = await self._create(arguments)
        message, usage = _extract_message(response)
        content = _message_content(message)
        try:
            value = response_model.model_validate(json.loads(content))
        except (TypeError, ValueError, ValidationError):
            raise ProviderRequestError(
                ProviderFailureCategory.INVALID_RESPONSE,
                "OpenAI-compatible returned invalid structured JSON.",
            ) from None
        return StructuredGenerationResult(
            value=value,
            metrics=_metrics(usage, latency_ms=(perf_counter() - started) * 1000),
        )

    async def generate_program(
        self,
        request: ProgramGenerationRequest,
    ) -> ProgramGenerationResult:
        """Generate one plain program through one tool-free Chat call."""
        started = perf_counter()
        response = await self._create(self._request_arguments(request))
        message, usage = _extract_message(response)
        content = _message_content(message)
        source = extract_program_source(content, provider_label="OpenAI-compatible")
        if len(source) > PROGRAM_MAX_SOURCE_CHARS:
            raise ProviderRequestError(
                ProviderFailureCategory.INVALID_RESPONSE,
                "OpenAI-compatible returned a program exceeding the source length limit.",
            )
        return ProgramGenerationResult(
            text=source,
            metrics=_metrics(usage, latency_ms=(perf_counter() - started) * 1000),
        )

    def _request_arguments(
        self,
        request: StructuredGenerationRequest | ProgramGenerationRequest,
    ) -> dict[str, object]:
        """Build the sparse, deterministic Chat Completions request."""
        arguments: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "timeout": request.timeout_seconds,
        }
        if request.temperature is not None:
            arguments["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            arguments[self.max_tokens_parameter] = request.max_output_tokens
        return arguments

    async def _create(self, arguments: dict[str, object]) -> object:
        """Call exactly one configured Chat Completions operation."""
        chat = getattr(self.client, "chat", None)
        completions = getattr(chat, "completions", None)
        create = getattr(completions, "create", None)
        if not callable(create):
            raise ProviderRequestError(
                ProviderFailureCategory.CONFIGURATION,
                "OpenAI-compatible output requires chat.completions.create.",
            )
        try:
            return await create(**arguments)
        except ProviderRequestError:
            raise
        except Exception as exc:
            raise _map_provider_exception(exc) from None


def _extract_message(response: object) -> tuple[object, object]:
    """Validate one assistant choice and return its message and usage."""
    choices = _field(response, "choices")
    if not isinstance(choices, (list, tuple)) or len(choices) != 1:
        raise ProviderRequestError(
            ProviderFailureCategory.INVALID_RESPONSE,
            "OpenAI-compatible returned an unusable completion choice.",
        )
    choice = choices[0]
    message = _field(choice, "message")
    if message is None:
        raise ProviderRequestError(
            ProviderFailureCategory.INVALID_RESPONSE,
            "OpenAI-compatible returned no completion message.",
        )
    role = _field(message, "role")
    if role is not None and role != "assistant":
        raise ProviderRequestError(
            ProviderFailureCategory.INVALID_RESPONSE,
            "OpenAI-compatible returned a non-assistant completion message.",
        )
    finish_reason = _field(choice, "finish_reason")
    if finish_reason in _REFUSAL_FINISH_REASONS or _message_refusal(message):
        raise ProviderRequestError(
            ProviderFailureCategory.PROVIDER_REJECTED,
            "OpenAI-compatible rejected the request.",
        )
    if finish_reason in _INCOMPLETE_FINISH_REASONS or (
        finish_reason is not None and finish_reason != _NORMAL_FINISH_REASON
    ):
        raise ProviderRequestError(
            ProviderFailureCategory.INVALID_RESPONSE,
            "OpenAI-compatible returned incomplete output.",
        )
    if _field(message, "tool_calls"):
        raise ProviderRequestError(
            ProviderFailureCategory.INVALID_RESPONSE,
            "OpenAI-compatible returned a tool call instead of output.",
        )
    return message, _field(response, "usage")


def _message_content(message: object) -> str:
    """Return one string message body without accepting tool payloads."""
    content = _field(message, "content")
    if not isinstance(content, str):
        raise ProviderRequestError(
            ProviderFailureCategory.INVALID_RESPONSE,
            "OpenAI-compatible returned no usable completion content.",
        )
    return content


def _message_refusal(message: object) -> bool:
    """Detect refusal metadata without retaining its contents."""
    return _field(message, "refusal") is not None


def _schema_name(response_model: type[BaseModel]) -> str:
    """Return one deterministic API-compatible JSON Schema name."""
    name = _SCHEMA_NAME_PATTERN.sub("-", response_model.__name__).strip("-_")
    return (name or "response")[:64]


def _metrics(usage: object, *, latency_ms: float) -> ProviderMetrics:
    """Normalize Chat Completions usage and local latency measurements."""
    return ProviderMetrics(
        input_tokens=_usage_integer(usage, "prompt_tokens"),
        output_tokens=_usage_integer(usage, "completion_tokens"),
        total_tokens=_usage_integer(usage, "total_tokens"),
        latency_ms=latency_ms,
    )


def _field(value: object, field_name: str) -> object:
    """Read a field from either an SDK object or a test mapping."""
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _usage_integer(usage: object, field_name: str) -> int | None:
    """Read one non-negative integer usage field without inference."""
    value = _field(usage, field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _status_code(exc: Exception) -> int | None:
    """Return only a valid status code exposed by a provider exception."""
    value = getattr(exc, "status_code", None)
    if isinstance(value, bool) or not isinstance(value, int) or not 100 <= value <= 599:
        return None
    return value


def _map_provider_exception(exc: Exception) -> ProviderRequestError:
    """Map compatible-provider failures to stable redacted categories."""
    status_code = _status_code(exc)
    name = type(exc).__name__.casefold()
    if _is_json_schema_capability_error(exc):
        category = ProviderFailureCategory.CONFIGURATION
        message = "OpenAI-compatible JSON Schema output is not supported."
    elif status_code in {401, 403} or "auth" in name:
        category = ProviderFailureCategory.AUTHENTICATION
        message = "OpenAI-compatible authentication failed."
    elif status_code == 429 or "ratelimit" in name or "rate_limit" in name:
        category = ProviderFailureCategory.RATE_LIMIT
        message = "OpenAI-compatible rate limit reached."
    elif status_code == 408 or isinstance(exc, TimeoutError) or "timeout" in name:
        category = ProviderFailureCategory.TIMEOUT
        message = "OpenAI-compatible request timed out."
    elif 500 <= (status_code or 0) <= 599 or "connection" in name:
        category = ProviderFailureCategory.TRANSPORT
        message = "OpenAI-compatible transport request failed."
    elif isinstance(exc, ValidationError):
        category = ProviderFailureCategory.INVALID_RESPONSE
        message = "OpenAI-compatible returned an invalid response."
    elif 400 <= (status_code or 0) <= 499 or "badrequest" in name:
        category = ProviderFailureCategory.PROVIDER_REJECTED
        message = "OpenAI-compatible provider rejected the request."
    elif isinstance(exc, (TypeError, ValueError)):
        category = ProviderFailureCategory.CONFIGURATION
        message = "OpenAI-compatible request configuration is invalid."
    else:
        category = ProviderFailureCategory.TRANSPORT
        message = "OpenAI-compatible transport request failed."
    return ProviderRequestError(category, message, status_code=status_code)


def _is_json_schema_capability_error(exc: Exception) -> bool:
    """Classify only explicit provider error metadata, never raw body text."""
    for field_name in ("code", "error_code", "error_type"):
        value = getattr(exc, field_name, None)
        if isinstance(value, str) and value.casefold() in _JSON_SCHEMA_CAPABILITY_CODES:
            return True
    return False


__all__ = ["OpenAICompatibleBackendV2"]
