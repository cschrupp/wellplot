"""Neutral runtime value objects shared by authoring adapters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuthoringToolCall:
    """One provider-issued tool call retained in a bounded result trace."""

    round: int
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class FunctionToolDefinition:
    """One generic function-tool definition passed to a provider adapter."""

    name: str
    description: str
    parameters: dict[str, object]


@dataclass(frozen=True)
class ProviderRunResult:
    """Normalized provider-loop result returned to an adapter."""

    final_text: str
    tool_trace: tuple[AuthoringToolCall, ...]
    report_facts: dict[str, object] = field(default_factory=dict)


__all__ = ["AuthoringToolCall", "FunctionToolDefinition", "ProviderRunResult"]
