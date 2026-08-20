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

"""Chat Completions adapter for OpenAI-compatible authoring providers."""

from __future__ import annotations

import json

from ..core import (
    AuthoringToolCall,
    FunctionToolDefinition,
    ProviderAdapterError,
    ProviderRunResult,
    ToolCaller,
)
from ._openai_responses import _required_tool_name, _required_tool_submission_outcome


def _message_text(message: object) -> str:
    """Return plain text from an OpenAI-style chat message."""
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""


def _chat_response_parts(
    response: object,
) -> tuple[str, list[dict[str, str]], str | None]:
    """Collect text, tool calls, and finish reason from provider output."""
    choices = getattr(response, "choices", None)
    if choices is not None:
        if not choices:
            return "", [], None
        choice = choices[0]
        message = getattr(choice, "message", None)
        if message is None:
            return "", [], getattr(choice, "finish_reason", None)
        function_calls: list[dict[str, str]] = []
        for call in list(getattr(message, "tool_calls", None) or []):
            function = getattr(call, "function", None)
            if function is None:
                continue
            function_calls.append(
                {
                    "id": str(getattr(call, "id", "") or ""),
                    "name": str(getattr(function, "name", "") or ""),
                    "arguments": str(getattr(function, "arguments", "") or ""),
                }
            )
        return _message_text(message), function_calls, getattr(choice, "finish_reason", None)

    content_parts: list[str] = []
    calls_by_index: dict[int, dict[str, str]] = {}
    finish_reason: str | None = None
    for chunk in response:
        chunk_choices = getattr(chunk, "choices", [])
        for choice in chunk_choices:
            current_finish_reason = getattr(choice, "finish_reason", None)
            if current_finish_reason:
                finish_reason = str(current_finish_reason)
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            content = getattr(delta, "content", None)
            if isinstance(content, str):
                content_parts.append(content)
            for call in list(getattr(delta, "tool_calls", None) or []):
                index = int(getattr(call, "index", 0) or 0)
                current = calls_by_index.setdefault(
                    index,
                    {"id": "", "name": "", "arguments": ""},
                )
                call_id = getattr(call, "id", None)
                if call_id:
                    current["id"] = str(call_id)
                function = getattr(call, "function", None)
                if function is None:
                    continue
                name = getattr(function, "name", None)
                if name:
                    current["name"] += str(name)
                arguments = getattr(function, "arguments", None)
                if arguments:
                    current["arguments"] += str(arguments)

    return (
        "".join(content_parts),
        [calls_by_index[index] for index in sorted(calls_by_index)],
        finish_reason,
    )


async def run_chat_completions_authoring_loop(
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
    """Run one Chat Completions loop and replay tool calls through MCP."""
    if not tool_definitions:
        raise RuntimeError(f"No function tools were provided to the {provider_label} backend.")

    messages: list[dict[str, object]] = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": initial_user_message},
    ]
    function_tools = [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tool_definitions
    ]
    required_name = _required_tool_name(tool_definitions, required_tool_name)
    required_tool_called = False
    required_submission_accepted = False
    tool_trace: list[AuthoringToolCall] = []
    final_text = ""
    finish_reasons: list[str] = []
    response_rounds = 0
    controller_stopped = False

    for round_index in range(1, max_rounds + 1):
        response_rounds = round_index
        request_kwargs: dict[str, object] = {
            "model": model,
            "messages": messages,
            "tools": function_tools,
            "stream": True,
        }
        if required_name is not None and not required_tool_called:
            request_kwargs["tool_choice"] = {
                "type": "function",
                "function": {"name": required_name},
            }
        response = client.chat.completions.create(**request_kwargs)
        response_text, function_calls, finish_reason = _chat_response_parts(response)
        if finish_reason is not None:
            finish_reasons.append(finish_reason)
            if finish_reason.lower() in {"length", "content_filter"}:
                raise ProviderAdapterError(
                    "truncated_response",
                    f"The {provider_label} chat response ended with {finish_reason!r}.",
                )
        if not response_text and not function_calls:
            raise ProviderAdapterError(
                "empty_response",
                f"The {provider_label} chat response contained no text or tool calls.",
            )
        if not function_calls:
            final_text = response_text
            if required_name is not None and not required_tool_called:
                raise ProviderAdapterError(
                    "required_tool_not_called",
                    f"The {provider_label} provider returned without calling required tool "
                    f"{required_name!r}.",
                )
            break

        assistant_tool_calls: list[dict[str, object]] = []
        for call in function_calls:
            call_name = call["name"].strip()
            call_id = call["id"].strip()
            raw_arguments = call["arguments"]
            if not call_name or not call_id or not raw_arguments.strip():
                raise ProviderAdapterError(
                    "truncated_tool_call",
                    f"The {provider_label} provider emitted an incomplete streamed tool call.",
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
                arguments = json.loads(raw_arguments)
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

            assistant_tool_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": call_name,
                        "arguments": json.dumps(arguments),
                    },
                }
            )
            tool_trace.append(
                AuthoringToolCall(
                    round=round_index,
                    name=call_name,
                    arguments=arguments,
                )
            )
            tool_payload = await tool_caller(call_name, arguments)
            if call_name == required_name:
                submission_outcome = _required_tool_submission_outcome(tool_payload)
                required_tool_called = submission_outcome is not False
                required_submission_accepted = submission_outcome is True
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(tool_payload),
                }
            )
            control = tool_payload.get("_agent_control")
            if isinstance(control, dict) and control.get("action") == "stop":
                final_text = str(control.get("message") or "")
                controller_stopped = True
                break
            if required_submission_accepted:
                message = tool_payload.get("message") if isinstance(tool_payload, dict) else None
                final_text = message if isinstance(message, str) else ""
                break

        messages.insert(
            len(messages) - len(assistant_tool_calls),
            {
                "role": "assistant",
                "content": response_text or None,
                "tool_calls": assistant_tool_calls,
            },
        )
        if controller_stopped or required_submission_accepted:
            break
    else:
        raise ProviderAdapterError(
            "round_budget_exhausted",
            f"The {provider_label} authoring loop exceeded {max_rounds} rounds.",
            tool_trace=tuple(tool_trace),
            report_facts={
                "provider_response": {
                    "adapter": "chat_completions",
                    "rounds": response_rounds,
                    "tool_calls_emitted": bool(tool_trace),
                    "finish_reasons": finish_reasons,
                    "response_statuses": [],
                    "required_tool_name": required_name,
                    "required_submission_accepted": required_submission_accepted,
                    "controller_stopped": controller_stopped,
                }
            },
        )

    if not final_text.strip() and not required_submission_accepted:
        messages.append(
            {
                "role": "user",
                "content": (
                    "Summarize the applied draft changes in three concise bullet points "
                    "without calling more tools."
                ),
            }
        )
        summary_response = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )
        final_text, _, summary_finish_reason = _chat_response_parts(summary_response)
        if summary_finish_reason is not None:
            finish_reasons.append(summary_finish_reason)

    return ProviderRunResult(
        final_text=final_text,
        tool_trace=tuple(tool_trace),
        report_facts={
            "provider_response": {
                "adapter": "chat_completions",
                "rounds": response_rounds,
                "tool_calls_emitted": bool(tool_trace),
                "finish_reasons": finish_reasons,
                "response_statuses": [],
                "required_tool_name": required_name,
                "required_submission_accepted": required_submission_accepted,
                "controller_stopped": controller_stopped,
            }
        },
    )
