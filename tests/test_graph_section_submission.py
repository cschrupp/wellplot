"""Section instructions and native submission agree at the provider boundary."""

import asyncio

import pytest

from wellplot.agent.core import ProviderRunResult
from wellplot.agent.graph.models import SectionPlan
from wellplot.agent.graph.provider_adapter import ExistingProviderStructuredAdapter
from wellplot.agent.graph.section_worker import SectionCompiler
from wellplot.capabilities import create_builtin_registry


@pytest.mark.parametrize("mode", ["reconstruct", "revise"])
def test_section_instructions_require_native_submission(mode: str) -> None:
    """Both modes advertise the same submission mechanism enforced by the adapter."""
    payload = {
        "section": {
            "section_id": "main",
            "title": "Main",
            "tracks": [{"track_id": "gr", "title": "GR", "kind": "normal", "width_mm": 30}],
        }
    }

    class Backend:
        async def run_authoring(self, **kwargs: object) -> ProviderRunResult:
            instructions = kwargs["instructions"]
            name = kwargs["required_tool_name"]
            assert name == "submit_section_artifact"
            assert f"Call {name}" in instructions
            assert "function arguments" in instructions
            assert "assistant text or a Markdown code block is not a submission" in instructions
            assert "Do not emit MCP calls" not in instructions
            assert [tool.name for tool in kwargs["tool_definitions"]] == [name]
            # Plain section-shaped arguments still fail: the advertised wrapper matters.
            rejected = await kwargs["tool_caller"](name, payload["section"])
            assert rejected["is_error"]
            assert await kwargs["tool_caller"](name, payload) == {"accepted": True}
            return ProviderRunResult(final_text="", tool_trace=())

    compiler = SectionCompiler(
        model=ExistingProviderStructuredAdapter(Backend()), registry=create_builtin_registry()
    )
    plan = SectionPlan.model_validate(
        {
            "section_id": "main",
            "capability_id": "section.log_plot",
            "goal": "Add GR track.",
            "components": [
                {
                    "component_id": "main.gr",
                    "target_id": "gr",
                    "capability_id": "track.normal",
                    "goal": "Add GR track.",
                    "parent_component_id": None,
                }
            ],
        }
    )
    result = asyncio.run(
        compiler.compile(
            request="Add GR track.", plan=plan, current_document={}, source_manifest={}, mode=mode
        )
    )
    assert result.payload == payload
    assert result.covered_component_ids == ["main.gr"]
