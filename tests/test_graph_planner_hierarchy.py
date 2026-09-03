"""Contract tests for explicit semantic component ownership."""

from __future__ import annotations

import pytest

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


def test_component_parent_is_required_by_the_advertised_schema() -> None:
    """Providers must see an explicit structural-parent field in the plan schema."""
    schema = ReconstructionPlan.model_json_schema()
    component = schema["$defs"]["SemanticComponentPlan"]

    assert "parent_component_id" in component["properties"]
    assert "parent_component_id" in component["required"]
    assert "depends_on" not in component["properties"]


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
