"""Provider-neutral asynchronous generation contracts for Code Mode v2."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

TModel = TypeVar("TModel", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class StructuredGenerationRequest:
    """Explicit provider-neutral request for one structured response."""

    system_prompt: str
    user_prompt: str
    timeout_seconds: float
    temperature: float | None = None
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        """Reject malformed request values before provider dispatch."""
        _require_text(self.system_prompt, "system_prompt")
        _require_text(self.user_prompt, "user_prompt")
        _require_positive_number(self.timeout_seconds, "timeout_seconds")
        if self.temperature is not None:
            _require_nonnegative_number(self.temperature, "temperature")
        if self.max_output_tokens is not None:
            _require_positive_integer(self.max_output_tokens, "max_output_tokens")


@dataclass(frozen=True, slots=True)
class ProgramGenerationRequest:
    """Explicit provider-neutral request for plain authoring program text."""

    system_prompt: str
    user_prompt: str
    timeout_seconds: float
    temperature: float | None = None
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        """Reject malformed request values before provider dispatch."""
        _require_text(self.system_prompt, "system_prompt")
        _require_text(self.user_prompt, "user_prompt")
        _require_positive_number(self.timeout_seconds, "timeout_seconds")
        if self.temperature is not None:
            _require_nonnegative_number(self.temperature, "temperature")
        if self.max_output_tokens is not None:
            _require_positive_integer(self.max_output_tokens, "max_output_tokens")


@dataclass(frozen=True, slots=True)
class ProviderMetrics:
    """Per-call provider measurements with unavailable values represented by None."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float | None = None

    def __post_init__(self) -> None:
        """Validate measurements without imposing provider-specific accounting."""
        for field_name in ("input_tokens", "output_tokens", "total_tokens"):
            value = getattr(self, field_name)
            if value is not None:
                _require_nonnegative_integer(value, field_name)
        if self.latency_ms is not None:
            _require_nonnegative_number(self.latency_ms, "latency_ms")

    def public_metadata(self) -> dict[str, int | float | None]:
        """Return deterministic, provider-neutral serialized metrics."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
        }


@dataclass(frozen=True, slots=True)
class StructuredGenerationResult(Generic[TModel]):
    """Validated structured value and measurements from one provider call."""

    value: TModel
    metrics: ProviderMetrics


@dataclass(frozen=True, slots=True)
class ProgramGenerationResult:
    """Plain program source text and measurements from one provider call."""

    text: str
    metrics: ProviderMetrics

    def __post_init__(self) -> None:
        """Require text to remain a plain string at the provider boundary."""
        if not isinstance(self.text, str):
            raise TypeError("Program generation result text must be a string.")


class ProviderFailureCategory(StrEnum):
    """Stable provider failure categories shared by all concrete adapters."""

    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    TRANSPORT = "transport"
    PROVIDER_REJECTED = "provider_rejected"
    INVALID_RESPONSE = "invalid_response"
    VALIDATION = "validation"


_RETRYABLE_CATEGORIES = frozenset(
    {
        ProviderFailureCategory.TIMEOUT,
        ProviderFailureCategory.RATE_LIMIT,
        ProviderFailureCategory.TRANSPORT,
    }
)


class ProviderRequestError(RuntimeError):
    """Redacted, stable failure raised by a provider-v2 implementation."""

    category: ProviderFailureCategory
    safe_message: str
    retryable: bool
    status_code: int | None

    def __init__(
        self,
        category: ProviderFailureCategory,
        safe_message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        """Create an error from explicitly safe fields only."""
        if not isinstance(category, ProviderFailureCategory):
            category = ProviderFailureCategory(category)
        _require_text(safe_message, "safe_message")
        if status_code is not None:
            if isinstance(status_code, bool) or not isinstance(status_code, int):
                raise TypeError("status_code must be an integer or None.")
            if not 100 <= status_code <= 599:
                raise ValueError("status_code must be between 100 and 599.")
        self.category = category
        self.safe_message = safe_message
        self.retryable = category in _RETRYABLE_CATEGORIES
        self.status_code = status_code
        super().__init__(self.safe_message)

    def __str__(self) -> str:
        """Return only the stable category and explicitly safe message."""
        return f"{self.category.value}: {self.safe_message}"

    def __repr__(self) -> str:
        """Return a redacted representation suitable for public diagnostics."""
        return (
            f"ProviderRequestError(category={self.category.value!r}, "
            f"safe_message={self.safe_message!r}, retryable={self.retryable!r}, "
            f"status_code={self.status_code!r})"
        )

    def public_metadata(self) -> dict[str, str | bool | int | None]:
        """Return the only fields concrete adapters may serialize publicly."""
        return {
            "category": self.category.value,
            "safe_message": self.safe_message,
            "retryable": self.retryable,
            "status_code": self.status_code,
        }


class ModelBackendProtocol(Protocol):
    """Async provider contract for validated structured and plain generation."""

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[TModel],
    ) -> StructuredGenerationResult[TModel]:
        """Return a response validated as the supplied Pydantic model."""

    async def generate_program(
        self,
        request: ProgramGenerationRequest,
    ) -> ProgramGenerationResult:
        """Return plain program source without parsing or interpreting it."""


def _require_text(value: object, field_name: str) -> None:
    """Require one non-empty string without retaining provider payloads."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")


def _require_positive_number(value: object, field_name: str) -> None:
    """Require one finite number greater than zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number greater than zero.")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be a number greater than zero.")


def _require_nonnegative_number(value: object, field_name: str) -> None:
    """Require one finite number greater than or equal to zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a non-negative number.")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative number.")


def _require_positive_integer(value: object, field_name: str) -> None:
    """Require one integer greater than zero."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer greater than zero.")
    if value <= 0:
        raise ValueError(f"{field_name} must be an integer greater than zero.")


def _require_nonnegative_integer(value: object, field_name: str) -> None:
    """Require one integer greater than or equal to zero."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be a non-negative integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer.")


__all__ = [
    "ModelBackendProtocol",
    "ProgramGenerationRequest",
    "ProgramGenerationResult",
    "ProviderFailureCategory",
    "ProviderMetrics",
    "ProviderRequestError",
    "StructuredGenerationRequest",
    "StructuredGenerationResult",
]
