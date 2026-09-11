"""Tests for provider-neutral desired-state authoring intents."""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from wellplot.model import (
    AuthoringClearIntent,
    AuthoringCurveBindingIntent,
    AuthoringDepthIntent,
    AuthoringDocumentIntent,
    AuthoringFillIntent,
    AuthoringGridIntent,
    AuthoringPageIntent,
    AuthoringRasterBindingIntent,
    AuthoringRemarkIntent,
    AuthoringRemoveIntent,
    AuthoringServiceTitleIntent,
    AuthoringStyleIntent,
    AuthoringTrackIntent,
    authoring_intent_json_schema,
)


def test_intent_distinguishes_omitted_set_and_clear_values() -> None:
    """Preserve the difference between no instruction, set, and clear."""
    intent = AuthoringDocumentIntent(
        title="CBL report",
        output={"dpi": 240},
        header={
            "general_fields": [
                {"slot_id": "rmf", "value": {"value": "0.5 @ 25"}},
            ]
        },
        depth={"major_step": {"operation": "clear"}},
    )

    assert intent.is_omitted("subtitle")
    assert intent.title == "CBL report"
    assert intent.output is not None
    assert intent.output.is_omitted("output_path")
    assert isinstance(intent.depth.major_step, AuthoringClearIntent)
    assert intent.model_dump(exclude_unset=True)["title"] == "CBL report"
    assert "subtitle" not in intent.model_dump(exclude_unset=True)


def test_raw_null_is_not_an_implicit_clear() -> None:
    """Require the explicit clear operation rather than ambiguous JSON null."""
    with pytest.raises(ValidationError, match="cannot be null"):
        AuthoringDocumentIntent(title=None)

    with pytest.raises(ValidationError, match="cannot be null"):
        AuthoringCurveBindingIntent(kind="curve", binding_id="cbl-1", label=None)


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (AuthoringPageIntent, {"width_mm": 0}),
        (AuthoringPageIntent, {"height_mm": -1}),
        (AuthoringDepthIntent, {"major_step": 0}),
        (AuthoringStyleIntent, {"line_width": 0}),
        (AuthoringStyleIntent, {"alpha": 1.1}),
        (AuthoringStyleIntent, {"fill_alpha": -0.1}),
        (AuthoringGridIntent, {"horizontal_major_thickness": 0}),
        (AuthoringGridIntent, {"vertical_main_line_count": 0}),
        (AuthoringGridIntent, {"vertical_secondary_alpha": 1.1}),
        (AuthoringTrackIntent, {"track_id": "curve", "width_mm": 0}),
        (AuthoringRasterBindingIntent, {"kind": "raster", "binding_id": "vdl", "alpha": -0.1}),
        (AuthoringFillIntent, {"fill_id": "gas", "alpha": 1.1}),
        (AuthoringRemarkIntent, {"remark_id": "scope", "font_size": 0}),
        (AuthoringServiceTitleIntent, {"slot_id": "service_title.1", "font_size": 0}),
    ],
)
def test_intent_numeric_constraints_match_canonical_patch_invariants(
    model: type[BaseModel],
    values: dict[str, object],
) -> None:
    """Reject values that the canonical mutation patches cannot persist."""
    with pytest.raises(ValidationError):
        model(**values)


def test_binding_intent_requires_kind_when_nested_under_a_track() -> None:
    """Keep scalar and raster binding intent types unambiguous."""
    track = AuthoringTrackIntent(
        track_id="array",
        bindings=[
            {"kind": "curve", "binding_id": "gr", "channel": "GR"},
            {"kind": "raster", "binding_id": "vdl", "channel": "VDL"},
        ],
    )

    assert [type(binding).__name__ for binding in track.bindings] == [
        "AuthoringCurveBindingIntent",
        "AuthoringRasterBindingIntent",
    ]

    with pytest.raises(ValidationError):
        AuthoringTrackIntent(
            track_id="ambiguous",
            bindings=[{"binding_id": "unknown", "channel": "X"}],
        )


def test_remove_is_separate_from_field_clear() -> None:
    """Represent object deletion with identity and parent scope."""
    intent = AuthoringDocumentIntent(
        removals=[
            AuthoringRemoveIntent(
                object_kind="curve_binding",
                object_id="cbl-2",
                section_id="main_pass",
                track_id="cbl",
            )
        ]
    )

    removal = intent.removals[0]
    assert removal.operation == "remove"
    assert removal.object_id == "cbl-2"
    assert removal.track_id == "cbl"
    assert "title" not in intent.model_dump(exclude_unset=True)


def test_intent_models_are_strict_and_schema_is_generated() -> None:
    """Reject invented fields and expose clear/remove operations in schema."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        AuthoringDocumentIntent(unexpected_field="value")

    schema = authoring_intent_json_schema()
    serialized = str(schema)
    assert "AuthoringClearIntent" in serialized
    assert "AuthoringRemoveIntent" in serialized


def test_intent_schema_advertises_omission_or_explicit_clear_not_raw_null() -> None:
    """Provider schemas must agree with runtime intent-null validation."""
    schema = authoring_intent_json_schema()
    title = schema["properties"]["title"]

    assert {"type": "null"} not in title["anyOf"]
    assert "default" not in title
    assert {"$ref": "#/$defs/AuthoringClearIntent"} in title["anyOf"]

    remove = schema["$defs"]["AuthoringRemoveIntent"]
    section_id = remove["properties"]["section_id"]
    assert {"type": "null"} not in section_id["anyOf"]
    assert "default" not in section_id

    validator = Draft202012Validator(schema)
    assert list(validator.iter_errors({"title": None}))
    assert not list(validator.iter_errors({}))
    assert not list(validator.iter_errors({"title": {"operation": "clear"}}))
