"""Provider-free SI-V2R model, compiler, and equivalence tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from scripts.semantic_ir_v2r_analysis import capability_type_equivalent

from wellplot.agent.code_mode.semantic_ir_v2_registry import (
    SemanticLoweringRule,
    create_builtin_semantic_lowering_registry,
)
from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R
from wellplot.agent.code_mode.semantic_ir_v2r_compiler import compile_semantic_ir_v2r
from wellplot.capabilities import create_builtin_registry

FIXTURE = Path("tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json")


def _gold_cases() -> list[dict[str, object]]:
    """Load the manually authored V2R gold fixture."""
    return list(json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"])


def _signature(plan: object) -> dict[str, object]:
    """Project a plan into the reviewable capability signature."""
    return {
        "report": list(plan.report_task.capability_ids) if plan.report_task else [],
        "sections": [list(task.capability_ids) for task in plan.section_tasks],
    }


def test_all_fresh_v2r_gold_cases_compile_to_existing_gold_capability_types() -> None:
    """All 24 authored intents lower to the frozen CM-59A capability topology."""
    corpus = {
        case["case_id"]: case
        for case in json.loads(
            Path("tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json").read_text()
        )["cases"]
    }
    for case in _gold_cases():
        plan = compile_semantic_ir_v2r(
            {key: value for key, value in case.items() if key != "case_id"},
            registry=create_builtin_registry(),
        )
        expected = {
            "report": corpus[case["case_id"]]["expected_report_capabilities"],
            "sections": corpus[case["case_id"]]["expected_sections"],
        }
        assert capability_type_equivalent(_signature(plan), expected)


def test_additional_domain_fixtures_are_representable() -> None:
    """The selected abstraction is not limited to the 24-case benchmark."""
    payload = json.loads(
        Path("tests/fixtures/semantic_ir_v2r/domain_representability.json").read_text()
    )
    for case in payload["cases"]:
        plan = compile_semantic_ir_v2r(
            case["intent"],
            registry=create_builtin_registry(),
        )
        assert capability_type_equivalent(_signature(plan), case["expected"])


def test_reference_intent_is_section_owned_not_a_feature_boolean() -> None:
    """Companion and reference-track meanings lower through the same data feature."""
    companion = {
        "summary": "companion",
        "sections": [
            {
                "kind": "log_plot",
                "goal": "density with depth lane",
                "features": [{"kind": "curve", "semantic_id": "density"}],
                "reference_intent": {"kind": "companion_depth_lane"},
            }
        ],
    }
    reference_track = {
        "summary": "reference data",
        "sections": [
            {
                "kind": "log_plot",
                "goal": "data on reference track",
                "features": [{"kind": "raster", "semantic_id": "image"}],
                "reference_intent": {
                    "kind": "reference_track",
                    "target_semantic_id": "image",
                },
            }
        ],
    }
    registry = create_builtin_registry()
    companion_plan = compile_semantic_ir_v2r(companion, registry=registry)
    reference_track_plan = compile_semantic_ir_v2r(reference_track, registry=registry)
    assert _signature(companion_plan)["sections"] == [
        ["section.log_plot", "track.reference", "track.normal", "binding.curve"]
    ]
    assert _signature(reference_track_plan)["sections"] == [
        ["section.log_plot", "track.reference", "track.array", "binding.raster"]
    ]

    same_curve_companion = companion_plan
    same_curve_reference = compile_semantic_ir_v2r(
        {
            "summary": "reference data",
            "sections": [
                {
                    "kind": "log_plot",
                    "goal": "density with depth lane",
                    "features": [{"kind": "curve", "semantic_id": "density"}],
                    "reference_intent": {
                        "kind": "reference_track",
                        "target_semantic_id": "density",
                    },
                }
            ],
        },
        registry=registry,
    )
    assert same_curve_companion.section_tasks == same_curve_reference.section_tasks
    assert same_curve_companion.reference_intents != same_curve_reference.reference_intents
    assert same_curve_companion.reference_intents[0].kind == "companion_depth_lane"
    assert same_curve_reference.reference_intents[0].kind == "reference_track"


def test_reference_track_requires_an_existing_feature_target() -> None:
    """The compiler does not invent a feature to satisfy reference intent."""
    with pytest.raises(ValidationError, match="Reference target"):
        SemanticIRV2R.model_validate(
            {
                "summary": "invalid",
                "sections": [
                    {
                        "kind": "log_plot",
                        "goal": "invalid",
                        "features": [{"kind": "curve", "semantic_id": "curve"}],
                        "reference_intent": {
                            "kind": "reference_track",
                            "target_semantic_id": "missing",
                        },
                    }
                ],
            }
        )


def test_report_work_is_coarse_and_worker_details_are_forbidden() -> None:
    """Report construction fields do not leak into the planner IR."""
    with pytest.raises(ValidationError):
        SemanticIRV2R.model_validate(
            {
                "summary": "invalid report",
                "report_work": {"goal": "write report", "title": "not planner-owned"},
            }
        )


def test_v2r_schema_has_no_provider_or_worker_detail_fields() -> None:
    """The provider-facing schema remains planner-level and path-free."""
    schema_text = json.dumps(SemanticIRV2R.model_json_schema(), sort_keys=True)
    for forbidden in (
        "channel",
        "scale",
        "sample_axis",
        "canonical_id",
        "filesystem",
        "renderer",
        "provider",
        "report SDK",
    ):
        assert forbidden not in schema_text
    assert '"reference"' not in schema_text


def test_plugin_semantic_extension_uses_generic_compiler() -> None:
    """A registry extension compiles without a central compiler edit."""
    lowering = create_builtin_semantic_lowering_registry().register(
        SemanticLoweringRule(
            semantic_key="plugin.marker",
            capability_ids=("track.annotation", "annotation.typed"),
        )
    )
    intent = {
        "summary": "plugin",
        "sections": [
            {
                "kind": "log_plot",
                "goal": "plugin marker",
                "features": [
                    {
                        "kind": "extension",
                        "semantic_id": "marker",
                        "semantic_key": "plugin.marker",
                    }
                ],
            }
        ],
    }
    plan = compile_semantic_ir_v2r(
        intent,
        registry=create_builtin_registry(),
        lowering_registry=lowering,
    )
    assert _signature(plan)["sections"] == [
        ["section.log_plot", "track.annotation", "annotation.typed"]
    ]


def test_ambiguous_plugin_parent_fails_closed() -> None:
    """A plugin cannot make the compiler guess between reference and normal tracks."""
    lowering = create_builtin_semantic_lowering_registry().register(
        SemanticLoweringRule(semantic_key="plugin.curve", capability_ids=("binding.curve",))
    )
    with pytest.raises(Exception, match="multiple meaningful parent"):
        compile_semantic_ir_v2r(
            {
                "summary": "ambiguous",
                "sections": [
                    {
                        "kind": "log_plot",
                        "goal": "ambiguous",
                        "features": [
                            {
                                "kind": "extension",
                                "semantic_id": "curve",
                                "semantic_key": "plugin.curve",
                            }
                        ],
                    }
                ],
            },
            registry=create_builtin_registry(),
            lowering_registry=lowering,
        )


def test_compilation_does_not_mutate_intent() -> None:
    """The provider-facing value remains immutable across deterministic lowering."""
    payload = {
        "summary": "immutable",
        "sections": [
            {
                "kind": "log_plot",
                "goal": "immutable",
                "features": [{"kind": "curve", "semantic_id": "curve"}],
            }
        ],
    }
    before = json.loads(json.dumps(payload))
    compile_semantic_ir_v2r(payload, registry=create_builtin_registry())
    assert payload == before


def test_capability_equivalence_ignores_internal_order_but_not_section_order() -> None:
    """Evaluation equivalence is not a replacement for production validation."""
    expected = {
        "report": ["report.standard"],
        "sections": [["section.log_plot", "track.normal", "binding.curve"]],
    }
    reordered = {
        "report": ["report.standard"],
        "sections": [["binding.curve", "section.log_plot", "track.normal"]],
    }
    reversed_sections = {
        "report": [],
        "sections": [
            ["section.log_plot", "track.normal", "binding.curve"],
            ["section.log_plot", "track.array", "binding.raster"],
        ],
    }
    expected_two = {
        "report": [],
        "sections": [
            ["section.log_plot", "track.normal", "binding.curve"],
            ["section.log_plot", "track.array", "binding.raster"],
        ],
    }
    assert capability_type_equivalent(reordered, expected)
    assert capability_type_equivalent(reversed_sections, expected_two)
    assert not capability_type_equivalent(
        {"report": [], "sections": list(reversed(expected_two["sections"]))}, expected_two
    )
    assert not capability_type_equivalent(
        {"report": [], "sections": [["section.log_plot", "track.normal"]]}, expected_two
    )
    assert not capability_type_equivalent(
        {"report": [], "sections": [["section.log_plot", "track.normal", "track.normal"]]},
        {"report": [], "sections": [["section.log_plot", "track.normal"]]},
    )
