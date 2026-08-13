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
    DepthPatch,
    MoveRequest,
    PagePatch,
    RemoveRequest,
    SectionPatch,
    UpdateCurveBindingRequest,
    UpdateDepthRequest,
    UpdateHeaderRequest,
    UpdateHeaderSlotRequest,
    UpdateOutputRequest,
    UpdatePageRequest,
    UpdateSectionRequest,
    UpdateServiceTitleRequest,
    UpdateTailRequest,
    UpdateTrackRequest,
    authoring_hierarchy_catalog,
)
from wellplot.model.authoring import (
    AnnotationTextSpec,
    AnnotationTrackSpec,
    ArrayTrackSpec,
    AuthoringDocumentSpec,
    AuthoringHeaderFieldSpec,
    AuthoringHeaderSpec,
    AuthoringOutputSpec,
    AuthoringRemarkSpec,
    AuthoringReportValueSpec,
    AuthoringScale,
    AuthoringScaleKind,
    AuthoringServiceTitleSpec,
    CurveBindingSpec,
    CurveFillSpec,
    NormalTrackSpec,
    RasterBindingSpec,
    ReferenceTrackSpec,
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


def test_hierarchy_catalog_is_generated_from_canonical_contracts() -> None:
    """Expose parent/child operations and isolated schemas for each object kind."""
    catalog = authoring_hierarchy_catalog()
    nodes = {node["object_kind"]: node for node in catalog["nodes"]}

    assert catalog["root_object_kind"] == "report"
    assert nodes["report"]["children"] == [
        "output",
        "page",
        "depth",
        "header",
        "tail",
        "remark",
        "section",
    ]
    assert nodes["section"]["parent"] == {
        "object_kind": "report",
        "fields": [],
    }
    assert nodes["track"]["parent"] == {
        "object_kind": "section",
        "fields": ["section_id"],
    }
    assert nodes["track"]["constraints"]["form_kind_immutable"] is True
    assert nodes["track"]["constraints"]["child_compatibility"]["array"] == [
        "curve_binding",
        "raster_binding",
    ]
    assert {"id", "kind", "title", "width_mm"}.issubset(nodes["track"]["fields"])
    assert "create" in nodes["track"]["operations"]
    assert "update" in nodes["track"]["operation_schemas"]
    assert "width_mm" in nodes["track"]["mutable_on_update"]
    assert nodes["track"]["verification"] == {
        "operation": "get",
        "object_kind": "track",
    }

    header = authoring_hierarchy_catalog("header")["nodes"][0]
    assert "sections" not in header["canonical_schema"]["properties"]
    assert header["children"] == ["header_slot", "service_title"]
    assert header["fields"]["provider_name"]["category"] == "constrained"


def test_header_slot_and_service_title_updates_preserve_siblings() -> None:
    """Patch one header object without replacing other header objects."""
    service = _service()
    service.update(
        UpdateHeaderRequest(
            header=AuthoringHeaderSpec(
                provider_name="Company",
                general_fields=[
                    AuthoringHeaderFieldSpec(
                        slot_id="company",
                        key="company",
                        label="Company",
                        value=AuthoringReportValueSpec(value="Old Company"),
                    ),
                    AuthoringHeaderFieldSpec(
                        slot_id="well",
                        key="well",
                        label="Well",
                        value=AuthoringReportValueSpec(value="Well-1"),
                    ),
                ],
                service_titles=[
                    AuthoringServiceTitleSpec(
                        slot_id="service-1",
                        value=AuthoringReportValueSpec(value="CBL"),
                        bold=True,
                    ),
                    AuthoringServiceTitleSpec(
                        slot_id="service-2",
                        value=AuthoringReportValueSpec(value="VDL"),
                    ),
                ],
            )
        )
    )

    updated_slot = service.update(
        UpdateHeaderSlotRequest(
            slot_id="company",
            patch={"value": "New Company", "provenance": "user"},
        )
    )
    assert updated_slot.value == "New Company"
    assert updated_slot.provenance == "user"
    assert (
        service.get(AuthoringTarget(object_kind="header_slot", object_id="well")).value == "Well-1"
    )

    updated_title = service.update(
        UpdateServiceTitleRequest(
            slot_id="service-1",
            patch={"value": "CBL Amplitude", "italic": True},
        )
    )
    assert updated_title.value.value == "CBL Amplitude"
    assert updated_title.bold is True
    assert updated_title.italic is True
    assert (
        service.get(AuthoringTarget(object_kind="service_title", object_id="service-2")).value.value
        == "VDL"
    )


def test_hierarchy_catalog_rejects_unknown_object_kind() -> None:
    """Keep focused hierarchy discovery limited to canonical object kinds."""
    with pytest.raises(ValueError, match="Unsupported authoring object kind"):
        authoring_hierarchy_catalog("not-an-authoring-object")


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


def test_reference_track_updates_merge_presentation_fields() -> None:
    """Reference-track patches update typed axis presentation without replacing the track."""
    service = _service()
    service.create(
        CreateTrackRequest(
            section_id="main",
            track=ReferenceTrackSpec(id="depth", title="Depth", width_mm=12),
        )
    )

    updated = service.update(
        UpdateTrackRequest(
            section_id="main",
            track_id="depth",
            patch={
                "reference": {
                    "scale_ratio": 500,
                    "major_step": 50,
                    "minor_step": 10,
                    "secondary_grid_display": False,
                    "display_unit_in_header": False,
                    "number_format": "fixed",
                    "precision": 1,
                    "events": [{"depth": 1002.0, "label": "Casing Foot"}],
                }
            },
        )
    )

    assert updated.scale_ratio == 500
    assert updated.major_step == 50
    assert updated.minor_step == 10
    assert updated.secondary_grid_display is False
    assert updated.display_unit_in_header is False
    assert updated.number_format.value == "fixed"
    assert updated.precision == 1
    assert updated.events[0].label == "Casing Foot"


def test_document_settings_are_typed_and_parent_scoped() -> None:
    """Page and depth settings use the same atomic service update contract."""
    service = _service()

    assert [item.object_id for item in service.list("page")] == ["page"]
    assert [item.object_id for item in service.list("depth")] == ["depth"]

    service.update(
        UpdatePageRequest(patch=PagePatch(size="a4", orientation="landscape", continuous=True))
    )
    service.update(
        UpdateDepthRequest(patch=DepthPatch(unit="ft", scale="1:240", major_step=10, minor_step=2))
    )

    page = service.get(AuthoringTarget(object_kind="page", object_id="page"))
    depth = service.get(AuthoringTarget(object_kind="depth", object_id="depth"))
    assert page.orientation == "landscape"
    assert page.continuous is True
    assert depth.unit == "ft"
    assert depth.major_step == 10


def test_report_header_tail_and_output_are_first_class_service_objects() -> None:
    """Expose stable document-level report objects through typed service operations."""
    service = _service()

    assert [item.object_id for item in service.list("output")] == ["output"]
    assert [item.object_id for item in service.list("header")] == ["header"]
    assert [item.object_id for item in service.list("tail")] == ["tail"]

    service.update(
        UpdateOutputRequest(
            output=AuthoringOutputSpec(output_path="packet.pdf", dpi=300),
        )
    )
    service.update(
        UpdateHeaderRequest(
            header=AuthoringHeaderSpec(
                provider_name="Company",
                general_fields=[
                    AuthoringHeaderFieldSpec(
                        slot_id="general.well",
                        key="well",
                        label="Well",
                        value={"value": "Demo-1", "provenance": "user"},
                    )
                ],
            )
        )
    )
    service.update(UpdateTailRequest(tail={"enabled": True}))

    output = service.get(AuthoringTarget(object_kind="output", object_id="output"))
    header = service.get(AuthoringTarget(object_kind="header", object_id="header"))
    tail = service.get(AuthoringTarget(object_kind="tail", object_id="tail"))
    assert output.output_path == "packet.pdf"
    assert header.general_fields[0].value.value == "Demo-1"
    assert tail.enabled is True


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
