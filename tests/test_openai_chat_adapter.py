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
from types import SimpleNamespace

import anyio
import pytest

from wellplot.agent.core import FunctionToolDefinition, ProviderAdapterError
from wellplot.agent.providers._openai_chat import run_chat_completions_authoring_loop


class _FakeCompletions:
    """Minimal synchronous Chat Completions client for adapter tests."""

    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.requests.append(kwargs)
        return self.responses.pop(0)


class _FakeStream:
    """Iterable wrapper for streamed Chat Completions chunks."""

    def __init__(self, chunks: list[object]) -> None:
        self.chunks = chunks

    def __iter__(self) -> Iterator[object]:
        return iter(self.chunks)


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


def test_chat_adapter_preserves_correction_message_order() -> None:
    """Keep assistant tool calls immediately before their tool results."""
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
            _chat_response(content="Submission accepted.", finish_reason="stop"),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    received: list[dict[str, object]] = []

    async def call_tool(_: str, arguments: dict[str, object]) -> dict[str, object]:
        received.append(arguments)
        return {"accepted": len(received) == 2}

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
    assert [message["role"] for message in completions.requests[2]["messages"]] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
    ]
    assert completions.requests[0]["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_report_intent"},
    }
    assert "tool_choice" not in completions.requests[1]


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
