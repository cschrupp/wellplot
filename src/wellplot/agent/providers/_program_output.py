"""Provider-neutral validation for one generated authoring program envelope."""

from __future__ import annotations

import ast
import json

from wellplot.authoring_program.grammar import DEFAULT_PROGRAM_POLICY_LIMITS

from .base import ProviderFailureCategory, ProviderRequestError

PROGRAM_MAX_SOURCE_CHARS = DEFAULT_PROGRAM_POLICY_LIMITS.max_source_chars
_ALLOWED_FENCE_LINES = frozenset({"```python"})


def extract_program_source(text: str, *, provider_label: str = "OpenAI") -> str:
    """Extract one raw or strictly fenced, syntax-valid program envelope."""
    source = text.strip()
    if not source:
        raise ProviderRequestError(
            ProviderFailureCategory.INVALID_RESPONSE,
            f"{provider_label} returned empty program output.",
        )

    lines = source.splitlines(keepends=True)
    fence_lines = [line.rstrip("\r\n") for line in lines if _is_fence_line(line)]
    first_line = lines[0].rstrip("\r\n")
    if fence_lines:
        if first_line not in _ALLOWED_FENCE_LINES or len(fence_lines) != 2:
            raise ProviderRequestError(
                ProviderFailureCategory.INVALID_RESPONSE,
                f"{provider_label} returned an ambiguous program envelope.",
            )
        if lines[-1].rstrip("\r\n") != "```":
            raise ProviderRequestError(
                ProviderFailureCategory.INVALID_RESPONSE,
                f"{provider_label} returned an unterminated program fence.",
            )
        source = "".join(lines[1:-1])
        if source.endswith("\r\n"):
            source = source[:-2]
        elif source.endswith("\n") or source.endswith("\r"):
            source = source[:-1]
        if not source.strip():
            raise ProviderRequestError(
                ProviderFailureCategory.INVALID_RESPONSE,
                f"{provider_label} returned an empty fenced program.",
            )
    elif "```" in source:
        raise ProviderRequestError(
            ProviderFailureCategory.INVALID_RESPONSE,
            f"{provider_label} returned an ambiguous program envelope.",
        )

    try:
        json_value = json.loads(source)
    except (TypeError, ValueError):
        json_value = None
    if isinstance(json_value, (dict, list)):
        raise ProviderRequestError(
            ProviderFailureCategory.INVALID_RESPONSE,
            f"{provider_label} returned JSON instead of program text.",
        )

    try:
        ast.parse(source, mode="exec")
    except SyntaxError:
        raise ProviderRequestError(
            ProviderFailureCategory.INVALID_RESPONSE,
            f"{provider_label} returned syntactically invalid program text.",
        ) from None
    return source


def _is_fence_line(line: str) -> bool:
    """Identify a complete-line Markdown fence without parsing Markdown."""
    return line.rstrip("\r\n").startswith("```")


__all__ = ["PROGRAM_MAX_SOURCE_CHARS", "extract_program_source"]
