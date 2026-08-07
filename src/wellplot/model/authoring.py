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

"""Canonical typed authoring models.

These models define report intent at the public authoring boundary. They are
currently introduced alongside the existing logfile mappings and renderer
dataclasses; adapters will connect those layers in a later implementation
slice.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AuthoringScaleKind(StrEnum):
    """Scale transforms exposed by the authoring contract."""

    LINEAR = "linear"
    LOG = "log"
    TANGENTIAL = "tangential"


class AuthoringRasterProfileKind(StrEnum):
    """Raster presentation profiles exposed by the authoring contract."""

    GENERIC = "generic"
    VDL = "vdl"
    WAVEFORM = "waveform"


class AuthoringRasterNormalizationKind(StrEnum):
    """Raster amplitude normalization modes."""

    AUTO = "auto"
    NONE = "none"
    TRACE_MAXABS = "trace_maxabs"
    GLOBAL_MAXABS = "global_maxabs"


class AuthoringReferenceAxisKind(StrEnum):
    """Reference-axis kinds exposed by the authoring contract."""

    DEPTH = "depth"
    TIME = "time"


class AuthoringCurveFillKind(StrEnum):
    """Curve fill semantics exposed by the authoring contract."""

    BETWEEN_CURVES = "between_curves"
    BETWEEN_INSTANCES = "between_instances"
    TO_LOWER_LIMIT = "to_lower_limit"
    TO_UPPER_LIMIT = "to_upper_limit"
    BASELINE_SPLIT = "baseline_split"


class _AuthoringModel(BaseModel):
    """Base configuration shared by canonical authoring models."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class AuthoringStyle(_AuthoringModel):
    """Style properties for a rendered curve or overlay."""

    color: str | None = Field(default=None, min_length=1)
    line_style: str = Field(default="-", min_length=1)
    line_width: float = Field(default=0.8, gt=0)
    alpha: float = Field(default=1.0, ge=0, le=1)
    fill_color: str | None = Field(default=None, min_length=1)
    fill_alpha: float = Field(default=0.2, ge=0, le=1)
    colormap: str = Field(default="viridis", min_length=1)


class AuthoringScale(_AuthoringModel):
    """Validated numeric scale for a track or scalar curve binding."""

    kind: AuthoringScaleKind = AuthoringScaleKind.LINEAR
    minimum: float
    maximum: float
    reverse: bool = False
    unit: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> AuthoringScale:
        """Require distinct bounds and positive bounds for logarithmic scales."""
        if self.maximum == self.minimum:
            raise ValueError("Scale minimum and maximum must differ.")
        if self.kind == AuthoringScaleKind.LOG and self.minimum <= 0:
            raise ValueError("Logarithmic scales require a positive minimum.")
        if self.kind == AuthoringScaleKind.LOG and self.maximum <= 0:
            raise ValueError("Logarithmic scales require a positive maximum.")
        return self


class AuthoringDataSource(_AuthoringModel):
    """File-backed data source assigned to a section."""

    source_path: str = Field(min_length=1)
    source_format: Literal["auto", "las", "dlis"] = "auto"


class CurveBindingSpec(_AuthoringModel):
    """One scalar channel binding with stable instance identity."""

    kind: Literal["curve"] = "curve"
    binding_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    label: str | None = Field(default=None, min_length=1)
    scale: AuthoringScale | None = None
    style: AuthoringStyle = Field(default_factory=AuthoringStyle)
    extensions: dict[str, Any] = Field(default_factory=dict)


class RasterBindingSpec(_AuthoringModel):
    """One array or raster channel binding."""

    kind: Literal["raster"] = "raster"
    binding_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    label: str | None = Field(default=None, min_length=1)
    style: AuthoringStyle = Field(default_factory=AuthoringStyle)
    profile: AuthoringRasterProfileKind = AuthoringRasterProfileKind.GENERIC
    normalization: AuthoringRasterNormalizationKind = AuthoringRasterNormalizationKind.AUTO
    alpha: float = Field(default=1.0, ge=0, le=1)
    extensions: dict[str, Any] = Field(default_factory=dict)


BindingSpec: TypeAlias = Annotated[
    CurveBindingSpec | RasterBindingSpec,
    Field(discriminator="kind"),
]


class CurveFillSpec(_AuthoringModel):
    """Fill relation between curve binding instances."""

    kind: AuthoringCurveFillKind
    binding_id: str = Field(min_length=1)
    other_binding_id: str | None = Field(default=None, min_length=1)
    baseline: float | None = None

    @model_validator(mode="after")
    def validate_targets(self) -> CurveFillSpec:
        """Require the target fields implied by the selected fill kind."""
        if (
            self.kind
            in {
                AuthoringCurveFillKind.BETWEEN_CURVES,
                AuthoringCurveFillKind.BETWEEN_INSTANCES,
            }
            and self.other_binding_id is None
        ):
            raise ValueError(f"Fill kind {self.kind} requires other_binding_id.")
        if self.kind == AuthoringCurveFillKind.BASELINE_SPLIT and self.baseline is None:
            raise ValueError("Baseline-split fills require baseline.")
        return self


class AnnotationIntervalSpec(_AuthoringModel):
    """Interval annotation occupying a depth range."""

    kind: Literal["interval"] = "interval"
    annotation_id: str = Field(min_length=1)
    top: float
    base: float
    text: str = ""

    @model_validator(mode="after")
    def validate_range(self) -> AnnotationIntervalSpec:
        """Require the interval base to be deeper than its top."""
        if self.base <= self.top:
            raise ValueError("Annotation interval base must be greater than top.")
        return self


class AnnotationTextSpec(_AuthoringModel):
    """Free-form text annotation anchored at a depth."""

    kind: Literal["text"] = "text"
    annotation_id: str = Field(min_length=1)
    depth: float
    text: str = Field(min_length=1)


class AnnotationMarkerSpec(_AuthoringModel):
    """Marker annotation anchored at a depth."""

    kind: Literal["marker"] = "marker"
    annotation_id: str = Field(min_length=1)
    depth: float
    shape: str = Field(default="circle", min_length=1)
    label: str | None = Field(default=None, min_length=1)


class AnnotationArrowSpec(_AuthoringModel):
    """Arrow annotation spanning a depth range."""

    kind: Literal["arrow"] = "arrow"
    annotation_id: str = Field(min_length=1)
    top: float
    base: float
    label: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_range(self) -> AnnotationArrowSpec:
        """Require the arrow base to be deeper than its top."""
        if self.base <= self.top:
            raise ValueError("Annotation arrow base must be greater than top.")
        return self


class AnnotationGlyphSpec(_AuthoringModel):
    """Glyph annotation anchored at a depth."""

    kind: Literal["glyph"] = "glyph"
    annotation_id: str = Field(min_length=1)
    depth: float
    glyph: str = Field(min_length=1)


AnnotationSpec: TypeAlias = Annotated[
    AnnotationIntervalSpec
    | AnnotationTextSpec
    | AnnotationMarkerSpec
    | AnnotationArrowSpec
    | AnnotationGlyphSpec,
    Field(discriminator="kind"),
]


class _TrackSpec(_AuthoringModel):
    """Shared form properties for all canonical track kinds."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    width_mm: float = Field(gt=0)
    extensions: dict[str, Any] = Field(default_factory=dict)


class NormalTrackSpec(_TrackSpec):
    """Normal curve track."""

    kind: Literal["normal"] = "normal"
    x_scale: AuthoringScale | None = None
    bindings: list[CurveBindingSpec] = Field(default_factory=list)
    fills: list[CurveFillSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fill_targets(self) -> NormalTrackSpec:
        """Require fills to reference binding instances on this track."""
        binding_ids = {binding.binding_id for binding in self.bindings}
        if len(binding_ids) != len(self.bindings):
            raise ValueError(f"Track {self.id} contains duplicate binding ids.")
        for fill in self.fills:
            targets = {fill.binding_id}
            if fill.other_binding_id is not None:
                targets.add(fill.other_binding_id)
            missing = sorted(targets - binding_ids)
            if missing:
                raise ValueError(f"Track {self.id} fill references missing binding ids: {missing}.")
        return self


class ReferenceTrackSpec(_TrackSpec):
    """Reference/depth/time track containing scalar curve bindings."""

    kind: Literal["reference"] = "reference"
    axis: AuthoringReferenceAxisKind = AuthoringReferenceAxisKind.DEPTH
    bindings: list[CurveBindingSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_binding_ids(self) -> ReferenceTrackSpec:
        """Require unique binding identities within this track."""
        _ensure_unique_binding_ids(self.bindings, self.id)
        return self


class ArrayTrackSpec(_TrackSpec):
    """Array track containing raster bindings and supported curve overlays."""

    kind: Literal["array"] = "array"
    bindings: list[BindingSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_binding_ids(self) -> ArrayTrackSpec:
        """Require unique binding identities within this track."""
        _ensure_unique_binding_ids(self.bindings, self.id)
        return self


class AnnotationTrackSpec(_TrackSpec):
    """Annotation track containing typed annotation objects."""

    kind: Literal["annotation"] = "annotation"
    annotations: list[AnnotationSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_annotation_ids(self) -> AnnotationTrackSpec:
        """Require unique annotation identities within this track."""
        annotation_ids = [annotation.annotation_id for annotation in self.annotations]
        if len(set(annotation_ids)) != len(annotation_ids):
            raise ValueError(f"Track {self.id} contains duplicate annotation ids.")
        return self


TrackSpec: TypeAlias = Annotated[
    NormalTrackSpec | ReferenceTrackSpec | ArrayTrackSpec | AnnotationTrackSpec,
    Field(discriminator="kind"),
]


class AuthoringPageSpec(_AuthoringModel):
    """Page settings used by the report authoring contract."""

    size: str | None = Field(default="letter", min_length=1)
    width_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)
    orientation: Literal["portrait", "landscape"] = "portrait"
    continuous: bool = False
    bottom_track_header_enabled: bool = True
    margin_left_mm: float = Field(default=0.0, ge=0)
    margin_right_mm: float = Field(default=10.0, ge=0)
    margin_top_mm: float = Field(default=10.0, ge=0)
    margin_bottom_mm: float = Field(default=10.0, ge=0)
    header_height_mm: float = Field(default=18.0, ge=0)
    track_header_height_mm: float = Field(default=8.0, ge=0)
    footer_height_mm: float = Field(default=10.0, ge=0)
    track_gap_mm: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def validate_dimensions(self) -> AuthoringPageSpec:
        """Require a named size or both explicit physical dimensions."""
        if self.size is None and (self.width_mm is None or self.height_mm is None):
            raise ValueError("Page requires size or both width_mm and height_mm.")
        return self


class AuthoringDepthSpec(_AuthoringModel):
    """Depth-axis settings shared by report sections."""

    unit: str = Field(default="ft", min_length=1)
    scale: str | float = "1:240"
    major_step: float | None = Field(default=None, gt=0)
    minor_step: float | None = Field(default=None, gt=0)


class AuthoringRemarkSpec(_AuthoringModel):
    """Simple report remark block."""

    title: str | None = Field(default=None, min_length=1)
    text: str | None = None
    lines: list[str] = Field(default_factory=list)
    alignment: Literal["left", "center", "right"] = "left"
    font_size: float | None = Field(default=None, gt=0)
    title_font_size: float | None = Field(default=None, gt=0)
    border: bool | None = None

    @model_validator(mode="after")
    def validate_content(self) -> AuthoringRemarkSpec:
        """Require either text or at least one line."""
        if self.text is None and not self.lines:
            raise ValueError("Remark requires text or at least one line.")
        return self


class AuthoringSectionSpec(_AuthoringModel):
    """Report section containing tracks and section-local source routing."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    subtitle: str | None = Field(default=None, min_length=1)
    depth_range: tuple[float, float] | None = None
    data_source: AuthoringDataSource | None = None
    tracks: list[TrackSpec] = Field(min_length=1)
    extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_section(self) -> AuthoringSectionSpec:
        """Require unique track ids and an ordered depth range."""
        track_ids = [track.id for track in self.tracks]
        if len(set(track_ids)) != len(track_ids):
            raise ValueError(f"Section {self.id} contains duplicate track ids.")
        if self.depth_range is not None and self.depth_range[1] <= self.depth_range[0]:
            raise ValueError("Section depth_range must be ordered from top to base.")
        return self


class AuthoringDocumentSpec(_AuthoringModel):
    """Root canonical authoring object for a multi-section report."""

    name: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    subtitle: str | None = Field(default=None, min_length=1)
    page: AuthoringPageSpec = Field(default_factory=AuthoringPageSpec)
    depth: AuthoringDepthSpec = Field(default_factory=AuthoringDepthSpec)
    sections: list[AuthoringSectionSpec] = Field(min_length=1)
    remarks: list[AuthoringRemarkSpec] = Field(default_factory=list)
    extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_document_references(self) -> AuthoringDocumentSpec:
        """Require unique section ids and binding ids across the document."""
        section_ids = [section.id for section in self.sections]
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("Document contains duplicate section ids.")

        binding_ids: list[str] = []
        for section in self.sections:
            for track in section.tracks:
                bindings = getattr(track, "bindings", ())
                binding_ids.extend(binding.binding_id for binding in bindings)
        if len(set(binding_ids)) != len(binding_ids):
            raise ValueError("Document contains duplicate binding ids.")
        return self


def _ensure_unique_binding_ids(bindings: list[BindingSpec], track_id: str) -> None:
    """Reject duplicate binding identities within one track."""
    binding_ids = [binding.binding_id for binding in bindings]
    if len(set(binding_ids)) != len(binding_ids):
        raise ValueError(f"Track {track_id} contains duplicate binding ids.")


def authoring_json_schema() -> dict[str, Any]:
    """Return the generated JSON Schema for the canonical document contract."""
    return AuthoringDocumentSpec.model_json_schema()


__all__ = [
    "AnnotationArrowSpec",
    "AnnotationGlyphSpec",
    "AnnotationIntervalSpec",
    "AnnotationMarkerSpec",
    "AnnotationSpec",
    "AnnotationTextSpec",
    "ArrayTrackSpec",
    "AuthoringCurveFillKind",
    "AuthoringDataSource",
    "AuthoringDepthSpec",
    "AuthoringDocumentSpec",
    "AuthoringPageSpec",
    "AuthoringRasterNormalizationKind",
    "AuthoringRasterProfileKind",
    "AuthoringReferenceAxisKind",
    "AuthoringRemarkSpec",
    "AuthoringScale",
    "AuthoringScaleKind",
    "AuthoringSectionSpec",
    "AuthoringStyle",
    "BindingSpec",
    "CurveBindingSpec",
    "CurveFillSpec",
    "NormalTrackSpec",
    "RasterBindingSpec",
    "ReferenceTrackSpec",
    "TrackSpec",
    "AnnotationTrackSpec",
    "authoring_json_schema",
]
