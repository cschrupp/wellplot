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

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..model.intent import (
    AuthoringAnnotationIntent,
    AuthoringCurveBindingIntent,
    AuthoringDocumentIntent,
    AuthoringFillIntent,
    AuthoringRasterBindingIntent,
    AuthoringRemarkIntent,
    AuthoringSectionIntent,
    AuthoringTrackIntent,
)
from .base import CapabilitySpec
from .registry import CapabilityRegistry


class LogPlotSectionArtifact(BaseModel):
    """Typed worker output for one conventional well-log plot section."""

    model_config = ConfigDict(extra="forbid")

    section: AuthoringSectionIntent
    report_remarks: list[AuthoringRemarkIntent] = Field(default_factory=list)


class ReportArtifact(BaseModel):
    """Typed worker output for report-wide settings only."""

    model_config = ConfigDict(extra="forbid")

    intent: AuthoringDocumentIntent

    @model_validator(mode="after")
    def reject_section_content(self) -> ReportArtifact:
        """Keep report artifacts separate from independently compiled sections."""
        forbidden = (
            "sections",
            "curve_bindings",
            "raster_bindings",
            "fills",
            "annotations",
        )
        supplied = self.intent.supplied_fields()
        invalid = sorted(field for field in forbidden if field in supplied)
        if invalid:
            raise ValueError(
                "Report worker cannot author section-local content: " + ", ".join(invalid)
            )
        return self


def _compile_log_plot_section(artifact: BaseModel) -> AuthoringDocumentIntent:
    typed = LogPlotSectionArtifact.model_validate(artifact)
    payload: dict[str, object] = {"sections": [typed.section]}
    if typed.report_remarks:
        payload["remarks"] = typed.report_remarks
    return AuthoringDocumentIntent.model_validate(payload)


def _compile_report(artifact: BaseModel) -> AuthoringDocumentIntent:
    return ReportArtifact.model_validate(artifact).intent


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
        ),
        CapabilitySpec(
            capability_id="track.normal",
            category="track",
            description="Standard scalar/multi-curve track with x scale, grid, bindings and fills.",
            aliases=("scalar track", "curve track", "normal track"),
            artifact_model=AuthoringTrackIntent,
            compiler=_no_document_compiler,
            allowed_parents=("section.log_plot",),
        ),
        CapabilitySpec(
            capability_id="track.reference",
            category="track",
            description="Depth/reference track used for depth and reference presentation.",
            aliases=("depth track", "reference track"),
            artifact_model=AuthoringTrackIntent,
            compiler=_no_document_compiler,
            allowed_parents=("section.log_plot",),
        ),
        CapabilitySpec(
            capability_id="track.array",
            category="track",
            description="Array/raster-capable track for depth-indexed matrix data such as VDL.",
            aliases=("array track", "raster track", "vdl track"),
            artifact_model=AuthoringTrackIntent,
            compiler=_no_document_compiler,
            allowed_parents=("section.log_plot",),
        ),
        CapabilitySpec(
            capability_id="track.annotation",
            category="track",
            description="Track containing typed annotations rather than sampled log curves.",
            aliases=("annotation track",),
            artifact_model=AuthoringTrackIntent,
            compiler=_no_document_compiler,
            allowed_parents=("section.log_plot",),
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
        ),
        CapabilitySpec(
            capability_id="fill.curve",
            category="fill",
            description="Fill relative to one or two scalar curve bindings.",
            aliases=("curve fill", "crossover fill"),
            artifact_model=AuthoringFillIntent,
            compiler=_no_document_compiler,
            allowed_parents=("track.normal",),
        ),
        CapabilitySpec(
            capability_id="annotation.typed",
            category="annotation",
            description="Typed annotation object placed on an annotation-capable track.",
            aliases=("annotation", "marker"),
            artifact_model=AuthoringAnnotationIntent,
            compiler=_no_document_compiler,
            allowed_parents=("track.annotation",),
        ),
    )


def create_builtin_registry() -> CapabilityRegistry:
    """Create the deterministic registry of currently supported capabilities."""
    registry = CapabilityRegistry()
    registry.register_many(builtin_capabilities())
    return registry
