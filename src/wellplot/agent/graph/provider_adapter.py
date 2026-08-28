###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Structured-output adapter used by graph planner/compiler nodes.

The graph depends on this small interface, not directly on OpenAI, LangChain or
MCP. The adapter below reuses Wellplot's existing provider abstraction and its
function-tool structured-output mechanism. This lets the LangGraph migration
start without replacing the provider layer at the same time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

TModel = TypeVar("TModel", bound=BaseModel)


class StructuredModelProtocol(Protocol):
    """Minimal structured-generation interface required by compiler nodes."""

    async def generate(
        self,
        *,
        instructions: str,
        user_message: str,
        response_model: type[TModel],
        tool_name: str,
        tool_description: str,
        max_rounds: int = 3,
    ) -> TModel:
        """Return exactly one validated structured result."""


@dataclass(slots=True)
class ExistingProviderStructuredAdapter:
    """Bridge the current ProviderBackendProtocol into structured graph nodes.

    Importing ``core`` is delayed until invocation so this module can remain a
    leaf dependency. During the migration, ``core.py`` should call into the new
    graph package; graph modules should not import ``core`` at module import
    time.
    """

    backend: object

    async def generate(
        self,
        *,
        instructions: str,
        user_message: str,
        response_model: type[TModel],
        tool_name: str,
        tool_description: str,
        max_rounds: int = 3,
    ) -> TModel:
        """Generate and validate one required structured response."""
        from ..core import FunctionToolDefinition

        accepted: TModel | None = None

        async def capture(name: str, arguments: dict[str, object]) -> dict[str, object]:
            nonlocal accepted
            if name != tool_name:
                return {
                    "is_error": True,
                    "error": f"Only {tool_name!r} is available in this graph stage.",
                }
            try:
                accepted = response_model.model_validate(arguments)
            except Exception as exc:
                return {
                    "is_error": True,
                    "error": f"Invalid {response_model.__name__}: {exc}",
                }
            return {"accepted": True}

        await self.backend.run_authoring(
            instructions=instructions,
            initial_user_message=user_message,
            tool_definitions=[
                FunctionToolDefinition(
                    name=tool_name,
                    description=tool_description,
                    parameters=response_model.model_json_schema(),
                )
            ],
            tool_caller=capture,
            max_rounds=max_rounds,
            required_tool_name=tool_name,
        )
        if accepted is None:
            raise RuntimeError(
                f"Provider finished without submitting required structured output {tool_name!r}."
            )
        return accepted
