"""Section submissions receive canonical errors inside the correction loop."""

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

import pytest

from wellplot.agent.core import FunctionToolDefinition, ProviderRunResult
from wellplot.agent.graph.models import SectionPlan
from wellplot.agent.graph.provider_adapter import ExistingProviderStructuredAdapter
from wellplot.agent.graph.section_worker import SectionCompiler
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec


class _Backend:
    def __init__(self, submissions: list[dict[str, Any]]) -> None:
        self.submissions = submissions
        self.replies: list[dict[str, Any]] = []

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: Callable[[str, dict[str, object]], Awaitable[dict[str, object]]],
        max_rounds: int,
        required_tool_name: str | None = None,
    ) -> ProviderRunResult:
        assert max_rounds == 3
        assert required_tool_name == "submit_section_artifact"
        for submission in self.submissions:
            reply = await tool_caller("submit_section_artifact", submission)
            self.replies.append(reply)
            if reply == {"accepted": True}:
                break
        return ProviderRunResult(final_text="Submitted", tool_trace=())


@pytest.mark.parametrize("revision", [False, True])
@pytest.mark.parametrize("corrected", [False, True])
def test_raster_conflict_is_correctable_without_mutating_context(
    revision: bool, corrected: bool
) -> None:
    """Validate both new rasters and updates inheriting their VDL profile."""
    tracks = [{"id": "depth", "title": "Depth", "kind": "reference", "width_mm": 10}]
    if revision:
        tracks.append(
            {
                "id": "vdl",
                "title": "VDL",
                "kind": "array",
                "width_mm": 40,
                "bindings": [
                    {"kind": "raster", "binding_id": "wave", "channel": "VDL", "profile": "vdl"}
                ],
            }
        )
    document = AuthoringDocumentSpec(
        name="test", sections=[{"id": "main", "title": "Main", "tracks": tracks}]
    ).model_dump(mode="json")
    manifest = {"main": {"channels": [{"mnemonic": "VDL", "kind": "array"}]}}
    before = deepcopy((document, manifest))
    plan = SectionPlan.model_validate(
        {
            "section_id": "main",
            "capability_id": "section.log_plot",
            "goal": "Set raster",
            "components": [
                {
                    "component_id": "track",
                    "target_id": "vdl",
                    "capability_id": "track.array",
                    "goal": "VDL track",
                    "parent_component_id": None,
                },
                {
                    "component_id": "binding",
                    "target_id": "wave",
                    "capability_id": "binding.raster",
                    "parent_component_id": "track",
                    "goal": "Waveform",
                },
            ],
        }
    )
    binding = {"kind": "raster", "binding_id": "wave", "color_limits": [0, 1]}
    track = {"track_id": "vdl", "bindings": [binding]}
    if not revision:
        binding.update(channel="VDL", profile="vdl")
        track.update(title="VDL", kind="array", width_mm=40)
    invalid = {"section": {"section_id": "main", "tracks": [track]}}
    valid = deepcopy(invalid)
    if revision:
        valid["section"]["tracks"][0]["bindings"][0]["color_limits"] = [-1, 1]
    else:
        del valid["section"]["tracks"][0]["bindings"][0]["color_limits"]
    backend = _Backend([invalid, valid] if corrected else [invalid])
    compiler = SectionCompiler(
        ExistingProviderStructuredAdapter(backend), create_builtin_registry()
    )
    call = compiler.compile(
        request="Configure VDL",
        plan=plan,
        current_document=document,
        source_manifest=manifest,
        mode="revise" if revision else "reconstruct",
    )
    if corrected:
        result = asyncio.run(call)
        assert result.payload == valid
        assert backend.replies[1] == {"accepted": True}
    else:
        with pytest.raises(RuntimeError, match="without submitting required structured output"):
            asyncio.run(call)
    assert backend.replies[0]["is_error"] is True
    assert "straddle zero" in backend.replies[0]["error"]
    assert (document, manifest) == before
