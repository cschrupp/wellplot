"""Worker track scales agree with supported canonical track kinds."""

from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from wellplot.agent.graph.models import SectionPlan
from wellplot.agent.graph.worker_contracts import section_contract
from wellplot.capabilities import create_builtin_registry


@pytest.mark.parametrize("kind", ["normal", "reference", "array", "annotation"])
@pytest.mark.parametrize("reconstruct", [False, True])
@pytest.mark.parametrize("existing", [False, True])
def test_track_scale_schema_matches_kind(kind: str, reconstruct: bool, existing: bool) -> None:
    """Only normal and array tracks expose track-level x_scale, in either mode."""
    plan = SectionPlan.model_validate(
        {
            "section_id": "main",
            "capability_id": "section.log_plot",
            "goal": "Configure track.",
            "components": [
                {
                    "component_id": "track",
                    "target_id": "track",
                    "capability_id": f"track.{kind}",
                    "parent_component_id": None,
                    "goal": "Configure track.",
                }
            ],
        }
    )
    document = {"sections": [{"id": "main", "tracks": [{"id": "track", "kind": kind}]}]}
    model = section_contract(
        plan, document if existing else {}, create_builtin_registry(), reconstruct=reconstruct
    )
    payload = {
        "section": {
            "section_id": "main",
            "title": "Main",
            "tracks": [{"track_id": "track", "title": "Track", "kind": kind, "width_mm": 30}],
        }
    }
    schema = model.model_json_schema()
    validator = Draft202012Validator(schema)
    validator.validate(payload)
    model.model_validate(payload)
    if kind in {"reference", "annotation"}:
        assert "x_scale" not in schema["$defs"]["trackTrackIntent"]["properties"]
    for scale in ({"kind": "linear", "minimum": 0, "maximum": 1}, None, {"clear": True}):
        candidate = deepcopy(payload)
        candidate["section"]["tracks"][0]["x_scale"] = scale
        if kind in {"reference", "annotation"}:
            assert not validator.is_valid(candidate)
            with pytest.raises(ValidationError, match="x_scale"):
                model.model_validate(candidate)
        elif isinstance(scale, dict) and "kind" in scale:
            validator.validate(candidate)
            model.model_validate(candidate)


def test_reference_binding_retains_independent_scale() -> None:
    """Reference-track curves may use their own reversed display ranges."""
    plan = SectionPlan.model_validate(
        {
            "section_id": "main",
            "capability_id": "section.log_plot",
            "goal": "Plot tension in depth track.",
            "components": [
                {
                    "component_id": "depth",
                    "target_id": "depth",
                    "capability_id": "track.reference",
                    "parent_component_id": None,
                    "goal": "Add depth.",
                },
                {
                    "component_id": "tension",
                    "target_id": "main.depth.TENS.1",
                    "capability_id": "binding.curve",
                    "parent_component_id": "depth",
                    "goal": "Plot tension.",
                },
            ],
        }
    )
    model = section_contract(plan, {}, create_builtin_registry(), reconstruct=True)
    payload = {
        "section": {
            "section_id": "main",
            "title": "Main",
            "tracks": [
                {
                    "track_id": "depth",
                    "title": "Depth",
                    "kind": "reference",
                    "width_mm": 10,
                    "bindings": [
                        {
                            "kind": "curve",
                            "binding_id": "main.depth.TENS.1",
                            "channel": "TENS",
                            "scale": {"kind": "linear", "minimum": 5000, "maximum": 0},
                        }
                    ],
                }
            ],
        }
    }
    Draft202012Validator(model.model_json_schema()).validate(payload)
    artifact = model.model_validate(payload)
    assert artifact.section.tracks[0].bindings[0].scale.minimum == 5000
    assert artifact.section.tracks[0].bindings[0].scale.maximum == 0
