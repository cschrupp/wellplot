###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################

"""Shared helpers for OpenAI-style Responses API provider adapters."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from jsonschema import Draft202012Validator

from wellplot.errors import DependencyUnavailableError

from ..core import (
    AuthoringToolCall,
    FunctionToolDefinition,
    ProviderAdapterError,
    ProviderRunResult,
    ToolCaller,
)


def load_api_key_from_sources(
    *,
    server_root: str | Path,
    api_key: str | None,
    env_var_names: tuple[str, ...],
    env_file_keys: tuple[str, ...],
    text_file_names: tuple[str, ...],
    missing_message: str,
) -> tuple[str, str]:
    """Load one API key from explicit input or local ignored sources."""
    if api_key is not None and api_key.strip():
        return api_key.strip(), "explicit api_key argument"

    for env_var_name in env_var_names:
        env_key = os.getenv(env_var_name, "").strip()
        if env_key:
            return env_key, f"environment variable {env_var_name}"

    root = Path(server_root).resolve()
    env_paths = (root / ".env.local", root / ".env")
    env_key_names = set(env_file_keys)
    for env_path in env_paths:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            normalized_key = key.strip()
            if normalized_key not in env_key_names or not value.strip():
                continue
            token = value.strip().strip('"').strip("'")
            if token:
                return token, str(env_path.relative_to(root))

    for file_name in text_file_names:
        text_path = root / file_name
        if not text_path.exists():
            continue
        token = text_path.read_text(encoding="utf-8").strip()
        if token:
            return token, str(text_path.relative_to(root))

    raise RuntimeError(missing_message)


def load_openai_client(
    *,
    api_key: str,
    base_url: str | None = None,
    timeout: float | None = None,
) -> object:
    """Import and construct the optional OpenAI client lazily."""
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise DependencyUnavailableError(
            "Install `wellplot[agent]` or add the `openai` package to use an "
            "OpenAI-based authoring session."
        ) from exc

    client_kwargs: dict[str, object] = {"api_key": api_key}
    if base_url is not None and base_url.strip():
        client_kwargs["base_url"] = base_url.strip()
    if timeout is not None:
        if timeout <= 0:
            raise ValueError("OpenAI client timeout must be greater than zero seconds.")
        client_kwargs["timeout"] = timeout
    return OpenAI(**client_kwargs)


def _required_tool_name(
    tool_definitions: list[FunctionToolDefinition],
    required_tool_name: str | None,
) -> str | None:
    """Validate and normalize an optional required provider function name."""
    if required_tool_name is None:
        return None
    normalized = required_tool_name.strip()
    if not normalized:
        return None
    available_names = {tool.name for tool in tool_definitions}
    if normalized not in available_names:
        raise ProviderAdapterError(
            "invalid_required_tool",
            f"Required tool {normalized!r} was not supplied to the provider adapter.",
        )
    return normalized


def _required_tool_submission_outcome(payload: object) -> bool | None:
    """Return a required submission outcome, when the tool reports one.

    ``None`` preserves the normal tool-loop behavior for required operational
    tools. Typed compiler submissions explicitly return either ``accepted`` or
    ``is_error``; those signals determine whether the adapter must request one
    corrective submission or can end the stage without a prose round-trip.
    """
    if not isinstance(payload, Mapping):
        return None
    accepted = payload.get("accepted")
    if isinstance(accepted, bool):
        return accepted
    if payload.get("is_error") is True:
        return False
    return None


def _tool_argument_schema_error(
    *,
    tool_name: str,
    arguments: dict[str, object],
    validators: Mapping[str, Draft202012Validator],
) -> str | None:
    """Return the first advertised-schema violation for one provider tool call."""
    validator = validators.get(tool_name)
    if validator is None:
        return f"Tool {tool_name!r} is not part of the advertised MCP contract."

    errors = sorted(
        validator.iter_errors(arguments),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return None

    error = errors[0]
    path = ".".join(str(part) for part in error.absolute_path)
    location = f" at {path!r}" if path else ""
    return (
        f"Tool {tool_name!r} arguments do not match the advertised MCP schema"
        f"{location}: {error.message}. Correct the arguments and retry the same "
        "tool using native JSON types; do not serialize nested objects or arrays "
        "as strings."
    )


async def run_responses_authoring_loop(
    *,
    client: object,
    model: str,
    provider_label: str,
    instructions: str,
    initial_user_message: str,
    tool_definitions: list[FunctionToolDefinition],
    tool_caller: ToolCaller,
    max_rounds: int,
    required_tool_name: str | None = None,
) -> ProviderRunResult:
    """Run one OpenAI-style Responses loop and replay tool calls through MCP."""
    response = None
    final_text = ""
    pending_input: list[dict[str, object]] = [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": initial_user_message,
                }
            ],
        }
    ]
    tool_trace: list[AuthoringToolCall] = []
    response_statuses: list[str] = []
    response_rounds = 0
    function_tools = [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
        for tool in tool_definitions
    ]
    tool_argument_validators = {
        tool.name: Draft202012Validator(tool.parameters) for tool in tool_definitions
    }
    if not function_tools:
        raise RuntimeError(f"No function tools were provided to the {provider_label} backend.")
    required_name = _required_tool_name(tool_definitions, required_tool_name)
    required_tool_called = False
    required_submission_accepted = False
    controller_stopped = False
    schema_validation_retries = 0

    for round_index in range(1, max_rounds + 1):
        response_rounds = round_index
        request_kwargs: dict[str, object] = {
            "model": model,
            "tools": function_tools,
        }
        if response is None:
            request_kwargs["instructions"] = instructions
            request_kwargs["input"] = pending_input
        else:
            request_kwargs["previous_response_id"] = getattr(response, "id", None)
            request_kwargs["input"] = pending_input
        if required_name is not None and not required_tool_called:
            request_kwargs["tool_choice"] = {
                "type": "function",
                "name": required_name,
            }
        response = client.responses.create(**request_kwargs)
        response_status = getattr(response, "status", None)
        if response_status is not None:
            response_statuses.append(str(response_status))
            if str(response_status).lower() == "incomplete":
                raise ProviderAdapterError(
                    "truncated_response",
                    f"The {provider_label} Responses request ended incomplete.",
                )
        output = getattr(response, "output", [])
        function_calls = [item for item in output if getattr(item, "type", None) == "function_call"]
        if not function_calls:
            response_text = getattr(response, "output_text", "")
            final_text = response_text if isinstance(response_text, str) else ""
            if not final_text.strip():
                raise ProviderAdapterError(
                    "empty_response",
                    f"The {provider_label} Responses response contained no text or tool calls.",
                )
            if required_name is not None and not required_tool_called:
                raise ProviderAdapterError(
                    "required_tool_not_called",
                    f"The {provider_label} provider returned without calling required tool "
                    f"{required_name!r}.",
                )
            break

        pending_input = []
        for call in function_calls:
            call_name = str(getattr(call, "name", "") or "").strip()
            call_id = str(getattr(call, "call_id", "") or "").strip()
            if not call_name or not call_id:
                raise ProviderAdapterError(
                    "truncated_tool_call",
                    f"The {provider_label} provider emitted a tool call without a stable "
                    "name or call id.",
                )
            if (
                required_name is not None
                and not required_tool_called
                and call_name != required_name
            ):
                raise ProviderAdapterError(
                    "unexpected_tool_call",
                    f"The {provider_label} provider called {call_name!r} before required "
                    f"tool {required_name!r}.",
                )
            try:
                arguments = json.loads(getattr(call, "arguments", "") or "{}")
            except json.JSONDecodeError as exc:
                raise ProviderAdapterError(
                    "malformed_tool_arguments",
                    f"The {provider_label} provider emitted malformed JSON arguments for "
                    f"tool {call_name!r}.",
                ) from exc
            if not isinstance(arguments, dict):
                raise ProviderAdapterError(
                    "malformed_tool_arguments",
                    f"The {provider_label} provider emitted non-object arguments for tool "
                    f"{call_name!r}.",
                )
            tool_trace.append(
                AuthoringToolCall(
                    round=round_index,
                    name=call_name,
                    arguments=arguments,
                )
            )
            schema_error = _tool_argument_schema_error(
                tool_name=call_name,
                arguments=arguments,
                validators=tool_argument_validators,
            )
            if schema_error is None:
                tool_payload = await tool_caller(call_name, arguments)
            else:
                schema_validation_retries += 1
                tool_payload = {
                    "is_error": True,
                    "error": schema_error,
                }
            if call_name == required_name:
                submission_outcome = _required_tool_submission_outcome(tool_payload)
                required_tool_called = submission_outcome is not False
                required_submission_accepted = submission_outcome is True
            pending_input.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(tool_payload),
                }
            )
            control = tool_payload.get("_agent_control")
            if isinstance(control, Mapping) and control.get("action") == "stop":
                final_text = str(control.get("message") or "")
                controller_stopped = True
                break
            if required_submission_accepted:
                message = tool_payload.get("message") if isinstance(tool_payload, Mapping) else None
                final_text = message if isinstance(message, str) else ""
                break
        if controller_stopped or required_submission_accepted:
            break
    else:
        provider_response_facts: dict[str, object] = {
            "adapter": "responses",
            "rounds": response_rounds,
            "tool_calls_emitted": bool(tool_trace),
            "finish_reasons": response_statuses,
            "response_statuses": response_statuses,
            "required_tool_name": required_name,
            "required_submission_accepted": required_submission_accepted,
            "controller_stopped": controller_stopped,
        }
        if schema_validation_retries:
            provider_response_facts["schema_validation_retries"] = schema_validation_retries
        raise ProviderAdapterError(
            "round_budget_exhausted",
            f"The {provider_label} authoring loop exceeded {max_rounds} rounds.",
            tool_trace=tuple(tool_trace),
            report_facts={"provider_response": provider_response_facts},
        )

    if response is not None and not final_text.strip() and not required_submission_accepted:
        summary_response = client.responses.create(
            model=model,
            previous_response_id=getattr(response, "id", None),
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Summarize the applied draft changes in three concise "
                                "bullet points without calling more tools."
                            ),
                        }
                    ],
                }
            ],
        )
        summary_text = getattr(summary_response, "output_text", "")
        final_text = summary_text if isinstance(summary_text, str) else ""

    provider_response_facts = {
        "adapter": "responses",
        "rounds": response_rounds,
        "tool_calls_emitted": bool(tool_trace),
        "finish_reasons": response_statuses,
        "response_statuses": response_statuses,
        "required_tool_name": required_name,
        "required_submission_accepted": required_submission_accepted,
        "controller_stopped": controller_stopped,
    }
    if schema_validation_retries:
        provider_response_facts["schema_validation_retries"] = schema_validation_retries
    return ProviderRunResult(
        final_text=final_text,
        tool_trace=tuple(tool_trace),
        report_facts={"provider_response": provider_response_facts},
    )
