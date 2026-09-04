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
from dataclasses import dataclass

from jsonschema import Draft202012Validator

from ..core import (
    AuthoringToolCall,
    FunctionToolDefinition,
    ProviderAdapterError,
    ProviderRunResult,
    ToolCaller,
)
from ..execution_trace import assistant_response_trace_payload, current_agent_trace
from ._openai_responses import (
    _required_tool_name,
    _required_tool_submission_outcome,
    _tool_argument_schema_error,
)

_MAX_TRANSPORT_ERROR_CHARACTERS = 500


@dataclass(frozen=True)
class _PartialChatResponse:
    """Provider response fragments received before a stream interruption."""

    text: str
    function_calls: list[dict[str, str]]
    finish_reason: str | None


class _ChatStreamInterrupted(RuntimeError):
    """Carry partial streamed output when a provider closes the response early."""

    def __init__(self, cause: BaseException, partial_response: _PartialChatResponse) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.partial_response = partial_response


def _transport_exception_details(exc: BaseException) -> dict[str, str]:
    """Return bounded transport evidence suitable for a trace report fact."""
    message = str(exc).strip()
    if len(message) > _MAX_TRANSPORT_ERROR_CHARACTERS:
        message = message[: _MAX_TRANSPORT_ERROR_CHARACTERS - 3].rstrip() + "..."
    return {
        "exception_type": type(exc).__name__,
        "exception_message": message,
    }


def _partial_response_trace_payload(
    partial_response: _PartialChatResponse | None,
) -> dict[str, object] | None:
    """Project incomplete streamed output into the durable response trace shape."""
    if partial_response is None:
        return None
    return {
        "assistant_response": assistant_response_trace_payload(partial_response.text),
        "tool_calls": partial_response.function_calls,
        "finish_reason": partial_response.finish_reason,
    }


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
    try:
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
    except Exception as exc:
        raise _ChatStreamInterrupted(
            exc,
            _PartialChatResponse(
                text="".join(content_parts),
                function_calls=[calls_by_index[index] for index in sorted(calls_by_index)],
                finish_reason=finish_reason,
            ),
        ) from exc

    return (
        "".join(content_parts),
        [calls_by_index[index] for index in sorted(calls_by_index)],
        finish_reason,
    )


def _request_chat_response(
    *,
    client: object,
    request_kwargs: dict[str, object],
    provider_label: str,
) -> tuple[str, list[dict[str, str]], str | None]:
    """Send one streamed request and normalize provider transport failures."""
    try:
        response = client.chat.completions.create(**request_kwargs)
        return _chat_response_parts(response)
    except ProviderAdapterError:
        raise
    except _ChatStreamInterrupted as exc:
        cause = exc.cause
        raise ProviderAdapterError(
            "transport_failure",
            f"The {provider_label} chat request failed while receiving a response.",
            final_text=exc.partial_response.text,
            report_facts={
                "transport": _transport_exception_details(cause),
                "partial_response": _partial_response_trace_payload(exc.partial_response),
            },
        ) from cause
    except Exception as exc:
        raise ProviderAdapterError(
            "transport_failure",
            f"The {provider_label} chat request failed while receiving a response.",
            report_facts={"transport": _transport_exception_details(exc)},
        ) from exc


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
    tool_argument_validators = {
        tool.name: Draft202012Validator(tool.parameters) for tool in tool_definitions
    }
    required_name = _required_tool_name(tool_definitions, required_tool_name)
    required_tool_called = False
    required_submission_accepted = False
    tool_trace: list[AuthoringToolCall] = []
    final_text = ""
    finish_reasons: list[str] = []
    response_rounds = 0
    controller_stopped = False
    schema_validation_retries = 0

    for round_index in range(1, max_rounds + 1):
        response_rounds = round_index
        trace = current_agent_trace()
        if trace is not None:
            trace.record(
                "provider_round_started",
                status="started",
                details={
                    "adapter": "chat_completions",
                    "provider": provider_label,
                    "model": model,
                    "round": round_index,
                    "required_tool_name": required_name,
                },
            )
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
        try:
            response_text, function_calls, finish_reason = _request_chat_response(
                client=client,
                request_kwargs=request_kwargs,
                provider_label=provider_label,
            )
        except ProviderAdapterError as exc:
            if trace is not None:
                transport = exc.report_facts.get("transport")
                partial_response = exc.report_facts.get("partial_response")
                details: dict[str, object] = {"round": round_index, "error": str(exc)}
                if isinstance(transport, dict):
                    details["transport"] = transport
                failure_payload: dict[str, object] = {}
                if isinstance(partial_response, dict):
                    failure_payload["partial_response"] = partial_response
                if tool_trace:
                    failure_payload["prior_tool_calls"] = [
                        {
                            "round": call.round,
                            "name": call.name,
                            "arguments": call.arguments,
                        }
                        for call in tool_trace
                    ]
                trace.record(
                    "provider_round_finished",
                    status=exc.status,
                    details=details,
                    payload=failure_payload or None,
                )
            raise ProviderAdapterError(
                exc.status,
                str(exc),
                tool_trace=(*tool_trace, *exc.tool_trace),
                final_text=exc.final_text or final_text,
                report_facts=exc.report_facts,
            ) from exc
        if trace is not None:
            trace.record(
                "provider_round_finished",
                status="received",
                details={
                    "round": round_index,
                    "finish_reason": finish_reason,
                    "tool_names": [call["name"] for call in function_calls],
                    "text_characters": len(response_text),
                },
                payload={
                    "assistant_response": assistant_response_trace_payload(response_text),
                    "tool_calls": function_calls,
                },
            )
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
            schema_error = _tool_argument_schema_error(
                tool_name=call_name,
                arguments=arguments,
                validators=tool_argument_validators,
            )
            if schema_error is None:
                tool_payload = await tool_caller(call_name, arguments)
            else:
                schema_validation_retries += 1
                if trace is not None:
                    trace.record(
                        "provider_submission_rejected",
                        status="invalid_schema",
                        details={
                            "round": round_index,
                            "tool_name": call_name,
                            "error": schema_error,
                        },
                        payload=arguments,
                    )
                tool_payload = {
                    "is_error": True,
                    "error": schema_error,
                }
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
        provider_response_facts: dict[str, object] = {
            "adapter": "chat_completions",
            "rounds": response_rounds,
            "tool_calls_emitted": bool(tool_trace),
            "finish_reasons": finish_reasons,
            "response_statuses": [],
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
        final_text, _, summary_finish_reason = _request_chat_response(
            client=client,
            request_kwargs={
                "model": model,
                "messages": messages,
                "stream": True,
            },
            provider_label=provider_label,
        )
        if summary_finish_reason is not None:
            finish_reasons.append(summary_finish_reason)

    provider_response_facts = {
        "adapter": "chat_completions",
        "rounds": response_rounds,
        "tool_calls_emitted": bool(tool_trace),
        "finish_reasons": finish_reasons,
        "response_statuses": [],
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
