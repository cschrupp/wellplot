"""CM-23 tests for curve and raster binding capabilities."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from wellplot.authoring_program.builders import HandleBuilder
from wellplot.authoring_program.intent_builder import IntentBuilder
from wellplot.capabilities import create_builtin_registry
from wellplot.capabilities.bindings import (
    CurveBindingArgs,
    CurveScaleArgs,
    RasterBindingArgs,
    compile_binding_curve,
    compile_binding_raster,
)
from wellplot.model.authoring import AuthoringRasterColorbarSpec, AuthoringRasterSampleAxisSpec


def test_sdk_constructs_cbl_vdl_bindings_with_independent_content_settings() -> None:
    """A single SDK sequence constructs the supported CBL/VDL binding content."""
    builder = IntentBuilder(handles=HandleBuilder(builder_id="cm23"))
    report = builder.report(title="CBL Quicklook")
    section = builder.add_section(report, id_hint="main", title="Main Pass")
    combo = builder.add_track(
        section,
        id_hint="combo",
        kind="normal",
        title="Combo",
        width_mm=32,
    )
    vdl_track = builder.add_track(
        section,
        id_hint="vdl",
        kind="array",
        title="VDL",
        width_mm=40,
    )

    cbl = builder.add_curve(
        combo,
        channel="CBL",
        label="Amplitude (CBL)",
        scale_minimum=0,
        scale_maximum=100,
        color="#2142ff",
        line_style="dashed",
        line_width=0.7,
    )
    builder.add_raster(
        vdl_track,
        channel="VDL",
        label="Variable Density Log",
        profile="vdl",
        normalization="none",
        color_minimum=-100,
        color_maximum=100,
        colormap="seismic",
        colorbar=AuthoringRasterColorbarSpec(enabled=True, label="Amplitude"),
        sample_axis=AuthoringRasterSampleAxisSpec(
            enabled=True,
            label="Time",
            unit="us",
            source_origin=0,
            source_step=2,
        ),
    )

    intent = builder.intent()
    tracks = intent.sections[0].tracks
    assert tracks is not None
    combo_binding = tracks[0].bindings[0]
    raster_binding = tracks[1].bindings[0]
    assert combo_binding.binding_id == cbl.binding_id
    assert combo_binding.scale.minimum == 0
    assert combo_binding.style.line_style == "dashed"
    assert raster_binding.profile == "vdl"
    assert raster_binding.color_limits == (-100, 100)
    assert raster_binding.colorbar.label == "Amplitude"
    assert raster_binding.sample_axis.source_step == 2


def test_binding_handlers_compile_create_select_and_update_without_lookup() -> None:
    """Binding handlers use exact host identities and emit canonical fragments."""
    curve = compile_binding_curve(
        CurveBindingArgs(
            operation="create",
            section_id="main",
            track_id="combo",
            channel="GR",
            label="Gamma Ray",
            scale=CurveScaleArgs(minimum=0, maximum=150, unit="gAPI"),
        )
    )
    selected = compile_binding_curve(
        CurveBindingArgs(
            operation="select",
            section_id="main",
            track_id="combo",
            binding_id="main.combo.GR",
        )
    )
    updated = compile_binding_raster(
        RasterBindingArgs(
            operation="update",
            section_id="main",
            track_id="vdl",
            binding_id="main.vdl.VDL",
            profile="vdl",
            color_minimum=-100,
            color_maximum=100,
        )
    )

    assert curve.sections[0].tracks[0].bindings[0].channel == "GR"
    assert selected.sections[0].tracks[0].bindings[0].binding_id == "main.combo.GR"
    assert updated.sections[0].tracks[0].bindings[0].profile == "vdl"
    assert updated.sections[0].tracks[0].bindings[0].color_limits == (-100, 100)


def test_binding_contracts_reject_ambiguous_operations_and_invalid_scales() -> None:
    """Strict operation contracts prevent inferred identity or scale behavior."""
    with pytest.raises(ValidationError, match="requires channel"):
        CurveBindingArgs(operation="create", section_id="main", track_id="combo")
    with pytest.raises(ValidationError, match="requires binding_id"):
        RasterBindingArgs(operation="update", section_id="main", track_id="vdl")
    with pytest.raises(ValidationError, match="both minimum and maximum"):
        RasterBindingArgs(
            operation="create",
            section_id="main",
            track_id="vdl",
            channel="VDL",
            color_minimum=-100,
        )
    with pytest.raises(ValidationError, match="positive bounds"):
        CurveScaleArgs(minimum=0, maximum=100, kind="log")


def test_binding_capabilities_expose_v2_contracts_and_source_parent_constraints() -> None:
    """Registry metadata remains the declarative source/parent boundary."""
    registry = create_builtin_registry()
    curve = registry.get("binding.curve")
    raster = registry.get("binding.raster")

    assert curve.supports_v2 is True
    assert curve.allowed_parents == ("track.normal", "track.reference")
    assert curve.source_kinds == ("LAS", "DLIS")
    assert raster.supports_v2 is True
    assert raster.allowed_parents == ("track.array",)
    assert raster.source_kinds == ("DLIS",)

    descriptors = [
        json.dumps(spec.code_mode_worker_descriptor(), sort_keys=True) for spec in (curve, raster)
    ]
    assert descriptors == [json.dumps(json.loads(item), sort_keys=True) for item in descriptors]
