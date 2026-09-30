"""Bounded diagnostics for locally classified structured responses."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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


_ERROR_TYPE_PATTERN = re.compile(r"^[a-z0-9_.-]{1,64}$")
MAX_SCHEMA_VALIDATION_ISSUES = 16
MAX_SCHEMA_VALIDATION_LOCATION_DEPTH = 8
UNKNOWN_ERROR_TYPE = "<unknown_error_type>"
UNKNOWN_FIELD = "<unknown_field>"
UNKNOWN_SEGMENT = "<unknown_segment>"
TRUNCATED_LOCATION = "<truncated>"


@dataclass(frozen=True, slots=True)
class ProviderSchemaValidationIssue:
    """One bounded, provider-neutral structured-validation issue."""

    error_type: str
    location: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject values outside the intentionally small diagnostic vocabulary."""
        if (
            not _ERROR_TYPE_PATTERN.fullmatch(self.error_type)
            and self.error_type != UNKNOWN_ERROR_TYPE
        ):
            raise ValueError("error_type is not a bounded diagnostic identifier.")
        if not self.location or len(self.location) > MAX_SCHEMA_VALIDATION_LOCATION_DEPTH:
            raise ValueError("location depth is outside the diagnostic bound.")
        if any(not isinstance(segment, str) for segment in self.location):
            raise TypeError("location segments must be strings.")

    def to_json(self) -> dict[str, object]:
        """Return a plain JSON-compatible representation."""
        return {
            "error_type": self.error_type,
            "location": list(self.location),
        }


@dataclass(frozen=True, slots=True)
class ProviderSchemaValidationShape:
    """Bounded shape of a Pydantic validation failure without model data."""

    issue_count: int
    issues: tuple[ProviderSchemaValidationIssue, ...]
    truncated: bool

    def __post_init__(self) -> None:
        """Validate the retained issue count and immutable issue collection."""
        if isinstance(self.issue_count, bool) or self.issue_count < 0:
            raise ValueError("issue_count must be a non-negative integer.")
        if len(self.issues) > MAX_SCHEMA_VALIDATION_ISSUES:
            raise ValueError("too many validation issues retained.")
        if self.issue_count < len(self.issues):
            raise ValueError("issue_count cannot be smaller than retained issues.")
        if not isinstance(self.truncated, bool):
            raise TypeError("truncated must be a boolean.")
        if any(not isinstance(issue, ProviderSchemaValidationIssue) for issue in self.issues):
            raise TypeError("issues must contain ProviderSchemaValidationIssue values.")

    def to_json(self) -> dict[str, object]:
        """Return a plain JSON-compatible representation."""
        return {
            "issue_count": self.issue_count,
            "issues": [issue.to_json() for issue in self.issues],
            "truncated": self.truncated,
        }


def schema_validation_shape(
    error: Exception,
    response_schema: Mapping[str, object],
) -> ProviderSchemaValidationShape | None:
    """Extract only bounded error types and schema-known locations."""
    try:
        raw_errors = error.errors(
            include_url=False,
            include_context=False,
            include_input=False,
        )
        if not isinstance(raw_errors, Sequence) or isinstance(raw_errors, (str, bytes)):
            return None
        declared_fields = _declared_schema_fields(response_schema)
        sanitized = [_sanitize_issue(item, declared_fields) for item in raw_errors]
        sanitized.sort(key=lambda issue: (issue.error_type, issue.location))
        issue_count = len(sanitized)
        retained = tuple(sanitized[:MAX_SCHEMA_VALIDATION_ISSUES])
        return ProviderSchemaValidationShape(
            issue_count=issue_count,
            issues=retained,
            truncated=issue_count > MAX_SCHEMA_VALIDATION_ISSUES,
        )
    except Exception:
        return None


def _declared_schema_fields(schema: Mapping[str, object]) -> frozenset[str]:
    """Collect declared JSON Schema property names recursively."""
    fields: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            properties = value.get("properties")
            if isinstance(properties, Mapping):
                fields.update(key for key in properties if isinstance(key, str))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return frozenset(fields)


def _sanitize_issue(
    raw_issue: object,
    declared_fields: frozenset[str],
) -> ProviderSchemaValidationIssue:
    """Sanitize one error without retaining arbitrary provider/model content."""
    if not isinstance(raw_issue, Mapping):
        return ProviderSchemaValidationIssue(UNKNOWN_ERROR_TYPE, (UNKNOWN_SEGMENT,))
    raw_type = raw_issue.get("type")
    error_type = (
        raw_type
        if isinstance(raw_type, str) and _ERROR_TYPE_PATTERN.fullmatch(raw_type)
        else UNKNOWN_ERROR_TYPE
    )
    location = raw_issue.get("loc", ())
    if not isinstance(location, (tuple, list)):
        location = ()
    if not location:
        sanitized_location = ("$root",)
    else:
        segments: list[str] = []
        for segment in location:
            if isinstance(segment, int) and not isinstance(segment, bool):
                segments.append("*")
            elif isinstance(segment, str):
                segments.append(segment if segment in declared_fields else UNKNOWN_FIELD)
            else:
                segments.append(UNKNOWN_SEGMENT)
        if len(segments) > MAX_SCHEMA_VALIDATION_LOCATION_DEPTH:
            segments = segments[: MAX_SCHEMA_VALIDATION_LOCATION_DEPTH - 1]
            segments.append(TRUNCATED_LOCATION)
        sanitized_location = tuple(segments)
    return ProviderSchemaValidationIssue(error_type, sanitized_location)


class StructuredResponseProviderError(ProviderRequestError):
    """Invalid-response error carrying bounded internal diagnostics."""

    response_reason: ProviderResponseFailureReason

    def __init__(
        self,
        safe_message: str,
        *,
        response_reason: ProviderResponseFailureReason,
        status_code: int | None = None,
        validation_shape: ProviderSchemaValidationShape | None = None,
    ) -> None:
        """Create an invalid-response error with one bounded reason."""
        if not isinstance(response_reason, ProviderResponseFailureReason):
            response_reason = ProviderResponseFailureReason(response_reason)
        if (
            response_reason is not ProviderResponseFailureReason.SCHEMA_VALIDATION
            and validation_shape is not None
        ):
            raise ValueError("validation_shape is only valid for schema_validation responses.")
        super().__init__(
            ProviderFailureCategory.INVALID_RESPONSE,
            safe_message,
            status_code=status_code,
        )
        self.response_reason = response_reason
        self.validation_shape = validation_shape

    def diagnostic_metadata(self) -> dict[str, str]:
        """Return only the bounded reason for internal diagnostics."""
        return {"response_reason": self.response_reason.value}


__all__ = [
    "MAX_SCHEMA_VALIDATION_ISSUES",
    "MAX_SCHEMA_VALIDATION_LOCATION_DEPTH",
    "ProviderResponseFailureReason",
    "ProviderSchemaValidationIssue",
    "ProviderSchemaValidationShape",
    "StructuredResponseProviderError",
    "schema_validation_shape",
]
