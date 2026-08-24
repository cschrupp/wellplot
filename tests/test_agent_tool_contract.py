"""Tests for the stable model-facing tool profile."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from wellplot.agent.tool_contract import (
    stable_tool_budget,
    stable_tool_profile,
)
from wellplot.authoring_service import authoring_operation_json_schema

TASK_TOOL_COVERAGE = {
    "initial_open_hole": ("create_draft", "edit_report_settings", "edit_header"),
    "remarks_only": ("edit_remarks",),
    "natural_language_header_fill": ("inspect_authoring", "edit_header"),
    "sp_overview_curve": ("inspect_source", "edit_curve_binding"),
    "resistivity_track": ("inspect_source", "edit_track", "edit_curve_binding"),
    "uncatalogued_scalar_track": ("inspect_vocab", "edit_track", "edit_curve_binding"),
    "duplicate_mirrored_fill": ("edit_curve_binding", "edit_fill"),
    "array_raster_track": ("inspect_source", "edit_track", "edit_raster_binding"),
    "annotation_objects": ("edit_annotation",),
    "page_output_depth_settings": ("edit_report_settings",),
    "flexible_main_repeat_sections": ("edit_section", "edit_track"),
    "reject_ambiguous_unavailable_requests": ("inspect_source", "validate_logfile"),
}


def test_stable_profile_has_sixteen_distinct_responsibilities() -> None:
    """The profile stays within the approved tool-count budget."""
    profile = stable_tool_profile()

    assert len(profile) == 17
    assert len({tool.name for tool in profile}) == 17
    assert len({tool.description for tool in profile}) == 17


def test_profile_budget_is_bounded_and_smaller_than_diagnostic_contract() -> None:
    """The compact profile is substantially smaller than the canonical union."""
    budget = stable_tool_budget()
    diagnostic_chars = len(
        json.dumps(authoring_operation_json_schema(), separators=(",", ":"), sort_keys=True)
    )

    assert budget["tool_count"] <= 17
    assert budget["combined_schema_chars"] <= 40_000
    # Typed nested fields and conditional remark content cost more than the
    # former coarse ``object`` annotations.
    # The wire contract remains substantially smaller than the canonical union.
    assert budget["combined_schema_chars"] < diagnostic_chars * 0.38


def test_profile_does_not_expose_internal_canonical_unions() -> None:
    """Model-facing schemas contain only compact user-facing fields."""
    serialized = json.dumps(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "input": tool.input_schema,
                "output": tool.output_schema,
            }
            for tool in stable_tool_profile()
        ],
        sort_keys=True,
    )

    assert "AuthoringDocumentIntent" not in serialized
    assert "AuthoringDocumentSpec" not in serialized
    assert "canonical_operations" not in serialized
    assert "extensions" not in serialized




def test_binding_and_remarks_tools_expose_one_public_payload_shape() -> None:
    """Do not advertise host-only wrapper/flat aliases for the same mutation."""
    profile = {tool.name: tool for tool in stable_tool_profile()}

    curve_fields = set(profile["edit_curve_binding"].input_schema["properties"])
    raster_fields = set(profile["edit_raster_binding"].input_schema["properties"])
    remarks_fields = set(profile["edit_remarks"].input_schema["properties"])

    assert "binding" not in curve_fields
    assert "patch" not in curve_fields
    assert "binding" not in raster_fields
    assert "patch" not in raster_fields
    assert {"title", "text", "lines", "alignment"}.isdisjoint(remarks_fields)
    assert {"remark", "patch"} <= remarks_fields


def test_binding_tools_require_target_scope_and_channel() -> None:
    """Binding calls carry the complete target identity on the public wire."""
    profile = {tool.name: tool for tool in stable_tool_profile()}

    for tool_name in ("edit_curve_binding", "edit_raster_binding"):
        required = set(profile[tool_name].input_schema["required"])
        assert {"section_id", "track_id", "channel"} <= required


def test_high_risk_nested_fields_are_not_unconstrained_objects() -> None:
    """Scale/style fields that triggered provider repair logic remain typed on the wire."""
    profile = {tool.name: tool for tool in stable_tool_profile()}

    for tool_name, field_name in (
        ("edit_track", "x_scale"),
        ("edit_curve_binding", "scale"),
        ("edit_curve_binding", "style"),
        ("edit_raster_binding", "style"),
    ):
        schema = profile[tool_name].input_schema["properties"][field_name]
        serialized = json.dumps(schema, sort_keys=True)
        assert '"additionalProperties": true' not in serialized
        assert "$ref" in serialized


def test_mutation_tools_have_standard_results_and_annotations() -> None:
    """Every edit responsibility advertises safe response and behavior metadata."""
    for tool in stable_tool_profile():
        assert set(tool.annotations) == {
            "readOnlyHint",
            "idempotentHint",
            "destructiveHint",
            "openWorldHint",
        }
        if tool.name.startswith("edit_") or tool.name == "create_draft":
            assert "operation" in tool.input_schema["properties"]
            required = set(tool.output_schema["required"])
            assert {"ok", "changed", "warnings", "next_steps"} <= required


def test_remarks_tool_explains_operation_payloads() -> None:
    """The active remarks task receives generic operation-shape guidance."""
    remarks = next(tool for tool in stable_tool_profile() if tool.name == "edit_remarks")

    assert "add=remark" in remarks.description
    assert "actual content" in remarks.description
    assert "non-empty remark.text" in remarks.description
    assert "update=remark_id+patch" in remarks.description
    assert "remove/move=remark_id" in remarks.description
    assert "clear=all" in remarks.description
    remark = remarks.input_schema["properties"]["remark"]
    variants = remark.get("anyOf", [])
    reference = next(item["$ref"] for item in variants if isinstance(item, dict) and "$ref" in item)
    definition_name = reference.rsplit("/", 1)[-1]
    definition = remarks.input_schema["$defs"][definition_name]
    assert {"title", "text", "lines", "alignment"} <= set(definition["properties"])
    text_schema = next(
        item
        for item in definition["properties"]["text"]["anyOf"]
        if item.get("type") == "string"
    )
    lines_schema = next(
        item
        for item in definition["properties"]["lines"]["anyOf"]
        if item.get("type") == "array"
    )
    assert text_schema["minLength"] == 1
    assert lines_schema["minItems"] == 1
    assert {tuple(item["required"]) for item in definition["anyOf"]} == {
        ("text",),
        ("lines",),
    }


def test_fill_tool_requires_dispatch_target_fields() -> None:
    """The fill schema requires fields that every dispatcher branch consumes."""
    fill = next(tool for tool in stable_tool_profile() if tool.name == "edit_fill")

    assert {"section_id", "track_id", "channel"} <= set(fill.input_schema["required"])
    with pytest.raises(ValidationError):
        fill.input_model.model_validate(
            {
                "logfile_path": "draft.log.yaml",
                "operation": "add",
                "section_id": "main",
                "track_id": "porosity",
                "kind": "between_instances",
                "binding_id": "porosity.nphi",
                "other_binding_id": "porosity.rhob",
            }
        )


def test_track_tool_explains_add_and_existing_target_semantics() -> None:
    """Track operation guidance distinguishes creation from edits."""
    track = next(tool for tool in stable_tool_profile() if tool.name == "edit_track")

    assert "operation=add" in track.description
    assert "section_id and track_id are required for every operation" in track.description
    assert "title, kind, and width_mm in the same call" in track.description
    assert "Never call set_scales without a scale payload" in track.description
    assert "successful no-op" in track.description
    assert "track_id must already exist" in track.description
    assert {"section_id", "track_id"} <= set(track.input_schema["required"])


def test_track_add_requires_all_creation_fields_in_the_profile() -> None:
    """The stable profile requires the track identity on every operation."""
    track = next(tool for tool in stable_tool_profile() if tool.name == "edit_track")

    with pytest.raises(ValidationError):
        track.input_model.model_validate(
            {
                "logfile_path": "draft.log.yaml",
                "operation": "add",
                "title": "Resistivity",
                "kind": "normal",
                "width_mm": 30,
            }
        )


def test_raster_schema_uses_canonical_alpha_field() -> None:
    """Keep the advertised raster opacity name aligned with the service patch."""
    raster = next(tool for tool in stable_tool_profile() if tool.name == "edit_raster_binding")

    assert "alpha" in raster.input_schema["properties"]
    assert "raster_alpha" not in raster.input_schema["properties"]


def test_raster_schema_exposes_typed_array_presentation_fields() -> None:
    """Expose the existing typed VDL presentation controls at the stable boundary."""
    raster = next(tool for tool in stable_tool_profile() if tool.name == "edit_raster_binding")

    for field_name in (
        "waveform_normalization",
        "clip_percentiles",
        "interpolation",
        "colorbar",
        "sample_axis",
        "waveform",
    ):
        field = raster.input_schema["properties"][field_name]
        variants = field.get("anyOf", [])
        assert isinstance(variants, list)
        assert any(
            isinstance(variant, dict)
            and (
                "$ref" in variant
                or variant.get("type") in {"array", "string"}
                or "enum" in variant
            )
            for variant in variants
        )


def test_inspect_authoring_exposes_server_supported_object_kinds() -> None:
    """The provider sees valid inspection kinds instead of guessing a document root."""
    inspect = next(tool for tool in stable_tool_profile() if tool.name == "inspect_authoring")

    object_kind = inspect.input_schema["properties"]["object_kind"]
    assert set(object_kind["enum"]) == {
        "page",
        "depth",
        "header_slot",
        "service_title",
        "section",
        "track",
        "curve_binding",
        "raster_binding",
        "annotation",
        "fill",
        "remark",
    }


def test_profile_does_not_advertise_ignored_create_or_render_controls() -> None:
    """Keep public fields limited to controls the stable dispatcher honors."""
    profile = {tool.name: tool for tool in stable_tool_profile()}

    create_fields = profile["create_draft"].input_schema["properties"]
    render_fields = profile["render_logfile"].input_schema["properties"]

    assert "source_data_file" not in create_fields
    assert "backend" not in render_fields


def test_all_development_tasks_map_to_existing_profile_tools() -> None:
    """The profile expresses every planned task without a task-specific tool."""
    names = {tool.name for tool in stable_tool_profile()}

    assert len(TASK_TOOL_COVERAGE) == 12
    assert all(
        tool_name in names
        for responsibilities in TASK_TOOL_COVERAGE.values()
        for tool_name in responsibilities
    )
    assert "caliper" not in names
    assert "cbl" not in names


def test_profile_models_enforce_declared_operation_and_nested_payloads() -> None:
    """The models behind the advertised profile reject invalid typed values."""
    profile = {tool.name: tool for tool in stable_tool_profile()}

    with pytest.raises(ValidationError):
        profile["create_draft"].input_model.model_validate(
            {"logfile_path": "draft.log.yaml", "operation": "replace"}
        )
    with pytest.raises(ValidationError):
        profile["inspect_authoring"].input_model.model_validate(
            {
                "logfile_path": "draft.log.yaml",
                "object_kind": "document",
            }
        )
    with pytest.raises(ValidationError):
        profile["edit_remarks"].input_model.model_validate(
            {
                "logfile_path": "draft.log.yaml",
                "operation": "add",
                "remark": {"title": "Notes", "unsupported": "value"},
            }
        )


def test_profile_output_models_reject_undeclared_fields() -> None:
    """The structured response envelopes cannot silently drift at runtime."""
    mutation = next(tool for tool in stable_tool_profile() if tool.name == "edit_track")
    assert mutation.output_model is not None

    with pytest.raises(ValidationError):
        mutation.output_model.model_validate(
            {
                "ok": True,
                "changed": False,
                "target": {},
                "before": {},
                "after": {},
                "warnings": [],
                "next_steps": [],
                "unexpected": True,
            }
        )
