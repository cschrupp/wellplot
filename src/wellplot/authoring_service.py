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
    AuthoringDataSource,
    AuthoringDepthSpec,
    AuthoringDocumentSpec,
    AuthoringGridPatch,
    AuthoringGridSpec,
    AuthoringPageSpec,
    AuthoringRasterNormalizationKind,
    AuthoringRasterProfileKind,
    AuthoringRemarkSpec,
    AuthoringScale,
    AuthoringSectionSpec,
    AuthoringStyle,
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
    "page",
    "depth",
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


class TrackPatch(_OperationModel):
    """Typed mutable fields for one track."""

    title: str | None = None
    width_mm: float | None = Field(default=None, gt=0)
    x_scale: AuthoringScale | None = None
    grid: AuthoringGridPatch | None = None
    track_header: AuthoringTrackHeaderPatch | None = None
    extensions: dict[str, Any] | None = None


class CurveBindingPatch(_OperationModel):
    """Typed mutable fields for one scalar binding."""

    label: str | None = None
    scale: AuthoringScale | None = None
    style: AuthoringStylePatch | None = None
    extensions: dict[str, Any] | None = None


class RasterBindingPatch(_OperationModel):
    """Typed mutable fields for one raster binding."""

    label: str | None = None
    style: AuthoringStylePatch | None = None
    profile: AuthoringRasterProfileKind | None = None
    normalization: AuthoringRasterNormalizationKind | None = None
    alpha: float | None = Field(default=None, ge=0, le=1)
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
    UpdatePageRequest
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
    AuthoringPageSpec
    | AuthoringDepthSpec
    | AuthoringSectionSpec
    | TrackSpec
    | CurveBindingSpec
    | RasterBindingSpec
    | AnnotationSpec
    | CurveFillSpec
    | AuthoringRemarkSpec
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
        if object_kind in {"page", "depth"}:
            return [
                AuthoringObjectRef(
                    object_kind=object_kind,
                    object_id=object_kind,
                    index=0,
                )
            ]
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
        if target.object_kind == "page":
            return deepcopy(self._document.page)
        if target.object_kind == "depth":
            return deepcopy(self._document.depth)
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
        if isinstance(request, UpdatePageRequest):
            self._commit(lambda document: self._patch_model(document.page, request.patch))
            return self.get(AuthoringTarget(object_kind="page", object_id="page"))
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
        if request.target.object_kind in {"page", "depth"}:
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
    def _patch_track(track: TrackSpec, patch: TrackPatch) -> None:
        """Apply track fields while merging partial canonical grid updates."""
        for field_name in patch.model_fields_set:
            value = getattr(patch, field_name)
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


__all__ = [
    "AuthoringObjectKind",
    "AuthoringObjectRef",
    "AuthoringService",
    "AuthoringStylePatch",
    "AuthoringTarget",
    "AuthoringValidationResult",
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
    "RemoveRequest",
    "RemarkPatch",
    "SectionPatch",
    "TrackPatch",
    "UpdateAnnotationRequest",
    "UpdateCurveBindingRequest",
    "UpdateDepthRequest",
    "UpdateFillRequest",
    "UpdatePageRequest",
    "UpdateRasterBindingRequest",
    "UpdateRemarkRequest",
    "UpdateRequest",
    "UpdateSectionRequest",
    "UpdateTrackRequest",
    "authoring_operation_json_schema",
]
