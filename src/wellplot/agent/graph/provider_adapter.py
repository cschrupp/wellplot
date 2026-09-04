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

import json
from collections.abc import Callable
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
        response_validator: Callable[[TModel], None] | None = None,
    ) -> TModel:
        """Return exactly one schema- and semantics-validated structured result."""


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
        response_validator: Callable[[TModel], None] | None = None,
    ) -> TModel:
        """Generate and validate one required structured response."""
        from ..core import FunctionToolDefinition, ProviderAdapterError
        from ..execution_trace import current_agent_trace

        accepted: TModel | None = None
        trace = current_agent_trace()
        response_schema = response_model.model_json_schema()
        response_schema_characters = len(
            json.dumps(response_schema, separators=(",", ":"), default=str)
        )

        async def capture(name: str, arguments: dict[str, object]) -> dict[str, object]:
            nonlocal accepted
            if name != tool_name:
                return {
                    "is_error": True,
                    "error": f"Only {tool_name!r} is available in this graph stage.",
                }
            try:
                candidate = response_model.model_validate(arguments)
            except Exception as exc:
                if trace is not None:
                    trace.record(
                        "structured_submission_rejected",
                        status="invalid_response_model",
                        details={
                            "tool_name": tool_name,
                            "response_model": response_model.__name__,
                            "error": str(exc),
                        },
                        payload=arguments,
                    )
                return {
                    "is_error": True,
                    "error": f"Invalid {response_model.__name__}: {exc}",
                }
            if response_validator is not None:
                try:
                    response_validator(candidate)
                except Exception as exc:
                    if trace is not None:
                        trace.record(
                            "structured_submission_rejected",
                            status="invalid_semantics",
                            details={
                                "tool_name": tool_name,
                                "response_model": response_model.__name__,
                                "error": str(exc),
                            },
                            payload=arguments,
                        )
                    return {
                        "is_error": True,
                        "error": f"Rejected {response_model.__name__}: {exc}",
                    }
            accepted = candidate
            return {"accepted": True}

        if trace is not None:
            trace.record(
                "structured_request_started",
                status="started",
                details={
                    "tool_name": tool_name,
                    "response_model": response_model.__name__,
                    "max_rounds": max_rounds,
                    "instructions_characters": len(instructions),
                    "user_message_characters": len(user_message),
                    "response_schema_characters": response_schema_characters,
                    "prompt_and_schema_characters": (
                        len(instructions) + len(user_message) + response_schema_characters
                    ),
                },
            )
        try:
            provider_result = await self.backend.run_authoring(
                instructions=instructions,
                initial_user_message=user_message,
                tool_definitions=[
                    FunctionToolDefinition(
                        name=tool_name,
                        description=tool_description,
                        parameters=response_schema,
                    )
                ],
                tool_caller=capture,
                max_rounds=max_rounds,
                required_tool_name=tool_name,
            )
        except ProviderAdapterError as exc:
            if trace is not None:
                details: dict[str, object] = {
                    "tool_name": tool_name,
                    "error": str(exc),
                    "provider_response": exc.report_facts.get("provider_response", {}),
                }
                transport = exc.report_facts.get("transport")
                if isinstance(transport, dict):
                    details["transport"] = transport
                trace.record(
                    "structured_request_finished",
                    status=exc.status,
                    details=details,
                    payload={
                        "tool_trace": [
                            {
                                "round": call.round,
                                "name": call.name,
                                "arguments": call.arguments,
                            }
                            for call in exc.tool_trace
                        ]
                    },
                )
            raise
        if accepted is None:
            if trace is not None:
                trace.record(
                    "structured_request_finished",
                    status="missing_submission",
                    details={"tool_name": tool_name},
                )
            raise RuntimeError(
                f"Provider finished without submitting required structured output {tool_name!r}."
            )
        if trace is not None:
            trace.record(
                "structured_request_finished",
                status="succeeded",
                details={
                    "tool_name": tool_name,
                    "provider_response": provider_result.report_facts.get("provider_response", {}),
                },
                payload=accepted.model_dump(mode="json"),
            )
        return accepted
