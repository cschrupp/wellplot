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

"""Tests for the OpenAI-compatible Chat Completions adapter."""

from __future__ import annotations

from collections.abc import Iterator
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest

from wellplot.agent.core import FunctionToolDefinition, ProviderAdapterError
from wellplot.agent.execution_trace import AgentRunTrace, bind_agent_trace, read_agent_trace
from wellplot.agent.providers._openai_chat import run_chat_completions_authoring_loop


class _FakeCompletions:
    """Minimal synchronous Chat Completions client for adapter tests."""

    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        request = dict(kwargs)
        messages = request.get("messages")
        if isinstance(messages, list):
            request["messages"] = [dict(message) for message in messages]
        self.requests.append(request)
        return self.responses.pop(0)


class _FakeStream:
    """Iterable wrapper for streamed Chat Completions chunks."""

    def __init__(self, chunks: list[object]) -> None:
        self.chunks = chunks

    def __iter__(self) -> Iterator[object]:
        return iter(self.chunks)


class _BrokenStream:
    """Raise a representative gateway failure while reading a response body."""

    def __iter__(self) -> Iterator[object]:
        raise RuntimeError("peer closed connection without sending complete message body")


class _PartiallyBrokenStream:
    """Yield text and a partial tool call before a gateway interruption."""

    def __iter__(self) -> Iterator[object]:
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content="I will submit ",
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="call-partial",
                                function=SimpleNamespace(
                                    name="submit_reconstruction_plan",
                                    arguments='{"summary":"CBL',
                                ),
                            )
                        ],
                    )
                )
            ]
        )
        raise RuntimeError("peer closed connection without sending complete message body")


def _chat_response(
    *,
    content: str | None,
    tool_calls: list[object] | None = None,
    finish_reason: str | None = None,
) -> object:
    """Build one SDK-shaped chat completion response."""
    message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def test_chat_adapter_replays_function_tool_calls() -> None:
    """Replay Chat Completions tool calls and return the final assistant text."""
    completions = _FakeCompletions(
        [
            _FakeStream(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content="I will inspect the draft.",
                                    tool_calls=[
                                        SimpleNamespace(
                                            index=0,
                                            id="call-1",
                                            function=SimpleNamespace(
                                                name="inspect_logfile",
                                                arguments='{"logfile_path":',
                                            ),
                                        )
                                    ],
                                )
                            )
                        ]
                    ),
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content=None,
                                    tool_calls=[
                                        SimpleNamespace(
                                            index=0,
                                            function=SimpleNamespace(
                                                arguments='"draft.log.yaml"}',
                                            ),
                                        )
                                    ],
                                )
                            )
                        ]
                    ),
                ]
            ),
            _chat_response(content="The draft was inspected.", finish_reason="stop"),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    tool_calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        tool_calls.append((name, arguments))
        return {"ok": True}

    result = anyio.run(
        partial(
            run_chat_completions_authoring_loop,
            client=client,
            model="local-model",
            provider_label="OpenAI-compatible",
            instructions="Use the available tools.",
            initial_user_message="Inspect the draft.",
            tool_definitions=[
                FunctionToolDefinition(
                    name="inspect_logfile",
                    description="Inspect a draft.",
                    parameters={"type": "object"},
                )
            ],
            tool_caller=call_tool,
            max_rounds=2,
            required_tool_name="inspect_logfile",
        )
    )

    assert result.final_text == "The draft was inspected."
    assert result.report_facts["provider_response"] == {
        "adapter": "chat_completions",
        "rounds": 2,
        "tool_calls_emitted": True,
        "finish_reasons": ["stop"],
        "response_statuses": [],
        "required_tool_name": "inspect_logfile",
        "required_submission_accepted": False,
        "controller_stopped": False,
    }
    assert [(call.name, call.arguments) for call in result.tool_trace] == [
        ("inspect_logfile", {"logfile_path": "draft.log.yaml"})
    ]
    assert tool_calls == [("inspect_logfile", {"logfile_path": "draft.log.yaml"})]
    assert [message["role"] for message in completions.requests[1]["messages"]] == [
        "system",
        "user",
        "assistant",
        "tool",
    ]
    assert completions.requests[0]["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "inspect_logfile",
                "description": "Inspect a draft.",
                "parameters": {"type": "object"},
            },
        }
    ]
    assert completions.requests[0]["stream"] is True
    assert completions.requests[1]["stream"] is True
    assert completions.requests[0]["tool_choice"] == {
        "type": "function",
        "function": {"name": "inspect_logfile"},
    }
    assert "tool_choice" not in completions.requests[1]


def test_chat_adapter_normalizes_stream_transport_failure() -> None:
    """Expose interrupted streamed responses through a stable provider status."""
    completions = _FakeCompletions([_BrokenStream()])
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    async def call_tool(_: str, __: dict[str, object]) -> dict[str, object]:
        raise AssertionError("the provider must fail before calling a tool")

    with pytest.raises(ProviderAdapterError) as exc_info:
        anyio.run(
            partial(
                run_chat_completions_authoring_loop,
                client=client,
                model="local-model",
                provider_label="OpenAI-compatible",
                instructions="Use the available tools.",
                initial_user_message="Inspect the draft.",
                tool_definitions=[
                    FunctionToolDefinition(
                        name="inspect_logfile",
                        description="Inspect a draft.",
                        parameters={"type": "object"},
                    )
                ],
                tool_caller=call_tool,
                max_rounds=1,
            )
        )

    assert exc_info.value.status == "transport_failure"


def test_chat_adapter_traces_partial_stream_transport_failure(tmp_path: Path) -> None:
    """Retain bounded provider fragments and transport evidence after a stream breaks."""
    completions = _FakeCompletions([_PartiallyBrokenStream()])
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    trace = AgentRunTrace.create(logfile_path=tmp_path / "draft.log.yaml", mode="reconstruct")

    async def call_tool(_: str, __: dict[str, object]) -> dict[str, object]:
        raise AssertionError("the provider must fail before calling a tool")

    async def run_with_trace() -> None:
        with bind_agent_trace(trace):
            await run_chat_completions_authoring_loop(
                client=client,
                model="local-model",
                provider_label="OpenAI-compatible",
                instructions="Use the available tools.",
                initial_user_message="Inspect the draft.",
                tool_definitions=[
                    FunctionToolDefinition(
                        name="submit_reconstruction_plan",
                        description="Submit a reconstruction plan.",
                        parameters={"type": "object"},
                    )
                ],
                tool_caller=call_tool,
                max_rounds=1,
                required_tool_name="submit_reconstruction_plan",
            )

    with pytest.raises(ProviderAdapterError) as exc_info:
        anyio.run(run_with_trace)

    assert exc_info.value.status == "transport_failure"
    assert exc_info.value.final_text == "I will submit "
    assert exc_info.value.report_facts["transport"] == {
        "exception_type": "RuntimeError",
        "exception_message": "peer closed connection without sending complete message body",
    }

    interrupted = next(
        event
        for event in read_agent_trace(trace.path)
        if event.event == "provider_round_finished" and event.status == "transport_failure"
    )

    assert interrupted.details["transport"] == exc_info.value.report_facts["transport"]
    assert isinstance(interrupted.payload, dict)
    partial_response = interrupted.payload["partial_response"]
    assert isinstance(partial_response, dict)
    assistant_response = partial_response["assistant_response"]
    assert assistant_response == {
        "original_characters": 14,
        "sha256": "e1ba5c1e854bd28aa9e5e81840c63a1298c6657d8f0dfb295b8db3fd1c743d5c",
        "truncated": False,
        "excerpt": "I will submit ",
    }
    assert partial_response["tool_calls"] == [
        {
            "id": "call-partial",
            "name": "submit_reconstruction_plan",
            "arguments": '{"summary":"CBL',
        }
    ]
    assert partial_response["finish_reason"] is None


def test_chat_adapter_preserves_prior_tool_calls_after_transport_failure(tmp_path: Path) -> None:
    """Keep completed calls inspectable when a corrective round loses its stream."""
    completions = _FakeCompletions(
        [
            _chat_response(
                content=None,
                tool_calls=[
                    SimpleNamespace(
                        id="call-1",
                        function=SimpleNamespace(
                            name="submit_report_artifact",
                            arguments='{"title":"First report attempt"}',
                        ),
                    )
                ],
                finish_reason="tool_calls",
            ),
            _BrokenStream(),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    trace = AgentRunTrace.create(logfile_path=tmp_path / "draft.log.yaml", mode="reconstruct")

    async def reject_submission(_: str, __: dict[str, object]) -> dict[str, object]:
        return {"is_error": True, "error": "correct the report artifact"}

    async def run_with_trace() -> None:
        with bind_agent_trace(trace):
            await run_chat_completions_authoring_loop(
                client=client,
                model="local-model",
                provider_label="OpenAI-compatible",
                instructions="Submit one report artifact.",
                initial_user_message="Compile the report.",
                tool_definitions=[
                    FunctionToolDefinition(
                        name="submit_report_artifact",
                        description="Submit one report artifact.",
                        parameters={"type": "object"},
                    )
                ],
                tool_caller=reject_submission,
                max_rounds=2,
                required_tool_name="submit_report_artifact",
            )

    with pytest.raises(ProviderAdapterError) as exc_info:
        anyio.run(run_with_trace)

    assert [(call.name, call.arguments) for call in exc_info.value.tool_trace] == [
        ("submit_report_artifact", {"title": "First report attempt"})
    ]
    events = read_agent_trace(trace.path)
    received = next(
        event
        for event in events
        if event.event == "provider_round_finished" and event.status == "received"
    )
    failed = next(
        event
        for event in events
        if event.event == "provider_round_finished" and event.status == "transport_failure"
    )

    assert received.payload == {
        "assistant_response": {
            "original_characters": 0,
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "truncated": False,
            "excerpt": "",
        },
        "tool_calls": [
            {
                "id": "call-1",
                "name": "submit_report_artifact",
                "arguments": '{"title":"First report attempt"}',
            }
        ],
    }
    assert isinstance(failed.payload, dict)
    assert failed.payload["prior_tool_calls"] == [
        {
            "round": 1,
            "name": "submit_report_artifact",
            "arguments": {"title": "First report attempt"},
        }
    ]
    assert failed.payload["partial_response"] == {
        "assistant_response": {
            "original_characters": 0,
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "truncated": False,
            "excerpt": "",
        },
        "tool_calls": [],
        "finish_reason": None,
    }


def test_chat_adapter_records_provider_response_excerpt(tmp_path: Path) -> None:
    """Trace the assistant prose when a provider declines the required tool call."""
    response_text = "I will answer in prose instead of using a tool."
    completions = _FakeCompletions([_chat_response(content=response_text, finish_reason="stop")])
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    trace = AgentRunTrace.create(logfile_path=tmp_path / "draft.log.yaml", mode="reconstruct")

    async def call_tool(_: str, __: dict[str, object]) -> dict[str, object]:
        raise AssertionError("the provider did not emit a tool call")

    async def run_with_trace() -> None:
        with bind_agent_trace(trace):
            await run_chat_completions_authoring_loop(
                client=client,
                model="local-model",
                provider_label="OpenAI-compatible",
                instructions="Use the available tools.",
                initial_user_message="Inspect the draft.",
                tool_definitions=[
                    FunctionToolDefinition(
                        name="inspect_logfile",
                        description="Inspect a draft.",
                        parameters={"type": "object"},
                    )
                ],
                tool_caller=call_tool,
                max_rounds=1,
                required_tool_name="inspect_logfile",
            )

    with pytest.raises(ProviderAdapterError, match="required tool"):
        anyio.run(run_with_trace)

    received = next(
        event
        for event in read_agent_trace(trace.path)
        if event.event == "provider_round_finished" and event.status == "received"
    )

    assert isinstance(received.payload, dict)
    response_payload = received.payload["assistant_response"]
    assert response_payload["original_characters"] == len(response_text)
    assert len(response_payload["sha256"]) == 64
    assert response_payload["truncated"] is False
    assert response_payload["excerpt"] == response_text


def test_chat_adapter_honors_host_feedback_loop_stop() -> None:
    """Stop provider calls when the host controller reports a terminal state."""
    completions = _FakeCompletions(
        [
            _chat_response(
                content=None,
                tool_calls=[
                    SimpleNamespace(
                        id="call-1",
                        function=SimpleNamespace(
                            name="inspect_logfile",
                            arguments='{"logfile_path":"draft.log.yaml"}',
                        ),
                    )
                ],
                finish_reason="tool_calls",
            )
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    async def stop_loop(_: str, __: dict[str, object]) -> dict[str, object]:
        """Return the host controller's terminal feedback."""
        return {
            "ok": False,
            "_agent_control": {
                "action": "stop",
                "status": "blocked",
                "message": "Repeated inspection errors.",
            },
        }

    result = anyio.run(
        partial(
            run_chat_completions_authoring_loop,
            client=client,
            model="local-model",
            provider_label="OpenAI-compatible",
            instructions="Use the available tools.",
            initial_user_message="Inspect the draft.",
            tool_definitions=[
                FunctionToolDefinition(
                    name="inspect_logfile",
                    description="Inspect a draft.",
                    parameters={"type": "object"},
                )
            ],
            tool_caller=stop_loop,
            max_rounds=12,
        )
    )

    assert result.final_text == "Repeated inspection errors."
    assert len(completions.requests) == 1
    assert result.report_facts["provider_response"]["controller_stopped"] is True


def test_chat_adapter_preserves_partial_trace_on_round_exhaustion() -> None:
    """Expose the last submitted tool when a required stage exhausts its budget."""
    completions = _FakeCompletions(
        [
            _chat_response(
                content=None,
                tool_calls=[
                    SimpleNamespace(
                        id="call-1",
                        function=SimpleNamespace(
                            name="submit_report_intent",
                            arguments='{"coverage": []}',
                        ),
                    )
                ],
                finish_reason="tool_calls",
            )
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    async def reject_submission(_: str, __: dict[str, object]) -> dict[str, object]:
        """Keep the adapter in its bounded correction path."""
        return {"is_error": True, "error": "coverage is incomplete"}

    with pytest.raises(ProviderAdapterError) as caught:
        anyio.run(
            partial(
                run_chat_completions_authoring_loop,
                client=client,
                model="local-model",
                provider_label="OpenAI-compatible",
                instructions="Submit the typed report intent.",
                initial_user_message="Set the report title.",
                tool_definitions=[
                    FunctionToolDefinition(
                        name="submit_report_intent",
                        description="Submit one report fragment.",
                        parameters={"type": "object"},
                    )
                ],
                tool_caller=reject_submission,
                max_rounds=1,
                required_tool_name="submit_report_intent",
            )
        )

    assert caught.value.status == "round_budget_exhausted"
    assert [call.name for call in caught.value.tool_trace] == ["submit_report_intent"]
    assert caught.value.report_facts["provider_response"]["rounds"] == 1


def test_chat_adapter_preserves_and_enforces_correction_message_order() -> None:
    """Keep a rejected submission retryable until a correction is accepted."""
    completions = _FakeCompletions(
        [
            _FakeStream(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content=None,
                                    tool_calls=[
                                        SimpleNamespace(
                                            index=0,
                                            id="call-1",
                                            function=SimpleNamespace(
                                                name="submit_report_intent",
                                                arguments='{"title":"First"}',
                                            ),
                                        )
                                    ],
                                )
                            )
                        ]
                    )
                ]
            ),
            _FakeStream(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content=None,
                                    tool_calls=[
                                        SimpleNamespace(
                                            index=0,
                                            id="call-2",
                                            function=SimpleNamespace(
                                                name="submit_report_intent",
                                                arguments='{"title":"Corrected"}',
                                            ),
                                        )
                                    ],
                                )
                            )
                        ]
                    )
                ]
            ),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    received: list[dict[str, object]] = []

    async def call_tool(_: str, arguments: dict[str, object]) -> dict[str, object]:
        received.append(arguments)
        if len(received) == 1:
            return {"is_error": True, "error": "title must not be blank"}
        return {"accepted": True, "message": "Submission accepted."}

    result = anyio.run(
        partial(
            run_chat_completions_authoring_loop,
            client=client,
            model="local-model",
            provider_label="OpenAI-compatible",
            instructions="Submit the typed report intent.",
            initial_user_message="Set the report title.",
            tool_definitions=[
                FunctionToolDefinition(
                    name="submit_report_intent",
                    description="Submit one report fragment.",
                    parameters={"type": "object"},
                )
            ],
            tool_caller=call_tool,
            max_rounds=3,
            required_tool_name="submit_report_intent",
        )
    )

    assert result.final_text == "Submission accepted."
    assert received == [{"title": "First"}, {"title": "Corrected"}]
    assert len(completions.requests) == 2
    assert [message["role"] for message in completions.requests[1]["messages"]] == [
        "system",
        "user",
        "assistant",
        "tool",
    ]
    assert completions.requests[0]["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_report_intent"},
    }
    assert completions.requests[1]["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_report_intent"},
    }


def test_chat_adapter_rejects_schema_invalid_nested_arguments_before_dispatch() -> None:
    """Return nested type errors to the provider without calling MCP."""
    completions = _FakeCompletions(
        [
            _chat_response(
                content=None,
                tool_calls=[
                    SimpleNamespace(
                        id="call-1",
                        function=SimpleNamespace(
                            name="edit_curve_binding",
                            arguments=(
                                '{"track_id":"cbl","style":'
                                '"{\\"color\\":\\"#2142ff\\",\\"line_width\\":0.075}"}'
                            ),
                        ),
                    )
                ],
                finish_reason="tool_calls",
            ),
            _chat_response(
                content=None,
                tool_calls=[
                    SimpleNamespace(
                        id="call-2",
                        function=SimpleNamespace(
                            name="edit_curve_binding",
                            arguments=(
                                '{"track_id":"cbl","style":{"color":"#2142ff","line_width":0.075}}'
                            ),
                        ),
                    )
                ],
                finish_reason="tool_calls",
            ),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    dispatched: list[dict[str, object]] = []

    async def call_tool(_: str, arguments: dict[str, object]) -> dict[str, object]:
        dispatched.append(arguments)
        return {"accepted": True, "message": "Binding updated."}

    result = anyio.run(
        partial(
            run_chat_completions_authoring_loop,
            client=client,
            model="local-model",
            provider_label="OpenAI-compatible",
            instructions="Update the binding.",
            initial_user_message="Make the CBL curve blue.",
            tool_definitions=[
                FunctionToolDefinition(
                    name="edit_curve_binding",
                    description="Edit one curve binding.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "track_id": {"type": "string"},
                            "style": {
                                "type": "object",
                                "properties": {
                                    "color": {"type": "string"},
                                    "line_width": {"type": "number"},
                                },
                                "additionalProperties": False,
                            },
                        },
                        "required": ["track_id", "style"],
                        "additionalProperties": False,
                    },
                )
            ],
            tool_caller=call_tool,
            max_rounds=2,
            required_tool_name="edit_curve_binding",
        )
    )

    assert dispatched == [
        {
            "track_id": "cbl",
            "style": {"color": "#2142ff", "line_width": 0.075},
        }
    ]
    assert result.final_text == "Binding updated."
    assert result.report_facts["provider_response"]["schema_validation_retries"] == 1
    retry_messages = completions.requests[1]["messages"]
    tool_message = next(message for message in retry_messages if message["role"] == "tool")
    assert "native JSON types" in str(tool_message["content"])


@pytest.mark.parametrize(
    ("response", "expected_status"),
    [
        (_FakeStream([]), "empty_response"),
        (
            _chat_response(content="I will not submit.", finish_reason="stop"),
            "required_tool_not_called",
        ),
        (
            _FakeStream(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content=None,
                                    tool_calls=[
                                        SimpleNamespace(
                                            index=0,
                                            id="call-1",
                                            function=SimpleNamespace(
                                                name="submit_report_intent",
                                                arguments="{",
                                            ),
                                        )
                                    ],
                                )
                            )
                        ]
                    )
                ]
            ),
            "malformed_tool_arguments",
        ),
        (
            _FakeStream(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content=None,
                                    tool_calls=[
                                        SimpleNamespace(
                                            index=0,
                                            function=SimpleNamespace(
                                                name="submit_report_intent",
                                                arguments="{}",
                                            ),
                                        )
                                    ],
                                )
                            )
                        ]
                    )
                ]
            ),
            "truncated_tool_call",
        ),
    ],
)
def test_chat_adapter_normalizes_required_submission_failures(
    response: object,
    expected_status: str,
) -> None:
    """Expose no-tool and malformed streamed calls through stable statuses."""
    completions = _FakeCompletions([response])
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    async def call_tool(_: str, __: dict[str, object]) -> dict[str, object]:
        raise AssertionError("the malformed call must not reach the tool caller")

    with pytest.raises(ProviderAdapterError) as exc_info:
        anyio.run(
            partial(
                run_chat_completions_authoring_loop,
                client=client,
                model="local-model",
                provider_label="OpenAI-compatible",
                instructions="Submit the typed report intent.",
                initial_user_message="Set the report title.",
                tool_definitions=[
                    FunctionToolDefinition(
                        name="submit_report_intent",
                        description="Submit one report fragment.",
                        parameters={"type": "object"},
                    )
                ],
                tool_caller=call_tool,
                max_rounds=1,
                required_tool_name="submit_report_intent",
            )
        )

    assert exc_info.value.status == expected_status


def test_chat_adapter_allows_prose_when_no_submission_is_required() -> None:
    """Retain automatic tool selection for freeform authoring workflows."""
    completions = _FakeCompletions(
        [_chat_response(content="I can answer without a tool.", finish_reason="stop")]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    async def call_tool(_: str, __: dict[str, object]) -> dict[str, object]:
        raise AssertionError("the provider should not call a tool")

    result = anyio.run(
        partial(
            run_chat_completions_authoring_loop,
            client=client,
            model="local-model",
            provider_label="OpenAI-compatible",
            instructions="Use a tool only when needed.",
            initial_user_message="Describe the draft.",
            tool_definitions=[
                FunctionToolDefinition(
                    name="inspect_logfile",
                    description="Inspect a draft.",
                    parameters={"type": "object"},
                )
            ],
            tool_caller=call_tool,
            max_rounds=1,
        )
    )

    assert result.final_text == "I can answer without a tool."
    assert "tool_choice" not in completions.requests[0]
