"""Regression tests for provider-visible worker ownership and construction schemas."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from wellplot.agent.graph.models import ReconstructionPlan, SectionPlan
from wellplot.agent.graph.planner import ReconstructionPlanner
from wellplot.agent.graph.section_worker import SectionCompiler
from wellplot.agent.graph.worker_contracts import report_contract, section_contract
from wellplot.authoring import load_authoring_document
from wellplot.authoring_context import resolve_authoring_context
from wellplot.capabilities import create_builtin_registry
from wellplot.capabilities.builtins import ReportArtifact
from wellplot.model.intent import AuthoringDocumentIntent


def _document() -> dict[str, object]:
    return {
        "header": {"general_fields": [{"slot_id": "general.country", "label": "State / Country"}]},
        "sections": [
            {
                "id": "main",
                "title": "Main",
                "tracks": [
                    {"id": "existing", "kind": "normal", "title": "Existing", "width_mm": 30},
                ],
            }
        ],
    }


def _plan() -> SectionPlan:
    return SectionPlan.model_validate(
        {
            "section_id": "repeat",
            "capability_id": "section.log_plot",
            "goal": "Build repeat.",
            "components": [
                {
                    "component_id": "repeat.combo.plan",
                    "target_id": "combo",
                    "capability_id": "track.normal",
                    "goal": "Add combo.",
                    "parent_component_id": None,
                }
            ],
        }
    )


def _nested_plan() -> SectionPlan:
    """Declare every nested object under its exact planned track parent."""
    return SectionPlan.model_validate(
        {
            "section_id": "repeat",
            "capability_id": "section.log_plot",
            "goal": "Build a scoped mixed-content section.",
            "components": [
                {
                    "component_id": "repeat.combo",
                    "target_id": "combo",
                    "capability_id": "track.normal",
                    "goal": "Add combo.",
                    "parent_component_id": None,
                },
                {
                    "component_id": "repeat.notes",
                    "target_id": "notes",
                    "capability_id": "track.annotation",
                    "goal": "Add notes.",
                    "parent_component_id": None,
                },
                {
                    "component_id": "repeat.combo.gr",
                    "target_id": "repeat.combo.GR.1",
                    "capability_id": "binding.curve",
                    "goal": "Bind gamma ray.",
                    "parent_component_id": "repeat.combo",
                },
                {
                    "component_id": "repeat.combo.fill",
                    "target_id": "repeat.combo.fill.1",
                    "capability_id": "fill.curve",
                    "goal": "Add the planned curve fill.",
                    "parent_component_id": "repeat.combo",
                },
                {
                    "component_id": "repeat.notes.marker",
                    "target_id": "repeat.notes.marker.1",
                    "capability_id": "annotation.typed",
                    "goal": "Add the planned annotation.",
                    "parent_component_id": "repeat.notes",
                },
            ],
        }
    )


@pytest.mark.parametrize(
    "field", ["sections", "curve_bindings", "raster_bindings", "fills", "annotations"]
)
def test_report_schema_rejects_section_content_before_submission(field: str) -> None:
    """All three rejected submissions from run 00f94d exposed these forbidden fields."""
    payload = {"intent": {field: {"operation": "clear"}}}
    for model in (ReportArtifact, report_contract(_document(), reconstruct=True)):
        schema = model.model_json_schema()
        assert list(Draft202012Validator(schema).iter_errors(payload))
        with pytest.raises(ValidationError):
            model.model_validate(payload)


@pytest.mark.parametrize(
    "page",
    [
        {"width_mm": 0},
        {"height_mm": 0},
        {"width_mm": -1},
        {"height_mm": -1},
    ],
)
def test_report_schema_rejects_non_positive_page_dimensions(page: dict[str, object]) -> None:
    """Page dimensions fail at the provider contract, not during execution."""
    payload = {"intent": {"page": page}}
    for model in (ReportArtifact, report_contract(_document(), reconstruct=True)):
        schema = model.model_json_schema()
        assert list(Draft202012Validator(schema).iter_errors(payload))
        with pytest.raises(ValidationError):
            model.model_validate(payload)


def test_report_schema_permits_zero_sized_page_layout_settings() -> None:
    """Page layout fields retain the zero values allowed by ``PagePatch``."""
    payload = {
        "intent": {
            "page": {
                "margin_left_mm": 0,
                "margin_right_mm": 0,
                "margin_top_mm": 0,
                "margin_bottom_mm": 0,
                "header_height_mm": 0,
                "track_header_height_mm": 0,
                "footer_height_mm": 0,
                "track_gap_mm": 0,
            }
        }
    }
    for model in (ReportArtifact, report_contract(_document(), reconstruct=True)):
        assert not list(Draft202012Validator(model.model_json_schema()).iter_errors(payload))
        model.model_validate(payload)


@pytest.mark.parametrize("reconstruct", [True, False])
def test_report_requires_existing_header_slot_ids(reconstruct: bool) -> None:
    """Reject invented targets in both modes while accepting an inspected slot."""
    model = report_contract(_document(), reconstruct=reconstruct)
    payload = {
        "intent": {
            "header": {
                "general_fields": [
                    {"slot_id": "general.state", "value": {"value": "Utah"}},
                ]
            }
        }
    }
    assert list(Draft202012Validator(model.model_json_schema()).iter_errors(payload))
    with pytest.raises(ValidationError, match="slot_id"):
        model.model_validate(payload)
    payload["intent"]["header"]["general_fields"][0]["slot_id"] = "general.country"
    model.model_validate(payload)


def test_planner_requires_inspected_header_slot_ids() -> None:
    """A semantic State request is directed to the inspected State/Country slot."""

    class Model:
        async def generate(self, **kwargs: object) -> BaseModel:
            response_model = kwargs["response_model"]
            assert isinstance(response_model, type)
            invalid = {
                "summary": "Set the state.",
                "report_values": {
                    "header": {
                        "general_fields": [{"slot_id": "general.state", "value": "Utah"}],
                    }
                },
                "sections": [
                    {
                        "section_id": "main",
                        "capability_id": "section.log_plot",
                        "goal": "Keep main.",
                        "components": [
                            {
                                "component_id": "main.existing",
                                "target_id": "existing",
                                "capability_id": "track.normal",
                                "goal": "Keep existing.",
                                "parent_component_id": None,
                            }
                        ],
                    }
                ],
            }
            with pytest.raises(ValidationError, match="general.country"):
                response_model.model_validate(invalid)
            invalid["report_values"]["header"]["general_fields"][0]["slot_id"] = "general.country"
            return response_model.model_validate(invalid)

    plan = asyncio.run(
        ReconstructionPlanner(model=Model(), registry=create_builtin_registry()).plan(
            request="Set the state to Utah.",
            current_document=_document(),
            source_manifest={},
        )
    )
    assert plan.report_values["header"]["general_fields"] == [
        {"slot_id": "general.country", "value": "Utah"}
    ]


def test_construction_rejects_clear_and_preserves_omitted_values() -> None:
    """An omitted construction field stays omitted through model serialization."""
    model = section_contract(_plan(), _document(), create_builtin_registry(), reconstruct=True)
    payload = {
        "section": {
            "section_id": "repeat",
            "title": "Repeat",
            "tracks": [
                {"track_id": "combo", "title": "Combo", "kind": "normal", "width_mm": 50},
            ],
        }
    }
    valid = model.model_validate(payload)
    assert valid.model_dump(exclude_unset=True) == payload
    assert "AuthoringClearIntent" not in model.model_json_schema().get("$defs", {})
    for field in ("title", "x_scale", "grid", "track_header"):
        invalid = deepcopy(payload)
        invalid["section"]["tracks"][0][field] = {"operation": "clear"}
        assert list(Draft202012Validator(model.model_json_schema()).iter_errors(invalid))
        with pytest.raises(ValidationError):
            model.model_validate(invalid)


@pytest.mark.parametrize("reconstruct", [True, False])
@pytest.mark.parametrize("collection", ["bindings", "fills", "annotations"])
def test_unplanned_child_collections_advertise_no_item_models(
    reconstruct: bool, collection: str
) -> None:
    """Empty collections preserve omission without inviting unplanned objects."""
    model = section_contract(
        _plan(), _document(), create_builtin_registry(), reconstruct=reconstruct
    )
    schema = model.model_json_schema()
    assert not any(
        name.endswith(("BindingIntent", "FillIntent", "AnnotationIntent"))
        for name in schema.get("$defs", {})
    )
    payload = {
        "section": {
            "section_id": "repeat",
            "title": "Repeat",
            "tracks": [
                {
                    "track_id": "combo",
                    "title": "Combo",
                    "kind": "normal",
                    "width_mm": 50,
                    collection: [],
                }
            ],
        }
    }
    assert not list(Draft202012Validator(schema).iter_errors(payload))
    assert model.model_validate(payload).model_dump(exclude_unset=True) == payload
    payload["section"]["tracks"][0][collection] = [{}]
    assert list(Draft202012Validator(schema).iter_errors(payload))
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    "change",
    [
        {"track_id": "repeat.combo.plan"},
        {"section_id": "main"},
        {"kind": "array"},
        {"title": None},
        {"width_mm": 0},
    ],
)
def test_track_identity_and_creation_requirements_are_structural(change: dict[str, object]) -> None:
    """Provider JSON Schema and Pydantic enforce the same creation contract."""
    model = section_contract(_plan(), _document(), create_builtin_registry(), reconstruct=True)
    payload = {
        "section": {
            "section_id": "repeat",
            "title": "Repeat",
            "tracks": [
                {"track_id": "combo", "title": "Combo", "kind": "normal", "width_mm": 50, **change},
            ],
        }
    }
    with pytest.raises(ValidationError):
        model.model_validate(payload)
    assert list(Draft202012Validator(model.model_json_schema()).iter_errors(payload))


def test_revision_retains_explicit_clear_and_report_removal_contracts() -> None:
    """Revisions can still explicitly clear existing fields and remove remarks."""
    plan = SectionPlan(
        section_id="main",
        capability_id="section.log_plot",
        goal="Clear grid.",
        components=[
            {
                "component_id": "main.existing",
                "target_id": "existing",
                "capability_id": "track.normal",
                "goal": "Clear the existing grid.",
                "parent_component_id": None,
            }
        ],
    )
    model = section_contract(plan, _document(), create_builtin_registry(), reconstruct=False)
    payload = {
        "section": {
            "section_id": "main",
            "subtitle": {"operation": "clear"},
            "tracks": [
                {"track_id": "existing", "grid": {"operation": "clear"}},
            ],
        }
    }
    assert model.model_validate(payload).model_dump(exclude_unset=True) == payload
    report = report_contract(_document(), reconstruct=False)
    report.model_validate(
        {
            "intent": {
                "subtitle": {"operation": "clear"},
                "removals": [
                    {"object_kind": "remark", "object_id": "notice"},
                ],
            }
        }
    )
    with pytest.raises(ValidationError):
        report.model_validate(
            {"intent": {"removals": [{"object_kind": "track", "object_id": "existing"}]}}
        )


@pytest.mark.parametrize("kind", ["normal", "reference", "array", "annotation"])
@pytest.mark.parametrize("collection", [[], {"operation": "clear"}])
def test_empty_and_cleared_collections_do_not_require_content_track_kinds(
    kind: str,
    collection: object,
) -> None:
    """Only actual fill or annotation objects impose track compatibility."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "track",
                        "kind": kind,
                        "fills": collection,
                        "annotations": collection,
                    }
                ],
            }
        ]
    )
    assert resolve_authoring_context(intent).ready


def test_worker_detects_omitted_planned_targets() -> None:
    """A worker cannot claim coverage of targets absent from its artifact."""
    compiler = SectionCompiler(model=object(), registry=create_builtin_registry())
    model = section_contract(_plan(), _document(), compiler.registry, reconstruct=True)
    artifact = model.model_validate(
        {
            "section": {
                "section_id": "repeat",
                "title": "Repeat",
                "tracks": [
                    {"track_id": "combo", "title": "Combo", "kind": "normal", "width_mm": 50},
                ],
            }
        }
    )
    compiler._validate_targets(artifact, _plan())
    missing = _plan().model_copy(deep=True)
    missing.components[0].target_id = "other"
    with pytest.raises(ValueError, match="planned target order"):
        compiler._validate_targets(artifact, missing)


def test_section_schema_binds_nested_content_to_planned_identity() -> None:
    """New bindings, fills and annotations require their planned nested IDs."""
    registry = create_builtin_registry()
    plan = _nested_plan()
    model = section_contract(plan, _document(), registry, reconstruct=True)
    payload = {
        "section": {
            "section_id": "repeat",
            "title": "Repeat",
            "tracks": [
                {
                    "track_id": "combo",
                    "title": "Combo",
                    "kind": "normal",
                    "width_mm": 50,
                    "bindings": [
                        {
                            "kind": "curve",
                            "binding_id": "repeat.combo.GR.1",
                            "channel": "GR",
                        }
                    ],
                    "fills": [{"fill_id": "repeat.combo.fill.1"}],
                },
                {
                    "track_id": "notes",
                    "title": "Notes",
                    "kind": "annotation",
                    "width_mm": 15,
                    "annotations": [{"annotation_id": "repeat.notes.marker.1"}],
                },
            ],
        }
    }
    artifact = model.model_validate(payload)
    SectionCompiler(model=object(), registry=registry)._validate_targets(artifact, plan)

    invalid_values = [
        ("bindings", "binding_id", "unplanned.binding"),
        ("fills", "fill_id", "unplanned.fill"),
    ]
    for collection, field, value in invalid_values:
        invalid = deepcopy(payload)
        invalid["section"]["tracks"][0][collection][0][field] = value
        with pytest.raises(ValidationError):
            model.model_validate(invalid)

    invalid = deepcopy(payload)
    del invalid["section"]["tracks"][0]["bindings"][0]["channel"]
    with pytest.raises(ValidationError, match="channel"):
        model.model_validate(invalid)

    invalid = deepcopy(payload)
    invalid["section"]["tracks"][1]["annotations"][0]["annotation_id"] = "unplanned.marker"
    with pytest.raises(ValidationError):
        model.model_validate(invalid)


def test_section_schema_requires_the_declared_source_route() -> None:
    """A planned staged source cannot be omitted or changed by a section worker."""
    plan = SectionPlan.model_validate(
        {
            **_plan().model_dump(mode="json"),
            "data_source": {"source_path": "repeat.dlis", "source_format": "dlis"},
        }
    )
    model = section_contract(plan, _document(), create_builtin_registry(), reconstruct=True)
    payload = {
        "section": {
            "section_id": "repeat",
            "title": "Repeat",
            "data_source": {"source_path": "repeat.dlis", "source_format": "dlis"},
            "tracks": [
                {"track_id": "combo", "title": "Combo", "kind": "normal", "width_mm": 50},
            ],
        }
    }
    model.model_validate(payload)

    missing = deepcopy(payload)
    del missing["section"]["data_source"]
    with pytest.raises(ValidationError, match="data_source"):
        model.model_validate(missing)

    invalid = deepcopy(payload)
    invalid["section"]["data_source"]["source_path"] = "other.dlis"
    with pytest.raises(ValidationError, match="source_path"):
        model.model_validate(invalid)


def test_new_section_plan_requires_components_in_advertised_schema() -> None:
    """A plan that hides new tracks in prose fails its advertised schema."""

    class Model:
        async def generate(self, **kwargs: object) -> BaseModel:
            schema = kwargs["response_model"].model_json_schema()
            payload = {
                "summary": "Build repeat",
                "sections": [
                    {
                        "section_id": "repeat",
                        "capability_id": "section.log_plot",
                        "goal": "Build repeat",
                        "components": [],
                    }
                ],
            }
            assert list(Draft202012Validator(schema).iter_errors(payload))
            return kwargs["response_model"].model_validate(payload)

    with pytest.raises(ValidationError, match="components"):
        asyncio.run(
            ReconstructionPlanner(model=Model(), registry=create_builtin_registry()).plan(
                request="Create the repeat pass.",
                current_document=_document(),
                source_manifest={},
            )
        )


def test_cbl_report_schema_is_smaller_and_contains_only_owned_fields() -> None:
    """CBL worker schemas remain scoped instead of duplicating document models."""
    document = load_authoring_document(
        Path("tests/fixtures/agentic_cbl/cased_hole_starter.log.yaml")
    )
    current_document = document.model_dump(mode="json")
    report_schema = report_contract(current_document, reconstruct=True).model_json_schema()
    assert len(json.dumps(report_schema, separators=(",", ":"))) < 15000
    assert "AuthoringTrackIntent" not in report_schema.get("$defs", {})

    contract = json.loads(
        Path("tests/fixtures/agentic_cbl/compile_contract.json").read_text(encoding="utf-8")
    )
    plan = ReconstructionPlan.model_validate(contract["reconstruction_plan"])
    registry = create_builtin_registry()
    for section in plan.sections:
        schema = section_contract(
            section, current_document, registry, reconstruct=True
        ).model_json_schema()
        assert len(json.dumps(schema, separators=(",", ":"))) < 35000
        assert not any(
            name.endswith(("FillIntent", "AnnotationIntent")) for name in schema.get("$defs", {})
        )
