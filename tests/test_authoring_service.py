"""Tests for deterministic canonical authoring operations."""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from wellplot.authoring_service import (
    AuthoringService,
    AuthoringStylePatch,
    AuthoringTarget,
    CreateAnnotationRequest,
    CreateCurveBindingRequest,
    CreateFillRequest,
    CreateRasterBindingRequest,
    CreateRemarkRequest,
    CreateTrackRequest,
    MoveRequest,
    RemoveRequest,
    SectionPatch,
    UpdateCurveBindingRequest,
    UpdateSectionRequest,
)
from wellplot.model.authoring import (
    AnnotationTextSpec,
    AnnotationTrackSpec,
    ArrayTrackSpec,
    AuthoringDocumentSpec,
    AuthoringRemarkSpec,
    AuthoringScale,
    AuthoringScaleKind,
    CurveBindingSpec,
    CurveFillSpec,
    NormalTrackSpec,
    RasterBindingSpec,
)


def _service() -> AuthoringService:
    """Build one typed document used by the operation tests."""
    return AuthoringService(
        AuthoringDocumentSpec(
            name="service-test",
            sections=[
                {
                    "id": "main",
                    "title": "Main",
                    "tracks": [
                        NormalTrackSpec(
                            id="curves",
                            title="Curves",
                            width_mm=30,
                            bindings=[
                                CurveBindingSpec(binding_id="gr", channel="GR"),
                                CurveBindingSpec(binding_id="gr_overlay", channel="GR"),
                            ],
                        ),
                        ArrayTrackSpec(id="vdl", title="VDL", width_mm=40),
                        AnnotationTrackSpec(id="notes", title="Notes", width_mm=20),
                    ],
                }
            ],
            remarks=[AuthoringRemarkSpec(lines=["Initial remark"])],
        )
    )


def test_list_and_get_return_scoped_defensive_objects() -> None:
    """List and get expose stable identities without leaking mutable state."""
    service = _service()

    tracks = service.list("track", section_id="main")
    bindings = service.list("curve_binding", section_id="main", track_id="curves")
    remark = service.list("remark")[0]

    assert [item.object_id for item in tracks] == ["curves", "vdl", "notes"]
    assert [item.object_id for item in bindings] == ["gr", "gr_overlay"]
    assert remark.object_id == "remark-1"

    returned = service.get(
        AuthoringTarget(object_kind="track", object_id="curves", section_id="main")
    )
    returned.title = "Changed outside service"
    assert (
        service.get(
            AuthoringTarget(object_kind="track", object_id="curves", section_id="main")
        ).title
        == "Curves"
    )


def test_create_operations_cover_typed_content_families() -> None:
    """Create operations enforce parent/child compatibility and stable IDs."""
    service = _service()

    service.create(
        CreateTrackRequest(
            section_id="main",
            track={"id": "depth", "title": "Depth", "kind": "reference", "width_mm": 16},
        )
    )
    service.create(
        CreateCurveBindingRequest(
            section_id="main",
            track_id="curves",
            binding=CurveBindingSpec(binding_id="sp", channel="SP"),
        )
    )
    service.create(
        CreateRasterBindingRequest(
            section_id="main",
            track_id="vdl",
            binding=RasterBindingSpec(binding_id="vdl_main", channel="VDL"),
        )
    )
    service.create(
        CreateAnnotationRequest(
            section_id="main",
            track_id="notes",
            annotation=AnnotationTextSpec(annotation_id="note-1", depth=100, text="Check interval"),
        )
    )
    service.create(
        CreateFillRequest(
            section_id="main",
            track_id="curves",
            fill=CurveFillSpec(
                kind="between_instances",
                binding_id="gr",
                other_binding_id="gr_overlay",
            ),
        )
    )
    service.create(CreateRemarkRequest(remark=AuthoringRemarkSpec(lines=["Added remark"])))

    assert [item.object_id for item in service.list("raster_binding")] == ["vdl_main"]
    assert [item.object_id for item in service.list("annotation")] == ["note-1"]
    assert [item.object_id for item in service.list("fill")] == ["curves.fill.1"]
    assert [item.object_id for item in service.list("remark")] == ["remark-1", "remark-2"]


def test_typed_updates_apply_partial_style_and_section_patches() -> None:
    """Updates use explicit patch fields and preserve omitted values."""
    service = _service()
    original_scale = service.get(
        AuthoringTarget(
            object_kind="curve_binding", object_id="gr", section_id="main", track_id="curves"
        )
    ).scale

    service.update(
        UpdateCurveBindingRequest(
            section_id="main",
            track_id="curves",
            binding_id="gr",
            patch={
                "style": AuthoringStylePatch(color="red", line_width=1.2),
                "scale": AuthoringScale(kind=AuthoringScaleKind.LINEAR, minimum=0, maximum=200),
            },
        )
    )
    service.update(
        UpdateSectionRequest(
            section_id="main",
            patch=SectionPatch(title="Updated Main", depth_range=(100, 500)),
        )
    )

    binding = service.get(
        AuthoringTarget(
            object_kind="curve_binding", object_id="gr", section_id="main", track_id="curves"
        )
    )
    assert binding.style.color == "red"
    assert binding.style.line_width == 1.2
    assert binding.scale != original_scale
    assert (
        service.get(AuthoringTarget(object_kind="section", object_id="main")).title
        == "Updated Main"
    )


def test_failed_update_is_atomic() -> None:
    """A cross-field validation failure leaves the published snapshot unchanged."""
    service = _service()
    before = copy.deepcopy(service.document)

    with pytest.raises(ValidationError):
        service.update(
            UpdateSectionRequest(
                section_id="main",
                patch=SectionPatch(depth_range=(500, 100)),
            )
        )

    assert service.document == before
    assert service.validate().valid is True


def test_remove_and_move_are_parent_scoped() -> None:
    """Removal and ordering operations target stable object identities."""
    service = _service()

    service.move(
        MoveRequest(object_kind="track", object_id="notes", section_id="main", new_index=0)
    )
    assert [item.object_id for item in service.list("track", section_id="main")] == [
        "notes",
        "curves",
        "vdl",
    ]
    removed = service.remove(
        RemoveRequest(
            target=AuthoringTarget(
                object_kind="curve_binding",
                object_id="gr_overlay",
                section_id="main",
                track_id="curves",
            )
        )
    )

    assert removed.binding_id == "gr_overlay"
    assert [item.object_id for item in service.list("curve_binding")] == ["gr"]

    removed_track = service.remove(
        RemoveRequest(
            target=AuthoringTarget(object_kind="track", object_id="vdl", section_id="main")
        )
    )
    assert removed_track.id == "vdl"
    assert [item.object_id for item in service.list("track", section_id="main")] == [
        "notes",
        "curves",
    ]
