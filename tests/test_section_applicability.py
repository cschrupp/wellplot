"""Section submissions receive canonical errors inside the correction loop."""

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from wellplot.agent.core import FunctionToolDefinition, ProviderRunResult
from wellplot.agent.graph.models import SectionPlan
from wellplot.agent.graph.provider_adapter import ExistingProviderStructuredAdapter
from wellplot.agent.graph.section_worker import SectionCompiler
from wellplot.agent.graph.worker_contracts import section_contract
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


@pytest.mark.parametrize("mode", ["reconstruct", "revise"])
def test_empty_section_and_style_fields_are_reported_together(mode: str) -> None:
    """Run 81feb7 spent three rounds discovering separate empty-string errors."""
    document = AuthoringDocumentSpec(
        name="test",
        sections=[
            {
                "id": "repeat",
                "title": "Repeat",
                "tracks": [
                    {"id": "combo", "title": "Combo", "kind": "normal", "width_mm": 50},
                    {"id": "vdl", "title": "VDL", "kind": "array", "width_mm": 48},
                ],
            }
        ],
    ).model_dump(mode="json")
    components = []
    tracks = []
    for track_id, capability, binding_kind, channel in (
        ("combo", "track.normal", "curve", "GR"),
        ("vdl", "track.array", "raster", "VDL"),
    ):
        components.extend(
            [
                {
                    "component_id": track_id,
                    "target_id": track_id,
                    "capability_id": capability,
                    "goal": "Configure track",
                    "parent_component_id": None,
                },
                {
                    "component_id": channel,
                    "target_id": channel,
                    "capability_id": f"binding.{binding_kind}",
                    "goal": "Bind channel",
                    "parent_component_id": track_id,
                },
            ]
        )
        tracks.append(
            {
                "track_id": track_id,
                "bindings": [
                    {
                        "kind": binding_kind,
                        "binding_id": channel,
                        "channel": channel,
                        "style": {"color": "", "line_style": "", "fill_color": "", "colormap": ""},
                    }
                ],
            }
        )
    plan = SectionPlan(
        section_id="repeat",
        capability_id="section.log_plot",
        goal="Configure repeat",
        components=components,
    )
    invalid = {"section": {"section_id": "repeat", "subtitle": "", "tracks": tracks}}
    model = section_contract(
        plan, document, create_builtin_registry(), reconstruct=mode == "reconstruct"
    )
    assert list(Draft202012Validator(model.model_json_schema()).iter_errors(invalid))
    with pytest.raises(ValidationError) as caught:
        model.model_validate(invalid)
    errors = caught.value.errors()
    for field in ("subtitle", "color", "line_style", "fill_color", "colormap"):
        assert any(
            field in error["loc"] and error["type"] == "string_too_short" for error in errors
        )
    valid = deepcopy(invalid)
    del valid["section"]["subtitle"]
    for track in valid["section"]["tracks"]:
        del track["bindings"][0]["style"]
    backend = _Backend([invalid, valid])
    result = asyncio.run(
        SectionCompiler(
            ExistingProviderStructuredAdapter(backend), create_builtin_registry()
        ).compile(
            request="Configure repeat",
            plan=plan,
            current_document=document,
            source_manifest={
                "repeat": {
                    "channels": [
                        {"mnemonic": "GR", "kind": "scalar"},
                        {"mnemonic": "VDL", "kind": "array"},
                    ]
                }
            },
            mode=mode,
        )
    )
    assert result.payload == valid
    assert len(backend.replies) == 2
    assert backend.replies[-1] == {"accepted": True}
