"""CM-24 tests for fill and typed-annotation capabilities."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from wellplot.authoring_program.builders import BindingHandle, HandleBuilder, TrackHandle
from wellplot.authoring_program.errors import ProgramNameError, ProgramPolicyError
from wellplot.authoring_program.intent_builder import IntentBuilder
from wellplot.capabilities import create_builtin_registry
from wellplot.capabilities.fills_annotations import (
    CurveFillArgs,
    TypedAnnotationArgs,
    compile_annotation_typed,
    compile_fill_curve,
)
from wellplot.model.authoring import (
    AnnotationArrowSpec,
    AnnotationGlyphSpec,
    AnnotationIntervalSpec,
    AnnotationMarkerSpec,
    AnnotationTextSpec,
    AuthoringCurveFillBaselineSpec,
    AuthoringCurveFillCrossoverSpec,
)


def _builder(builder_id: str = "cm24") -> IntentBuilder:
    """Create one isolated builder for CM-24 tests."""
    return IntentBuilder(handles=HandleBuilder(builder_id=builder_id))


def _normal_fixture(
    builder: IntentBuilder,
) -> tuple[TrackHandle, BindingHandle, BindingHandle]:
    """Create a normal track with two scalar binding handles."""
    report = builder.report(title="CM-24")
    section = builder.add_section(report, id_hint="main", title="Main")
    track = builder.add_track(section, id_hint="combo", kind="normal", title="Combo", width_mm=30)
    first = builder.add_curve(track, channel="GR")
    second = builder.add_curve(track, channel="SP")
    return track, first, second


def test_builder_supports_all_fill_kinds_and_nested_styles() -> None:
    """The SDK emits every canonical fill kind with valid nested configuration."""
    builder = _builder()
    track, first, second = _normal_fixture(builder)
    builder.add_fill(
        track,
        kind="between_curves",
        binding=first,
        other_binding=second,
        crossover=AuthoringCurveFillCrossoverSpec(
            enabled=True,
            left_color="#00aa00",
            right_color="#aa0000",
        ),
    )
    builder.add_fill(
        track,
        kind="between_instances",
        binding=first,
        other_binding=second,
    )
    builder.add_fill(track, kind="to_lower_limit", binding=first)
    builder.add_fill(track, kind="to_upper_limit", binding=second)
    builder.add_fill(
        track,
        kind="baseline_split",
        binding=first,
        baseline=AuthoringCurveFillBaselineSpec(value=50, lower_color="#0000aa"),
    )

    fills = builder.intent().sections[0].tracks[0].fills
    assert [fill.kind for fill in fills] == [
        "between_curves",
        "between_instances",
        "to_lower_limit",
        "to_upper_limit",
        "baseline_split",
    ]
    assert fills[0].crossover.enabled is True
    assert fills[4].baseline.value == 50


def test_builder_supports_all_typed_annotation_variants() -> None:
    """The annotation SDK covers interval, text, marker, arrow, and glyph."""
    builder = _builder("cm24-annotations")
    report = builder.report(title="CM-24")
    section = builder.add_section(report, id_hint="main", title="Main")
    track = builder.add_track(
        section,
        id_hint="notes",
        kind="annotation",
        title="Notes",
        width_mm=20,
    )
    annotations = (
        AnnotationIntervalSpec(annotation_id="requested", top=100, base=110, text="Zone"),
        AnnotationTextSpec(annotation_id="requested", depth=120, text="Text"),
        AnnotationMarkerSpec(annotation_id="requested", depth=130),
        AnnotationArrowSpec(
            annotation_id="requested",
            start_depth=140,
            end_depth=150,
            start_x=0.2,
            end_x=0.8,
        ),
        AnnotationGlyphSpec(annotation_id="requested", depth=160, glyph="*"),
    )
    for annotation in annotations:
        builder.add_typed_annotation(track, annotation=annotation)

    result = builder.intent().sections[0].tracks[0].annotations
    assert [annotation.annotation.kind for annotation in result] == [
        "interval",
        "text",
        "marker",
        "arrow",
        "glyph",
    ]
    assert len({annotation.annotation_id for annotation in result}) == 5


def test_fill_contract_rejects_invalid_nested_configuration() -> None:
    """Fill contracts enforce canonical kind-specific target rules."""
    base = {"section_id": "main", "track_id": "combo", "binding_id": "main.combo.GR"}
    with pytest.raises(ValidationError, match="complete baseline"):
        CurveFillArgs(kind="baseline_split", **base)
    with pytest.raises(ValidationError, match="between-curve fill"):
        CurveFillArgs(
            kind="to_lower_limit",
            crossover=AuthoringCurveFillCrossoverSpec(enabled=True),
            **base,
        )
    with pytest.raises(ValidationError, match="other_binding_id"):
        CurveFillArgs(kind="between_instances", **base)


def test_fill_and_annotation_handlers_preserve_identity_and_replace_payloads() -> None:
    """Handlers select exact IDs and replace complete nested annotation payloads."""
    created_fill = compile_fill_curve(
        CurveFillArgs(
            operation="create",
            section_id="main",
            track_id="combo",
            kind="between_instances",
            binding_id="main.combo.GR",
            other_binding_id="main.combo.SP",
        )
    )
    selected_fill = compile_fill_curve(
        CurveFillArgs(
            operation="select",
            section_id="main",
            track_id="combo",
            fill_id="main.combo.fill.1",
        )
    )
    updated_annotation = compile_annotation_typed(
        TypedAnnotationArgs(
            operation="update",
            section_id="main",
            track_id="notes",
            annotation_id="main.notes.annotation.1",
            annotation=AnnotationMarkerSpec(annotation_id="ignored", depth=250),
        )
    )

    assert created_fill.sections[0].tracks[0].fills[0].kind == "between_instances"
    assert selected_fill.sections[0].tracks[0].fills[0].fill_id == "main.combo.fill.1"
    annotation = updated_annotation.sections[0].tracks[0].annotations[0]
    assert annotation.annotation_id == "main.notes.annotation.1"
    assert annotation.annotation.kind == "marker"
    assert annotation.annotation.depth == 250


def test_fill_and_annotation_ownership_remains_strict() -> None:
    """Referenced leaves cannot cross tracks or identity builders."""
    builder = _builder("cm24-ownership")
    report = builder.report(title="CM-24")
    section = builder.add_section(report, id_hint="main", title="Main")
    first_track = builder.add_track(
        section, id_hint="first", kind="normal", title="First", width_mm=20
    )
    second_track = builder.add_track(
        section, id_hint="second", kind="normal", title="Second", width_mm=20
    )
    first_binding = builder.add_curve(first_track, channel="GR")
    first_fill = builder.add_fill(first_track, kind="to_lower_limit", binding=first_binding)
    with pytest.raises(ProgramPolicyError, match="does not belong"):
        builder.update_fill(second_track, first_fill, color="#ff0000")

    foreign = _builder("cm24-foreign")
    foreign_report = foreign.report(title="Foreign")
    foreign_section = foreign.add_section(foreign_report, id_hint="main", title="Main")
    foreign_track = foreign.add_track(
        foreign_section,
        id_hint="first",
        kind="normal",
        title="First",
        width_mm=20,
    )
    foreign_binding = foreign.add_curve(foreign_track, channel="GR")
    foreign_fill = foreign.add_fill(foreign_track, kind="to_lower_limit", binding=foreign_binding)
    with pytest.raises(ProgramNameError, match="different identity builder"):
        builder.update_fill(first_track, foreign_fill, color="#ff0000")

    annotation_track = builder.add_track(
        section, id_hint="notes", kind="annotation", title="Notes", width_mm=20
    )
    other_annotation_track = builder.add_track(
        section, id_hint="other-notes", kind="annotation", title="Other", width_mm=20
    )
    annotation = builder.add_typed_annotation(
        annotation_track,
        annotation=AnnotationTextSpec(annotation_id="requested", depth=10, text="Note"),
    )
    with pytest.raises(ProgramPolicyError, match="does not belong"):
        builder.update_typed_annotation(
            other_annotation_track,
            annotation,
            payload=AnnotationTextSpec(annotation_id="replacement", depth=20, text="Other"),
        )


def test_fill_and_annotation_capabilities_expose_static_v2_descriptors() -> None:
    """The migrated declarations keep v1 behavior and expose static v2 metadata."""
    registry = create_builtin_registry()
    fill = registry.get("fill.curve")
    annotation = registry.get("annotation.typed")
    assert fill.supports_v2 is True
    assert fill.allowed_parents == ("track.normal",)
    assert annotation.supports_v2 is True
    assert annotation.allowed_parents == ("track.annotation",)
    descriptors = [
        json.dumps(spec.code_mode_worker_descriptor(), sort_keys=True)
        for spec in (fill, annotation)
    ]
    assert descriptors == [json.dumps(json.loads(item), sort_keys=True) for item in descriptors]
