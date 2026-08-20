###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Tests for the OpenAI Responses provider adapter."""

from __future__ import annotations

from functools import partial
from types import SimpleNamespace

import anyio
import pytest

from wellplot.agent.core import FunctionToolDefinition, ProviderAdapterError
from wellplot.agent.providers._openai_responses import run_responses_authoring_loop


class _FakeResponses:
    """Minimal synchronous Responses client for adapter tests."""

    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.requests.append(kwargs)
        return self.responses.pop(0)


def _response(
    *,
    response_id: str,
    output: list[object] | None = None,
    output_text: str = "",
    status: str = "completed",
) -> object:
    """Build one SDK-shaped Responses API result."""
    return SimpleNamespace(
        id=response_id,
        output=output or [],
        output_text=output_text,
        status=status,
    )


def _function_call(
    *,
    call_id: str,
    name: str = "submit_report_intent",
    arguments: str = "{}",
) -> object:
    """Build one SDK-shaped Responses function-call item."""
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=arguments,
    )


def _tool_definition() -> list[FunctionToolDefinition]:
    """Return the single required submission contract used by fixtures."""
    return [
        FunctionToolDefinition(
            name="submit_report_intent",
            description="Submit one report fragment.",
            parameters={"type": "object"},
        )
    ]


def test_responses_adapter_ends_after_an_accepted_submission() -> None:
    """End a typed compiler stage without a redundant prose continuation."""
    responses = _FakeResponses(
        [
            _response(
                response_id="response-1",
                output=[
                    _function_call(
                        call_id="call-1",
                        arguments='{"title":"Revised"}',
                    )
                ],
            ),
        ]
    )
    client = SimpleNamespace(responses=responses)
    received: list[tuple[str, dict[str, object]]] = []

    async def call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        received.append((name, arguments))
        return {"accepted": True, "message": "Submission accepted."}

    result = anyio.run(
        partial(
            run_responses_authoring_loop,
            client=client,
            model="openai-model",
            provider_label="OpenAI",
            instructions="Submit the typed report intent.",
            initial_user_message="Set the report title.",
            tool_definitions=_tool_definition(),
            tool_caller=call_tool,
            max_rounds=2,
            required_tool_name="submit_report_intent",
        )
    )

    assert result.final_text == "Submission accepted."
    assert received == [("submit_report_intent", {"title": "Revised"})]
    assert [(call.name, call.arguments) for call in result.tool_trace] == received
    assert responses.requests[0]["tool_choice"] == {
        "type": "function",
        "name": "submit_report_intent",
    }
    assert len(responses.requests) == 1
    assert result.report_facts["provider_response"] == {
        "adapter": "responses",
        "rounds": 1,
        "tool_calls_emitted": True,
        "finish_reasons": ["completed"],
        "response_statuses": ["completed"],
        "required_tool_name": "submit_report_intent",
        "required_submission_accepted": True,
        "controller_stopped": False,
    }


def test_responses_adapter_preserves_partial_trace_on_round_exhaustion() -> None:
    """Expose the last submitted tool when a required stage exhausts its budget."""
    responses = _FakeResponses(
        [
            _response(
                response_id="response-1",
                output=[_function_call(call_id="call-1", arguments='{"coverage": []}')],
            )
        ]
    )
    client = SimpleNamespace(responses=responses)

    async def reject_submission(_: str, __: dict[str, object]) -> dict[str, object]:
        """Keep the adapter in its bounded correction path."""
        return {"is_error": True, "error": "coverage is incomplete"}

    with pytest.raises(ProviderAdapterError) as caught:
        anyio.run(
            partial(
                run_responses_authoring_loop,
                client=client,
                model="openai-model",
                provider_label="OpenAI",
                instructions="Submit the typed report intent.",
                initial_user_message="Set the report title.",
                tool_definitions=_tool_definition(),
                tool_caller=reject_submission,
                max_rounds=1,
                required_tool_name="submit_report_intent",
            )
        )

    assert caught.value.status == "round_budget_exhausted"
    assert [call.name for call in caught.value.tool_trace] == ["submit_report_intent"]
    assert caught.value.report_facts["provider_response"]["rounds"] == 1


def test_responses_adapter_preserves_and_enforces_correction_exchange() -> None:
    """Require one corrective submission after an explicit tool validation error."""
    responses = _FakeResponses(
        [
            _response(
                response_id="response-1",
                output=[_function_call(call_id="call-1", arguments='{"title":"First"}')],
            ),
            _response(
                response_id="response-2",
                output=[
                    _function_call(
                        call_id="call-2",
                        arguments='{"title":"Corrected"}',
                    )
                ],
            ),
        ]
    )
    client = SimpleNamespace(responses=responses)
    submissions: list[dict[str, object]] = []

    async def call_tool(_: str, arguments: dict[str, object]) -> dict[str, object]:
        submissions.append(arguments)
        if len(submissions) == 1:
            return {"is_error": True, "error": "title must not be blank"}
        return {"accepted": True, "message": "Submission accepted."}

    result = anyio.run(
        partial(
            run_responses_authoring_loop,
            client=client,
            model="openai-model",
            provider_label="OpenAI",
            instructions="Submit the typed report intent.",
            initial_user_message="Set the report title.",
            tool_definitions=_tool_definition(),
            tool_caller=call_tool,
            max_rounds=3,
            required_tool_name="submit_report_intent",
        )
    )

    assert result.final_text == "Submission accepted."
    assert submissions == [{"title": "First"}, {"title": "Corrected"}]
    assert responses.requests[1]["previous_response_id"] == "response-1"
    assert len(responses.requests) == 2
    assert responses.requests[1]["tool_choice"] == {
        "type": "function",
        "name": "submit_report_intent",
    }


@pytest.mark.parametrize(
    ("response", "expected_status"),
    [
        (_response(response_id="response-1"), "empty_response"),
        (
            _response(response_id="response-1", output_text="I will not submit."),
            "required_tool_not_called",
        ),
        (
            _response(
                response_id="response-1",
                output=[_function_call(call_id="call-1", arguments="{")],
            ),
            "malformed_tool_arguments",
        ),
        (
            _response(response_id="response-1", status="incomplete"),
            "truncated_response",
        ),
    ],
)
def test_responses_adapter_normalizes_submission_failures(
    response: object,
    expected_status: str,
) -> None:
    """Use stable error statuses for required submission failures."""
    responses = _FakeResponses([response])
    client = SimpleNamespace(responses=responses)

    async def call_tool(_: str, __: dict[str, object]) -> dict[str, object]:
        raise AssertionError("the invalid submission must not reach the tool caller")

    with pytest.raises(ProviderAdapterError) as exc_info:
        anyio.run(
            partial(
                run_responses_authoring_loop,
                client=client,
                model="openai-model",
                provider_label="OpenAI",
                instructions="Submit the typed report intent.",
                initial_user_message="Set the report title.",
                tool_definitions=_tool_definition(),
                tool_caller=call_tool,
                max_rounds=1,
                required_tool_name="submit_report_intent",
            )
        )

    assert exc_info.value.status == expected_status


def test_responses_adapter_allows_prose_when_no_submission_is_required() -> None:
    """Retain automatic tool selection for non-compilation authoring workflows."""
    responses = _FakeResponses(
        [_response(response_id="response-1", output_text="I can answer without a tool.")]
    )
    client = SimpleNamespace(responses=responses)

    async def call_tool(_: str, __: dict[str, object]) -> dict[str, object]:
        raise AssertionError("the provider should not call a tool")

    result = anyio.run(
        partial(
            run_responses_authoring_loop,
            client=client,
            model="openai-model",
            provider_label="OpenAI",
            instructions="Use a tool only when needed.",
            initial_user_message="Describe the draft.",
            tool_definitions=_tool_definition(),
            tool_caller=call_tool,
            max_rounds=1,
        )
    )

    assert result.final_text == "I can answer without a tool."
    assert "tool_choice" not in responses.requests[0]
