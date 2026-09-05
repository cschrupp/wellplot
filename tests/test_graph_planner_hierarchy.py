"""Contract tests for explicit semantic component ownership."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from wellplot.agent.graph import ReconstructionPlanner
from wellplot.agent.graph.models import ReconstructionPlan
from wellplot.capabilities import create_builtin_registry


def _component(
    component_id: str,
    capability_id: str,
    parent_component_id: str | None,
) -> dict[str, object]:
    """Build one minimal semantic component for hierarchy tests."""
    return {
        "component_id": component_id,
        "target_id": component_id,
        "capability_id": capability_id,
        "goal": component_id,
        "parent_component_id": parent_component_id,
    }


def _plan(components: list[dict[str, object]]) -> ReconstructionPlan:
    """Build one minimal section plan with the supplied components."""
    return ReconstructionPlan.model_validate(
        {
            "summary": "Validate semantic component ownership.",
            "sections": [
                {
                    "section_id": "main",
                    "capability_id": "section.log_plot",
                    "goal": "Compile the main section.",
                    "components": components,
                }
            ],
        }
    )


def _validate_capabilities(plan: ReconstructionPlan) -> None:
    """Validate one plan through the registry-backed planner boundary."""
    planner = ReconstructionPlanner(model=object(), registry=create_builtin_registry())
    planner._validate_capabilities(plan)


class _PlannerValidationModel:
    """Expose the planner's structured semantic validator to a focused test."""

    response_validator: object | None = None

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
        """Submit a Pydantic-valid plan with a registry-invalid parent relationship."""
        del instructions, user_message, tool_description, max_rounds
        assert tool_name == "submit_reconstruction_plan"
        self.response_validator = response_validator
        plan = response_model.model_validate(
            {
                "summary": "Compile one invalid parent relationship.",
                "sections": [
                    {
                        "section_id": "main",
                        "capability_id": "section.log_plot",
                        "goal": "Compile main.",
                        "components": [
                            _component("array", "track.array", None),
                            _component("curve", "binding.curve", "array"),
                        ],
                    }
                ],
            }
        )
        assert callable(response_validator)
        response_validator(plan)
        return plan


def test_component_parent_is_required_by_the_advertised_schema() -> None:
    """Providers must see an explicit structural-parent field in the plan schema."""
    schema = ReconstructionPlan.model_json_schema()
    component = schema["$defs"]["SemanticComponentPlan"]

    assert "parent_component_id" in component["properties"]
    assert "parent_component_id" in component["required"]
    assert "depends_on" not in component["properties"]


def test_section_source_routing_is_typed_and_not_hidden_in_values() -> None:
    """Planner source routing has one explicit schema location."""
    schema = ReconstructionPlan.model_json_schema()
    section = schema["$defs"]["SectionPlan"]

    assert "data_source" in section["properties"]
    assert (
        ReconstructionPlan.model_validate(
            {
                "summary": "Build the repeat section from its staged source.",
                "sections": [
                    {
                        "section_id": "repeat_pass",
                        "capability_id": "section.log_plot",
                        "goal": "Build the repeat section.",
                        "data_source": {
                            "source_path": "CBL_Repeat.dlis",
                            "source_format": "dlis",
                        },
                    }
                ],
            }
        )
        .sections[0]
        .data_source
        is not None
    )

    with pytest.raises(ValueError, match="typed data_source field"):
        ReconstructionPlan.model_validate(
            {
                "summary": "Build the repeat section from its staged source.",
                "sections": [
                    {
                        "section_id": "repeat_pass",
                        "capability_id": "section.log_plot",
                        "goal": "Build the repeat section.",
                        "values": {
                            "source_path": "CBL_Repeat.dlis",
                            "source_format": "dlis",
                        },
                    }
                ],
            }
        )


def test_registry_accepts_all_builtin_component_parent_relationships() -> None:
    """Containment remains generic across the built-in component families."""
    plan = _plan(
        [
            _component("normal", "track.normal", None),
            _component("reference", "track.reference", None),
            _component("array", "track.array", None),
            _component("annotation", "track.annotation", None),
            _component("curve-normal", "binding.curve", "normal"),
            _component("curve-reference", "binding.curve", "reference"),
            _component("raster", "binding.raster", "array"),
            _component("fill", "fill.curve", "normal"),
            _component("marker", "annotation.typed", "annotation"),
        ]
    )

    _validate_capabilities(plan)


def test_registry_rejects_incompatible_component_parent_capability() -> None:
    """A scalar curve cannot be contained by an array track."""
    plan = _plan(
        [
            _component("array", "track.array", None),
            _component("curve", "binding.curve", "array"),
        ]
    )

    with pytest.raises(ValueError, match="Allowed parents"):
        _validate_capabilities(plan)


def test_planner_supplies_registry_validation_to_the_structured_submission() -> None:
    """Provider adapters receive capability validation before accepting a plan."""
    model = _PlannerValidationModel()
    planner = ReconstructionPlanner(model=model, registry=create_builtin_registry())

    with pytest.raises(ValueError, match="Allowed parents"):
        asyncio.run(
            planner.plan(
                request="Add a scalar curve under an array track.",
                current_document={},
                source_manifest={},
            )
        )

    assert callable(model.response_validator)


@pytest.mark.parametrize(
    ("components", "message"),
    [
        (
            [
                _component("normal", "track.normal", None),
                _component("curve", "binding.curve", "missing"),
            ],
            "unknown parent component",
        ),
        (
            [_component("normal", "track.normal", "normal")],
            "cannot be its own parent",
        ),
        (
            [
                _component("first", "track.normal", "second"),
                _component("second", "track.normal", "first"),
            ],
            "contains a cycle",
        ),
    ],
)
def test_model_rejects_invalid_component_hierarchy(
    components: list[dict[str, object]],
    message: str,
) -> None:
    """Malformed ownership never reaches the registry or a provider retry loop."""
    with pytest.raises(ValueError, match=message):
        _plan(components)
