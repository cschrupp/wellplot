###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Built-in capability declarations backed by the current Wellplot models.

This starter intentionally registers only capabilities already represented by
Wellplot's canonical authoring model. Future capabilities such as
``track.image`` or ``section.well_diagram`` should be added in their own modules
and registered without changing the LangGraph workflow.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..model.intent import (
    AuthoringAnnotationIntent,
    AuthoringCurveBindingIntent,
    AuthoringDocumentIntent,
    AuthoringFillIntent,
    AuthoringRasterBindingIntent,
    AuthoringRemarkIntent,
    AuthoringRemoveIntent,
    AuthoringReportIntent,
    AuthoringSectionIntent,
    AuthoringTrackIntent,
)
from .base import CapabilitySpec
from .bindings import (
    CurveBindingArgs,
    RasterBindingArgs,
    compile_binding_curve,
    compile_binding_raster,
)
from .fills_annotations import (
    CurveFillArgs,
    TypedAnnotationArgs,
    compile_annotation_typed,
    compile_fill_curve,
)
from .registry import CapabilityRegistry
from .report_standard import ReportStandardArgs, compile_report_standard
from .structural import (
    SectionLogPlotArgs,
    TrackAnnotationArgs,
    TrackArrayArgs,
    TrackNormalArgs,
    TrackReferenceArgs,
    compile_section_log_plot,
    compile_track_annotation,
    compile_track_array,
    compile_track_normal,
    compile_track_reference,
)


class ReportRemoval(AuthoringRemoveIntent):
    """Only report-owned objects may be removed by the report worker."""

    object_kind: Literal["report", "page", "depth", "output", "header", "tail", "remark"]


class ReportIntent(AuthoringReportIntent):
    """Report mutation contract, including explicitly requested removals."""

    removals: list[ReportRemoval] = Field(default_factory=list)


class LogPlotSectionArtifact(BaseModel):
    """Typed worker output for one conventional well-log plot section."""

    model_config = ConfigDict(extra="forbid")

    section: AuthoringSectionIntent
    report_remarks: list[AuthoringRemarkIntent] = Field(default_factory=list)


class ReportArtifact(BaseModel):
    """Typed worker output for report-wide settings only."""

    model_config = ConfigDict(extra="forbid")

    intent: ReportIntent


def _compile_log_plot_section(artifact: BaseModel) -> AuthoringDocumentIntent:
    typed = LogPlotSectionArtifact.model_validate(artifact)
    payload: dict[str, object] = {"sections": [typed.section]}
    if typed.report_remarks:
        payload["remarks"] = typed.report_remarks
    return AuthoringDocumentIntent.model_validate(payload)


def _compile_report(artifact: BaseModel) -> AuthoringDocumentIntent:
    typed = ReportArtifact.model_validate(artifact)
    return AuthoringDocumentIntent.model_validate(
        typed.intent.model_dump(mode="python", exclude_unset=True)
    )


def _no_document_compiler(artifact: BaseModel) -> AuthoringDocumentIntent:
    """Track/binding descriptors guide section workers; they are not root workers."""
    del artifact
    raise RuntimeError(
        "Leaf capabilities are compiled inside a section capability and cannot be merged "
        "as standalone document artifacts."
    )


def builtin_capabilities() -> tuple[CapabilitySpec, ...]:
    """Return built-ins in a deterministic order."""
    return (
        CapabilitySpec(
            capability_id="report.standard",
            category="report",
            description=(
                "Report-wide title, header, page, depth, output, remarks and tail settings."
            ),
            aliases=("report", "header", "page settings"),
            artifact_model=ReportArtifact,
            compiler=_compile_report,
            arguments_model=ReportStandardArgs,
            handler=compile_report_standard,
            worker_hints=(
                "Use semantic header keys and explicit report settings only.",
                "Omit report collections that do not need changes.",
            ),
            examples=("report.standard(header_fields=[{key: 'well', value: {value: 'Demo'}}])",),
        ),
        CapabilitySpec(
            capability_id="section.log_plot",
            category="section",
            description=(
                "A depth-indexed well-log plotting section composed of ordered tracks, "
                "curve/raster bindings, fills and annotations."
            ),
            aliases=("log section", "well log section", "logging pass"),
            artifact_model=LogPlotSectionArtifact,
            compiler=_compile_log_plot_section,
            source_kinds=("LAS", "DLIS"),
            planning_hints=(
                "Use one section per logically distinct logging pass or independently styled "
                "panel.",
                "Prefer explicit section ids that are stable across revisions.",
            ),
            arguments_model=SectionLogPlotArgs,
            handler=compile_section_log_plot,
            worker_hints=(
                "Use create, select, or update explicitly; selection adopts a host-resolved id.",
                "Omit section fields that should be preserved during an update.",
            ),
            examples=("section.log_plot(operation='create', id_hint='main', title='Main Pass')",),
        ),
        CapabilitySpec(
            capability_id="track.normal",
            category="track",
            description="Standard scalar/multi-curve track with x scale, grid, bindings and fills.",
            aliases=("scalar track", "curve track", "normal track"),
            artifact_model=AuthoringTrackIntent,
            compiler=_no_document_compiler,
            allowed_parents=("section.log_plot",),
            metadata={"track_kind": "normal"},
            arguments_model=TrackNormalArgs,
            handler=compile_track_normal,
            worker_hints=("This capability always creates or updates a normal track kind.",),
            examples=(
                "track.normal(operation='create', section_id='main', title='GR', width_mm=30)",
            ),
        ),
        CapabilitySpec(
            capability_id="track.reference",
            category="track",
            description="Depth/reference track used for depth and reference presentation.",
            aliases=("depth track", "reference track"),
            artifact_model=AuthoringTrackIntent,
            compiler=_no_document_compiler,
            allowed_parents=("section.log_plot",),
            metadata={"track_kind": "reference"},
            arguments_model=TrackReferenceArgs,
            handler=compile_track_reference,
            worker_hints=("This capability always creates or updates a reference track kind.",),
            examples=(
                "track.reference(operation='create', section_id='main', "
                "title='Depth', width_mm=12)",
            ),
        ),
        CapabilitySpec(
            capability_id="track.array",
            category="track",
            description="Array/raster-capable track for depth-indexed matrix data such as VDL.",
            aliases=("array track", "raster track", "vdl track"),
            artifact_model=AuthoringTrackIntent,
            compiler=_no_document_compiler,
            allowed_parents=("section.log_plot",),
            metadata={"track_kind": "array"},
            arguments_model=TrackArrayArgs,
            handler=compile_track_array,
            worker_hints=("This capability always creates or updates an array track kind.",),
            examples=(
                "track.array(operation='create', section_id='main', title='VDL', width_mm=40)",
            ),
        ),
        CapabilitySpec(
            capability_id="track.annotation",
            category="track",
            description="Track containing typed annotations rather than sampled log curves.",
            aliases=("annotation track",),
            artifact_model=AuthoringTrackIntent,
            compiler=_no_document_compiler,
            allowed_parents=("section.log_plot",),
            metadata={"track_kind": "annotation"},
            arguments_model=TrackAnnotationArgs,
            handler=compile_track_annotation,
            worker_hints=("This capability always creates or updates an annotation track kind.",),
            examples=(
                "track.annotation(operation='create', section_id='main', "
                "title='Notes', width_mm=20)",
            ),
        ),
        CapabilitySpec(
            capability_id="binding.curve",
            category="binding",
            description="Bind one scalar source channel to a track with scale and style metadata.",
            aliases=("curve", "curve binding", "scalar binding"),
            artifact_model=AuthoringCurveBindingIntent,
            compiler=_no_document_compiler,
            allowed_parents=("track.normal", "track.reference"),
            source_kinds=("LAS", "DLIS"),
            arguments_model=CurveBindingArgs,
            handler=compile_binding_curve,
            worker_hints=(
                "Use create, select, or update explicitly; selection adopts a host-resolved id.",
                "Curve scale and line style are binding-local and do not change the parent track.",
            ),
            examples=(
                "binding.curve(operation='create', section_id='main', track_id='combo', "
                "channel='GR', label='Gamma Ray')",
            ),
        ),
        CapabilitySpec(
            capability_id="binding.raster",
            category="binding",
            description="Bind one depth-indexed array/raster source channel to an array track.",
            aliases=("raster", "raster binding", "vdl binding"),
            artifact_model=AuthoringRasterBindingIntent,
            compiler=_no_document_compiler,
            allowed_parents=("track.array",),
            source_kinds=("DLIS",),
            arguments_model=RasterBindingArgs,
            handler=compile_binding_raster,
            worker_hints=(
                "Use create, select, or update explicitly; selection adopts a host-resolved id.",
                "Use profile, colorbar, sample_axis, and explicit color limits "
                "only when requested.",
            ),
            examples=(
                "binding.raster(operation='create', section_id='main', track_id='vdl', "
                "channel='VDL', profile='vdl')",
            ),
        ),
        CapabilitySpec(
            capability_id="fill.curve",
            category="fill",
            description="Fill relative to one or two scalar curve bindings.",
            aliases=("curve fill", "crossover fill"),
            artifact_model=AuthoringFillIntent,
            compiler=_no_document_compiler,
            allowed_parents=("track.normal",),
            arguments_model=CurveFillArgs,
            handler=compile_fill_curve,
            worker_hints=(
                "Use create, select, or update explicitly; fill identity is host-owned.",
                "Supply complete baseline or crossover objects when those nested fields are used.",
            ),
            examples=(
                "fill.curve(operation='create', section_id='main', track_id='combo', "
                "kind='between_instances', binding_id='main.combo.GR', "
                "other_binding_id='main.combo.SP')",
            ),
        ),
        CapabilitySpec(
            capability_id="annotation.typed",
            category="annotation",
            description="Typed annotation object placed on an annotation-capable track.",
            aliases=("annotation", "marker"),
            artifact_model=AuthoringAnnotationIntent,
            compiler=_no_document_compiler,
            allowed_parents=("track.annotation",),
            arguments_model=TypedAnnotationArgs,
            handler=compile_annotation_typed,
            worker_hints=(
                "Use create, select, or update explicitly; annotation identity is host-owned.",
                "Create and update require a complete typed annotation payload.",
            ),
            examples=(
                "annotation.typed(operation='create', section_id='main', track_id='notes', "
                "annotation={kind: 'text', annotation_id: 'requested', depth: 2500, "
                "text: 'Bond'})",
            ),
        ),
    )


def create_builtin_registry() -> CapabilityRegistry:
    """Create the deterministic registry of currently supported capabilities."""
    registry = CapabilityRegistry()
    registry.register_many(builtin_capabilities())
    return registry
