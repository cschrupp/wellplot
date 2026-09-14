"""CM-22 tests for structural section and track capabilities."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from wellplot.authoring_program.builders import HandleBuilder
from wellplot.authoring_program.errors import (
    ProgramNameError,
    ProgramPolicyError,
)
from wellplot.authoring_program.intent_builder import IntentBuilder
from wellplot.capabilities import create_builtin_registry
from wellplot.capabilities.structural import (
    SectionLogPlotArgs,
    TrackAnnotationArgs,
    TrackArrayArgs,
    TrackNormalArgs,
    TrackReferenceArgs,
    TrackScaleArgs,
    compile_section_log_plot,
    compile_track_annotation,
    compile_track_array,
    compile_track_normal,
    compile_track_reference,
)


def test_structural_builder_creates_empty_section_with_all_fixed_track_kinds() -> None:
    """One deterministic builder program creates the CM-22 structural proof."""
    builder = IntentBuilder(handles=HandleBuilder(builder_id="cm22"))
    report = builder.report(title="Structural proof")
    section = builder.add_section(report, id_hint="Main Pass", title="Main Pass")

    builder.add_track(section, id_hint="depth", kind="reference", title="Depth", width_mm=12)
    builder.add_track(section, id_hint="gr", kind="normal", title="GR", width_mm=30)
    builder.add_track(section, id_hint="vdl", kind="array", title="VDL", width_mm=40)
    builder.add_track(section, id_hint="notes", kind="annotation", title="Notes", width_mm=20)

    intent = builder.intent()
    tracks = intent.sections[0].tracks
    assert [(track.track_id, track.kind) for track in tracks] == [
        ("depth", "reference"),
        ("gr", "normal"),
        ("vdl", "array"),
        ("notes", "annotation"),
    ]
    assert all(track.bindings is None for track in tracks)
    assert all(track.fills is None for track in tracks)
    assert all(track.annotations is None for track in tracks)


def test_selection_is_exact_adoption_and_sparse_track_update_preserves_omissions() -> None:
    """A width-only update preserves identity, parent, and all omitted fields."""
    builder = IntentBuilder(handles=HandleBuilder(builder_id="cm22-update"))
    report = builder.report()
    section = builder.select_section(report, section_id="main")
    track = builder.select_track(section, track_id="combo")
    builder.update_track(track, width_mm=35)

    intent = builder.intent()
    updated = intent.sections[0].tracks[0]
    assert updated.track_id == "combo"
    assert updated.section_id == "main"
    assert updated.width_mm == 35
    assert updated.title is None
    assert updated.kind is None
    assert updated.x_scale is None
    assert intent.model_dump(mode="json", exclude_none=True) == {
        "sections": [
            {
                "section_id": "main",
                "tracks": [{"track_id": "combo", "section_id": "main", "width_mm": 35}],
            }
        ],
        "removals": [],
    }


def test_section_selection_and_update_are_sparse_and_identity_stable() -> None:
    """Section updates cannot rename or recreate an adopted section."""
    builder = IntentBuilder(handles=HandleBuilder(builder_id="cm22-section"))
    report = builder.report()
    section = builder.select_section(report, section_id="main_pass")
    builder.update_section(section, subtitle="Updated subtitle")

    selected = builder.intent().sections[0]
    assert selected.section_id == "main_pass"
    assert selected.subtitle == "Updated subtitle"
    assert selected.title is None

    with pytest.raises(ProgramPolicyError, match="mutable field"):
        builder.update_section(section)


def test_track_kind_is_fixed_by_each_capability_handler() -> None:
    """Each v2 track capability emits exactly its declared canonical kind."""
    cases = (
        (TrackNormalArgs, compile_track_normal, "normal"),
        (TrackReferenceArgs, compile_track_reference, "reference"),
        (TrackArrayArgs, compile_track_array, "array"),
        (TrackAnnotationArgs, compile_track_annotation, "annotation"),
    )
    for model_type, handler, kind in cases:
        result = handler(
            model_type(
                operation="create",
                section_id="main",
                id_hint="track",
                title="Track",
                width_mm=20,
            )
        )
        assert result.sections[0].tracks[0].kind == kind


def test_structural_handlers_support_create_select_and_sparse_update() -> None:
    """Static handlers compile each explicit operation without document lookup."""
    created = compile_section_log_plot(
        SectionLogPlotArgs(operation="create", id_hint="main", title="Main Pass")
    )
    selected = compile_section_log_plot(SectionLogPlotArgs(operation="select", section_id="main"))
    updated = compile_track_normal(
        TrackNormalArgs(
            operation="update",
            section_id="main",
            track_id="combo",
            width_mm=35,
        )
    )

    assert created.sections[0].section_id == "main"
    assert selected.sections[0].section_id == "main"
    assert selected.sections[0].title is None
    assert updated.sections[0].tracks[0].width_mm == 35
    assert updated.sections[0].tracks[0].title is None


def test_structural_arguments_reject_ambiguous_create_update_combinations() -> None:
    """Operation-specific identity rules prevent inferred mutation behavior."""
    with pytest.raises(ValidationError, match="does not accept section_id"):
        SectionLogPlotArgs(operation="create", section_id="main", title="Main")
    with pytest.raises(ValidationError, match="requires section_id"):
        SectionLogPlotArgs(operation="update", subtitle="Updated")
    with pytest.raises(ValidationError, match="requires title and width_mm"):
        TrackNormalArgs(operation="create", section_id="main", id_hint="combo")
    with pytest.raises(ValidationError, match="accepts only section_id and track_id"):
        TrackNormalArgs(
            operation="select",
            section_id="main",
            track_id="combo",
            width_mm=35,
        )
    with pytest.raises(ValidationError, match="requires a mutable field"):
        TrackNormalArgs(operation="update", section_id="main", track_id="combo")


def test_parent_and_foreign_handle_validation_remain_strict() -> None:
    """Selection and updates cannot cross builder or section ownership."""
    first = IntentBuilder(handles=HandleBuilder(builder_id="first"))
    first_report = first.report()
    first_section = first.add_section(first_report, id_hint="main", title="Main")
    first_track = first.add_track(
        first_section,
        id_hint="combo",
        kind="normal",
        title="Combo",
        width_mm=30,
    )
    first_repeat = first.add_section(first_report, id_hint="repeat", title="Repeat")
    second = IntentBuilder(handles=HandleBuilder(builder_id="second"))

    with pytest.raises(ProgramNameError, match="different identity builder"):
        second.update_track(first_track, width_mm=40)
    with pytest.raises(ProgramPolicyError, match="does not belong"):
        first.handles.validate_track_parent(first_repeat, first_track)


def test_ids_are_host_allocated_and_section_local() -> None:
    """Duplicate hints suffix deterministically and may repeat in another section."""
    builder = IntentBuilder(handles=HandleBuilder(builder_id="cm22-ids"))
    report = builder.report()
    main = builder.add_section(report, id_hint="main", title="Main")
    repeat = builder.add_section(report, id_hint="repeat", title="Repeat")
    first = builder.add_track(main, id_hint="combo", kind="normal", title="One", width_mm=20)
    second = builder.add_track(main, id_hint="combo", kind="normal", title="Two", width_mm=20)
    third = builder.add_track(repeat, id_hint="combo", kind="normal", title="Three", width_mm=20)

    assert [first.track_id, second.track_id, third.track_id] == [
        "combo",
        "combo.2",
        "combo",
    ]


def test_all_structural_capabilities_are_dual_mode_with_stable_descriptors() -> None:
    """The five migrated declarations keep v1 and expose deterministic v2 metadata."""
    registry = create_builtin_registry()
    capability_ids = (
        "section.log_plot",
        "track.normal",
        "track.reference",
        "track.array",
        "track.annotation",
    )
    descriptors = []
    for capability_id in capability_ids:
        spec = registry.get(capability_id)
        assert spec.supports_v2 is True
        assert spec.compiler is not None
        descriptor = spec.code_mode_worker_descriptor()
        assert "handler" not in descriptor
        assert "compiler" not in descriptor
        descriptors.append(json.dumps(descriptor, sort_keys=True))
    assert descriptors == [json.dumps(json.loads(item), sort_keys=True) for item in descriptors]


def test_invalid_track_scale_is_rejected_before_the_handler() -> None:
    """Static scale validation remains canonical and deterministic."""
    with pytest.raises(ValidationError):
        TrackScaleArgs(minimum=0, maximum=10, kind="log")
