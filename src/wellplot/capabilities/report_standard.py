###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Static v2 arguments and host handler for ``report.standard``."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..authoring_program.intent_builder import IntentBuilder
from ..model.intent import (
    AuthoringDepthIntent,
    AuthoringDocumentIntent,
    AuthoringOutputIntent,
    AuthoringPageIntent,
    AuthoringReportValueIntent,
)


class ReportStandardValueArgs(BaseModel):
    """Static source/value metadata accepted by report slots."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    value: str | None = None
    source_key: str | None = None
    default: str | None = None
    unit: str | None = None
    provenance: Literal["unknown", "source", "user", "default", "preserved"] | None = None
    availability: Literal["unknown", "available", "missing", "not_applicable"] | None = None


class ReportStandardFieldArgs(BaseModel):
    """One semantic general or detail field update."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    key: str = Field(min_length=1)
    value: ReportStandardValueArgs = Field(default_factory=ReportStandardValueArgs)
    label: str | None = None


class ReportStandardServiceTitleArgs(BaseModel):
    """One stable service-title slot update."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    slot_id: str = Field(min_length=1)
    value: ReportStandardValueArgs = Field(default_factory=ReportStandardValueArgs)
    font_size: float | None = None
    auto_adjust: bool | None = None
    bold: bool | None = None
    italic: bool | None = None
    alignment: Literal["left", "center", "right"] | None = None


class ReportStandardRemarkArgs(BaseModel):
    """One stable report remark update."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    remark_id: str = Field(min_length=1)
    title: str | None = None
    text: str | None = None
    lines: tuple[str, ...] | None = Field(default=None, min_length=1)
    alignment: str | None = None
    font_size: float | None = None
    title_font_size: float | None = None
    border: bool | None = None

    @model_validator(mode="after")
    def require_content(self) -> ReportStandardRemarkArgs:
        """Require explicit remark content rather than an empty placeholder."""
        if self.text is None and self.lines is None:
            raise ValueError("A report remark requires text or lines.")
        if self.text is not None and self.lines is not None:
            raise ValueError("A report remark accepts text or lines, not both.")
        return self


class ReportStandardArgs(BaseModel):
    """Sparse, static v2 arguments for deterministic report authoring."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    title: str | None = None
    subtitle: str | None = None
    header_fields: tuple[ReportStandardFieldArgs, ...] | None = None
    service_titles: tuple[ReportStandardServiceTitleArgs, ...] | None = None
    detail_fields: tuple[ReportStandardFieldArgs, ...] | None = None
    remarks: tuple[ReportStandardRemarkArgs, ...] | None = None
    page: AuthoringPageIntent | None = None
    depth: AuthoringDepthIntent | None = None
    output: AuthoringOutputIntent | None = None

    @field_validator("header_fields", "service_titles", "detail_fields", "remarks")
    @classmethod
    def reject_empty_collections(
        cls,
        value: tuple[object, ...] | None,
    ) -> tuple[object, ...] | None:
        """Keep supplied collections meaningful while allowing omission."""
        if value == ():
            raise ValueError("Supplied report collections must not be empty.")
        return value


def compile_report_standard(arguments: BaseModel) -> AuthoringDocumentIntent:
    """Compile one static report argument object through explicit SDK methods."""
    typed = ReportStandardArgs.model_validate(arguments)
    builder = IntentBuilder()
    report = builder.report(title=typed.title, subtitle=typed.subtitle)

    for field in typed.header_fields or ():
        builder.set_header_field(
            report,
            key=field.key,
            value=_report_value(field.value),
            label=field.label,
        )
    for title in typed.service_titles or ():
        builder.set_service_title(
            report,
            slot_id=title.slot_id,
            value=_report_value(title.value),
            font_size=title.font_size,
            auto_adjust=title.auto_adjust,
            bold=title.bold,
            italic=title.italic,
            alignment=title.alignment,
        )
    for field in typed.detail_fields or ():
        builder.set_detail_field(
            report,
            key=field.key,
            value=_report_value(field.value),
            label=field.label,
        )
    for remark in typed.remarks or ():
        builder.add_remark(
            report,
            remark_id=remark.remark_id,
            title=remark.title,
            text=remark.text,
            lines=list(remark.lines) if remark.lines is not None else None,
            alignment=remark.alignment,
            font_size=remark.font_size,
            title_font_size=remark.title_font_size,
            border=remark.border,
        )
    if typed.page is not None:
        builder.update_page(report, page=typed.page)
    if typed.depth is not None:
        builder.update_depth(report, depth=typed.depth)
    if typed.output is not None:
        builder.update_output(report, output=typed.output)
    return builder.intent()


def _report_value(value: ReportStandardValueArgs) -> AuthoringReportValueIntent:
    """Convert static v2 value metadata to the canonical report value model."""
    return AuthoringReportValueIntent.model_validate(value.model_dump(exclude_unset=True))


__all__ = [
    "ReportStandardArgs",
    "ReportStandardFieldArgs",
    "ReportStandardRemarkArgs",
    "ReportStandardServiceTitleArgs",
    "ReportStandardValueArgs",
    "compile_report_standard",
]
