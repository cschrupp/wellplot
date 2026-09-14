###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Static v2 contracts and handlers for curve and raster bindings."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..authoring_program.intent_builder import IntentBuilder
from ..model.authoring import AuthoringRasterColorbarSpec, AuthoringRasterSampleAxisSpec
from ..model.intent import AuthoringDocumentIntent

BindingOperation = Literal["create", "select", "update"]


class CurveScaleArgs(BaseModel):
    """Explicit scalar scale options for one curve binding."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    minimum: float
    maximum: float
    kind: Literal["linear", "log", "tangential"] = "linear"
    reverse: bool = False
    unit: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> CurveScaleArgs:
        """Reject degenerate and invalid logarithmic scales before compilation."""
        if self.minimum == self.maximum:
            raise ValueError("Curve scale minimum and maximum must differ.")
        if self.kind == "log" and (self.minimum <= 0 or self.maximum <= 0):
            raise ValueError("Logarithmic curve scales require positive bounds.")
        return self


class CurveStyleArgs(BaseModel):
    """Supported line style fields for one curve binding."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    color: str | None = Field(default=None, min_length=1)
    line_style: str | None = Field(default=None, min_length=1)
    line_width: float | None = Field(default=None, gt=0)


class RasterStyleArgs(BaseModel):
    """Supported raster style fields for one raster binding."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    colormap: str | None = Field(default=None, min_length=1)
    alpha: float | None = Field(default=None, ge=0, le=1)


class _BindingArgs(BaseModel):
    """Shared strict identity fields for one binding operation."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    operation: BindingOperation = "create"
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    binding_id: str | None = Field(default=None, min_length=1)
    id_hint: str | None = Field(default=None, min_length=1)
    channel: str | None = Field(default=None, min_length=1)
    label: str | None = Field(default=None, min_length=1)


class CurveBindingArgs(_BindingArgs):
    """Arguments for creating, selecting, or updating one curve binding."""

    scale: CurveScaleArgs | None = None
    style: CurveStyleArgs | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> CurveBindingArgs:
        """Require a complete identity and unambiguous mutable fields."""
        _validate_operation(
            self,
            mutable=(self.channel, self.label, self.scale, self.style),
            label="curve binding",
        )
        return self


class RasterBindingArgs(_BindingArgs):
    """Arguments for creating, selecting, or updating one raster binding."""

    profile: Literal["generic", "vdl", "waveform"] | None = None
    normalization: Literal["auto", "none", "trace_maxabs", "global_maxabs"] | None = None
    color_minimum: float | None = None
    color_maximum: float | None = None
    style: RasterStyleArgs | None = None
    colorbar: AuthoringRasterColorbarSpec | None = None
    sample_axis: AuthoringRasterSampleAxisSpec | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> RasterBindingArgs:
        """Require a complete identity and paired raster color limits."""
        if (self.color_minimum is None) != (self.color_maximum is None):
            raise ValueError("Raster color limits require both minimum and maximum.")
        _validate_operation(
            self,
            mutable=(
                self.channel,
                self.label,
                self.profile,
                self.normalization,
                self.color_minimum,
                self.color_maximum,
                self.style,
                self.colorbar,
                self.sample_axis,
            ),
            label="raster binding",
        )
        return self


def compile_binding_curve(arguments: BaseModel) -> AuthoringDocumentIntent:
    """Compile one curve binding fragment through explicit builder calls."""
    typed = CurveBindingArgs.model_validate(arguments)
    builder = IntentBuilder()
    report = builder.report()
    section = builder.select_section(report, section_id=typed.section_id)
    track = builder.select_track(section, track_id=typed.track_id)
    if typed.operation == "create":
        builder.add_curve(
            track,
            channel=typed.channel or "",
            id_hint=typed.id_hint,
            label=typed.label,
            scale_minimum=typed.scale.minimum if typed.scale else None,
            scale_maximum=typed.scale.maximum if typed.scale else None,
            scale_kind=typed.scale.kind if typed.scale else "linear",
            reverse=typed.scale.reverse if typed.scale else False,
            scale_unit=typed.scale.unit if typed.scale else None,
            color=typed.style.color if typed.style else None,
            line_style=typed.style.line_style if typed.style else None,
            line_width=typed.style.line_width if typed.style else None,
        )
    else:
        binding = builder.select_curve(track, binding_id=typed.binding_id or "")
        if typed.operation == "update":
            builder.update_curve(
                track,
                binding,
                channel=typed.channel,
                label=typed.label,
                scale_minimum=typed.scale.minimum if typed.scale else None,
                scale_maximum=typed.scale.maximum if typed.scale else None,
                scale_kind=typed.scale.kind if typed.scale else "linear",
                reverse=typed.scale.reverse if typed.scale else False,
                scale_unit=typed.scale.unit if typed.scale else None,
                color=typed.style.color if typed.style else None,
                line_style=typed.style.line_style if typed.style else None,
                line_width=typed.style.line_width if typed.style else None,
            )
    return builder.intent()


def compile_binding_raster(arguments: BaseModel) -> AuthoringDocumentIntent:
    """Compile one raster binding fragment through explicit builder calls."""
    typed = RasterBindingArgs.model_validate(arguments)
    builder = IntentBuilder()
    report = builder.report()
    section = builder.select_section(report, section_id=typed.section_id)
    track = builder.select_track(section, track_id=typed.track_id)
    if typed.operation == "create":
        builder.add_raster(
            track,
            channel=typed.channel or "",
            id_hint=typed.id_hint,
            label=typed.label,
            profile=typed.profile,
            normalization=typed.normalization,
            color_minimum=typed.color_minimum,
            color_maximum=typed.color_maximum,
            colormap=typed.style.colormap if typed.style else None,
            alpha=typed.style.alpha if typed.style else None,
            colorbar=typed.colorbar,
            sample_axis=typed.sample_axis,
        )
    else:
        binding = builder.select_raster(track, binding_id=typed.binding_id or "")
        if typed.operation == "update":
            builder.update_raster(
                track,
                binding,
                channel=typed.channel,
                label=typed.label,
                profile=typed.profile,
                normalization=typed.normalization,
                color_minimum=typed.color_minimum,
                color_maximum=typed.color_maximum,
                colormap=typed.style.colormap if typed.style else None,
                alpha=typed.style.alpha if typed.style else None,
                colorbar=typed.colorbar,
                sample_axis=typed.sample_axis,
            )
    return builder.intent()


def _validate_operation(
    arguments: _BindingArgs,
    *,
    mutable: tuple[object, ...],
    label: str,
) -> None:
    """Apply common operation-specific identity rules to binding arguments."""
    if arguments.operation == "create":
        if arguments.binding_id is not None:
            raise ValueError(f"{label} create does not accept binding_id.")
        if arguments.channel is None:
            raise ValueError(f"{label} create requires channel.")
    elif arguments.operation == "select":
        if arguments.binding_id is None:
            raise ValueError(f"{label} select requires binding_id.")
        if arguments.id_hint is not None or any(value is not None for value in mutable):
            raise ValueError(f"{label} select accepts only section_id, track_id, and binding_id.")
    else:
        if arguments.binding_id is None:
            raise ValueError(f"{label} update requires binding_id.")
        if arguments.id_hint is not None:
            raise ValueError(f"{label} update does not accept id_hint.")
        if not any(value is not None for value in mutable):
            raise ValueError(f"{label} update requires a mutable field.")


__all__ = [
    "BindingOperation",
    "CurveBindingArgs",
    "CurveScaleArgs",
    "CurveStyleArgs",
    "RasterBindingArgs",
    "RasterStyleArgs",
    "compile_binding_curve",
    "compile_binding_raster",
]
