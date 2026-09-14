###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Static v2 contracts and handlers for fills and typed annotations."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..authoring_program.intent_builder import IntentBuilder
from ..model.authoring import (
    AnnotationSpec,
    AuthoringCurveFillBaselineSpec,
    AuthoringCurveFillCrossoverSpec,
)
from ..model.intent import AuthoringDocumentIntent

FillOperation = Literal["create", "select", "update"]
FillKind = Literal[
    "between_curves",
    "between_instances",
    "to_lower_limit",
    "to_upper_limit",
    "baseline_split",
]


class CurveFillArgs(BaseModel):
    """Arguments for one curve-fill relation."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    operation: FillOperation = "create"
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    fill_id: str | None = Field(default=None, min_length=1)
    id_hint: str | None = Field(default=None, min_length=1)
    kind: FillKind | None = None
    binding_id: str | None = Field(default=None, min_length=1)
    other_binding_id: str | None = Field(default=None, min_length=1)
    label: str | None = Field(default=None, min_length=1)
    color: str | None = Field(default=None, min_length=1)
    alpha: float | None = Field(default=None, ge=0, le=1)
    baseline: AuthoringCurveFillBaselineSpec | None = None
    crossover: AuthoringCurveFillCrossoverSpec | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> CurveFillArgs:
        """Enforce fill-kind target and nested replacement invariants."""
        if self.operation == "create":
            if self.fill_id is not None:
                raise ValueError("Fill create does not accept fill_id.")
            if self.kind is None or self.binding_id is None:
                raise ValueError("Fill create requires kind and binding_id.")
            _validate_fill_kind_fields(
                self.kind,
                self.other_binding_id,
                self.baseline,
                self.crossover,
            )
        elif self.operation == "select":
            if self.fill_id is None:
                raise ValueError("Fill select requires fill_id.")
            if any(
                value is not None
                for value in (
                    self.id_hint,
                    self.kind,
                    self.binding_id,
                    self.other_binding_id,
                    self.label,
                    self.color,
                    self.alpha,
                    self.baseline,
                    self.crossover,
                )
            ):
                raise ValueError("Fill select accepts only section_id, track_id, and fill_id.")
        else:
            if self.fill_id is None:
                raise ValueError("Fill update requires fill_id.")
            if self.id_hint is not None:
                raise ValueError("Fill update does not accept id_hint.")
            if not any(
                value is not None
                for value in (
                    self.kind,
                    self.binding_id,
                    self.other_binding_id,
                    self.label,
                    self.color,
                    self.alpha,
                    self.baseline,
                    self.crossover,
                )
            ):
                raise ValueError("Fill update requires a mutable field.")
            if self.kind is not None:
                _validate_fill_kind_fields(
                    self.kind,
                    self.other_binding_id,
                    self.baseline,
                    self.crossover,
                )
        return self


class TypedAnnotationArgs(BaseModel):
    """Arguments for one complete typed annotation payload."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    operation: Literal["create", "select", "update"] = "create"
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    annotation_id: str | None = Field(default=None, min_length=1)
    id_hint: str | None = Field(default=None, min_length=1)
    annotation: AnnotationSpec | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> TypedAnnotationArgs:
        """Require complete nested payloads for creation and replacement."""
        if self.operation == "create":
            if self.annotation_id is not None:
                raise ValueError("Annotation create does not accept annotation_id.")
            if self.annotation is None:
                raise ValueError("Annotation create requires annotation payload.")
        elif self.operation == "select":
            if self.annotation_id is None:
                raise ValueError("Annotation select requires annotation_id.")
            if self.id_hint is not None or self.annotation is not None:
                raise ValueError(
                    "Annotation select accepts only section_id, track_id, and annotation_id."
                )
        else:
            if self.annotation_id is None:
                raise ValueError("Annotation update requires annotation_id.")
            if self.annotation is None:
                raise ValueError("Annotation update requires a complete annotation payload.")
            if self.id_hint is not None:
                raise ValueError("Annotation update does not accept id_hint.")
        return self


def compile_fill_curve(arguments: BaseModel) -> AuthoringDocumentIntent:
    """Compile one curve fill through explicit builder calls."""
    typed = CurveFillArgs.model_validate(arguments)
    builder = IntentBuilder()
    report = builder.report()
    section = builder.select_section(report, section_id=typed.section_id)
    track = builder.select_track(section, track_id=typed.track_id)
    if typed.operation == "select":
        builder.select_fill(track, fill_id=typed.fill_id or "")
    elif typed.operation == "create":
        binding = builder.reference_binding(track, binding_id=typed.binding_id or "")
        other_binding = (
            builder.reference_binding(track, binding_id=typed.other_binding_id)
            if typed.other_binding_id is not None
            else None
        )
        builder.add_fill(
            track,
            kind=typed.kind or "between_curves",
            binding=binding,
            other_binding=other_binding,
            id_hint=typed.id_hint,
            label=typed.label,
            color=typed.color,
            alpha=typed.alpha,
            baseline=typed.baseline,
            crossover=typed.crossover,
        )
    else:
        fill = builder.select_fill(track, fill_id=typed.fill_id or "")
        binding = (
            builder.reference_binding(track, binding_id=typed.binding_id)
            if typed.binding_id is not None
            else None
        )
        other_binding = (
            builder.reference_binding(track, binding_id=typed.other_binding_id)
            if typed.other_binding_id is not None
            else None
        )
        builder.update_fill(
            track,
            fill,
            kind=typed.kind,
            binding=binding,
            other_binding=other_binding,
            label=typed.label,
            color=typed.color,
            alpha=typed.alpha,
            baseline=typed.baseline,
            crossover=typed.crossover,
        )
    return builder.intent()


def compile_annotation_typed(arguments: BaseModel) -> AuthoringDocumentIntent:
    """Compile one complete typed annotation through explicit builder calls."""
    typed = TypedAnnotationArgs.model_validate(arguments)
    builder = IntentBuilder()
    report = builder.report()
    section = builder.select_section(report, section_id=typed.section_id)
    track = builder.select_track(section, track_id=typed.track_id)
    if typed.operation == "create":
        builder.add_typed_annotation(
            track,
            annotation=typed.annotation,
            id_hint=typed.id_hint,
        )
    elif typed.operation == "select":
        builder.select_annotation(track, annotation_id=typed.annotation_id or "")
    else:
        annotation = builder.select_annotation(track, annotation_id=typed.annotation_id or "")
        builder.update_typed_annotation(track, annotation, payload=typed.annotation)
    return builder.intent()


def _validate_fill_kind_fields(
    kind: FillKind,
    other_binding_id: str | None,
    baseline: AuthoringCurveFillBaselineSpec | None,
    crossover: AuthoringCurveFillCrossoverSpec | None,
) -> None:
    """Validate targets and nested configuration against one fill kind."""
    between = kind in {"between_curves", "between_instances"}
    if between and other_binding_id is None:
        raise ValueError(f"Fill kind {kind} requires other_binding_id.")
    if not between and other_binding_id is not None:
        raise ValueError(f"Fill kind {kind} does not accept other_binding_id.")
    if kind == "baseline_split" and baseline is None:
        raise ValueError("Baseline-split fills require a complete baseline.")
    if kind != "baseline_split" and baseline is not None:
        raise ValueError(f"Fill kind {kind} does not accept baseline.")
    if crossover is not None and not between:
        raise ValueError("Crossover configuration requires a between-curve fill kind.")


__all__ = [
    "CurveFillArgs",
    "TypedAnnotationArgs",
    "compile_annotation_typed",
    "compile_fill_curve",
]
