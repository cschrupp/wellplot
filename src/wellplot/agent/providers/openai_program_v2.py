"""Plain OpenAI Responses transport for Code Mode program generation."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from ._program_output import PROGRAM_MAX_SOURCE_CHARS, extract_program_source
from .base import (
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
)
from .openai_v2 import (
    _contains_refusal,
    _field,
    _map_provider_exception,
    _usage_integer,
)

_TOOL_CALL_TYPES = frozenset(
    {
        "computer_call",
        "custom_tool_call",
        "file_search_call",
        "function_call",
        "image_generation_call",
        "mcp_call",
        "web_search_call",
    }
)
_INCOMPLETE_FINISH_REASONS = frozenset({"incomplete", "length", "max_output_tokens"})


@dataclass(frozen=True, slots=True)
class OpenAIProgramBackend:
    """Generate one plain program response through an injected client."""

    model: str
    client: object

    def __post_init__(self) -> None:
        """Reject an unusable model identifier before provider dispatch."""
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model must be a non-empty string.")

    async def generate_program(
        self,
        request: ProgramGenerationRequest,
    ) -> ProgramGenerationResult:
        """Generate and envelope-validate one plain authoring program."""
        responses = getattr(self.client, "responses", None)
        create = getattr(responses, "create", None)
        if not callable(create):
            raise ProviderRequestError(
                ProviderFailureCategory.CONFIGURATION,
                "OpenAI program output requires responses.create.",
            )

        arguments: dict[str, object] = {
            "model": self.model,
            "instructions": request.system_prompt,
            "input": request.user_prompt,
            "timeout": request.timeout_seconds,
        }
        if request.temperature is not None:
            arguments["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            arguments["max_output_tokens"] = request.max_output_tokens

        started = perf_counter()
        try:
            response = await create(**arguments)
        except ProviderRequestError:
            raise
        except Exception as exc:
            raise _map_provider_exception(exc) from None

        if _contains_refusal(response):
            raise ProviderRequestError(
                ProviderFailureCategory.PROVIDER_REJECTED,
                "OpenAI rejected the program request.",
            )
        if _response_is_incomplete(response):
            raise ProviderRequestError(
                ProviderFailureCategory.INVALID_RESPONSE,
                "OpenAI returned incomplete program output.",
            )
        if _contains_tool_call(response):
            raise ProviderRequestError(
                ProviderFailureCategory.INVALID_RESPONSE,
                "OpenAI returned a tool call instead of program text.",
            )

        output_text = _field(response, "output_text")
        if not isinstance(output_text, str):
            raise ProviderRequestError(
                ProviderFailureCategory.INVALID_RESPONSE,
                "OpenAI returned no program text.",
            )

        source = extract_program_source(output_text)
        if len(source) > PROGRAM_MAX_SOURCE_CHARS:
            raise ProviderRequestError(
                ProviderFailureCategory.INVALID_RESPONSE,
                "OpenAI returned a program exceeding the source length limit.",
            )

        usage = _field(response, "usage")
        latency_ms = (perf_counter() - started) * 1000
        metrics = ProviderMetrics(
            input_tokens=_usage_integer(usage, "input_tokens"),
            output_tokens=_usage_integer(usage, "output_tokens"),
            total_tokens=_usage_integer(usage, "total_tokens"),
            latency_ms=latency_ms,
        )
        return ProgramGenerationResult(text=source, metrics=metrics)


def _contains_tool_call(response: object) -> bool:
    """Detect returned tool-call output without dispatching or retaining it."""
    output = _field(response, "output") or ()
    for item in output:
        item_type = _field(item, "type")
        if item_type in _TOOL_CALL_TYPES:
            return True
    return False


def _response_is_incomplete(response: object) -> bool:
    """Detect provider completion metadata before syntax classification."""
    status = _field(response, "status")
    if isinstance(status, str) and status and status != "completed":
        return True
    if _field(response, "incomplete_details") is not None:
        return True
    finish_reason = _field(response, "finish_reason")
    return finish_reason in _INCOMPLETE_FINISH_REASONS


__all__ = ["OpenAIProgramBackend", "PROGRAM_MAX_SOURCE_CHARS"]
