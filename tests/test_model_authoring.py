"""Tests for the canonical typed authoring contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from wellplot.model import (
    AuthoringCurveCalloutSpec,
    AuthoringCurveFillBaselineSpec,
    AuthoringCurveFillCrossoverSpec,
    AuthoringCurveFillKind,
    AuthoringCurveHeaderDisplaySpec,
    AuthoringCurveValueLabelsSpec,
    AuthoringDocumentSpec,
    AuthoringGridScaleKind,
    AuthoringGridSpacingMode,
    AuthoringGridSpec,
    AuthoringRasterProfileKind,
    AuthoringRasterSampleAxisSpec,
    AuthoringRasterWaveformSpec,
    AuthoringReferenceEventSpec,
    AuthoringReferenceOverlayMode,
    AuthoringReferenceOverlaySpec,
    AuthoringScale,
    AuthoringScaleKind,
    AuthoringStyle,
    AuthoringTrackHeaderObjectKind,
    AuthoringTrackHeaderObjectSpec,
    AuthoringTrackHeaderSpec,
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


def test_curve_display_relations_are_typed() -> None:
    """Callouts and fill presentation settings are first-class curve data."""
    callout = AuthoringCurveCalloutSpec(
        depth=1005,
        label="GR Sand",
        placement="bottom",
        distance_from_top=1.0,
    )
    fill = CurveFillSpec(
        kind=AuthoringCurveFillKind.BASELINE_SPLIT,
        binding_id="gr",
        baseline=AuthoringCurveFillBaselineSpec(
            value=70,
            lower_color="#22c55e",
            line_style=":",
        ),
        crossover=AuthoringCurveFillCrossoverSpec(enabled=False),
    )
    binding = CurveBindingSpec(binding_id="gr", channel="GR", callouts=[callout])

    assert binding.callouts[0].placement == "bottom"
    assert fill.baseline is not None
    assert fill.baseline.lower_color == "#22c55e"


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


def test_raster_display_contract_validates_nested_controls() -> None:
    """Raster presentation settings are typed rather than arbitrary mappings."""
    raster = RasterBindingSpec(
        binding_id="vdl_display",
        channel="VDL",
        profile=AuthoringRasterProfileKind.VDL,
        clip_percentiles=(1, 99),
        color_limits=(-1, 1),
        sample_axis=AuthoringRasterSampleAxisSpec(
            enabled=True,
            unit="us",
            minimum=200,
            maximum=1200,
            tick_count=7,
        ),
        waveform=AuthoringRasterWaveformSpec(enabled=True, stride=5),
    )

    assert raster.sample_axis.maximum == 1200
    assert raster.waveform.stride == 5

    with pytest.raises(ValidationError, match="source_step must be non-zero"):
        AuthoringRasterSampleAxisSpec(source_origin=40, source_step=0)


def test_raster_color_limits_match_profile_normalization() -> None:
    """Reject ranges that cannot be consumed by the selected raster profile."""
    with pytest.raises(ValidationError, match="VDL color_limits must straddle zero"):
        RasterBindingSpec(
            binding_id="vdl_invalid_limits",
            channel="VDL",
            profile=AuthoringRasterProfileKind.VDL,
            color_limits=(0, 1),
        )

    with pytest.raises(ValidationError, match="strictly increasing"):
        RasterBindingSpec(
            binding_id="raster_invalid_limits",
            channel="IMAGE",
            color_limits=(1, 1),
        )


def test_grid_contract_validates_logarithmic_spacing_and_alpha() -> None:
    """Expose deterministic grid properties with the same validation rules as scales."""
    grid = AuthoringGridSpec(
        vertical_main_scale=AuthoringGridScaleKind.LOGARITHMIC,
        vertical_main_spacing_mode=AuthoringGridSpacingMode.SCALE,
        vertical_main_line_count=5,
        vertical_main_alpha=0.4,
    )

    assert grid.vertical_main_scale == AuthoringGridScaleKind.LOGARITHMIC
    assert grid.vertical_main_spacing_mode == AuthoringGridSpacingMode.SCALE
    assert grid.vertical_main_line_count == 5

    with pytest.raises(ValidationError, match="less than or equal to 1"):
        AuthoringGridSpec(vertical_main_alpha=1.1)


def test_track_header_contract_rejects_duplicate_rows() -> None:
    """Track-header row identity is explicit and cannot be duplicated."""
    row = AuthoringTrackHeaderObjectSpec(kind=AuthoringTrackHeaderObjectKind.TITLE)

    with pytest.raises(ValidationError, match="unique"):
        AuthoringTrackHeaderSpec(objects=[row, row.model_copy()])


def test_reference_overlay_contract_requires_ordered_lane_bounds() -> None:
    """Reference overlays must define a valid normalized lane when bounded."""
    overlay = AuthoringReferenceOverlaySpec(
        mode=AuthoringReferenceOverlayMode.INDICATOR,
        lane_start=0.2,
        lane_end=0.8,
        threshold=1.5,
    )

    assert overlay.mode == AuthoringReferenceOverlayMode.INDICATOR

    with pytest.raises(ValidationError, match="less than"):
        AuthoringReferenceOverlaySpec(lane_start=0.8, lane_end=0.2)


def test_reference_event_contract_validates_typed_presentation() -> None:
    """Reference event geometry and formatting are part of the canonical contract."""
    event = AuthoringReferenceEventSpec(
        depth=1002.0,
        label="Casing Foot",
        color="#8b5a2b",
        line_style="--",
        line_width=0.9,
        text_side="left",
        text_x=0.72,
        arrow=False,
    )

    assert event.label == "Casing Foot"
    assert event.line_style == "--"
    assert event.text_side == "left"

    with pytest.raises(ValidationError, match="set together"):
        AuthoringReferenceEventSpec(depth=1002.0, lane_start=0.2)


def test_curve_display_contract_validates_value_labels() -> None:
    """Curve display controls are typed independently from the curve style."""
    labels = AuthoringCurveValueLabelsSpec(step=10, format="fixed", precision=1)
    header = AuthoringCurveHeaderDisplaySpec(show_color=False)

    assert labels.step == 10
    assert labels.precision == 1
    assert header.show_color is False


def test_unknown_standard_fields_are_rejected() -> None:
    """Strict models prevent accidental contract drift through extra keys."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        CurveBindingSpec(binding_id="gr", channel="GR", colour="green")


def test_logarithmic_scale_requires_positive_minimum() -> None:
    """Logarithmic scales reject non-positive lower bounds."""
    with pytest.raises(ValidationError, match="positive minimum"):
        AuthoringScale(kind=AuthoringScaleKind.LOG, minimum=0, maximum=200)
