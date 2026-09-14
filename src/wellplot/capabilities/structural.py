###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Static v2 contracts and handlers for structural authoring capabilities."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..authoring_program.intent_builder import IntentBuilder
from ..model.intent import AuthoringDocumentIntent

StructuralOperation = Literal["create", "select", "update"]
TrackKind = Literal["normal", "reference", "array", "annotation"]


class SectionLogPlotArgs(BaseModel):
    """Explicit create/select/update arguments for one log-plot section."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    operation: StructuralOperation = "create"
    section_id: str | None = Field(default=None, min_length=1)
    id_hint: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, min_length=1)
    subtitle: str | None = Field(default=None, min_length=1)
    depth_minimum: float | None = None
    depth_maximum: float | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> SectionLogPlotArgs:
        """Require identity and mutable fields according to the operation."""
        if self.operation == "create":
            if self.section_id is not None:
                raise ValueError("Section create does not accept section_id.")
            if self.title is None:
                raise ValueError("Section create requires title.")
        elif self.operation == "select":
            if self.section_id is None:
                raise ValueError("Section select requires section_id.")
            if any(
                value is not None
                for value in (
                    self.id_hint,
                    self.title,
                    self.subtitle,
                    self.depth_minimum,
                    self.depth_maximum,
                )
            ):
                raise ValueError("Section select accepts only section_id.")
        else:
            if self.section_id is None:
                raise ValueError("Section update requires section_id.")
            if self.id_hint is not None:
                raise ValueError("Section update does not accept id_hint.")
            if not any(
                value is not None
                for value in (
                    self.title,
                    self.subtitle,
                    self.depth_minimum,
                    self.depth_maximum,
                )
            ):
                raise ValueError("Section update requires a mutable field.")
        if (self.depth_minimum is None) != (self.depth_maximum is None):
            raise ValueError("Section depth range requires both bounds.")
        return self


class TrackScaleArgs(BaseModel):
    """Static horizontal scale options for structural track operations."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    minimum: float
    maximum: float
    kind: Literal["linear", "log"] = "linear"
    reverse: bool = False

    @model_validator(mode="after")
    def validate_bounds(self) -> TrackScaleArgs:
        """Mirror canonical scale invariants before builder conversion."""
        if self.minimum == self.maximum:
            raise ValueError("Track scale minimum and maximum must differ.")
        if self.kind == "log" and (self.minimum <= 0 or self.maximum <= 0):
            raise ValueError("Logarithmic track scales require positive bounds.")
        return self


class _TrackArgs(BaseModel):
    """Shared strict operation contract for one fixed-kind track capability."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    operation: StructuralOperation = "create"
    section_id: str = Field(min_length=1)
    track_id: str | None = Field(default=None, min_length=1)
    id_hint: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, min_length=1)
    width_mm: float | None = Field(default=None, gt=0)
    scale: TrackScaleArgs | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> _TrackArgs:
        """Require exact target and patch fields according to the operation."""
        if self.operation == "create":
            if self.track_id is not None:
                raise ValueError("Track create does not accept track_id.")
            if self.title is None or self.width_mm is None:
                raise ValueError("Track create requires title and width_mm.")
        elif self.operation == "select":
            if self.track_id is None:
                raise ValueError("Track select requires track_id.")
            if any(
                value is not None for value in (self.id_hint, self.title, self.width_mm, self.scale)
            ):
                raise ValueError("Track select accepts only section_id and track_id.")
        else:
            if self.track_id is None:
                raise ValueError("Track update requires track_id.")
            if self.id_hint is not None:
                raise ValueError("Track update does not accept id_hint.")
            if not any(value is not None for value in (self.title, self.width_mm, self.scale)):
                raise ValueError("Track update requires a mutable field.")
        return self


class TrackNormalArgs(_TrackArgs):
    """Arguments for the fixed ``normal`` track capability."""


class TrackReferenceArgs(_TrackArgs):
    """Arguments for the fixed ``reference`` track capability."""


class TrackArrayArgs(_TrackArgs):
    """Arguments for the fixed ``array`` track capability."""


class TrackAnnotationArgs(_TrackArgs):
    """Arguments for the fixed ``annotation`` track capability."""


def compile_section_log_plot(arguments: BaseModel) -> AuthoringDocumentIntent:
    """Compile one section structural fragment through explicit builder calls."""
    typed = SectionLogPlotArgs.model_validate(arguments)
    builder = IntentBuilder()
    report = builder.report()
    if typed.operation == "create":
        builder.add_section(
            report,
            id_hint=typed.id_hint,
            title=typed.title or "",
            subtitle=typed.subtitle,
            depth_minimum=typed.depth_minimum,
            depth_maximum=typed.depth_maximum,
        )
    else:
        section = builder.select_section(report, section_id=typed.section_id or "")
        if typed.operation == "update":
            builder.update_section(
                section,
                title=typed.title,
                subtitle=typed.subtitle,
                depth_minimum=typed.depth_minimum,
                depth_maximum=typed.depth_maximum,
            )
    return builder.intent()


def compile_track_normal(arguments: BaseModel) -> AuthoringDocumentIntent:
    """Compile one fixed-kind normal-track structural fragment."""
    return _compile_track(arguments, TrackNormalArgs, "normal")


def compile_track_reference(arguments: BaseModel) -> AuthoringDocumentIntent:
    """Compile one fixed-kind reference-track structural fragment."""
    return _compile_track(arguments, TrackReferenceArgs, "reference")


def compile_track_array(arguments: BaseModel) -> AuthoringDocumentIntent:
    """Compile one fixed-kind array-track structural fragment."""
    return _compile_track(arguments, TrackArrayArgs, "array")


def compile_track_annotation(arguments: BaseModel) -> AuthoringDocumentIntent:
    """Compile one fixed-kind annotation-track structural fragment."""
    return _compile_track(arguments, TrackAnnotationArgs, "annotation")


def _compile_track(
    arguments: BaseModel,
    model_type: type[_TrackArgs],
    kind: TrackKind,
) -> AuthoringDocumentIntent:
    """Compile one fixed-kind track using an adopted host-resolved parent."""
    typed = model_type.model_validate(arguments)
    builder = IntentBuilder()
    report = builder.report()
    section = builder.select_section(report, section_id=typed.section_id)
    if typed.operation == "create":
        scale = typed.scale
        builder.add_track(
            section,
            id_hint=typed.id_hint,
            kind=kind,
            title=typed.title or "",
            width_mm=typed.width_mm or 0,
            scale_minimum=scale.minimum if scale is not None else None,
            scale_maximum=scale.maximum if scale is not None else None,
            scale_kind=scale.kind if scale is not None else "linear",
            reverse=scale.reverse if scale is not None else False,
        )
    else:
        track = builder.select_track(section, track_id=typed.track_id or "")
        if typed.operation == "update":
            scale = typed.scale
            builder.update_track(
                track,
                title=typed.title,
                width_mm=typed.width_mm,
                scale_minimum=scale.minimum if scale is not None else None,
                scale_maximum=scale.maximum if scale is not None else None,
                scale_kind=scale.kind if scale is not None else "linear",
                reverse=scale.reverse if scale is not None else False,
            )
    return builder.intent()


__all__ = [
    "SectionLogPlotArgs",
    "TrackAnnotationArgs",
    "TrackArrayArgs",
    "TrackNormalArgs",
    "TrackReferenceArgs",
    "TrackScaleArgs",
    "compile_section_log_plot",
    "compile_track_annotation",
    "compile_track_array",
    "compile_track_normal",
    "compile_track_reference",
]
