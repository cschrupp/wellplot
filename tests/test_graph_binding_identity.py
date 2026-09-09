"""Planner binding identities must satisfy the canonical document contract."""

import asyncio
from copy import deepcopy

import pytest

from wellplot.agent.core import ProviderRunResult
from wellplot.agent.graph.models import ReconstructionPlan
from wellplot.agent.graph.planner import ReconstructionPlanner
from wellplot.agent.graph.provider_adapter import ExistingProviderStructuredAdapter
from wellplot.capabilities import create_builtin_registry


def _plan() -> ReconstructionPlan:
    sections = []
    for section_id in ("main_pass", "repeat_pass"):
        sections.append(
            {
                "section_id": section_id,
                "capability_id": "section.log_plot",
                "goal": "Plot CBL in this pass.",
                "components": [
                    {
                        "component_id": "track",
                        "target_id": "cbl",
                        "capability_id": "track.normal",
                        "parent_component_id": None,
                        "goal": "Add CBL track.",
                    },
                    {
                        "component_id": "binding",
                        "target_id": "CBL",
                        "capability_id": "binding.curve",
                        "parent_component_id": "track",
                        "goal": "Plot CBL channel.",
                        "values": {"channel": "CBL"},
                    },
                ],
            }
        )
    return ReconstructionPlan.model_validate({"summary": "Two passes.", "sections": sections})


@pytest.mark.parametrize("same_section", [False, True])
@pytest.mark.parametrize("raster", [False, True])
def test_planner_rejects_binding_identity_collisions(same_section: bool, raster: bool) -> None:
    """Curve and raster instances share an ID namespace across tracks and sections."""
    plan = _plan()
    second = plan.sections[1].components
    if raster:
        second[0].capability_id = "track.array"
        second[1].capability_id = "binding.raster"
    if same_section:
        second[0].component_id = "other_track"
        second[0].target_id = "other"
        second[1].component_id = "other_binding"
        second[1].parent_component_id = "other_track"
        plan.sections[0].components.extend(second)
        plan.sections.pop()
    planner = ReconstructionPlanner(model=object(), registry=create_builtin_registry())
    with pytest.raises(ValueError, match="Binding target ID 'CBL'.*globally unique"):
        planner._validate_capabilities(plan)


@pytest.mark.parametrize("mode", ["reconstruct", "revise"])
def test_planner_corrects_ids_without_changing_channels(mode: str) -> None:
    """Existing provider feedback rejects the plan before accepting distinct instances."""
    invalid = _plan().model_dump(mode="json")
    corrected = deepcopy(invalid)
    for section in corrected["sections"]:
        section["components"][1]["target_id"] = f"{section['section_id']}.cbl.CBL.1"

    class Backend:
        async def run_authoring(self, **kwargs: object) -> ProviderRunResult:
            name = kwargs["required_tool_name"]
            assert name == "submit_reconstruction_plan"
            rejection = await kwargs["tool_caller"](name, invalid)
            assert rejection["is_error"]
            assert "main_pass" in rejection["error"]
            assert "repeat_pass" in rejection["error"]
            assert "globally unique" in rejection["error"]
            assert await kwargs["tool_caller"](name, corrected) == {"accepted": True}
            return ProviderRunResult(final_text="", tool_trace=())

    planner = ReconstructionPlanner(
        model=ExistingProviderStructuredAdapter(Backend()), registry=create_builtin_registry()
    )
    result = asyncio.run(
        planner.plan(
            request="Plot CBL in both passes.", current_document={}, source_manifest={}, mode=mode
        )
    )
    assert result.model_dump(mode="json") == corrected
    assert [section.components[0].target_id for section in result.sections] == ["cbl", "cbl"]
    assert [section.components[1].values["channel"] for section in result.sections] == [
        "CBL",
        "CBL",
    ]
