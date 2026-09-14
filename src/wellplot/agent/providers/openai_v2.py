"""Structured OpenAI Responses transport for Code Mode v2."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .base import (
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)

TModel = TypeVar("TModel", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class OpenAIStructuredBackend:
    """Call one injected OpenAI Responses client for structured generation.

    This component intentionally implements only the structured operation needed
    by CM-31. Program generation, retries, tool calls, and provider selection
    remain outside this slice.
    """

    model: str
    client: object

    def __post_init__(self) -> None:
        """Reject an unusable model identifier before provider dispatch."""
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model must be a non-empty string.")

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[TModel],
    ) -> StructuredGenerationResult[TModel]:
        """Generate one response parsed natively as ``response_model``."""
        if not isinstance(response_model, type) or not issubclass(response_model, BaseModel):
            raise ProviderRequestError(
                ProviderFailureCategory.CONFIGURATION,
                "OpenAI structured output requires a Pydantic response model.",
            )

        responses = getattr(self.client, "responses", None)
        parse = getattr(responses, "parse", None)
        if not callable(parse):
            raise ProviderRequestError(
                ProviderFailureCategory.CONFIGURATION,
                "OpenAI structured output requires responses.parse.",
            )

        arguments: dict[str, object] = {
            "model": self.model,
            "instructions": request.system_prompt,
            "input": request.user_prompt,
            "text_format": response_model,
            "timeout": request.timeout_seconds,
        }
        if request.temperature is not None:
            arguments["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            arguments["max_output_tokens"] = request.max_output_tokens

        started = perf_counter()
        try:
            response = await parse(**arguments)
        except ProviderRequestError:
            raise
        except Exception as exc:
            raise _map_provider_exception(exc) from None

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            category = (
                ProviderFailureCategory.PROVIDER_REJECTED
                if _contains_refusal(response)
                else ProviderFailureCategory.INVALID_RESPONSE
            )
            message = (
                "OpenAI rejected the structured request."
                if category is ProviderFailureCategory.PROVIDER_REJECTED
                else "OpenAI returned no valid structured result."
            )
            raise ProviderRequestError(category, message)

        try:
            value = (
                parsed
                if isinstance(parsed, response_model)
                else response_model.model_validate(parsed)
            )
        except (TypeError, ValidationError):
            raise ProviderRequestError(
                ProviderFailureCategory.INVALID_RESPONSE,
                "OpenAI returned an invalid structured result.",
            ) from None

        usage = getattr(response, "usage", None)
        latency_ms = (perf_counter() - started) * 1000
        metrics = ProviderMetrics(
            input_tokens=_usage_integer(usage, "input_tokens"),
            output_tokens=_usage_integer(usage, "output_tokens"),
            total_tokens=_usage_integer(usage, "total_tokens"),
            latency_ms=latency_ms,
        )
        return StructuredGenerationResult(value=value, metrics=metrics)


def _map_provider_exception(exc: Exception) -> ProviderRequestError:
    """Map SDK/transport failures to stable redacted provider categories."""
    status_code = _status_code(exc)
    name = type(exc).__name__.casefold()

    if status_code in {401, 403} or "auth" in name:
        category = ProviderFailureCategory.AUTHENTICATION
        message = "OpenAI authentication failed."
    elif status_code == 429 or "ratelimit" in name or "rate_limit" in name:
        category = ProviderFailureCategory.RATE_LIMIT
        message = "OpenAI rate limit reached."
    elif status_code == 408 or isinstance(exc, TimeoutError) or "timeout" in name:
        category = ProviderFailureCategory.TIMEOUT
        message = "OpenAI request timed out."
    elif 500 <= (status_code or 0) <= 599 or "connection" in name:
        category = ProviderFailureCategory.TRANSPORT
        message = "OpenAI transport request failed."
    elif 400 <= (status_code or 0) <= 499 or "badrequest" in name:
        category = ProviderFailureCategory.PROVIDER_REJECTED
        message = "OpenAI rejected the structured request."
    elif isinstance(exc, ValidationError):
        category = ProviderFailureCategory.INVALID_RESPONSE
        message = "OpenAI returned an invalid structured result."
    elif isinstance(exc, (TypeError, ValueError)):
        category = ProviderFailureCategory.CONFIGURATION
        message = "OpenAI structured request configuration is invalid."
    else:
        category = ProviderFailureCategory.TRANSPORT
        message = "OpenAI transport request failed."

    return ProviderRequestError(category, message, status_code=status_code)


def _status_code(exc: Exception) -> int | None:
    """Return only a valid HTTP status code exposed by an SDK exception."""
    value = getattr(exc, "status_code", None)
    if isinstance(value, bool) or not isinstance(value, int) or not 100 <= value <= 599:
        return None
    return value


def _usage_integer(usage: object, field_name: str) -> int | None:
    """Read one reported usage field without inferring unavailable values."""
    if usage is None:
        return None
    value = (
        usage.get(field_name) if isinstance(usage, Mapping) else getattr(usage, field_name, None)
    )
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _contains_refusal(response: object) -> bool:
    """Detect refusal metadata without retaining or exposing its contents."""
    if _field(response, "refusal"):
        return True
    output = _field(response, "output") or ()
    for item in output:
        for content in _field(item, "content") or ():
            if _field(content, "type") == "refusal" or _field(content, "refusal"):
                return True
    return False


def _field(value: object, field_name: str) -> object:
    """Read a field from either an SDK object or a test mapping."""
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


__all__ = ["OpenAIStructuredBackend"]
