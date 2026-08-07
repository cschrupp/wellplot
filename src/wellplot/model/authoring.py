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
used by the YAML/render compatibility adapters and the deterministic
authoring service, while the existing renderer dataclasses remain internal
render-layer representations.
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


class AuthoringRasterColorbarPosition(StrEnum):
    """Supported positions for raster colorbars."""

    RIGHT = "right"
    HEADER = "header"


class AuthoringReferenceAxisKind(StrEnum):
    """Reference-axis kinds exposed by the authoring contract."""

    DEPTH = "depth"
    TIME = "time"


class AuthoringGridDisplayMode(StrEnum):
    """Layer ordering options for one track grid."""

    BELOW = "below"
    ABOVE = "above"
    NONE = "none"


class AuthoringGridScaleKind(StrEnum):
    """Scale transforms used to place vertical grid lines."""

    LINEAR = "linear"
    LOGARITHMIC = "logarithmic"
    TANGENTIAL = "tangential"


class AuthoringGridSpacingMode(StrEnum):
    """Strategies for spacing vertical grid lines."""

    COUNT = "count"
    SCALE = "scale"


class AuthoringTrackHeaderObjectKind(StrEnum):
    """Logical rows available in a track header."""

    TITLE = "title"
    SCALE = "scale"
    LEGEND = "legend"
    DIVISIONS = "divisions"


class AuthoringAnnotationLabelMode(StrEnum):
    """Placement strategies for annotation labels."""

    NONE = "none"
    FREE = "free"
    DEDICATED_LANE = "dedicated_lane"


class AuthoringAnnotationMarkerShape(StrEnum):
    """Supported marker glyphs for annotation objects."""

    CIRCLE = "circle"
    SQUARE = "square"
    DIAMOND = "diamond"
    TRIANGLE_UP = "triangle_up"
    TRIANGLE_DOWN = "triangle_down"
    TRIANGLE_LEFT = "triangle_left"
    TRIANGLE_RIGHT = "triangle_right"
    X = "x"
    PLUS = "plus"
    BAR_HORIZONTAL = "bar_horizontal"
    BAR_VERTICAL = "bar_vertical"


class AuthoringReferenceOverlayMode(StrEnum):
    """Display modes for a curve overlaid on a reference track."""

    CURVE = "curve"
    INDICATOR = "indicator"
    TICKS = "ticks"


class AuthoringReferenceTickSide(StrEnum):
    """Sides on which reference overlay ticks may be drawn."""

    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"


class AuthoringNumberFormatKind(StrEnum):
    """Numeric formatting modes for curve labels."""

    AUTOMATIC = "automatic"
    FIXED = "fixed"
    SCIENTIFIC = "scientific"
    CONCISE = "concise"


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


class AuthoringRasterColorbarSpec(_AuthoringModel):
    """Colorbar settings for one raster binding."""

    enabled: bool = False
    label: str | None = Field(default=None, min_length=1)
    position: AuthoringRasterColorbarPosition = AuthoringRasterColorbarPosition.RIGHT


class AuthoringRasterColorbarPatch(_AuthoringModel):
    """Optional colorbar fields used by a partial raster update."""

    enabled: bool | None = None
    label: str | None = Field(default=None, min_length=1)
    position: AuthoringRasterColorbarPosition | None = None


class AuthoringRasterSampleAxisSpec(_AuthoringModel):
    """Sample-axis settings for one raster binding."""

    enabled: bool = False
    label: str | None = Field(default=None, min_length=1)
    unit: str | None = Field(default=None, min_length=1)
    source_origin: float | None = None
    source_step: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    tick_count: int = Field(default=5, ge=2)

    @model_validator(mode="after")
    def validate_axis_bounds(self) -> AuthoringRasterSampleAxisSpec:
        """Require paired source and display bounds."""
        if (self.source_origin is None) != (self.source_step is None):
            raise ValueError("Sample-axis source_origin and source_step must be set together.")
        if self.source_step is not None and self.source_step == 0:
            raise ValueError("Sample-axis source_step must be non-zero.")
        if (self.minimum is None) != (self.maximum is None):
            raise ValueError("Sample-axis minimum and maximum must be set together.")
        if self.minimum is not None and self.minimum == self.maximum:
            raise ValueError("Sample-axis minimum and maximum must differ.")
        return self


class AuthoringRasterSampleAxisPatch(_AuthoringModel):
    """Optional sample-axis fields used by a partial raster update."""

    enabled: bool | None = None
    label: str | None = Field(default=None, min_length=1)
    unit: str | None = Field(default=None, min_length=1)
    source_origin: float | None = None
    source_step: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    tick_count: int | None = Field(default=None, ge=2)


class AuthoringRasterWaveformSpec(_AuthoringModel):
    """Waveform overlay settings for one raster binding."""

    enabled: bool = False
    stride: int = Field(default=1, ge=1)
    amplitude_scale: float = Field(default=0.35, gt=0)
    color: str = Field(default="#5b3f8c", min_length=1)
    line_width: float = Field(default=0.3, gt=0)
    fill: bool = True
    positive_fill_color: str = Field(default="#000000", min_length=1)
    negative_fill_color: str = Field(default="#ffffff", min_length=1)
    invert_fill_polarity: bool = False
    max_traces: int | None = Field(default=None, gt=0)


class AuthoringRasterWaveformPatch(_AuthoringModel):
    """Optional waveform fields used by a partial raster update."""

    enabled: bool | None = None
    stride: int | None = Field(default=None, ge=1)
    amplitude_scale: float | None = Field(default=None, gt=0)
    color: str | None = Field(default=None, min_length=1)
    line_width: float | None = Field(default=None, gt=0)
    fill: bool | None = None
    positive_fill_color: str | None = Field(default=None, min_length=1)
    negative_fill_color: str | None = Field(default=None, min_length=1)
    invert_fill_polarity: bool | None = None
    max_traces: int | None = Field(default=None, gt=0)


class AuthoringGridSpec(_AuthoringModel):
    """Validated grid properties for one track."""

    display: AuthoringGridDisplayMode = AuthoringGridDisplayMode.BELOW
    major: bool = True
    minor: bool = True
    major_alpha: float = Field(default=0.35, ge=0, le=1)
    minor_alpha: float = Field(default=0.15, ge=0, le=1)
    horizontal_display: AuthoringGridDisplayMode = AuthoringGridDisplayMode.BELOW
    horizontal_major_visible: bool = True
    horizontal_minor_visible: bool = True
    horizontal_major_color: str | None = Field(default=None, min_length=1)
    horizontal_minor_color: str | None = Field(default=None, min_length=1)
    horizontal_major_thickness: float | None = Field(default=None, gt=0)
    horizontal_minor_thickness: float | None = Field(default=None, gt=0)
    horizontal_major_alpha: float | None = Field(default=None, ge=0, le=1)
    horizontal_minor_alpha: float | None = Field(default=None, ge=0, le=1)
    vertical_display: AuthoringGridDisplayMode = AuthoringGridDisplayMode.BELOW
    vertical_main_visible: bool = True
    vertical_main_line_count: int = Field(default=4, ge=1)
    vertical_main_thickness: float | None = Field(default=None, gt=0)
    vertical_main_color: str | None = Field(default=None, min_length=1)
    vertical_main_alpha: float = Field(default=0.35, ge=0, le=1)
    vertical_main_scale: AuthoringGridScaleKind = AuthoringGridScaleKind.LINEAR
    vertical_main_spacing_mode: AuthoringGridSpacingMode = AuthoringGridSpacingMode.COUNT
    vertical_secondary_visible: bool = True
    vertical_secondary_line_count: int = Field(default=4, ge=1)
    vertical_secondary_thickness: float | None = Field(default=None, gt=0)
    vertical_secondary_color: str | None = Field(default=None, min_length=1)
    vertical_secondary_alpha: float = Field(default=0.15, ge=0, le=1)
    vertical_secondary_scale: AuthoringGridScaleKind = AuthoringGridScaleKind.LINEAR
    vertical_secondary_spacing_mode: AuthoringGridSpacingMode = AuthoringGridSpacingMode.COUNT


class AuthoringGridPatch(_AuthoringModel):
    """Optional grid fields used by a partial track update."""

    display: AuthoringGridDisplayMode | None = None
    major: bool | None = None
    minor: bool | None = None
    major_alpha: float | None = Field(default=None, ge=0, le=1)
    minor_alpha: float | None = Field(default=None, ge=0, le=1)
    horizontal_display: AuthoringGridDisplayMode | None = None
    horizontal_major_visible: bool | None = None
    horizontal_minor_visible: bool | None = None
    horizontal_major_color: str | None = Field(default=None, min_length=1)
    horizontal_minor_color: str | None = Field(default=None, min_length=1)
    horizontal_major_thickness: float | None = Field(default=None, gt=0)
    horizontal_minor_thickness: float | None = Field(default=None, gt=0)
    horizontal_major_alpha: float | None = Field(default=None, ge=0, le=1)
    horizontal_minor_alpha: float | None = Field(default=None, ge=0, le=1)
    vertical_display: AuthoringGridDisplayMode | None = None
    vertical_main_visible: bool | None = None
    vertical_main_line_count: int | None = Field(default=None, ge=1)
    vertical_main_thickness: float | None = Field(default=None, gt=0)
    vertical_main_color: str | None = Field(default=None, min_length=1)
    vertical_main_alpha: float | None = Field(default=None, ge=0, le=1)
    vertical_main_scale: AuthoringGridScaleKind | None = None
    vertical_main_spacing_mode: AuthoringGridSpacingMode | None = None
    vertical_secondary_visible: bool | None = None
    vertical_secondary_line_count: int | None = Field(default=None, ge=1)
    vertical_secondary_thickness: float | None = Field(default=None, gt=0)
    vertical_secondary_color: str | None = Field(default=None, min_length=1)
    vertical_secondary_alpha: float | None = Field(default=None, ge=0, le=1)
    vertical_secondary_scale: AuthoringGridScaleKind | None = None
    vertical_secondary_spacing_mode: AuthoringGridSpacingMode | None = None


class AuthoringTrackHeaderObjectSpec(_AuthoringModel):
    """One validated row reservation within a track header."""

    kind: AuthoringTrackHeaderObjectKind
    enabled: bool = True
    reserve_space: bool = True
    line_units: int = Field(default=1, ge=1)


def _default_authoring_track_header_objects() -> list[AuthoringTrackHeaderObjectSpec]:
    """Return the standard ordered rows for a track header."""
    return [
        AuthoringTrackHeaderObjectSpec(
            kind=AuthoringTrackHeaderObjectKind.TITLE,
            line_units=1,
        ),
        AuthoringTrackHeaderObjectSpec(
            kind=AuthoringTrackHeaderObjectKind.SCALE,
            line_units=1,
        ),
        AuthoringTrackHeaderObjectSpec(
            kind=AuthoringTrackHeaderObjectKind.LEGEND,
            line_units=2,
        ),
        AuthoringTrackHeaderObjectSpec(
            kind=AuthoringTrackHeaderObjectKind.DIVISIONS,
            enabled=False,
            reserve_space=False,
            line_units=1,
        ),
    ]


class AuthoringTrackHeaderSpec(_AuthoringModel):
    """Ordered track-header rows and their reserved vertical space."""

    objects: list[AuthoringTrackHeaderObjectSpec] = Field(
        default_factory=_default_authoring_track_header_objects,
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_object_kinds(self) -> AuthoringTrackHeaderSpec:
        """Require one entry for each logical header row kind."""
        kinds = [item.kind for item in self.objects]
        if len(set(kinds)) != len(kinds):
            raise ValueError("Track header object kinds must be unique per track.")
        return self


class AuthoringTrackHeaderPatch(_AuthoringModel):
    """Optional track-header replacement used by a partial track update."""

    objects: list[AuthoringTrackHeaderObjectSpec] | None = None


class AuthoringReferenceOverlaySpec(_AuthoringModel):
    """Validated overlay properties for a reference-track curve binding."""

    mode: AuthoringReferenceOverlayMode = AuthoringReferenceOverlayMode.CURVE
    lane_start: float | None = Field(default=None, ge=0, le=1)
    lane_end: float | None = Field(default=None, ge=0, le=1)
    tick_side: AuthoringReferenceTickSide = AuthoringReferenceTickSide.BOTH
    tick_length_ratio: float | None = Field(default=None, gt=0)
    threshold: float | None = None

    @model_validator(mode="after")
    def validate_lane(self) -> AuthoringReferenceOverlaySpec:
        """Require paired and ordered normalized overlay lane bounds."""
        if (self.lane_start is None) != (self.lane_end is None):
            raise ValueError("Reference overlay lane_start and lane_end must be set together.")
        if (
            self.lane_start is not None
            and self.lane_end is not None
            and self.lane_start >= self.lane_end
        ):
            raise ValueError("Reference overlay lane_start must be less than lane_end.")
        return self


class AuthoringCurveHeaderDisplaySpec(_AuthoringModel):
    """Visibility controls for scalar curve header fields."""

    show_name: bool = True
    show_unit: bool = True
    show_limits: bool = True
    show_color: bool = True
    wrap_name: bool = False


class AuthoringCurveHeaderDisplayPatch(_AuthoringModel):
    """Optional curve-header visibility fields used by binding updates."""

    show_name: bool | None = None
    show_unit: bool | None = None
    show_limits: bool | None = None
    show_color: bool | None = None
    wrap_name: bool | None = None


class AuthoringCurveValueLabelsSpec(_AuthoringModel):
    """Validated in-track value-label rendering settings."""

    step: float = Field(default=5.0, gt=0)
    format: AuthoringNumberFormatKind = AuthoringNumberFormatKind.AUTOMATIC
    precision: int = Field(default=2, ge=0)
    color: str | None = Field(default=None, min_length=1)
    font_size: float = Field(default=5.5, gt=0)
    font_family: str | None = Field(default=None, min_length=1)
    font_weight: str = Field(default="normal", min_length=1)
    font_style: str = Field(default="normal", min_length=1)
    horizontal_alignment: Literal["left", "center", "right"] = "center"
    vertical_alignment: Literal["top", "center", "bottom"] = "center"


class AuthoringCurveValueLabelsPatch(_AuthoringModel):
    """Optional value-label fields used by binding updates."""

    step: float | None = Field(default=None, gt=0)
    format: AuthoringNumberFormatKind | None = None
    precision: int | None = Field(default=None, ge=0)
    color: str | None = Field(default=None, min_length=1)
    font_size: float | None = Field(default=None, gt=0)
    font_family: str | None = Field(default=None, min_length=1)
    font_weight: str | None = Field(default=None, min_length=1)
    font_style: str | None = Field(default=None, min_length=1)
    horizontal_alignment: Literal["left", "center", "right"] | None = None
    vertical_alignment: Literal["top", "center", "bottom"] | None = None


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
    reference_overlay: AuthoringReferenceOverlaySpec | None = None
    wrap: bool = False
    render_mode: Literal["line", "value_labels"] = "line"
    value_labels: AuthoringCurveValueLabelsSpec = Field(
        default_factory=AuthoringCurveValueLabelsSpec
    )
    header_display: AuthoringCurveHeaderDisplaySpec = Field(
        default_factory=AuthoringCurveHeaderDisplaySpec
    )
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
    waveform_normalization: AuthoringRasterNormalizationKind = AuthoringRasterNormalizationKind.AUTO
    clip_percentiles: tuple[float, float] | None = None
    interpolation: str = Field(default="nearest", min_length=1)
    show_raster: bool = True
    alpha: float = Field(default=1.0, ge=0, le=1)
    color_limits: tuple[float, float] | None = None
    colorbar: AuthoringRasterColorbarSpec = Field(default_factory=AuthoringRasterColorbarSpec)
    sample_axis: AuthoringRasterSampleAxisSpec = Field(
        default_factory=AuthoringRasterSampleAxisSpec
    )
    waveform: AuthoringRasterWaveformSpec = Field(default_factory=AuthoringRasterWaveformSpec)
    extensions: dict[str, Any] = Field(default_factory=dict)


BindingSpec: TypeAlias = Annotated[
    CurveBindingSpec | RasterBindingSpec,
    Field(discriminator="kind"),
]


class CurveFillSpec(_AuthoringModel):
    """Fill relation between curve binding instances."""

    kind: AuthoringCurveFillKind
    fill_id: str | None = Field(default=None, min_length=1)
    binding_id: str = Field(min_length=1)
    other_binding_id: str | None = Field(default=None, min_length=1)
    baseline: float | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)

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
    lane_start: float = Field(default=0.0, ge=0, lt=1)
    lane_end: float = Field(default=1.0, gt=0, le=1)
    fill_color: str = Field(default="#d9d9d9", min_length=1)
    fill_alpha: float = Field(default=1.0, ge=0, le=1)
    border_color: str = Field(default="#222222", min_length=1)
    border_linewidth: float = Field(default=0.6, gt=0)
    border_style: str = Field(default="-", min_length=1)
    text_color: str = Field(default="#111111", min_length=1)
    text_orientation: Literal["horizontal", "vertical"] = "horizontal"
    text_wrap: bool = True
    horizontal_alignment: Literal["left", "center", "right"] = "center"
    vertical_alignment: Literal["top", "center", "bottom"] = "center"
    font_size: float = Field(default=7.0, gt=0)
    font_weight: str = Field(default="normal", min_length=1)
    font_style: str = Field(default="normal", min_length=1)
    padding: float = Field(default=0.02, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> AnnotationIntervalSpec:
        """Require the interval base to be deeper than its top."""
        if self.base <= self.top:
            raise ValueError("Annotation interval base must be greater than top.")
        if self.lane_start >= self.lane_end:
            raise ValueError("Annotation interval lane_start must be less than lane_end.")
        return self


class AnnotationTextSpec(_AuthoringModel):
    """Free-form text annotation anchored at a depth."""

    kind: Literal["text"] = "text"
    annotation_id: str = Field(min_length=1)
    depth: float | None = None
    text: str = Field(min_length=1)
    top: float | None = None
    base: float | None = None
    lane_start: float = Field(default=0.0, ge=0, lt=1)
    lane_end: float = Field(default=1.0, gt=0, le=1)
    color: str = Field(default="#111111", min_length=1)
    background_color: str | None = Field(default=None, min_length=1)
    border_color: str | None = Field(default=None, min_length=1)
    border_linewidth: float | None = Field(default=None, gt=0)
    text_orientation: Literal["horizontal", "vertical"] = "horizontal"
    wrap: bool = True
    horizontal_alignment: Literal["left", "center", "right"] = "center"
    vertical_alignment: Literal["top", "center", "bottom"] = "center"
    font_size: float = Field(default=7.0, gt=0)
    font_weight: str = Field(default="normal", min_length=1)
    font_style: str = Field(default="normal", min_length=1)
    padding: float = Field(default=0.02, ge=0)

    @model_validator(mode="after")
    def validate_placement(self) -> AnnotationTextSpec:
        """Require either a point depth or a complete interval."""
        has_depth = self.depth is not None
        has_interval = self.top is not None or self.base is not None
        if has_depth == has_interval:
            raise ValueError("Annotation text must define either depth or top/base.")
        if (self.top is None) != (self.base is None):
            raise ValueError("Annotation text top and base must be set together.")
        if self.top is not None and self.base is not None and self.base <= self.top:
            raise ValueError("Annotation text base must be greater than top.")
        if self.lane_start >= self.lane_end:
            raise ValueError("Annotation text lane_start must be less than lane_end.")
        return self


class AnnotationMarkerSpec(_AuthoringModel):
    """Marker annotation anchored at a depth."""

    kind: Literal["marker"] = "marker"
    annotation_id: str = Field(min_length=1)
    depth: float
    x: float = Field(default=0.5, ge=0, le=1)
    shape: AuthoringAnnotationMarkerShape = AuthoringAnnotationMarkerShape.CIRCLE
    size: float = Field(default=32.0, gt=0)
    color: str = Field(default="#111111", min_length=1)
    fill_color: str | None = Field(default=None, min_length=1)
    edge_color: str | None = Field(default=None, min_length=1)
    line_width: float = Field(default=0.8, gt=0)
    label: str | None = Field(default=None, min_length=1)
    text_side: Literal["auto", "left", "right"] = "auto"
    text_x: float | None = Field(default=None, ge=0, le=1)
    depth_offset: float | None = None
    font_size: float | None = Field(default=None, gt=0)
    font_weight: str = Field(default="bold", min_length=1)
    font_style: str = Field(default="normal", min_length=1)
    arrow: bool = True
    arrow_style: str | None = Field(default=None, min_length=1)
    arrow_linewidth: float | None = Field(default=None, gt=0)
    priority: int = 100
    label_mode: AuthoringAnnotationLabelMode = AuthoringAnnotationLabelMode.FREE
    label_lane_start: float | None = Field(default=None, ge=0, lt=1)
    label_lane_end: float | None = Field(default=None, gt=0, le=1)

    @model_validator(mode="after")
    def validate_label_lane(self) -> AnnotationMarkerSpec:
        """Require a complete lane only for dedicated marker labels."""
        if (self.label_lane_start is None) != (self.label_lane_end is None):
            raise ValueError("Marker label lane bounds must be set together.")
        if self.label_lane_start is not None and self.label_lane_start >= self.label_lane_end:
            raise ValueError("Marker label_lane_start must be less than label_lane_end.")
        if self.label_mode == AuthoringAnnotationLabelMode.DEDICATED_LANE:
            if self.label_lane_start is None or self.label_lane_end is None:
                raise ValueError("Dedicated marker labels require lane bounds.")
        elif self.label_lane_start is not None:
            raise ValueError("Marker lane bounds require dedicated_lane label mode.")
        return self


class AnnotationArrowSpec(_AuthoringModel):
    """Arrow annotation spanning a depth range."""

    kind: Literal["arrow"] = "arrow"
    annotation_id: str = Field(min_length=1)
    start_depth: float
    end_depth: float
    start_x: float = Field(ge=0, le=1)
    end_x: float = Field(ge=0, le=1)
    label: str | None = Field(default=None, min_length=1)
    color: str = Field(default="#222222", min_length=1)
    line_width: float = Field(default=0.8, gt=0)
    line_style: str = Field(default="-", min_length=1)
    arrow_style: str = Field(default="-|>", min_length=1)
    label_x: float | None = Field(default=None, ge=0, le=1)
    label_depth: float | None = None
    font_size: float = Field(default=7.0, gt=0)
    font_weight: str = Field(default="bold", min_length=1)
    font_style: str = Field(default="normal", min_length=1)
    text_rotation: float = 0.0
    priority: int = 100
    label_mode: AuthoringAnnotationLabelMode = AuthoringAnnotationLabelMode.FREE
    label_lane_start: float | None = Field(default=None, ge=0, lt=1)
    label_lane_end: float | None = Field(default=None, gt=0, le=1)

    @model_validator(mode="after")
    def validate_range(self) -> AnnotationArrowSpec:
        """Require the arrow base to be deeper than its top."""
        if (self.label_lane_start is None) != (self.label_lane_end is None):
            raise ValueError("Arrow label lane bounds must be set together.")
        if self.label_lane_start is not None and self.label_lane_start >= self.label_lane_end:
            raise ValueError("Arrow label_lane_start must be less than label_lane_end.")
        if self.label_mode == AuthoringAnnotationLabelMode.DEDICATED_LANE:
            if self.label_lane_start is None or self.label_lane_end is None:
                raise ValueError("Dedicated arrow labels require lane bounds.")
        elif self.label_lane_start is not None:
            raise ValueError("Arrow lane bounds require dedicated_lane label mode.")
        return self


class AnnotationGlyphSpec(_AuthoringModel):
    """Glyph annotation anchored at a depth."""

    kind: Literal["glyph"] = "glyph"
    annotation_id: str = Field(min_length=1)
    depth: float | None = None
    glyph: str = Field(min_length=1)
    top: float | None = None
    base: float | None = None
    lane_start: float = Field(default=0.0, ge=0, lt=1)
    lane_end: float = Field(default=1.0, gt=0, le=1)
    color: str = Field(default="#111111", min_length=1)
    background_color: str | None = Field(default=None, min_length=1)
    border_color: str | None = Field(default=None, min_length=1)
    border_linewidth: float | None = Field(default=None, gt=0)
    font_size: float = Field(default=9.0, gt=0)
    font_weight: str = Field(default="bold", min_length=1)
    font_style: str = Field(default="normal", min_length=1)
    rotation: float = 0.0
    horizontal_alignment: Literal["left", "center", "right"] = "center"
    vertical_alignment: Literal["top", "center", "bottom"] = "center"
    padding: float = Field(default=0.02, ge=0)

    @model_validator(mode="after")
    def validate_placement(self) -> AnnotationGlyphSpec:
        """Require either a point depth or a complete interval."""
        has_depth = self.depth is not None
        has_interval = self.top is not None or self.base is not None
        if has_depth == has_interval:
            raise ValueError("Annotation glyph must define either depth or top/base.")
        if (self.top is None) != (self.base is None):
            raise ValueError("Annotation glyph top and base must be set together.")
        if self.top is not None and self.base is not None and self.base <= self.top:
            raise ValueError("Annotation glyph base must be greater than top.")
        if self.lane_start >= self.lane_end:
            raise ValueError("Annotation glyph lane_start must be less than lane_end.")
        return self


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
    grid: AuthoringGridSpec = Field(default_factory=AuthoringGridSpec)
    track_header: AuthoringTrackHeaderSpec = Field(default_factory=AuthoringTrackHeaderSpec)
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
        fill_ids: set[str] = set()
        for index, fill in enumerate(self.fills):
            if fill.fill_id is None:
                fill.fill_id = f"{self.id}.fill.{index + 1}"
            if fill.fill_id in fill_ids:
                raise ValueError(f"Track {self.id} contains duplicate fill ids.")
            fill_ids.add(fill.fill_id)
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

    remark_id: str | None = Field(default=None, min_length=1)
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
        """Require stable unique identities across the document."""
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
        remark_ids: set[str] = set()
        for index, remark in enumerate(self.remarks):
            if remark.remark_id is None:
                remark.remark_id = f"remark-{index + 1}"
            if remark.remark_id in remark_ids:
                raise ValueError("Document contains duplicate remark ids.")
            remark_ids.add(remark.remark_id)
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
    "AuthoringAnnotationLabelMode",
    "AuthoringAnnotationMarkerShape",
    "ArrayTrackSpec",
    "AuthoringCurveFillKind",
    "AuthoringCurveHeaderDisplayPatch",
    "AuthoringCurveHeaderDisplaySpec",
    "AuthoringCurveValueLabelsPatch",
    "AuthoringCurveValueLabelsSpec",
    "AuthoringDataSource",
    "AuthoringDepthSpec",
    "AuthoringDocumentSpec",
    "AuthoringGridDisplayMode",
    "AuthoringGridPatch",
    "AuthoringGridScaleKind",
    "AuthoringGridSpacingMode",
    "AuthoringGridSpec",
    "AuthoringPageSpec",
    "AuthoringRasterColorbarPosition",
    "AuthoringRasterColorbarPatch",
    "AuthoringRasterColorbarSpec",
    "AuthoringRasterNormalizationKind",
    "AuthoringRasterProfileKind",
    "AuthoringRasterSampleAxisPatch",
    "AuthoringRasterSampleAxisSpec",
    "AuthoringRasterWaveformPatch",
    "AuthoringRasterWaveformSpec",
    "AuthoringReferenceAxisKind",
    "AuthoringReferenceOverlayMode",
    "AuthoringReferenceOverlaySpec",
    "AuthoringReferenceTickSide",
    "AuthoringNumberFormatKind",
    "AuthoringRemarkSpec",
    "AuthoringScale",
    "AuthoringScaleKind",
    "AuthoringSectionSpec",
    "AuthoringStyle",
    "AuthoringTrackHeaderObjectKind",
    "AuthoringTrackHeaderObjectSpec",
    "AuthoringTrackHeaderPatch",
    "AuthoringTrackHeaderSpec",
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
