"""Bounded diagnostics for locally classified structured responses."""

from __future__ import annotations

from enum import StrEnum

from .base import ProviderFailureCategory, ProviderRequestError


class ProviderResponseFailureReason(StrEnum):
    """Provider-neutral reasons for invalid structured responses."""

    UNUSABLE_CHOICE = "unusable_choice"
    MISSING_MESSAGE = "missing_message"
    NON_ASSISTANT_MESSAGE = "non_assistant_message"
    INCOMPLETE_OUTPUT = "incomplete_output"
    UNEXPECTED_FINISH_REASON = "unexpected_finish_reason"
    TOOL_CALL = "tool_call"
    MISSING_CONTENT = "missing_content"
    INVALID_JSON = "invalid_json"
    SCHEMA_VALIDATION = "schema_validation"


class StructuredResponseProviderError(ProviderRequestError):
    """Invalid-response error carrying bounded internal diagnostics."""

    response_reason: ProviderResponseFailureReason

    def __init__(
        self,
        safe_message: str,
        *,
        response_reason: ProviderResponseFailureReason,
        status_code: int | None = None,
    ) -> None:
        """Create an invalid-response error with one bounded reason."""
        if not isinstance(response_reason, ProviderResponseFailureReason):
            response_reason = ProviderResponseFailureReason(response_reason)
        super().__init__(
            ProviderFailureCategory.INVALID_RESPONSE,
            safe_message,
            status_code=status_code,
        )
        self.response_reason = response_reason

    def diagnostic_metadata(self) -> dict[str, str]:
        """Return only the bounded reason for internal diagnostics."""
        return {"response_reason": self.response_reason.value}


__all__ = ["ProviderResponseFailureReason", "StructuredResponseProviderError"]
