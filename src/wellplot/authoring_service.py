###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################

"""Deterministic object operations over the canonical authoring model."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .authoring import authoring_document_from_mapping, authoring_document_to_mapping
from .model.authoring import (
    AnnotationSpec,
    AnnotationTrackSpec,
    ArrayTrackSpec,
    AuthoringCurveCalloutSpec,
    AuthoringCurveHeaderDisplayPatch,
    AuthoringCurveHeaderDisplaySpec,
    AuthoringCurveValueLabelsPatch,
    AuthoringCurveValueLabelsSpec,
    AuthoringDataSource,
    AuthoringDepthSpec,
    AuthoringDocumentSpec,
    AuthoringGridPatch,
    AuthoringGridSpec,
    AuthoringHeaderSpec,
    AuthoringNumberFormatKind,
    AuthoringOutputSpec,
    AuthoringPageSpec,
    AuthoringRasterColorbarPatch,
    AuthoringRasterColorbarSpec,
    AuthoringRasterNormalizationKind,
    AuthoringRasterProfileKind,
    AuthoringRasterSampleAxisPatch,
    AuthoringRasterSampleAxisSpec,
    AuthoringRasterWaveformPatch,
    AuthoringRasterWaveformSpec,
    AuthoringReferenceAxisKind,
    AuthoringReferenceEventSpec,
    AuthoringReferenceOverlaySpec,
    AuthoringRemarkSpec,
    AuthoringReportValueSpec,
    AuthoringScale,
    AuthoringSectionSpec,
    AuthoringServiceTitleSpec,
    AuthoringStyle,
    AuthoringTailSpec,
    AuthoringTrackHeaderPatch,
    AuthoringTrackHeaderSpec,
    CurveBindingSpec,
    CurveFillSpec,
    NormalTrackSpec,
    RasterBindingSpec,
    ReferenceTrackSpec,
    TrackSpec,
)


class _OperationModel(BaseModel):
    """Strict base model for typed service requests and results."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


AuthoringObjectKind: TypeAlias = Literal[
    "report",
    "page",
    "depth",
    "output",
    "header",
    "header_slot",
    "service_title",
    "tail",
    "section",
    "track",
    "curve_binding",
    "raster_binding",
    "annotation",
    "fill",
    "remark",
]


class AuthoringObjectRef(_OperationModel):
    """Stable reference returned by deterministic list operations."""

    object_kind: AuthoringObjectKind
    object_id: str
    section_id: str | None = None
    track_id: str | None = None
    index: int = Field(ge=0)


class AuthoringTarget(_OperationModel):
    """Parent-scoped identity used by get and remove operations."""

    object_kind: AuthoringObjectKind
    object_id: str = Field(min_length=1)
    section_id: str | None = None
    track_id: str | None = None


class AuthoringValidationResult(_OperationModel):
    """Structured result for validation without persistence."""

    valid: bool
    errors: list[str] = Field(default_factory=list)


class HeaderValuePatch(_OperationModel):
    """Typed mutable fields for one header value slot."""

    value: str | None = None
    source_key: str | None = None
    unit: str | None = None
    provenance: Literal["unknown", "source", "user", "default", "preserved"] | None = None
    availability: Literal["unknown", "available", "missing", "not_applicable"] | None = None


class ServiceTitlePatch(HeaderValuePatch):
    """Typed mutable fields for one service title and its presentation."""

    font_size: float | None = Field(default=None, gt=0)
    auto_adjust: bool | None = None
    bold: bool | None = None
    italic: bool | None = None
    alignment: Literal["left", "center", "right"] | None = None


class UpdateHeaderSlotRequest(_OperationModel):
    """Update one header value slot without replacing the header structure."""

    kind: Literal["header_slot"] = "header_slot"
    slot_id: str = Field(min_length=1)
    patch: HeaderValuePatch


class UpdateServiceTitleRequest(_OperationModel):
    """Update one service title without replacing sibling header objects."""

    kind: Literal["service_title"] = "service_title"
    slot_id: str = Field(min_length=1)
    patch: ServiceTitlePatch


class ReportPatch(_OperationModel):
    """Typed mutable fields for report title and subtitle."""

    title: str | None = None
    subtitle: str | None = None


class PagePatch(_OperationModel):
    """Typed mutable fields for document page settings."""

    size: str | None = None
    width_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)
    orientation: Literal["portrait", "landscape"] | None = None
    continuous: bool | None = None
    bottom_track_header_enabled: bool | None = None
    margin_left_mm: float | None = Field(default=None, ge=0)
    margin_right_mm: float | None = Field(default=None, ge=0)
    margin_top_mm: float | None = Field(default=None, ge=0)
    margin_bottom_mm: float | None = Field(default=None, ge=0)
    header_height_mm: float | None = Field(default=None, ge=0)
    track_header_height_mm: float | None = Field(default=None, ge=0)
    footer_height_mm: float | None = Field(default=None, ge=0)
    track_gap_mm: float | None = Field(default=None, ge=0)


class DepthPatch(_OperationModel):
    """Typed mutable fields for the shared document depth axis."""

    unit: str | None = None
    scale: str | float | None = None
    major_step: float | None = Field(default=None, gt=0)
    minor_step: float | None = Field(default=None, gt=0)


class AuthoringStylePatch(_OperationModel):
    """Optional style fields used by binding updates."""

    color: str | None = None
    line_style: str | None = None
    line_width: float | None = Field(default=None, gt=0)
    alpha: float | None = Field(default=None, ge=0, le=1)
    fill_color: str | None = None
    fill_alpha: float | None = Field(default=None, ge=0, le=1)
    colormap: str | None = None


class SectionPatch(_OperationModel):
    """Typed mutable fields for one section."""

    title: str | None = None
    subtitle: str | None = None
    depth_range: tuple[float, float] | None = None
    data_source: AuthoringDataSource | None = None
    extensions: dict[str, Any] | None = None


class ReferenceTrackPatch(_OperationModel):
    """Optional reference-track fields used by a partial track update."""

    axis: AuthoringReferenceAxisKind | None = None
    define_layout: bool | None = None
    unit: str | None = Field(default=None, min_length=1)
    scale_ratio: int | None = Field(default=None, gt=0)
    major_step: float | None = Field(default=None, gt=0)
    minor_step: float | None = Field(default=None, gt=0)
    secondary_grid_display: bool | None = None
    secondary_grid_line_count: int | None = Field(default=None, ge=1)
    display_unit_in_header: bool | None = None
    display_scale_in_header: bool | None = None
    display_annotations_in_header: bool | None = None
    number_format: AuthoringNumberFormatKind | None = None
    precision: int | None = Field(default=None, ge=0)
    values_orientation: Literal["horizontal", "vertical"] | None = None
    events: list[AuthoringReferenceEventSpec] | None = None


class TrackPatch(_OperationModel):
    """Typed mutable fields for one track."""

    title: str | None = None
    width_mm: float | None = Field(default=None, gt=0)
    x_scale: AuthoringScale | None = None
    reference: ReferenceTrackPatch | None = None
    grid: AuthoringGridPatch | None = None
    track_header: AuthoringTrackHeaderPatch | None = None
    extensions: dict[str, Any] | None = None


class CurveBindingPatch(_OperationModel):
    """Typed mutable fields for one scalar binding."""

    label: str | None = None
    scale: AuthoringScale | None = None
    style: AuthoringStylePatch | None = None
    reference_overlay: AuthoringReferenceOverlaySpec | None = None
    wrap: bool | None = None
    render_mode: Literal["line", "value_labels"] | None = None
    value_labels: AuthoringCurveValueLabelsPatch | None = None
    header_display: AuthoringCurveHeaderDisplayPatch | None = None
    callouts: list[AuthoringCurveCalloutSpec] | None = None
    extensions: dict[str, Any] | None = None


class RasterBindingPatch(_OperationModel):
    """Typed mutable fields for one raster binding."""

    label: str | None = None
    style: AuthoringStylePatch | None = None
    profile: AuthoringRasterProfileKind | None = None
    normalization: AuthoringRasterNormalizationKind | None = None
    waveform_normalization: AuthoringRasterNormalizationKind | None = None
    clip_percentiles: tuple[float, float] | None = None
    interpolation: str | None = Field(default=None, min_length=1)
    show_raster: bool | None = None
    alpha: float | None = Field(default=None, ge=0, le=1)
    color_limits: tuple[float, float] | None = None
    colorbar: AuthoringRasterColorbarPatch | None = None
    sample_axis: AuthoringRasterSampleAxisPatch | None = None
    waveform: AuthoringRasterWaveformPatch | None = None
    extensions: dict[str, Any] | None = None


class RemarkPatch(_OperationModel):
    """Typed mutable fields for one remark."""

    title: str | None = None
    text: str | None = None
    lines: list[str] | None = None
    alignment: Literal["left", "center", "right"] | None = None
    font_size: float | None = Field(default=None, gt=0)
    title_font_size: float | None = Field(default=None, gt=0)
    border: bool | None = None


class CreateSectionRequest(_OperationModel):
    """Create one complete section."""

    kind: Literal["section"] = "section"
    section: AuthoringSectionSpec


class CreateTrackRequest(_OperationModel):
    """Create one complete track under a section."""

    kind: Literal["track"] = "track"
    section_id: str = Field(min_length=1)
    track: TrackSpec


class CreateCurveBindingRequest(_OperationModel):
    """Create one curve binding under a compatible track."""

    kind: Literal["curve_binding"] = "curve_binding"
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    binding: CurveBindingSpec


class CreateRasterBindingRequest(_OperationModel):
    """Create one raster binding under an array track."""

    kind: Literal["raster_binding"] = "raster_binding"
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    binding: RasterBindingSpec


class CreateAnnotationRequest(_OperationModel):
    """Create one annotation under an annotation track."""

    kind: Literal["annotation"] = "annotation"
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    annotation: AnnotationSpec


class CreateFillRequest(_OperationModel):
    """Create one fill relation under a normal track."""

    kind: Literal["fill"] = "fill"
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    fill: CurveFillSpec


class CreateRemarkRequest(_OperationModel):
    """Create one report remark."""

    kind: Literal["remark"] = "remark"
    remark: AuthoringRemarkSpec
    index: int | None = Field(default=None, ge=0)


CreateRequest: TypeAlias = Annotated[
    CreateSectionRequest
    | CreateTrackRequest
    | CreateCurveBindingRequest
    | CreateRasterBindingRequest
    | CreateAnnotationRequest
    | CreateFillRequest
    | CreateRemarkRequest,
    Field(discriminator="kind"),
]


class UpdateSectionRequest(_OperationModel):
    """Update one section with a typed patch."""

    kind: Literal["section"] = "section"
    section_id: str = Field(min_length=1)
    patch: SectionPatch


class UpdatePageRequest(_OperationModel):
    """Update document page settings with a typed patch."""

    kind: Literal["page"] = "page"
    patch: PagePatch


class UpdateReportRequest(_OperationModel):
    """Update report title and subtitle with a typed patch."""

    kind: Literal["report"] = "report"
    patch: ReportPatch


class UpdateOutputRequest(_OperationModel):
    """Replace document output settings with a validated typed object."""

    kind: Literal["output"] = "output"
    output: AuthoringOutputSpec


class UpdateHeaderRequest(_OperationModel):
    """Replace the document header with a validated typed object."""

    kind: Literal["header"] = "header"
    header: AuthoringHeaderSpec


class UpdateTailRequest(_OperationModel):
    """Replace report-tail settings with a validated typed object."""

    kind: Literal["tail"] = "tail"
    tail: AuthoringTailSpec


class UpdateDepthRequest(_OperationModel):
    """Update document depth-axis settings with a typed patch."""

    kind: Literal["depth"] = "depth"
    patch: DepthPatch


class UpdateTrackRequest(_OperationModel):
    """Update one track with a typed patch."""

    kind: Literal["track"] = "track"
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    patch: TrackPatch


class UpdateCurveBindingRequest(_OperationModel):
    """Update one curve binding with a typed patch."""

    kind: Literal["curve_binding"] = "curve_binding"
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    binding_id: str = Field(min_length=1)
    patch: CurveBindingPatch


class UpdateRasterBindingRequest(_OperationModel):
    """Update one raster binding with a typed patch."""

    kind: Literal["raster_binding"] = "raster_binding"
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    binding_id: str = Field(min_length=1)
    patch: RasterBindingPatch


class UpdateAnnotationRequest(_OperationModel):
    """Replace one annotation with another object of the same kind."""

    kind: Literal["annotation"] = "annotation"
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    annotation_id: str = Field(min_length=1)
    annotation: AnnotationSpec


class UpdateFillRequest(_OperationModel):
    """Replace one fill relation while retaining its stable identity."""

    kind: Literal["fill"] = "fill"
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    fill_id: str = Field(min_length=1)
    fill: CurveFillSpec


class UpdateRemarkRequest(_OperationModel):
    """Update one report remark with a typed patch."""

    kind: Literal["remark"] = "remark"
    remark_id: str = Field(min_length=1)
    patch: RemarkPatch


UpdateRequest: TypeAlias = Annotated[
    UpdateReportRequest
    | UpdatePageRequest
    | UpdateOutputRequest
    | UpdateHeaderRequest
    | UpdateHeaderSlotRequest
    | UpdateServiceTitleRequest
    | UpdateTailRequest
    | UpdateDepthRequest
    | UpdateSectionRequest
    | UpdateTrackRequest
    | UpdateCurveBindingRequest
    | UpdateRasterBindingRequest
    | UpdateAnnotationRequest
    | UpdateFillRequest
    | UpdateRemarkRequest,
    Field(discriminator="kind"),
]


class RemoveRequest(_OperationModel):
    """Remove one identified authoring object."""

    target: AuthoringTarget


class MoveRequest(_OperationModel):
    """Move an ordered section, track, or remark."""

    object_kind: Literal["section", "track", "remark"]
    object_id: str = Field(min_length=1)
    new_index: int = Field(ge=0)
    section_id: str | None = None


AuthoringObject: TypeAlias = (
    AuthoringDocumentSpec
    | AuthoringPageSpec
    | AuthoringDepthSpec
    | AuthoringOutputSpec
    | AuthoringHeaderSpec
    | AuthoringReportValueSpec
    | AuthoringServiceTitleSpec
    | AuthoringTailSpec
    | AuthoringSectionSpec
    | TrackSpec
    | CurveBindingSpec
    | RasterBindingSpec
    | AnnotationSpec
    | CurveFillSpec
    | AuthoringRemarkSpec
)


_HIERARCHY_NODE_DEFINITIONS: tuple[dict[str, object], ...] = (
    {
        "object_kind": "report",
        "parent_kind": None,
        "children": ("output", "page", "depth", "header", "tail", "remark", "section"),
        "identity_field": "object_id",
        "parent_fields": (),
        "operations": ("list", "get", "update", "validate"),
        "canonical_contract": "AuthoringDocumentSpec",
        "update_request": UpdateReportRequest,
    },
    {
        "object_kind": "output",
        "parent_kind": "report",
        "children": (),
        "identity_field": "object_id",
        "parent_fields": (),
        "operations": ("list", "get", "update", "validate"),
        "canonical_contract": "AuthoringOutputSpec",
        "update_request": UpdateOutputRequest,
    },
    {
        "object_kind": "page",
        "parent_kind": "report",
        "children": (),
        "identity_field": "object_id",
        "parent_fields": (),
        "operations": ("list", "get", "update", "validate"),
        "canonical_contract": "AuthoringPageSpec",
        "update_request": UpdatePageRequest,
    },
    {
        "object_kind": "depth",
        "parent_kind": "report",
        "children": (),
        "identity_field": "object_id",
        "parent_fields": (),
        "operations": ("list", "get", "update", "validate"),
        "canonical_contract": "AuthoringDepthSpec",
        "update_request": UpdateDepthRequest,
    },
    {
        "object_kind": "header",
        "parent_kind": "report",
        "children": ("header_slot", "service_title"),
        "identity_field": "object_id",
        "parent_fields": (),
        "operations": ("list", "get", "update", "validate"),
        "canonical_contract": "AuthoringHeaderSpec",
        "update_request": UpdateHeaderRequest,
    },
    {
        "object_kind": "header_slot",
        "parent_kind": "header",
        "children": (),
        "identity_field": "slot_id",
        "parent_fields": (),
        "operations": ("list", "get", "update", "validate"),
        "canonical_contract": "AuthoringReportValueSpec",
        "update_request": UpdateHeaderSlotRequest,
    },
    {
        "object_kind": "service_title",
        "parent_kind": "header",
        "children": (),
        "identity_field": "slot_id",
        "parent_fields": (),
        "operations": ("list", "get", "update", "validate"),
        "canonical_contract": "AuthoringServiceTitleSpec",
        "update_request": UpdateServiceTitleRequest,
    },
    {
        "object_kind": "remark",
        "parent_kind": "report",
        "children": (),
        "identity_field": "remark_id",
        "parent_fields": (),
        "operations": ("list", "get", "create", "update", "remove", "move", "validate"),
        "canonical_contract": "AuthoringRemarkSpec",
        "create_request": CreateRemarkRequest,
        "update_request": UpdateRemarkRequest,
    },
    {
        "object_kind": "tail",
        "parent_kind": "report",
        "children": (),
        "identity_field": "object_id",
        "parent_fields": (),
        "operations": ("list", "get", "update", "validate"),
        "canonical_contract": "AuthoringTailSpec",
        "update_request": UpdateTailRequest,
    },
    {
        "object_kind": "section",
        "parent_kind": "report",
        "children": ("track",),
        "identity_field": "id",
        "parent_fields": (),
        "operations": ("list", "get", "create", "update", "remove", "move", "validate"),
        "canonical_contract": "AuthoringSectionSpec",
        "create_request": CreateSectionRequest,
        "update_request": UpdateSectionRequest,
    },
    {
        "object_kind": "track",
        "parent_kind": "section",
        "children": ("curve_binding", "raster_binding", "fill", "annotation"),
        "identity_field": "id",
        "parent_fields": ("section_id",),
        "operations": ("list", "get", "create", "update", "remove", "move", "validate"),
        "canonical_contract": "TrackSpec",
        "create_request": CreateTrackRequest,
        "update_request": UpdateTrackRequest,
        "constraints": {
            "form_kind_immutable": True,
            "child_compatibility": {
                "normal": ("curve_binding", "fill"),
                "reference": ("curve_binding",),
                "array": ("curve_binding", "raster_binding"),
                "annotation": ("annotation",),
            },
        },
    },
    {
        "object_kind": "curve_binding",
        "parent_kind": "track",
        "children": (),
        "identity_field": "binding_id",
        "parent_fields": ("section_id", "track_id"),
        "operations": ("list", "get", "create", "update", "remove", "validate"),
        "canonical_contract": "CurveBindingSpec",
        "create_request": CreateCurveBindingRequest,
        "update_request": UpdateCurveBindingRequest,
        "constraints": {
            "compatible_track_kinds": ("normal", "reference", "array"),
        },
    },
    {
        "object_kind": "raster_binding",
        "parent_kind": "track",
        "children": (),
        "identity_field": "binding_id",
        "parent_fields": ("section_id", "track_id"),
        "operations": ("list", "get", "create", "update", "remove", "validate"),
        "canonical_contract": "RasterBindingSpec",
        "create_request": CreateRasterBindingRequest,
        "update_request": UpdateRasterBindingRequest,
        "constraints": {
            "compatible_track_kinds": ("array",),
        },
    },
    {
        "object_kind": "fill",
        "parent_kind": "track",
        "children": (),
        "identity_field": "fill_id",
        "parent_fields": ("section_id", "track_id"),
        "operations": ("list", "get", "create", "update", "remove", "validate"),
        "canonical_contract": "CurveFillSpec",
        "create_request": CreateFillRequest,
        "update_request": UpdateFillRequest,
        "constraints": {
            "compatible_track_kinds": ("normal",),
            "target_fields": ("binding_id", "other_binding_id"),
        },
    },
    {
        "object_kind": "annotation",
        "parent_kind": "track",
        "children": (),
        "identity_field": "annotation_id",
        "parent_fields": ("section_id", "track_id"),
        "operations": ("list", "get", "create", "update", "remove", "validate"),
        "canonical_contract": "AnnotationSpec",
        "create_request": CreateAnnotationRequest,
        "update_request": UpdateAnnotationRequest,
        "constraints": {
            "compatible_track_kinds": ("annotation",),
        },
    },
)

_HIERARCHY_CANONICAL_MODELS: dict[str, object] = {
    "report": AuthoringDocumentSpec,
    "output": AuthoringOutputSpec,
    "page": AuthoringPageSpec,
    "depth": AuthoringDepthSpec,
    "header": AuthoringHeaderSpec,
    "header_slot": AuthoringReportValueSpec,
    "service_title": AuthoringServiceTitleSpec,
    "remark": AuthoringRemarkSpec,
    "tail": AuthoringTailSpec,
    "section": AuthoringSectionSpec,
    "track": TrackSpec,
    "curve_binding": CurveBindingSpec,
    "raster_binding": RasterBindingSpec,
    "fill": CurveFillSpec,
    "annotation": AnnotationSpec,
}

_HIERARCHY_ID_FIELDS = {
    "object_id",
    "id",
    "remark_id",
    "binding_id",
    "fill_id",
    "annotation_id",
    "section_id",
    "track_id",
}
_HIERARCHY_RELATIONAL_FIELDS = {
    "data_source",
    "binding_id",
    "other_binding_id",
    "track_id",
    "section_id",
}
_HIERARCHY_SCHEMA_CONSTRAINT_KEYS = (
    "enum",
    "minimum",
    "exclusiveMinimum",
    "maximum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "pattern",
)


class AuthoringService:
    """Own and atomically mutate one canonical authoring document."""

    def __init__(self, document: AuthoringDocumentSpec) -> None:
        """Initialize the service from an already validated document."""
        self._document = AuthoringDocumentSpec.model_validate(
            deepcopy(document).model_dump(mode="python")
        )

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> AuthoringService:
        """Create a service from canonical or legacy YAML-shaped data."""
        return cls(authoring_document_from_mapping(mapping))

    @property
    def document(self) -> AuthoringDocumentSpec:
        """Return a defensive copy of the current document."""
        return deepcopy(self._document)

    def replace_document(self, document: AuthoringDocumentSpec) -> None:
        """Publish one fully validated canonical document snapshot atomically."""
        candidate = AuthoringDocumentSpec.model_validate(
            deepcopy(document).model_dump(mode="python")
        )
        self._document = candidate

    def to_mapping(self) -> dict[str, object]:
        """Serialize a defensive snapshot through the canonical adapter."""
        return authoring_document_to_mapping(self._document)

    def validate(self, document: AuthoringDocumentSpec | None = None) -> AuthoringValidationResult:
        """Validate the current document or a candidate without persistence."""
        candidate = self._document if document is None else document
        try:
            AuthoringDocumentSpec.model_validate(candidate.model_dump(mode="python"))
        except ValidationError as exc:
            return AuthoringValidationResult(
                valid=False,
                errors=[error["msg"] for error in exc.errors()],
            )
        return AuthoringValidationResult(valid=True)

    def list(
        self,
        object_kind: AuthoringObjectKind,
        *,
        section_id: str | None = None,
        track_id: str | None = None,
    ) -> list[AuthoringObjectRef]:
        """List stable references for one object family."""
        refs: list[AuthoringObjectRef] = []
        if object_kind in {"report", "page", "depth", "output", "header", "tail"}:
            return [
                AuthoringObjectRef(
                    object_kind=object_kind,
                    object_id=object_kind,
                    index=0,
                )
            ]
        if object_kind in {"header_slot", "service_title"}:
            header = self._document.header
            if header is None:
                return []
            refs: list[AuthoringObjectRef] = []
            if object_kind == "header_slot":
                slot_index = 0
                for field in header.general_fields:
                    refs.append(
                        AuthoringObjectRef(
                            object_kind=object_kind,
                            object_id=field.slot_id,
                            index=slot_index,
                        )
                    )
                    slot_index += 1
                if header.detail is not None:
                    for row in header.detail.rows:
                        cells = list(row.values)
                        for column in row.columns:
                            cells.extend(column.cells)
                        for cell in cells:
                            refs.append(
                                AuthoringObjectRef(
                                    object_kind=object_kind,
                                    object_id=cell.slot_id,
                                    index=slot_index,
                                )
                            )
                            slot_index += 1
            else:
                refs = [
                    AuthoringObjectRef(
                        object_kind=object_kind,
                        object_id=title.slot_id,
                        index=index,
                    )
                    for index, title in enumerate(header.service_titles)
                ]
            return refs
        if object_kind == "section":
            for index, section in enumerate(self._document.sections):
                refs.append(
                    AuthoringObjectRef(
                        object_kind=object_kind,
                        object_id=section.id,
                        index=index,
                    )
                )
            return refs
        if object_kind == "remark":
            for index, remark in enumerate(self._document.remarks):
                refs.append(
                    AuthoringObjectRef(
                        object_kind=object_kind,
                        object_id=self._require_id(remark.remark_id, "remark"),
                        index=index,
                    )
                )
            return refs

        sections = self._scoped_sections(section_id)
        for section in sections:
            if object_kind == "track":
                for index, track in enumerate(section.tracks):
                    refs.append(
                        AuthoringObjectRef(
                            object_kind=object_kind,
                            object_id=track.id,
                            section_id=section.id,
                            index=index,
                        )
                    )
                continue
            tracks = self._scoped_tracks(section, track_id)
            for track in tracks:
                if object_kind in {"curve_binding", "raster_binding"}:
                    for index, binding in enumerate(getattr(track, "bindings", ())):
                        if object_kind == "curve_binding" and not isinstance(
                            binding, CurveBindingSpec
                        ):
                            continue
                        if object_kind == "raster_binding" and not isinstance(
                            binding, RasterBindingSpec
                        ):
                            continue
                        refs.append(
                            AuthoringObjectRef(
                                object_kind=object_kind,
                                object_id=binding.binding_id,
                                section_id=section.id,
                                track_id=track.id,
                                index=index,
                            )
                        )
                elif object_kind == "annotation" and isinstance(track, AnnotationTrackSpec):
                    for index, annotation in enumerate(track.annotations):
                        refs.append(
                            AuthoringObjectRef(
                                object_kind=object_kind,
                                object_id=annotation.annotation_id,
                                section_id=section.id,
                                track_id=track.id,
                                index=index,
                            )
                        )
                elif object_kind == "fill" and isinstance(track, NormalTrackSpec):
                    for index, fill in enumerate(track.fills):
                        refs.append(
                            AuthoringObjectRef(
                                object_kind=object_kind,
                                object_id=self._require_id(fill.fill_id, "fill"),
                                section_id=section.id,
                                track_id=track.id,
                                index=index,
                            )
                        )
        return refs

    def get(self, target: AuthoringTarget) -> AuthoringObject:
        """Return a defensive copy of one parent-scoped object."""
        if target.object_kind == "report":
            return deepcopy(self._document)
        if target.object_kind == "page":
            return deepcopy(self._document.page)
        if target.object_kind == "depth":
            return deepcopy(self._document.depth)
        if target.object_kind == "output":
            return deepcopy(self._document.output)
        if target.object_kind == "header":
            return deepcopy(self._document.header or AuthoringHeaderSpec())
        if target.object_kind == "header_slot":
            return deepcopy(self._find_header_slot_in(self._document, target.object_id))
        if target.object_kind == "service_title":
            return deepcopy(self._find_service_title_in(self._document, target.object_id))
        if target.object_kind == "tail":
            return deepcopy(self._document.tail)
        if target.object_kind == "section":
            return deepcopy(self._find_section(target.object_id))
        if target.object_kind == "remark":
            return deepcopy(self._find_remark(target.object_id))
        section = self._find_section(target.section_id)
        if target.object_kind == "track":
            return deepcopy(self._find_track(section, target.object_id))
        track = self._find_track(section, target.track_id)
        if target.object_kind == "annotation":
            if not isinstance(track, AnnotationTrackSpec):
                raise ValueError(f"Track {track.id!r} is not an annotation track.")
            return deepcopy(self._find_annotation(track, target.object_id))
        if target.object_kind == "fill":
            if not isinstance(track, NormalTrackSpec):
                raise ValueError(f"Track {track.id!r} is not a normal track.")
            return deepcopy(self._find_fill(track, target.object_id))
        binding = self._find_binding(track, target.object_id)
        if target.object_kind == "curve_binding" and not isinstance(binding, CurveBindingSpec):
            raise ValueError(f"Binding {target.object_id!r} is not a curve binding.")
        if target.object_kind == "raster_binding" and not isinstance(binding, RasterBindingSpec):
            raise ValueError(f"Binding {target.object_id!r} is not a raster binding.")
        return deepcopy(binding)

    def create(self, request: CreateRequest) -> AuthoringObject:
        """Create one typed object and atomically validate the result."""
        if isinstance(request, CreateSectionRequest):
            self._commit(lambda document: document.sections.append(deepcopy(request.section)))
            return self.get(AuthoringTarget(object_kind="section", object_id=request.section.id))
        if isinstance(request, CreateTrackRequest):
            self._commit(
                lambda document: self._find_section_in(document, request.section_id).tracks.append(
                    deepcopy(request.track)
                )
            )
            return self.get(
                AuthoringTarget(
                    object_kind="track",
                    object_id=request.track.id,
                    section_id=request.section_id,
                )
            )
        if isinstance(request, CreateCurveBindingRequest):
            self._create_binding(request.section_id, request.track_id, request.binding)
            return self.get(
                AuthoringTarget(
                    object_kind="curve_binding",
                    object_id=request.binding.binding_id,
                    section_id=request.section_id,
                    track_id=request.track_id,
                )
            )
        if isinstance(request, CreateRasterBindingRequest):
            self._create_binding(request.section_id, request.track_id, request.binding)
            return self.get(
                AuthoringTarget(
                    object_kind="raster_binding",
                    object_id=request.binding.binding_id,
                    section_id=request.section_id,
                    track_id=request.track_id,
                )
            )
        if isinstance(request, CreateAnnotationRequest):
            self._commit(
                lambda document: self._append_annotation_in(
                    document, request.section_id, request.track_id, request.annotation
                )
            )
            return self.get(
                AuthoringTarget(
                    object_kind="annotation",
                    object_id=request.annotation.annotation_id,
                    section_id=request.section_id,
                    track_id=request.track_id,
                )
            )
        if isinstance(request, CreateFillRequest):
            self._commit(
                lambda document: self._append_fill_in(
                    document, request.section_id, request.track_id, request.fill
                )
            )
            fill_id = request.fill.fill_id
            if fill_id is None:
                fill_id = self.list(
                    "fill", section_id=request.section_id, track_id=request.track_id
                )[-1].object_id
            return self.get(
                AuthoringTarget(
                    object_kind="fill",
                    object_id=fill_id,
                    section_id=request.section_id,
                    track_id=request.track_id,
                )
            )
        if isinstance(request, CreateRemarkRequest):
            remark = deepcopy(request.remark)
            if remark.remark_id is None:
                remark.remark_id = self._next_id("remark")

            def append_remark(document: AuthoringDocumentSpec) -> None:
                if request.index is None:
                    document.remarks.append(remark)
                else:
                    if request.index > len(document.remarks):
                        raise IndexError("Remark index is outside the ordered collection.")
                    document.remarks.insert(request.index, remark)

            self._commit(append_remark)
            return self.get(AuthoringTarget(object_kind="remark", object_id=remark.remark_id))
        raise TypeError(f"Unsupported create request {type(request).__name__}.")

    def update(self, request: UpdateRequest) -> AuthoringObject:
        """Apply one typed patch or replacement atomically."""
        if isinstance(request, UpdateReportRequest):
            self._commit(lambda document: self._patch_model(document, request.patch))
            return self.get(AuthoringTarget(object_kind="report", object_id="report"))
        if isinstance(request, UpdatePageRequest):
            self._commit(lambda document: self._patch_model(document.page, request.patch))
            return self.get(AuthoringTarget(object_kind="page", object_id="page"))
        if isinstance(request, UpdateOutputRequest):
            self._commit(lambda document: setattr(document, "output", deepcopy(request.output)))
            return self.get(AuthoringTarget(object_kind="output", object_id="output"))
        if isinstance(request, UpdateHeaderRequest):
            self._commit(lambda document: setattr(document, "header", deepcopy(request.header)))
            return self.get(AuthoringTarget(object_kind="header", object_id="header"))
        if isinstance(request, UpdateHeaderSlotRequest):
            self._commit(
                lambda document: self._patch_model(
                    self._find_header_slot_in(document, request.slot_id),
                    request.patch,
                )
            )
            return self.get(AuthoringTarget(object_kind="header_slot", object_id=request.slot_id))
        if isinstance(request, UpdateServiceTitleRequest):

            def patch_service_title(document: AuthoringDocumentSpec) -> None:
                title = self._find_service_title_in(document, request.slot_id)
                value_fields = set(HeaderValuePatch.model_fields)
                value_patch = HeaderValuePatch.model_validate(
                    {
                        field_name: getattr(request.patch, field_name)
                        for field_name in value_fields
                        if field_name in request.patch.model_fields_set
                    }
                )
                self._patch_model(title.value, value_patch)
                for field_name in request.patch.model_fields_set - value_fields:
                    setattr(title, field_name, deepcopy(getattr(request.patch, field_name)))

            self._commit(patch_service_title)
            return self.get(AuthoringTarget(object_kind="service_title", object_id=request.slot_id))
        if isinstance(request, UpdateTailRequest):
            self._commit(lambda document: setattr(document, "tail", deepcopy(request.tail)))
            return self.get(AuthoringTarget(object_kind="tail", object_id="tail"))
        if isinstance(request, UpdateDepthRequest):
            self._commit(lambda document: self._patch_model(document.depth, request.patch))
            return self.get(AuthoringTarget(object_kind="depth", object_id="depth"))
        if isinstance(request, UpdateSectionRequest):
            self._commit(
                lambda document: self._patch_model(
                    self._find_section_in(document, request.section_id), request.patch
                )
            )
            return self.get(AuthoringTarget(object_kind="section", object_id=request.section_id))
        if isinstance(request, UpdateTrackRequest):
            self._commit(
                lambda document: self._patch_track(
                    self._find_track_in(
                        self._find_section_in(document, request.section_id), request.track_id
                    ),
                    request.patch,
                )
            )
            return self.get(
                AuthoringTarget(
                    object_kind="track",
                    object_id=request.track_id,
                    section_id=request.section_id,
                )
            )
        if isinstance(request, UpdateCurveBindingRequest):
            self._commit(
                lambda document: self._patch_curve_binding(
                    document,
                    request.section_id,
                    request.track_id,
                    request.binding_id,
                    request.patch,
                )
            )
            return self.get(
                AuthoringTarget(
                    object_kind="curve_binding",
                    object_id=request.binding_id,
                    section_id=request.section_id,
                    track_id=request.track_id,
                )
            )
        if isinstance(request, UpdateRasterBindingRequest):
            self._commit(
                lambda document: self._patch_raster_binding(
                    document,
                    request.section_id,
                    request.track_id,
                    request.binding_id,
                    request.patch,
                )
            )
            return self.get(
                AuthoringTarget(
                    object_kind="raster_binding",
                    object_id=request.binding_id,
                    section_id=request.section_id,
                    track_id=request.track_id,
                )
            )
        if isinstance(request, UpdateAnnotationRequest):
            self._commit(
                lambda document: self._replace_annotation(
                    document,
                    request.section_id,
                    request.track_id,
                    request.annotation_id,
                    request.annotation,
                )
            )
            return self.get(
                AuthoringTarget(
                    object_kind="annotation",
                    object_id=request.annotation_id,
                    section_id=request.section_id,
                    track_id=request.track_id,
                )
            )
        if isinstance(request, UpdateFillRequest):
            self._commit(
                lambda document: self._replace_fill(
                    document, request.section_id, request.track_id, request.fill_id, request.fill
                )
            )
            return self.get(
                AuthoringTarget(
                    object_kind="fill",
                    object_id=request.fill_id,
                    section_id=request.section_id,
                    track_id=request.track_id,
                )
            )
        if isinstance(request, UpdateRemarkRequest):
            self._commit(
                lambda document: self._patch_model(
                    self._find_remark_in(document, request.remark_id), request.patch
                )
            )
            return self.get(AuthoringTarget(object_kind="remark", object_id=request.remark_id))
        raise TypeError(f"Unsupported update request {type(request).__name__}.")

    def remove(self, request: RemoveRequest) -> AuthoringObject:
        """Remove one object and atomically validate the remaining document."""
        if request.target.object_kind in {
            "report",
            "page",
            "depth",
            "output",
            "header",
            "header_slot",
            "service_title",
            "tail",
        }:
            raise ValueError(f"Cannot remove document-level {request.target.object_kind} settings.")
        existing = self.get(request.target)

        def mutate(document: AuthoringDocumentSpec) -> None:
            target = request.target
            if target.object_kind == "section":
                section = self._find_section_in(document, target.object_id)
                document.sections.remove(section)
            elif target.object_kind == "remark":
                document.remarks.remove(self._find_remark_in(document, target.object_id))
            else:
                section = self._find_section_in(document, target.section_id)
                if target.object_kind == "track":
                    section.tracks.remove(self._find_track_in(section, target.object_id))
                    return
                track = self._find_track_in(section, target.track_id)
                if target.object_kind in {"curve_binding", "raster_binding"}:
                    binding = self._find_binding(track, target.object_id)
                    if target.object_kind == "curve_binding" and not isinstance(
                        binding, CurveBindingSpec
                    ):
                        raise ValueError("Target is not a curve binding.")
                    if target.object_kind == "raster_binding" and not isinstance(
                        binding, RasterBindingSpec
                    ):
                        raise ValueError("Target is not a raster binding.")
                    track.bindings.remove(binding)
                elif target.object_kind == "annotation":
                    if not isinstance(track, AnnotationTrackSpec):
                        raise ValueError("Target track is not an annotation track.")
                    track.annotations.remove(self._find_annotation(track, target.object_id))
                elif target.object_kind == "fill":
                    if not isinstance(track, NormalTrackSpec):
                        raise ValueError("Target track is not a normal track.")
                    track.fills.remove(self._find_fill(track, target.object_id))

        self._commit(mutate)
        return existing

    def move(self, request: MoveRequest) -> AuthoringObject:
        """Move one ordered object and atomically validate the result."""
        target = AuthoringTarget(
            object_kind=request.object_kind,
            object_id=request.object_id,
            section_id=request.section_id,
        )
        existing = self.get(target)

        def mutate(document: AuthoringDocumentSpec) -> None:
            if request.object_kind == "section":
                collection = document.sections
                item = self._find_section_in(document, request.object_id)
            elif request.object_kind == "remark":
                collection = document.remarks
                item = self._find_remark_in(document, request.object_id)
            else:
                section = self._find_section_in(document, request.section_id)
                collection = section.tracks
                item = self._find_track_in(section, request.object_id)
            if request.new_index >= len(collection):
                raise IndexError("New index is outside the ordered collection.")
            collection.remove(item)
            collection.insert(request.new_index, item)

        self._commit(mutate)
        return existing

    def _commit(self, mutator: Callable[[AuthoringDocumentSpec], None]) -> None:
        """Apply a mutation to a copy and publish only after validation."""
        candidate = deepcopy(self._document)
        mutator(candidate)
        self._document = AuthoringDocumentSpec.model_validate(candidate.model_dump(mode="python"))

    @staticmethod
    def _patch_model(model: BaseModel, patch: BaseModel) -> None:
        """Apply only fields explicitly supplied by a typed patch model."""
        for field_name in patch.model_fields_set:
            setattr(model, field_name, deepcopy(getattr(patch, field_name)))

    @staticmethod
    def _find_header_slot_in(
        document: AuthoringDocumentSpec,
        slot_id: str,
    ) -> AuthoringReportValueSpec:
        """Find one general or detail-table header value by stable slot id."""
        header = document.header
        if header is None:
            raise KeyError(f"Unknown header slot {slot_id!r}: document has no header.")
        for field in header.general_fields:
            if field.slot_id == slot_id:
                return field.value
        if header.detail is not None:
            for row in header.detail.rows:
                for cell in row.values:
                    if cell.slot_id == slot_id:
                        return cell.value
                for column in row.columns:
                    for cell in column.cells:
                        if cell.slot_id == slot_id:
                            return cell.value
        raise KeyError(f"Unknown header slot {slot_id!r}.")

    @staticmethod
    def _find_service_title_in(
        document: AuthoringDocumentSpec,
        slot_id: str,
    ) -> AuthoringServiceTitleSpec:
        """Find one service title by stable slot id."""
        header = document.header
        if header is None:
            raise KeyError(f"Unknown service title {slot_id!r}: document has no header.")
        for title in header.service_titles:
            if title.slot_id == slot_id:
                return title
        raise KeyError(f"Unknown service title {slot_id!r}.")

    @staticmethod
    def _patch_track(track: TrackSpec, patch: TrackPatch) -> None:
        """Apply track fields while merging partial canonical grid updates."""
        for field_name in patch.model_fields_set:
            value = getattr(patch, field_name)
            if field_name == "reference":
                if not isinstance(track, ReferenceTrackSpec):
                    raise ValueError("Reference settings require a reference track.")
                if value is None:
                    defaults = ReferenceTrackSpec()
                    reference_fields = (
                        "axis",
                        "define_layout",
                        "unit",
                        "scale_ratio",
                        "major_step",
                        "minor_step",
                        "secondary_grid_display",
                        "secondary_grid_line_count",
                        "display_unit_in_header",
                        "display_scale_in_header",
                        "display_annotations_in_header",
                        "number_format",
                        "precision",
                        "values_orientation",
                        "events",
                    )
                    for reference_field in reference_fields:
                        setattr(
                            track,
                            reference_field,
                            deepcopy(getattr(defaults, reference_field)),
                        )
                else:
                    updates = value.model_dump(mode="python", exclude_unset=True)
                    for reference_field, reference_value in updates.items():
                        setattr(track, reference_field, deepcopy(reference_value))
                continue
            if field_name == "grid":
                if value is None:
                    track.grid = AuthoringGridSpec()
                    continue
                updates = value.model_dump(mode="python", exclude_unset=True)
                track.grid = AuthoringGridSpec.model_validate(
                    track.grid.model_dump(mode="python") | updates
                )
                continue
            if field_name == "track_header":
                if value is None:
                    track.track_header = AuthoringTrackHeaderSpec()
                else:
                    updates = value.model_dump(mode="python", exclude_unset=True)
                    track.track_header = AuthoringTrackHeaderSpec.model_validate(
                        track.track_header.model_dump(mode="python") | updates
                    )
                continue
            setattr(track, field_name, deepcopy(value))

    def _patch_curve_binding(
        self,
        document: AuthoringDocumentSpec,
        section_id: str,
        track_id: str,
        binding_id: str,
        patch: CurveBindingPatch,
    ) -> None:
        binding = self._find_binding(
            self._find_track_in(self._find_section_in(document, section_id), track_id), binding_id
        )
        if not isinstance(binding, CurveBindingSpec):
            raise ValueError(f"Binding {binding_id!r} is not a curve binding.")
        for field_name in patch.model_fields_set:
            value = getattr(patch, field_name)
            if field_name == "style":
                binding.style = (
                    AuthoringStyle()
                    if value is None
                    else binding.style.model_copy(
                        update={
                            key: deepcopy(getattr(value, key)) for key in value.model_fields_set
                        }
                    )
                )
            elif field_name == "value_labels":
                if value is None:
                    binding.value_labels = AuthoringCurveValueLabelsSpec()
                else:
                    updates = value.model_dump(mode="python", exclude_unset=True)
                    binding.value_labels = AuthoringCurveValueLabelsSpec.model_validate(
                        binding.value_labels.model_dump(mode="python") | updates
                    )
            elif field_name == "header_display":
                if value is None:
                    binding.header_display = AuthoringCurveHeaderDisplaySpec()
                else:
                    updates = value.model_dump(mode="python", exclude_unset=True)
                    binding.header_display = AuthoringCurveHeaderDisplaySpec.model_validate(
                        binding.header_display.model_dump(mode="python") | updates
                    )
            else:
                setattr(binding, field_name, deepcopy(value))

    def _patch_raster_binding(
        self,
        document: AuthoringDocumentSpec,
        section_id: str,
        track_id: str,
        binding_id: str,
        patch: RasterBindingPatch,
    ) -> None:
        binding = self._find_binding(
            self._find_track_in(self._find_section_in(document, section_id), track_id), binding_id
        )
        if not isinstance(binding, RasterBindingSpec):
            raise ValueError(f"Binding {binding_id!r} is not a raster binding.")
        for field_name in patch.model_fields_set:
            value = getattr(patch, field_name)
            if field_name == "style":
                binding.style = (
                    AuthoringStyle()
                    if value is None
                    else binding.style.model_copy(
                        update={
                            key: deepcopy(getattr(value, key)) for key in value.model_fields_set
                        }
                    )
                )
            elif field_name == "colorbar":
                binding.colorbar = (
                    AuthoringRasterColorbarSpec()
                    if value is None
                    else AuthoringRasterColorbarSpec.model_validate(
                        binding.colorbar.model_dump(mode="python")
                        | value.model_dump(mode="python", exclude_unset=True)
                    )
                )
            elif field_name == "sample_axis":
                binding.sample_axis = (
                    AuthoringRasterSampleAxisSpec()
                    if value is None
                    else AuthoringRasterSampleAxisSpec.model_validate(
                        binding.sample_axis.model_dump(mode="python")
                        | value.model_dump(mode="python", exclude_unset=True)
                    )
                )
            elif field_name == "waveform":
                binding.waveform = (
                    AuthoringRasterWaveformSpec()
                    if value is None
                    else AuthoringRasterWaveformSpec.model_validate(
                        binding.waveform.model_dump(mode="python")
                        | value.model_dump(mode="python", exclude_unset=True)
                    )
                )
            else:
                setattr(binding, field_name, deepcopy(value))

    @staticmethod
    def _replace_annotation(
        document: AuthoringDocumentSpec,
        section_id: str,
        track_id: str,
        annotation_id: str,
        annotation: AnnotationSpec,
    ) -> None:
        track = AuthoringService._find_track_in(
            AuthoringService._find_section_in(document, section_id), track_id
        )
        if not isinstance(track, AnnotationTrackSpec):
            raise ValueError("Target track is not an annotation track.")
        current = AuthoringService._find_annotation(track, annotation_id)
        if current.kind != annotation.kind:
            raise ValueError("Annotation kind cannot change during update.")
        index = track.annotations.index(current)
        replacement = deepcopy(annotation)
        replacement.annotation_id = annotation_id
        track.annotations[index] = replacement

    @staticmethod
    def _replace_fill(
        document: AuthoringDocumentSpec,
        section_id: str,
        track_id: str,
        fill_id: str,
        fill: CurveFillSpec,
    ) -> None:
        track = AuthoringService._find_track_in(
            AuthoringService._find_section_in(document, section_id), track_id
        )
        if not isinstance(track, NormalTrackSpec):
            raise ValueError("Target track is not a normal track.")
        current = AuthoringService._find_fill(track, fill_id)
        index = track.fills.index(current)
        replacement = deepcopy(fill)
        replacement.fill_id = fill_id
        track.fills[index] = replacement

    @staticmethod
    def _append_annotation_in(
        document: AuthoringDocumentSpec,
        section_id: str,
        track_id: str,
        annotation: AnnotationSpec,
    ) -> None:
        track = AuthoringService._find_track_in(
            AuthoringService._find_section_in(document, section_id), track_id
        )
        if not isinstance(track, AnnotationTrackSpec):
            raise ValueError("Target track is not an annotation track.")
        track.annotations.append(deepcopy(annotation))

    @staticmethod
    def _append_fill_in(
        document: AuthoringDocumentSpec,
        section_id: str,
        track_id: str,
        fill: CurveFillSpec,
    ) -> None:
        track = AuthoringService._find_track_in(
            AuthoringService._find_section_in(document, section_id), track_id
        )
        if not isinstance(track, NormalTrackSpec):
            raise ValueError("Target track is not a normal track.")
        track.fills.append(deepcopy(fill))

    def _create_binding(
        self,
        section_id: str,
        track_id: str,
        binding: CurveBindingSpec | RasterBindingSpec,
    ) -> None:
        def append(document: AuthoringDocumentSpec) -> None:
            track = self._find_track_in(self._find_section_in(document, section_id), track_id)
            if isinstance(binding, RasterBindingSpec) and not isinstance(track, ArrayTrackSpec):
                raise ValueError("Raster bindings require an array track.")
            if isinstance(binding, CurveBindingSpec) and not isinstance(
                track, (NormalTrackSpec, ReferenceTrackSpec, ArrayTrackSpec)
            ):
                raise ValueError("Curve bindings require a compatible content track.")
            track.bindings.append(deepcopy(binding))

        self._commit(append)

    @staticmethod
    def _find_section_in(
        document: AuthoringDocumentSpec, section_id: str | None
    ) -> AuthoringSectionSpec:
        if section_id is None:
            raise ValueError("section_id is required for this object.")
        for section in document.sections:
            if section.id == section_id:
                return section
        raise KeyError(f"Unknown section {section_id!r}.")

    def _find_section(self, section_id: str | None) -> AuthoringSectionSpec:
        return self._find_section_in(self._document, section_id)

    @staticmethod
    def _find_track_in(section: AuthoringSectionSpec, track_id: str | None) -> TrackSpec:
        if track_id is None:
            raise ValueError("track_id is required for this object.")
        for track in section.tracks:
            if track.id == track_id:
                return track
        raise KeyError(f"Unknown track {track_id!r} in section {section.id!r}.")

    def _find_track(self, section: AuthoringSectionSpec, track_id: str | None) -> TrackSpec:
        return self._find_track_in(section, track_id)

    @staticmethod
    def _find_binding(track: TrackSpec, binding_id: str) -> CurveBindingSpec | RasterBindingSpec:
        for binding in getattr(track, "bindings", ()):
            if binding.binding_id == binding_id:
                return binding
        raise KeyError(f"Unknown binding {binding_id!r} in track {track.id!r}.")

    @staticmethod
    def _find_annotation(track: AnnotationTrackSpec, annotation_id: str) -> AnnotationSpec:
        for annotation in track.annotations:
            if annotation.annotation_id == annotation_id:
                return annotation
        raise KeyError(f"Unknown annotation {annotation_id!r} in track {track.id!r}.")

    @staticmethod
    def _find_fill(track: NormalTrackSpec, fill_id: str) -> CurveFillSpec:
        for fill in track.fills:
            if fill.fill_id == fill_id:
                return fill
        raise KeyError(f"Unknown fill {fill_id!r} in track {track.id!r}.")

    @staticmethod
    def _find_remark_in(document: AuthoringDocumentSpec, remark_id: str) -> AuthoringRemarkSpec:
        for remark in document.remarks:
            if remark.remark_id == remark_id:
                return remark
        raise KeyError(f"Unknown remark {remark_id!r}.")

    def _find_remark(self, remark_id: str) -> AuthoringRemarkSpec:
        return self._find_remark_in(self._document, remark_id)

    def _scoped_sections(self, section_id: str | None) -> list[AuthoringSectionSpec]:
        if section_id is None:
            return list(self._document.sections)
        return [self._find_section(section_id)]

    @staticmethod
    def _scoped_tracks(section: AuthoringSectionSpec, track_id: str | None) -> list[TrackSpec]:
        if track_id is None:
            return list(section.tracks)
        return [AuthoringService._find_track_in(section, track_id)]

    def _next_id(self, prefix: str) -> str:
        existing = {
            ref.object_id
            for kind in ("remark", "fill")
            for ref in self.list(kind)  # type: ignore[arg-type]
        }
        index = 1
        while f"{prefix}-{index}" in existing:
            index += 1
        return f"{prefix}-{index}"

    @staticmethod
    def _require_id(value: str | None, object_kind: str) -> str:
        if value is None:
            raise ValueError(f"{object_kind} has no stable identity.")
        return value


def authoring_operation_json_schema() -> dict[str, Any]:
    """Return JSON Schemas for the typed authoring operation contracts."""
    return {
        "create": TypeAdapter(CreateRequest).json_schema(),
        "update": TypeAdapter(UpdateRequest).json_schema(),
        "remove": RemoveRequest.model_json_schema(),
        "move": MoveRequest.model_json_schema(),
    }


def _hierarchy_canonical_schema(object_kind: str) -> dict[str, Any]:
    """Return the generated canonical schema for one hierarchy node."""
    model = _HIERARCHY_CANONICAL_MODELS[object_kind]
    if object_kind in {"track", "annotation"}:
        return TypeAdapter(model).json_schema()
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise TypeError(f"Unsupported canonical schema model for {object_kind!r}.")
    return model.model_json_schema()


def _resolve_schema_reference(value: object, root_schema: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve a local JSON Schema reference when one is present."""
    if not isinstance(value, Mapping):
        return {}
    reference = value.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        definition = root_schema.get("$defs", {}).get(reference.rsplit("/", 1)[-1])
        if isinstance(definition, Mapping):
            return dict(definition)
    return dict(value)


def _schema_has_enum(value: object, root_schema: Mapping[str, Any]) -> bool:
    """Return whether a JSON Schema value resolves to a finite enum."""
    schema = _resolve_schema_reference(value, root_schema)
    if "enum" in schema:
        return True
    for key in ("anyOf", "oneOf", "allOf"):
        variants = schema.get(key)
        if isinstance(variants, list) and any(
            _schema_has_enum(variant, root_schema) for variant in variants
        ):
            return True
    return False


def _hierarchy_field_category(
    object_kind: str,
    field_name: str,
    field_schema: Mapping[str, Any],
    root_schema: Mapping[str, Any],
) -> str:
    """Classify one canonical field for hierarchy discovery."""
    definition = next(
        item for item in _HIERARCHY_NODE_DEFINITIONS if item["object_kind"] == object_kind
    )
    identity_field = str(definition["identity_field"])
    if field_name == identity_field:
        return "contextual"
    if field_name in _HIERARCHY_RELATIONAL_FIELDS or field_name.endswith("_id"):
        return "relational"
    if field_name in {"channel", "source_path", "source_format"}:
        return "contextual"
    if _schema_has_enum(field_schema, root_schema):
        return "finite"
    return "constrained"


def _hierarchy_field_catalog(object_kind: str, schema: Mapping[str, Any]) -> dict[str, Any]:
    """Generate field metadata from one canonical model schema."""
    schema_views: list[tuple[str | None, Mapping[str, Any]]] = []
    properties = schema.get("properties", {})
    if isinstance(properties, Mapping) and properties:
        schema_views.append((None, schema))
    else:
        variants = schema.get("oneOf", [])
        if isinstance(variants, list):
            for variant in variants:
                if not isinstance(variant, Mapping):
                    continue
                reference = variant.get("$ref")
                variant_name = reference.rsplit("/", 1)[-1] if isinstance(reference, str) else None
                variant_schema = _resolve_schema_reference(variant, schema)
                if isinstance(variant_schema.get("properties"), Mapping):
                    schema_views.append((variant_name, variant_schema))

    fields: dict[str, Any] = {}
    field_variants: dict[str, list[tuple[str | None, Mapping[str, Any]]]] = {}
    for variant_name, variant_schema in schema_views:
        variant_properties = variant_schema.get("properties", {})
        if not isinstance(variant_properties, Mapping):
            continue
        for field_name, field_schema in variant_properties.items():
            if isinstance(field_name, str) and isinstance(field_schema, Mapping):
                field_variants.setdefault(field_name, []).append((variant_name, field_schema))

    for field_name, variants in field_variants.items():
        field_schema = variants[0][1]
        resolved = _resolve_schema_reference(field_schema, schema)
        required = any(
            field_name in set(variant_schema.get("required", []))
            for _, variant_schema in schema_views
            if isinstance(variant_schema.get("required", []), list)
        )
        constraints = {
            key: deepcopy(resolved[key])
            for key in _HIERARCHY_SCHEMA_CONSTRAINT_KEYS
            if key in resolved
        }
        fields[field_name] = {
            "category": _hierarchy_field_category(
                object_kind,
                field_name,
                field_schema,
                schema,
            ),
            "required_on_create": required,
            "schema": deepcopy(dict(field_schema)),
            "constraints": constraints,
        }
        variant_names = sorted(
            {variant_name for variant_name, _ in variants if variant_name is not None}
        )
        if variant_names:
            fields[field_name]["variants"] = variant_names
    return fields


def _hierarchy_json_value(value: object) -> object:
    """Normalize generated metadata containers to JSON-compatible values."""
    if isinstance(value, Mapping):
        return {str(key): _hierarchy_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_hierarchy_json_value(item) for item in value]
    return deepcopy(value)


def _hierarchy_operation_schema(request_type: object) -> dict[str, Any] | None:
    """Generate one typed operation schema for hierarchy discovery."""
    if request_type is None:
        return None
    if not isinstance(request_type, type) or not issubclass(request_type, BaseModel):
        raise TypeError(f"Unsupported hierarchy request model {request_type!r}.")
    return request_type.model_json_schema()


def _hierarchy_update_fields(
    object_kind: str,
    update_schema: Mapping[str, Any] | None,
) -> list[str]:
    """Return mutable payload fields from one generated update schema."""
    if update_schema is None:
        return []
    properties = update_schema.get("properties", {})
    if not isinstance(properties, Mapping):
        return []
    payload_name = "patch" if "patch" in properties else object_kind
    payload_schema = _resolve_schema_reference(properties.get(payload_name), update_schema)
    payload_properties = payload_schema.get("properties", {})
    if not isinstance(payload_properties, Mapping):
        return []
    return sorted(str(field_name) for field_name in payload_properties)


def authoring_hierarchy_catalog(object_kind: str | None = None) -> dict[str, Any]:
    """Return generated canonical hierarchy and typed operation metadata."""
    normalized_kind = object_kind.strip().lower() if object_kind is not None else None
    definitions = list(_HIERARCHY_NODE_DEFINITIONS)
    if normalized_kind is not None:
        if normalized_kind not in {str(item["object_kind"]) for item in definitions}:
            allowed = sorted(str(item["object_kind"]) for item in definitions)
            raise ValueError(
                f"Unsupported authoring object kind {object_kind!r}. Allowed kinds: {allowed}."
            )
        definitions = [item for item in definitions if item["object_kind"] == normalized_kind]

    nodes: list[dict[str, Any]] = []
    for definition in definitions:
        kind = str(definition["object_kind"])
        canonical_schema = _hierarchy_canonical_schema(kind)
        operation_schemas: dict[str, Any] = {}
        for operation in definition["operations"]:
            request_key = f"{operation}_request"
            request_type = definition.get(request_key)
            if operation in {"create", "update"}:
                schema = _hierarchy_operation_schema(request_type)
            elif operation == "remove":
                schema = RemoveRequest.model_json_schema()
            elif operation == "move":
                schema = MoveRequest.model_json_schema()
            else:
                schema = None
            if schema is not None:
                operation_schemas[operation] = schema

        parent_kind = definition["parent_kind"]
        parent = None
        if parent_kind is not None:
            parent = {
                "object_kind": parent_kind,
                "fields": list(definition["parent_fields"]),
            }
        nodes.append(
            {
                "object_kind": kind,
                "canonical_contract": definition["canonical_contract"],
                "canonical_schema": canonical_schema,
                "identity": {
                    "field": definition["identity_field"],
                    "scope": list(definition["parent_fields"]),
                },
                "parent": parent,
                "children": list(definition["children"]),
                "operations": list(definition["operations"]),
                "operation_schemas": operation_schemas,
                "mutable_on_update": _hierarchy_update_fields(
                    kind,
                    operation_schemas.get("update"),
                ),
                "verification": {
                    "operation": "get",
                    "object_kind": kind,
                },
                "fields": _hierarchy_field_catalog(kind, canonical_schema),
                "constraints": _hierarchy_json_value(definition.get("constraints", {})),
            }
        )

    return {
        "schema_version": 1,
        "root_object_kind": "report",
        "object_kind": normalized_kind,
        "nodes": nodes,
        "precedence": [
            "explicit_user_value",
            "preserved_existing_state",
            "specific_defaults",
            "generic_form_defaults",
            "starter_scaffold",
        ],
    }


__all__ = [
    "AuthoringObjectKind",
    "AuthoringObjectRef",
    "AuthoringService",
    "AuthoringStylePatch",
    "AuthoringTarget",
    "AuthoringValidationResult",
    "HeaderValuePatch",
    "ServiceTitlePatch",
    "CreateAnnotationRequest",
    "CreateCurveBindingRequest",
    "CreateFillRequest",
    "CreateRasterBindingRequest",
    "CreateRemarkRequest",
    "CreateRequest",
    "CreateSectionRequest",
    "CreateTrackRequest",
    "CurveBindingPatch",
    "DepthPatch",
    "MoveRequest",
    "PagePatch",
    "RasterBindingPatch",
    "ReportPatch",
    "ReferenceTrackPatch",
    "RemoveRequest",
    "RemarkPatch",
    "SectionPatch",
    "TrackPatch",
    "UpdateAnnotationRequest",
    "UpdateCurveBindingRequest",
    "UpdateDepthRequest",
    "UpdateFillRequest",
    "UpdateHeaderRequest",
    "UpdateHeaderSlotRequest",
    "UpdateOutputRequest",
    "UpdatePageRequest",
    "UpdateReportRequest",
    "UpdateRasterBindingRequest",
    "UpdateRemarkRequest",
    "UpdateRequest",
    "UpdateSectionRequest",
    "UpdateServiceTitleRequest",
    "UpdateTailRequest",
    "UpdateTrackRequest",
    "authoring_hierarchy_catalog",
    "authoring_operation_json_schema",
]
