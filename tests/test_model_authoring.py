"""Tests for the canonical typed authoring contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from wellplot.model import (
    AuthoringCurveFillKind,
    AuthoringDocumentSpec,
    AuthoringRasterProfileKind,
    AuthoringScale,
    AuthoringScaleKind,
    AuthoringStyle,
    authoring_json_schema,
)
from wellplot.model.authoring import (
    ArrayTrackSpec,
    CurveBindingSpec,
    CurveFillSpec,
    NormalTrackSpec,
    RasterBindingSpec,
)


def _document_with_duplicate_channel_bindings() -> AuthoringDocumentSpec:
    """Build a valid document with two instances of the same channel."""
    first = CurveBindingSpec(
        binding_id="gr_primary",
        channel="GR",
        label="Gamma Ray",
        scale=AuthoringScale(minimum=0, maximum=200, unit="gAPI"),
        style=AuthoringStyle(color="black", line_width=0.75),
    )
    second = CurveBindingSpec(
        binding_id="gr_overlay",
        channel="GR",
        label="Gamma Ray overlay",
        scale=AuthoringScale(minimum=0, maximum=100, unit="gAPI"),
        style=AuthoringStyle(color="blue", line_style="--", line_width=0.65),
    )
    track = NormalTrackSpec(
        id="gr",
        title="Gamma Ray",
        width_mm=25,
        bindings=[first, second],
        fills=[
            CurveFillSpec(
                kind=AuthoringCurveFillKind.BETWEEN_INSTANCES,
                binding_id="gr_primary",
                other_binding_id="gr_overlay",
            )
        ],
    )
    return AuthoringDocumentSpec(
        name="duplicate-channel-test",
        sections=[
            {
                "id": "main",
                "title": "Main Pass",
                "tracks": [track],
            }
        ],
    )


def test_generated_schema_is_closed_at_the_document_boundary() -> None:
    """The canonical document rejects unknown root properties."""
    schema = authoring_json_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "sections" in schema["properties"]
    track_schema = schema["$defs"]["AuthoringSectionSpec"]["properties"]["tracks"]["items"]
    assert "oneOf" in track_schema
    assert track_schema["discriminator"]["propertyName"] == "kind"


def test_same_channel_can_have_distinct_binding_instances() -> None:
    """Binding identity is independent from the source channel mnemonic."""
    document = _document_with_duplicate_channel_bindings()
    bindings = document.sections[0].tracks[0].bindings

    assert [binding.channel for binding in bindings] == ["GR", "GR"]
    assert [binding.binding_id for binding in bindings] == [
        "gr_primary",
        "gr_overlay",
    ]
    restored = AuthoringDocumentSpec.model_validate(document.model_dump(mode="json"))
    assert restored == document


def test_duplicate_binding_id_is_rejected() -> None:
    """Two curve instances cannot share one stable identity."""
    binding = CurveBindingSpec(binding_id="same", channel="GR")

    with pytest.raises(ValidationError, match="duplicate binding ids"):
        NormalTrackSpec(
            id="gr",
            title="Gamma Ray",
            width_mm=25,
            bindings=[binding, binding.model_copy()],
        )


def test_fill_must_reference_bindings_on_its_track() -> None:
    """A fill cannot silently reference a missing curve instance."""
    with pytest.raises(ValidationError, match="missing binding ids"):
        NormalTrackSpec(
            id="gr",
            title="Gamma Ray",
            width_mm=25,
            bindings=[CurveBindingSpec(binding_id="gr", channel="GR")],
            fills=[
                CurveFillSpec(
                    kind=AuthoringCurveFillKind.BETWEEN_INSTANCES,
                    binding_id="gr",
                    other_binding_id="missing",
                )
            ],
        )


def test_array_track_accepts_raster_binding() -> None:
    """Array tracks accept raster content through the binding discriminator."""
    track = ArrayTrackSpec(
        id="vdl",
        title="VDL",
        width_mm=40,
        bindings=[
            RasterBindingSpec(
                binding_id="vdl_main",
                channel="VDL",
                profile=AuthoringRasterProfileKind.VDL,
            )
        ],
    )

    assert track.bindings[0].kind == "raster"
    assert track.bindings[0].profile == AuthoringRasterProfileKind.VDL


def test_unknown_standard_fields_are_rejected() -> None:
    """Strict models prevent accidental contract drift through extra keys."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        CurveBindingSpec(binding_id="gr", channel="GR", colour="green")


def test_logarithmic_scale_requires_positive_minimum() -> None:
    """Logarithmic scales reject non-positive lower bounds."""
    with pytest.raises(ValidationError, match="positive minimum"):
        AuthoringScale(kind=AuthoringScaleKind.LOG, minimum=0, maximum=200)
