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

"""Provider-neutral partial desired-state models.

These models deliberately sit between language-model output and deterministic
authoring mutations.  A field that is absent is omitted, a typed value is an
explicit set, :class:`AuthoringClearIntent` is an explicit clear, and
:class:`AuthoringRemoveIntent` is an explicit object removal.  Resolution and
execution are intentionally outside this module.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import GetJsonSchemaHandler, JsonSchemaValue
from pydantic_core import CoreSchema

from .authoring import (
    AnnotationSpec,
    AuthoringCurveCalloutSpec,
    AuthoringCurveFillBaselineSpec,
    AuthoringCurveFillCrossoverSpec,
    AuthoringCurveFillKind,
    AuthoringCurveHeaderDisplaySpec,
    AuthoringCurveValueLabelsSpec,
    AuthoringDataSource,
    AuthoringGridDisplayMode,
    AuthoringGridScaleKind,
    AuthoringGridSpacingMode,
    AuthoringHeaderDetailSpec,
    AuthoringRasterColorbarSpec,
    AuthoringRasterNormalizationKind,
    AuthoringRasterProfileKind,
    AuthoringRasterSampleAxisSpec,
    AuthoringRasterWaveformSpec,
    AuthoringReferenceOverlaySpec,
    AuthoringScale,
    AuthoringTrackHeaderSpec,
)


def _omit_rejected_nulls_from_schema(value: object) -> object:
    """Remove schema variants that intent validation rejects at runtime."""
    if isinstance(value, list):
        return [_omit_rejected_nulls_from_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    schema = {key: _omit_rejected_nulls_from_schema(item) for key, item in value.items()}
    removed_null = False

    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        non_null_variants = [
            item for item in any_of if not (isinstance(item, dict) and item.get("type") == "null")
        ]
        if len(non_null_variants) != len(any_of):
            schema["anyOf"] = non_null_variants
            removed_null = True

    schema_type = schema.get("type")
    if isinstance(schema_type, list) and "null" in schema_type:
        non_null_types = [item for item in schema_type if item != "null"]
        schema["type"] = non_null_types[0] if len(non_null_types) == 1 else non_null_types
        removed_null = True

    if removed_null and schema.get("default") is None:
        schema.pop("default", None)
    return schema


class _IntentModel(BaseModel):
    """Strict base model shared by desired-state intent objects."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        """Advertise omission-or-clear semantics rather than rejected raw nulls."""
        schema = _omit_rejected_nulls_from_schema(handler(core_schema))
        # Construction subclasses have already removed None from annotations,
        # but retain it as the internal sentinel for an omitted field.
        for field in schema.get("properties", {}).values():
            if field.get("default") is None:
                field.pop("default", None)
        return schema

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> Self:
        """Require callers to use the clear marker instead of raw ``null``."""
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(
                    f"Intent field '{field_name}' cannot be null; use "
                    '{"operation": "clear"} to clear it explicitly.'
                )
        return self

    def is_omitted(self, field_name: str) -> bool:
        """Return whether a field was omitted rather than explicitly supplied."""
        if field_name not in type(self).model_fields:
            raise ValueError(f"Unknown intent field '{field_name}'.")
        return field_name not in self.model_fields_set

    def supplied_fields(self) -> set[str]:
        """Return the fields supplied by the caller, excluding defaults."""
        return set(self.model_fields_set)


class AuthoringClearIntent(_IntentModel):
    """Explicitly clear one existing value or child collection."""

    operation: Literal["clear"] = "clear"


AuthoringIntentObjectKind: TypeAlias = Literal[
    "report",
    "page",
    "depth",
    "output",
    "header",
    "tail",
    "section",
    "track",
    "curve_binding",
    "raster_binding",
    "fill",
    "annotation",
    "remark",
]


class AuthoringRemoveIntent(_IntentModel):
    """Explicitly remove one identified authoring object."""

    operation: Literal["remove"] = "remove"
    object_kind: AuthoringIntentObjectKind
    object_id: str = Field(min_length=1)
    section_id: str | None = Field(default=None, min_length=1)
    track_id: str | None = Field(default=None, min_length=1)


ClearableText: TypeAlias = str | AuthoringClearIntent | None
NonEmptyClearableText: TypeAlias = Annotated[str, Field(min_length=1)] | AuthoringClearIntent | None
ClearableFloat: TypeAlias = float | AuthoringClearIntent | None
ClearableInteger: TypeAlias = int | AuthoringClearIntent | None
ClearableBoolean: TypeAlias = bool | AuthoringClearIntent | None
PositiveClearableFloat: TypeAlias = Annotated[float, Field(gt=0)] | AuthoringClearIntent | None
NonNegativeClearableFloat: TypeAlias = Annotated[float, Field(ge=0)] | AuthoringClearIntent | None
UnitIntervalClearableFloat: TypeAlias = (
    Annotated[float, Field(ge=0, le=1)] | AuthoringClearIntent | None
)
PositiveClearableInteger: TypeAlias = Annotated[int, Field(gt=0)] | AuthoringClearIntent | None


class AuthoringReportValueIntent(_IntentModel):
    """Partial update for a source-backed report value slot."""

    value: ClearableText = None
    source_key: NonEmptyClearableText = None
    default: ClearableText = None
    unit: NonEmptyClearableText = None
    provenance: Literal["unknown", "source", "user", "default", "preserved"] | None = None
    availability: Literal["unknown", "available", "missing", "not_applicable"] | None = None


class AuthoringHeaderFieldIntent(_IntentModel):
    """Partial update for one stable general-header field."""

    slot_id: str = Field(min_length=1)
    key: NonEmptyClearableText = None
    label: NonEmptyClearableText = None
    value: AuthoringReportValueIntent | AuthoringClearIntent | None = None
    aliases: list[str] | AuthoringClearIntent | None = None
    layout_path: NonEmptyClearableText = None


class AuthoringServiceTitleIntent(_IntentModel):
    """Partial update for one stable service-title slot."""

    slot_id: str = Field(min_length=1)
    value: AuthoringReportValueIntent | AuthoringClearIntent | None = None
    font_size: PositiveClearableFloat = None
    auto_adjust: ClearableBoolean = None
    bold: ClearableBoolean = None
    italic: ClearableBoolean = None
    alignment: Literal["left", "center", "right"] | AuthoringClearIntent | None = None


class AuthoringHeaderIntent(_IntentModel):
    """Partial desired state for the first-class report header."""

    enabled: ClearableBoolean = None
    provider_name: NonEmptyClearableText = None
    title: NonEmptyClearableText = None
    subtitle: NonEmptyClearableText = None
    general_fields: list[AuthoringHeaderFieldIntent] | AuthoringClearIntent | None = None
    service_titles: list[AuthoringServiceTitleIntent] | AuthoringClearIntent | None = None
    detail_fields: list[AuthoringHeaderFieldIntent] | AuthoringClearIntent | None = None
    detail: AuthoringHeaderDetailSpec | AuthoringClearIntent | None = None
    tail_enabled: ClearableBoolean = None
    extensions: dict[str, Any] | AuthoringClearIntent | None = None


class AuthoringOutputIntent(_IntentModel):
    """Partial desired state for report backend and output settings."""

    backend: Literal["matplotlib", "plotly"] | AuthoringClearIntent | None = None
    output_path: ClearableText = None
    dpi: ClearableInteger = None
    continuous_strip_page_height_mm: ClearableFloat = None
    extensions: dict[str, Any] | AuthoringClearIntent | None = None


class AuthoringPageIntent(_IntentModel):
    """Partial desired state for physical page and layout settings."""

    size: ClearableText = None
    width_mm: PositiveClearableFloat = None
    height_mm: PositiveClearableFloat = None
    orientation: Literal["portrait", "landscape"] | AuthoringClearIntent | None = None
    continuous: ClearableBoolean = None
    bottom_track_header_enabled: ClearableBoolean = None
    margin_left_mm: NonNegativeClearableFloat = None
    margin_right_mm: NonNegativeClearableFloat = None
    margin_top_mm: NonNegativeClearableFloat = None
    margin_bottom_mm: NonNegativeClearableFloat = None
    header_height_mm: NonNegativeClearableFloat = None
    track_header_height_mm: NonNegativeClearableFloat = None
    footer_height_mm: NonNegativeClearableFloat = None
    track_gap_mm: NonNegativeClearableFloat = None


class AuthoringDepthIntent(_IntentModel):
    """Partial desired state for the shared depth axis."""

    unit: ClearableText = None
    scale: str | float | AuthoringClearIntent | None = None
    major_step: PositiveClearableFloat = None
    minor_step: PositiveClearableFloat = None


class AuthoringStyleIntent(_IntentModel):
    """Partial style desired state used by curve and raster bindings."""

    color: NonEmptyClearableText = None
    line_style: NonEmptyClearableText = None
    line_width: PositiveClearableFloat = None
    alpha: UnitIntervalClearableFloat = None
    fill_color: NonEmptyClearableText = None
    fill_alpha: UnitIntervalClearableFloat = None
    colormap: NonEmptyClearableText = None


class AuthoringGridIntent(_IntentModel):
    """Partial desired state for a track grid."""

    display: AuthoringGridDisplayMode | AuthoringClearIntent | None = None
    major: ClearableBoolean = None
    minor: ClearableBoolean = None
    major_alpha: UnitIntervalClearableFloat = None
    minor_alpha: UnitIntervalClearableFloat = None
    horizontal_display: AuthoringGridDisplayMode | AuthoringClearIntent | None = None
    horizontal_major_visible: ClearableBoolean = None
    horizontal_minor_visible: ClearableBoolean = None
    horizontal_major_color: NonEmptyClearableText = None
    horizontal_minor_color: NonEmptyClearableText = None
    horizontal_major_thickness: PositiveClearableFloat = None
    horizontal_minor_thickness: PositiveClearableFloat = None
    horizontal_major_alpha: UnitIntervalClearableFloat = None
    horizontal_minor_alpha: UnitIntervalClearableFloat = None
    vertical_display: AuthoringGridDisplayMode | AuthoringClearIntent | None = None
    vertical_main_visible: ClearableBoolean = None
    vertical_main_line_count: PositiveClearableInteger = None
    vertical_main_thickness: PositiveClearableFloat = None
    vertical_main_color: NonEmptyClearableText = None
    vertical_main_alpha: UnitIntervalClearableFloat = None
    vertical_main_scale: AuthoringGridScaleKind | AuthoringClearIntent | None = None
    vertical_main_spacing_mode: AuthoringGridSpacingMode | AuthoringClearIntent | None = None
    vertical_secondary_visible: ClearableBoolean = None
    vertical_secondary_line_count: PositiveClearableInteger = None
    vertical_secondary_thickness: PositiveClearableFloat = None
    vertical_secondary_color: NonEmptyClearableText = None
    vertical_secondary_alpha: UnitIntervalClearableFloat = None
    vertical_secondary_scale: AuthoringGridScaleKind | AuthoringClearIntent | None = None
    vertical_secondary_spacing_mode: AuthoringGridSpacingMode | AuthoringClearIntent | None = None


class AuthoringTrackIntent(_IntentModel):
    """Partial desired state for one form track and its child objects."""

    track_id: str = Field(min_length=1)
    section_id: str | None = Field(default=None, min_length=1)
    title: ClearableText = None
    kind: Literal["normal", "reference", "array", "annotation"] | AuthoringClearIntent | None = None
    width_mm: PositiveClearableFloat = None
    x_scale: AuthoringScale | AuthoringClearIntent | None = None
    grid: AuthoringGridIntent | AuthoringClearIntent | None = None
    track_header: AuthoringTrackHeaderSpec | AuthoringClearIntent | None = None
    bindings: (
        list[AuthoringCurveBindingIntent | AuthoringRasterBindingIntent]
        | AuthoringClearIntent
        | None
    ) = None
    fills: list[AuthoringFillIntent] | AuthoringClearIntent | None = None
    annotations: list[AuthoringAnnotationIntent] | AuthoringClearIntent | None = None
    extensions: dict[str, Any] | AuthoringClearIntent | None = None


class AuthoringCurveBindingIntent(_IntentModel):
    """Partial desired state for one scalar curve binding instance."""

    kind: Literal["curve"]
    binding_id: str = Field(min_length=1)
    section_id: str | None = Field(default=None, min_length=1)
    track_id: str | None = Field(default=None, min_length=1)
    channel: ClearableText = None
    label: ClearableText = None
    scale: AuthoringScale | AuthoringClearIntent | None = None
    style: AuthoringStyleIntent | AuthoringClearIntent | None = None
    reference_overlay: AuthoringReferenceOverlaySpec | AuthoringClearIntent | None = None
    wrap: ClearableBoolean = None
    render_mode: Literal["line", "value_labels"] | AuthoringClearIntent | None = None
    value_labels: AuthoringCurveValueLabelsSpec | AuthoringClearIntent | None = None
    header_display: AuthoringCurveHeaderDisplaySpec | AuthoringClearIntent | None = None
    callouts: list[AuthoringCurveCalloutSpec] | AuthoringClearIntent | None = None
    extensions: dict[str, Any] | AuthoringClearIntent | None = None


class AuthoringRasterBindingIntent(_IntentModel):
    """Partial desired state for one raster binding instance."""

    kind: Literal["raster"]
    binding_id: str = Field(min_length=1)
    section_id: str | None = Field(default=None, min_length=1)
    track_id: str | None = Field(default=None, min_length=1)
    channel: ClearableText = None
    label: ClearableText = None
    style: AuthoringStyleIntent | AuthoringClearIntent | None = None
    profile: AuthoringRasterProfileKind | AuthoringClearIntent | None = None
    normalization: AuthoringRasterNormalizationKind | AuthoringClearIntent | None = None
    waveform_normalization: AuthoringRasterNormalizationKind | AuthoringClearIntent | None = None
    clip_percentiles: tuple[float, float] | AuthoringClearIntent | None = None
    interpolation: ClearableText = None
    show_raster: ClearableBoolean = None
    alpha: UnitIntervalClearableFloat = None
    color_limits: tuple[float, float] | AuthoringClearIntent | None = None
    colorbar: AuthoringRasterColorbarSpec | AuthoringClearIntent | None = None
    sample_axis: AuthoringRasterSampleAxisSpec | AuthoringClearIntent | None = None
    waveform: AuthoringRasterWaveformSpec | AuthoringClearIntent | None = None
    extensions: dict[str, Any] | AuthoringClearIntent | None = None


class AuthoringFillIntent(_IntentModel):
    """Partial desired state for one fill relation."""

    fill_id: str = Field(min_length=1)
    section_id: str | None = Field(default=None, min_length=1)
    track_id: str | None = Field(default=None, min_length=1)
    kind: AuthoringCurveFillKind | AuthoringClearIntent | None = None
    binding_id: ClearableText = None
    other_binding_id: ClearableText = None
    baseline: AuthoringCurveFillBaselineSpec | AuthoringClearIntent | None = None
    label: ClearableText = None
    color: ClearableText = None
    alpha: UnitIntervalClearableFloat = None
    crossover: AuthoringCurveFillCrossoverSpec | AuthoringClearIntent | None = None
    extensions: dict[str, Any] | AuthoringClearIntent | None = None


class AuthoringAnnotationIntent(_IntentModel):
    """Desired replacement state for one typed annotation object."""

    annotation_id: str = Field(min_length=1)
    section_id: str | None = Field(default=None, min_length=1)
    track_id: str | None = Field(default=None, min_length=1)
    annotation: AnnotationSpec | AuthoringClearIntent | None = None


class AuthoringRemarkIntent(_IntentModel):
    """Partial desired state for one report remark block."""

    remark_id: str = Field(min_length=1)
    title: ClearableText = None
    text: ClearableText = None
    lines: list[str] | AuthoringClearIntent | None = None
    alignment: Literal["left", "center", "right"] | AuthoringClearIntent | None = None
    font_size: PositiveClearableFloat = None
    title_font_size: PositiveClearableFloat = None
    border: ClearableBoolean = None


class AuthoringTailIntent(_IntentModel):
    """Partial desired state for report-tail behavior."""

    enabled: ClearableBoolean = None
    extensions: dict[str, Any] | AuthoringClearIntent | None = None


class AuthoringSectionIntent(_IntentModel):
    """Partial desired state for one section and its ordered children."""

    section_id: str = Field(min_length=1)
    title: NonEmptyClearableText = None
    subtitle: NonEmptyClearableText = None
    depth_range: tuple[float, float] | AuthoringClearIntent | None = None
    data_source: AuthoringDataSource | AuthoringClearIntent | None = None
    tracks: list[AuthoringTrackIntent] | AuthoringClearIntent | None = None
    extensions: dict[str, Any] | AuthoringClearIntent | None = None


class AuthoringReportIntent(_IntentModel):
    """Report-wide values, without section-local authoring permissions."""

    title: ClearableText = None
    subtitle: ClearableText = None
    output: AuthoringOutputIntent | AuthoringClearIntent | None = None
    page: AuthoringPageIntent | AuthoringClearIntent | None = None
    depth: AuthoringDepthIntent | AuthoringClearIntent | None = None
    header: AuthoringHeaderIntent | AuthoringClearIntent | None = None
    tail: AuthoringTailIntent | AuthoringClearIntent | None = None
    remarks: list[AuthoringRemarkIntent] | AuthoringClearIntent | None = None


class AuthoringDocumentIntent(AuthoringReportIntent):
    """Root provider-neutral desired state for one report revision."""

    sections: list[AuthoringSectionIntent] | AuthoringClearIntent | None = None
    curve_bindings: list[AuthoringCurveBindingIntent] | AuthoringClearIntent | None = None
    raster_bindings: list[AuthoringRasterBindingIntent] | AuthoringClearIntent | None = None
    fills: list[AuthoringFillIntent] | AuthoringClearIntent | None = None
    annotations: list[AuthoringAnnotationIntent] | AuthoringClearIntent | None = None
    removals: list[AuthoringRemoveIntent] = Field(default_factory=list)


def authoring_intent_json_schema() -> dict[str, Any]:
    """Return generated JSON Schema for provider-neutral desired state."""
    return AuthoringDocumentIntent.model_json_schema()


__all__ = [
    "AuthoringAnnotationIntent",
    "AuthoringClearIntent",
    "AuthoringCurveBindingIntent",
    "AuthoringDepthIntent",
    "AuthoringDocumentIntent",
    "AuthoringFillIntent",
    "AuthoringGridIntent",
    "AuthoringHeaderFieldIntent",
    "AuthoringHeaderIntent",
    "AuthoringIntentObjectKind",
    "AuthoringOutputIntent",
    "AuthoringPageIntent",
    "AuthoringRasterBindingIntent",
    "AuthoringRemoveIntent",
    "AuthoringRemarkIntent",
    "AuthoringReportIntent",
    "AuthoringReportValueIntent",
    "AuthoringSectionIntent",
    "AuthoringServiceTitleIntent",
    "AuthoringStyleIntent",
    "AuthoringTailIntent",
    "AuthoringTrackIntent",
    "authoring_intent_json_schema",
]
