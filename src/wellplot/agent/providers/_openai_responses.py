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
from pathlib import Path

from wellplot.errors import DependencyUnavailableError

from ..core import AuthoringToolCall, FunctionToolDefinition, ProviderRunResult, ToolCaller


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
) -> object:
    """Import and construct the optional OpenAI client lazily."""
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise DependencyUnavailableError(
            "Install `wellplot[agent]` or add the `openai` package to use an "
            "OpenAI-based authoring session."
        ) from exc

    client_kwargs: dict[str, str] = {"api_key": api_key}
    if base_url is not None and base_url.strip():
        client_kwargs["base_url"] = base_url.strip()
    return OpenAI(**client_kwargs)


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
    function_tools = [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
        for tool in tool_definitions
    ]
    if not function_tools:
        raise RuntimeError(f"No function tools were provided to the {provider_label} backend.")

    for round_index in range(1, max_rounds + 1):
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
        response = client.responses.create(**request_kwargs)
        output = getattr(response, "output", [])
        function_calls = [item for item in output if getattr(item, "type", None) == "function_call"]
        if not function_calls:
            response_text = getattr(response, "output_text", "")
            final_text = response_text if isinstance(response_text, str) else ""
            break

        pending_input = []
        for call in function_calls:
            arguments = json.loads(getattr(call, "arguments", "") or "{}")
            if not isinstance(arguments, dict):
                raise RuntimeError("Expected tool-call arguments to decode into a mapping.")
            tool_trace.append(
                AuthoringToolCall(
                    round=round_index,
                    name=getattr(call, "name", ""),
                    arguments=arguments,
                )
            )
            tool_payload = await tool_caller(getattr(call, "name", ""), arguments)
            pending_input.append(
                {
                    "type": "function_call_output",
                    "call_id": getattr(call, "call_id", ""),
                    "output": json.dumps(tool_payload),
                }
            )
    else:
        raise RuntimeError(f"The {provider_label} authoring loop exceeded {max_rounds} rounds.")

    if response is not None and not final_text.strip():
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

    return ProviderRunResult(
        final_text=final_text,
        tool_trace=tuple(tool_trace),
    )
