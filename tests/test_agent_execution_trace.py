"""Tests for durable graph-agent execution traces."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import BaseModel

pytest.importorskip("langgraph")

from wellplot.agent.core import AuthoringToolCall, ProviderRunResult
from wellplot.agent.execution_trace import (
    AgentRunTrace,
    assistant_response_trace_payload,
    bind_agent_trace,
    read_agent_trace,
)
from wellplot.agent.graph import (
    ExistingProviderStructuredAdapter,
    ReconstructionGraphDependencies,
    ReconstructionPlanner,
    ReportCompiler,
    SectionCompiler,
    build_compile_graph,
)
from wellplot.capabilities import create_builtin_registry


class _TraceStructuredModel:
    """Return deterministic graph artifacts for trace coverage."""

    def __init__(self) -> None:
        """Record graph prompts while returning deterministic artifacts."""
        self.user_messages: list[str] = []

    async def generate(
        self,
        *,
        instructions: str,
        user_message: str,
        response_model: type[BaseModel],
        tool_name: str,
        tool_description: str,
        max_rounds: int = 3,
        response_validator: object | None = None,
    ) -> BaseModel:
        """Produce each typed planner or compiler output without a provider."""
        del instructions, tool_description, max_rounds, response_validator
        self.user_messages.append(user_message)
        if tool_name == "submit_reconstruction_plan":
            return response_model.model_validate(
                {
                    "summary": "Compile the main and repeat passes.",
                    "sections": [
                        {
                            "section_id": "main_pass",
                            "capability_id": "section.log_plot",
                            "goal": "Compile the main pass.",
                            "components": [
                                {
                                    "component_id": "main_pass.depth",
                                    "target_id": "depth",
                                    "capability_id": "track.reference",
                                    "goal": "Add depth.",
                                    "parent_component_id": None,
                                }
                            ],
                        },
                        {
                            "section_id": "repeat_pass",
                            "capability_id": "section.log_plot",
                            "goal": "Compile the repeat pass.",
                            "components": [
                                {
                                    "component_id": "repeat_pass.depth",
                                    "target_id": "depth",
                                    "capability_id": "track.reference",
                                    "goal": "Add depth.",
                                    "parent_component_id": None,
                                }
                            ],
                        },
                    ],
                }
            )
        if tool_name == "submit_report_artifact":
            return response_model.model_validate({"intent": {"title": "Trace report"}})
        if tool_name == "submit_section_artifact":
            section_id = "repeat_pass" if "repeat_pass" in user_message else "main_pass"
            return response_model.model_validate(
                {
                    "section": {
                        "section_id": section_id,
                        "title": section_id,
                        "tracks": [
                            {
                                "track_id": "depth",
                                "title": "Depth",
                                "kind": "reference",
                                "width_mm": 10,
                            },
                        ],
                    }
                }
            )
        raise AssertionError(f"Unexpected structured request {tool_name!r}")


class _Submission(BaseModel):
    """Small response model for provider-adapter trace coverage."""

    title: str


@dataclass
class _ProviderBackend:
    """Submit one typed response through the existing provider protocol."""

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[object],
        tool_caller: object,
        max_rounds: int,
        required_tool_name: str | None = None,
        stream_response: bool = True,
    ) -> ProviderRunResult:
        """Call the required structured tool with a representative agent output."""
        del instructions, initial_user_message, tool_definitions, max_rounds
        assert required_tool_name == "submit_trace"
        assert stream_response is True
        response = await tool_caller("submit_trace", {"title": "Agent output"})  # type: ignore[misc]
        assert response == {"accepted": True}
        return ProviderRunResult(
            final_text="Submitted typed output.",
            tool_trace=(
                AuthoringToolCall(
                    round=1,
                    name="submit_trace",
                    arguments={"title": "Agent output"},
                ),
            ),
            report_facts={"provider_response": {"rounds": 1}},
        )


@dataclass
class _CorrectingProviderBackend:
    """Resubmit one typed value after the semantic validator rejects it."""

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[object],
        tool_caller: object,
        max_rounds: int,
        required_tool_name: str | None = None,
        stream_response: bool = True,
    ) -> ProviderRunResult:
        """Model the existing provider loop receiving one rejected submission."""
        del instructions, initial_user_message, tool_definitions, max_rounds
        assert required_tool_name == "submit_trace"
        assert stream_response is True
        rejected = await tool_caller("submit_trace", {"title": "Rejected"})  # type: ignore[misc]
        assert rejected["is_error"] is True
        accepted = await tool_caller("submit_trace", {"title": "Accepted"})  # type: ignore[misc]
        assert accepted == {"accepted": True}
        return ProviderRunResult(
            final_text="Submitted corrected typed output.",
            tool_trace=(
                AuthoringToolCall(
                    round=1,
                    name="submit_trace",
                    arguments={"title": "Rejected"},
                ),
                AuthoringToolCall(
                    round=2,
                    name="submit_trace",
                    arguments={"title": "Accepted"},
                ),
            ),
            report_facts={"provider_response": {"rounds": 2}},
        )


@dataclass
class _ResponseModelCorrectingProviderBackend:
    """Resubmit after the response model rejects the first provider payload."""

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[object],
        tool_caller: object,
        max_rounds: int,
        required_tool_name: str | None = None,
        stream_response: bool = True,
    ) -> ProviderRunResult:
        """Model the correction conversation after a Pydantic rejection."""
        del instructions, initial_user_message, tool_definitions, max_rounds
        assert required_tool_name == "submit_trace"
        assert stream_response is True
        rejected = await tool_caller("submit_trace", {"unexpected": "Rejected"})  # type: ignore[misc]
        assert rejected["is_error"] is True
        accepted = await tool_caller("submit_trace", {"title": "Accepted"})  # type: ignore[misc]
        assert accepted == {"accepted": True}
        return ProviderRunResult(
            final_text="Submitted corrected typed output.",
            tool_trace=(
                AuthoringToolCall(
                    round=1,
                    name="submit_trace",
                    arguments={"unexpected": "Rejected"},
                ),
                AuthoringToolCall(
                    round=2,
                    name="submit_trace",
                    arguments={"title": "Accepted"},
                ),
            ),
            report_facts={"provider_response": {"rounds": 2}},
        )


def test_agent_run_trace_redacts_sensitive_values_and_flushes_events(tmp_path: Path) -> None:
    """Trace files remain readable and never persist credential-shaped values."""
    trace = AgentRunTrace.create(logfile_path=tmp_path / "draft.log.yaml", mode="reconstruct")

    with bind_agent_trace(trace), trace.stage("planner"):
        trace.record(
            "structured_output",
            status="accepted",
            payload={
                "api_key": "sk-testtoken123456789",
                "message": "Bearer sk-testtoken123456789",
            },
        )

    events = read_agent_trace(trace.path)
    payload = next(event.payload for event in events if event.event == "structured_output")

    assert trace.path.exists()
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert payload == {"api_key": "[REDACTED]", "message": "Bearer [REDACTED]"}


def test_assistant_response_trace_payload_is_redacted_and_keeps_both_ends() -> None:
    """Verbose non-tool prose remains diagnosable without unbounded trace files."""
    response_text = (
        "start sk-testtoken123456789 " + ("x" * 20_000) + " Bearer nvapi-token123456789 tail"
    )

    payload = assistant_response_trace_payload(response_text)

    assert payload["original_characters"] == len(response_text)
    assert (
        payload["sha256"]
        == hashlib.sha256(
            ("start [REDACTED] " + ("x" * 20_000) + " Bearer [REDACTED] tail").encode("utf-8")
        ).hexdigest()
    )
    assert payload["truncated"] is True
    assert "start [REDACTED]" in str(payload["excerpt"])
    assert "Bearer [REDACTED] tail" in str(payload["excerpt"])
    assert "token123456789" not in str(payload["excerpt"])


def test_compile_graph_trace_records_stage_outputs(tmp_path: Path) -> None:
    """Planner, workers, and merge emit inspectable typed outputs per run."""
    registry = create_builtin_registry()
    model = _TraceStructuredModel()
    graph = build_compile_graph(
        ReconstructionGraphDependencies(
            planner=ReconstructionPlanner(model=model, registry=registry),
            report_compiler=ReportCompiler(model=model, registry=registry),
            section_compiler=SectionCompiler(model=model, registry=registry),
            registry=registry,
        )
    )
    trace = AgentRunTrace.create(logfile_path=tmp_path / "draft.log.yaml", mode="reconstruct")

    async def compile_graph() -> None:
        with bind_agent_trace(trace):
            await graph.ainvoke(
                {
                    "request": "Compile both sections.",
                    "mode": "reconstruct",
                    "current_document": {},
                    "source_manifest": {},
                    "compiled_artifacts": [],
                    "diagnostics": [],
                    "repair_attempt": 0,
                }
            )

    asyncio.run(compile_graph())
    events = read_agent_trace(trace.path)
    started = [event for event in events if event.event == "stage_started"]
    outputs = [event for event in events if event.event == "structured_output"]

    assert {event.stage for event in started} == {"planner", "report", "section", "merge"}
    assert {event.target_id for event in started if event.stage == "section"} == {
        "main_pass",
        "repeat_pass",
    }
    assert len(outputs) == 4
    assert any(event.event == "merged_intent" for event in events)

    report_context = next(
        json.loads(message.partition("Context:\n")[2])
        for message in model.user_messages
        if message.startswith("Compile the report-wide portion")
    )
    section_contexts = [
        json.loads(message.partition("Context:\n")[2])
        for message in model.user_messages
        if message.startswith("Compile section")
    ]

    assert report_context["capability"] == registry.get("report.standard").planning_descriptor()
    expected_section_capabilities = [
        registry.get("section.log_plot").planning_descriptor(),
        registry.get("track.reference").planning_descriptor(),
    ]
    assert all(
        context["capabilities"] == expected_section_capabilities for context in section_contexts
    )
    assert all("artifact_schema" not in message for message in model.user_messages)


def test_provider_adapter_trace_records_validated_agent_submission(tmp_path: Path) -> None:
    """The trace preserves the structured response needed for coherence review."""
    trace = AgentRunTrace.create(logfile_path=tmp_path / "draft.log.yaml", mode="reconstruct")
    adapter = ExistingProviderStructuredAdapter(backend=_ProviderBackend())

    async def generate() -> _Submission:
        with bind_agent_trace(trace), trace.stage("planner"):
            return await adapter.generate(
                instructions="Submit the response.",
                user_message="Set the title.",
                response_model=_Submission,
                tool_name="submit_trace",
                tool_description="Submit one trace response.",
            )

    result = asyncio.run(generate())
    events = read_agent_trace(trace.path)
    completed = next(
        event
        for event in events
        if event.event == "structured_request_finished" and event.status == "succeeded"
    )
    started = next(
        event
        for event in events
        if event.event == "structured_request_started" and event.status == "started"
    )

    assert result.title == "Agent output"
    assert completed.payload == {"title": "Agent output"}
    assert started.details["instructions_characters"] == len("Submit the response.")
    assert started.details["user_message_characters"] == len("Set the title.")
    assert started.details["response_schema_characters"] > 0
    assert started.details["prompt_and_schema_characters"] == sum(
        started.details[key]
        for key in (
            "instructions_characters",
            "user_message_characters",
            "response_schema_characters",
        )
    )


def test_provider_adapter_returns_semantic_rejections_to_the_same_provider(tmp_path: Path) -> None:
    """A semantic rejection is traceable and can be corrected within one conversation."""
    trace = AgentRunTrace.create(logfile_path=tmp_path / "draft.log.yaml", mode="reconstruct")
    adapter = ExistingProviderStructuredAdapter(backend=_CorrectingProviderBackend())

    def require_accepted_title(submission: _Submission) -> None:
        if submission.title != "Accepted":
            raise ValueError("title must be 'Accepted'.")

    async def generate() -> _Submission:
        with bind_agent_trace(trace), trace.stage("planner"):
            return await adapter.generate(
                instructions="Submit the response.",
                user_message="Set the title.",
                response_model=_Submission,
                tool_name="submit_trace",
                tool_description="Submit one trace response.",
                response_validator=require_accepted_title,
            )

    result = asyncio.run(generate())
    events = read_agent_trace(trace.path)
    rejection = next(event for event in events if event.event == "structured_submission_rejected")

    assert result.title == "Accepted"
    assert rejection.status == "invalid_semantics"
    assert rejection.payload == {"title": "Rejected"}
    assert "title must be 'Accepted'" in rejection.details["error"]


def test_provider_adapter_traces_response_model_rejections(tmp_path: Path) -> None:
    """Keep invalid typed provider submissions available for later trace review."""
    trace = AgentRunTrace.create(logfile_path=tmp_path / "draft.log.yaml", mode="reconstruct")
    adapter = ExistingProviderStructuredAdapter(backend=_ResponseModelCorrectingProviderBackend())

    async def generate() -> _Submission:
        with bind_agent_trace(trace), trace.stage("report", target_id="report"):
            return await adapter.generate(
                instructions="Submit the response.",
                user_message="Set the title.",
                response_model=_Submission,
                tool_name="submit_trace",
                tool_description="Submit one trace response.",
            )

    result = asyncio.run(generate())
    events = read_agent_trace(trace.path)
    rejection = next(
        event
        for event in events
        if event.event == "structured_submission_rejected"
        and event.status == "invalid_response_model"
    )

    assert result.title == "Accepted"
    assert rejection.payload == {"unexpected": "Rejected"}
    assert rejection.details["response_model"] == "_Submission"
    assert "title" in rejection.details["error"]
