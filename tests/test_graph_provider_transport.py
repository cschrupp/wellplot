"""Transport defaults for one-shot graph structured submissions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel

from wellplot.agent.core import FunctionToolDefinition, ProviderRunResult
from wellplot.agent.graph.provider_adapter import ExistingProviderStructuredAdapter


class _Submission(BaseModel):
    """Minimal graph structured output."""

    title: str


@dataclass
class _Backend:
    """Capture the transport selection made by the graph adapter."""

    stream_response: bool | None = None

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: Callable[[str, dict[str, object]], Awaitable[dict[str, object]]],
        max_rounds: int,
        required_tool_name: str | None = None,
        stream_response: bool = True,
    ) -> ProviderRunResult:
        """Submit one native structured response through the graph adapter."""
        del instructions, initial_user_message, tool_definitions, max_rounds
        self.stream_response = stream_response
        assert required_tool_name == "submit_graph_artifact"
        assert await tool_caller("submit_graph_artifact", {"title": "Compiled"}) == {
            "accepted": True
        }
        return ProviderRunResult(final_text="", tool_trace=())


def test_graph_adapter_preserves_backend_streaming_default() -> None:
    """Graph compilation does not override the backend transport default."""
    backend = _Backend()
    adapter = ExistingProviderStructuredAdapter(backend=backend)

    result = asyncio.run(
        adapter.generate(
            instructions="Submit the artifact.",
            user_message="Compile the requested graph artifact.",
            response_model=_Submission,
            tool_name="submit_graph_artifact",
            tool_description="Submit one graph artifact.",
        )
    )

    assert result == _Submission(title="Compiled")
    assert backend.stream_response is True
