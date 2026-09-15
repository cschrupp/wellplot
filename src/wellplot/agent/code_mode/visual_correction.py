"""Bounded visual correction for the Code Mode v2 section boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ...authoring_context import (
    AuthoringChannelAlias,
    AuthoringChannelCandidate,
    AuthoringChannelInput,
    resolve_authoring_context,
)
from ...authoring_executor import execute_authoring_plan
from ...authoring_reconciler import reconcile_authoring
from ...authoring_service import AuthoringService
from ...capabilities import CapabilityRegistry
from ...model.authoring import AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent
from ..providers.base import ProviderRequestError
from .enrichment import EnrichedSemanticContext, ReportContext, ResolvedSectionContext
from .planner import SectionTask, SemanticPlan
from .program_worker import ProgramSectionCompiler

VISUAL_SECTION_CAPABILITIES = frozenset({"section.log_plot"})
MAX_VISUAL_IMAGES = 4
MAX_VISUAL_IMAGE_BYTES = 8_000_000


class VisualCorrectionStopReason(StrEnum):
    """Stable terminal state for one bounded visual correction."""

    SEMANTIC_VERIFICATION_FAILED = "semantic_verification_failed"
    INITIAL_RENDER_FAILED = "initial_render_failed"
    REVIEW_FAILED = "review_failed"
    NO_CORRECTION = "no_correction"
    CORRECTION_REJECTED = "correction_rejected"
    CORRECTION_WORKER_FAILED = "correction_worker_failed"
    PRIVATE_APPLY_FAILED = "private_apply_failed"
    PRESERVATION_FAILED = "preservation_failed"
    POSTCONDITION_FAILED = "postcondition_failed"
    FINAL_RENDER_FAILED = "final_render_failed"
    CORRECTED = "corrected"


class VisualCorrectionError(ValueError):
    """Base class for safe, injected visual-boundary failures."""


class VisualRenderError(VisualCorrectionError):
    """A trusted host renderer could not produce review material."""


class VisualReviewError(VisualCorrectionError):
    """A trusted visual evaluator could not return a decision."""


class _VisualModel(BaseModel):
    """Strict immutable contract shared by visual correction models."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SectionRenderImage(_VisualModel):
    """One bounded in-memory image supplied to the visual evaluator."""

    mime_type: str = Field(min_length=1)
    data: bytes = Field(min_length=1, max_length=MAX_VISUAL_IMAGE_BYTES)
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)


class SectionRenderArtifact(_VisualModel):
    """Render evidence without output paths or persistence handles."""

    images: tuple[SectionRenderImage, ...] = Field(
        min_length=1,
        max_length=MAX_VISUAL_IMAGES,
    )


class VisualReviewRequest(_VisualModel):
    """Bounded review context that deliberately omits canonical identities."""

    request: str = Field(min_length=1)
    target_scope: Literal["selected_section"] = "selected_section"
    artifact: SectionRenderArtifact
    allowed_capabilities: tuple[str, ...] = ("section.log_plot",)


class VisualSectionCorrection(_VisualModel):
    """One semantic root-section adjustment proposed by visual review."""

    target_scope: Literal["selected_section"] = "selected_section"
    capability_id: str = Field(min_length=1)
    issue: str = Field(min_length=1)
    requested_adjustment: str = Field(min_length=1)


class VisualReviewDecision(_VisualModel):
    """One visual decision; multiple competing corrections are impossible."""

    correction: VisualSectionCorrection | None = None


class VisualCorrectionDiagnostic(_VisualModel):
    """Redacted deterministic evidence for one visual-correction outcome."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class VisualCorrectionMetrics(_VisualModel):
    """Bounded attempt counters for visual correction."""

    render_count: int = Field(default=0, ge=0, le=2)
    review_count: int = Field(default=0, ge=0, le=1)
    correction_count: int = Field(default=0, ge=0, le=1)
    repair_count: int = Field(default=0, ge=0, le=2)


@dataclass(frozen=True, slots=True)
class VisualCorrectionResult:
    """Terminal evidence from one section-scoped visual correction."""

    stop_reason: VisualCorrectionStopReason
    artifact: SectionRenderArtifact | None = None
    corrected_document: AuthoringDocumentSpec | None = None
    correction: VisualSectionCorrection | None = None
    diagnostics: tuple[VisualCorrectionDiagnostic, ...] = ()
    metrics: VisualCorrectionMetrics = VisualCorrectionMetrics()

    @property
    def success(self) -> bool:
        """Return whether the visual stage reached a successful terminal state."""
        return self.stop_reason in {
            VisualCorrectionStopReason.NO_CORRECTION,
            VisualCorrectionStopReason.CORRECTED,
        }

    def __post_init__(self) -> None:
        """Keep corrected documents private on failed terminal states."""
        if not self.success and self.corrected_document is not None:
            raise ValueError("Failed visual correction cannot expose a corrected document.")


class SectionRenderer(Protocol):
    """Host-owned renderer for one selected section."""

    def render(
        self,
        document: AuthoringDocumentSpec,
        *,
        section_id: str,
    ) -> SectionRenderArtifact:
        """Render one defensive document copy for visual review."""


class VisualEvaluator(Protocol):
    """Injected evaluator that returns one structured semantic decision."""

    async def review(self, request: VisualReviewRequest) -> VisualReviewDecision:
        """Review bounded in-memory render material without document access."""


@dataclass(frozen=True, slots=True)
class VisualSectionCorrectionCoordinator:
    """Coordinate one root-only visual correction without persistence or routing."""

    section_compiler: ProgramSectionCompiler
    registry: CapabilityRegistry
    renderer: SectionRenderer
    evaluator: VisualEvaluator

    async def correct(
        self,
        *,
        request: str,
        document: AuthoringDocumentSpec,
        original_intent: AuthoringDocumentIntent,
        section_context: ResolvedSectionContext,
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        scaffold: AuthoringDocumentSpec | None = None,
        defaults: Mapping[str, object] | None = None,
        channel_aliases: Sequence[AuthoringChannelAlias | Mapping[str, object]] = (),
        header_aliases: Mapping[str, Sequence[str]] | None = None,
    ) -> VisualCorrectionResult:
        """Run semantic verification, one review, and at most one correction."""
        section_id = section_context.section_id
        if section_id is None or _section_count(document, section_id) != 1:
            return _failure(
                VisualCorrectionStopReason.POSTCONDITION_FAILED,
                "The visual target must resolve to exactly one existing section.",
            )

        semantic_issues = _semantic_issues(
            document,
            original_intent,
            section_context=section_context,
            scaffold=scaffold,
            defaults=defaults,
            channel_aliases=channel_aliases,
            header_aliases=header_aliases,
        )
        if semantic_issues:
            return _failure(
                VisualCorrectionStopReason.SEMANTIC_VERIFICATION_FAILED,
                *semantic_issues,
            )

        try:
            artifact = self.renderer.render(
                document.model_copy(deep=True),
                section_id=section_id,
            )
        except VisualRenderError as error:
            return _failure(
                VisualCorrectionStopReason.INITIAL_RENDER_FAILED,
                str(error),
                metrics=VisualCorrectionMetrics(render_count=1),
            )

        review_request = VisualReviewRequest(
            request=request,
            artifact=artifact,
            allowed_capabilities=tuple(sorted(VISUAL_SECTION_CAPABILITIES)),
        )
        try:
            decision = VisualReviewDecision.model_validate(
                await self.evaluator.review(review_request)
            )
        except VisualReviewError as error:
            return _failure(
                VisualCorrectionStopReason.REVIEW_FAILED,
                str(error),
                artifact=artifact,
                metrics=VisualCorrectionMetrics(render_count=1, review_count=1),
            )
        except ValidationError:
            return _failure(
                VisualCorrectionStopReason.REVIEW_FAILED,
                "The visual evaluator returned an invalid structured decision.",
                artifact=artifact,
                metrics=VisualCorrectionMetrics(render_count=1, review_count=1),
            )

        base_metrics = VisualCorrectionMetrics(render_count=1, review_count=1)
        correction = decision.correction
        if correction is None:
            return VisualCorrectionResult(
                stop_reason=VisualCorrectionStopReason.NO_CORRECTION,
                artifact=artifact,
                metrics=base_metrics,
            )

        capability_error = _validate_correction_capability(correction, self.registry)
        if capability_error is not None:
            return _failure(
                VisualCorrectionStopReason.CORRECTION_REJECTED,
                capability_error,
                artifact=artifact,
                correction=correction,
                metrics=base_metrics.model_copy(update={"correction_count": 1}),
            )

        correction_context = _correction_context(correction, section_context)
        try:
            worker_result = await self.section_compiler.compile(
                task_index=0,
                context=correction_context,
                document=document,
                timeout_seconds=timeout_seconds,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        except ProviderRequestError as error:
            return _failure(
                VisualCorrectionStopReason.CORRECTION_WORKER_FAILED,
                error.safe_message,
                artifact=artifact,
                correction=correction,
                metrics=base_metrics.model_copy(update={"correction_count": 1}),
            )
        metrics = base_metrics.model_copy(
            update={
                "correction_count": 1,
                "repair_count": worker_result.metrics.program_repairs,
            }
        )
        if not worker_result.success or worker_result.artifact is None:
            return _failure(
                VisualCorrectionStopReason.CORRECTION_WORKER_FAILED,
                "The visual correction section worker did not produce a valid result.",
                artifact=artifact,
                correction=correction,
                metrics=metrics,
            )

        correction_intent = worker_result.artifact.intent_fragment
        intent_error = _validate_root_section_intent(correction_intent, section_id)
        if intent_error is not None:
            return _failure(
                VisualCorrectionStopReason.POSTCONDITION_FAILED,
                intent_error,
                artifact=artifact,
                correction=correction,
                metrics=metrics,
            )

        corrected_document, apply_error = _apply_private(
            document,
            correction_intent,
            section_context=section_context,
            scaffold=scaffold,
            defaults=defaults,
            channel_aliases=channel_aliases,
            header_aliases=header_aliases,
        )
        if corrected_document is None:
            return _failure(
                VisualCorrectionStopReason.PRIVATE_APPLY_FAILED,
                apply_error or "The correction could not be applied privately.",
                artifact=artifact,
                correction=correction,
                metrics=metrics,
            )

        preservation_error = _preservation_error(document, corrected_document, section_id)
        if preservation_error is not None:
            return _failure(
                VisualCorrectionStopReason.PRESERVATION_FAILED,
                preservation_error,
                artifact=artifact,
                correction=correction,
                metrics=metrics,
            )
        postcondition_issues = _semantic_issues(
            corrected_document,
            original_intent,
            section_context=section_context,
            scaffold=scaffold,
            defaults=defaults,
            channel_aliases=channel_aliases,
            header_aliases=header_aliases,
        )
        if postcondition_issues:
            return _failure(
                VisualCorrectionStopReason.POSTCONDITION_FAILED,
                *postcondition_issues,
                artifact=artifact,
                correction=correction,
                metrics=metrics,
            )
        correction_issues = _semantic_issues(
            corrected_document,
            correction_intent,
            section_context=section_context,
            scaffold=scaffold,
            defaults=defaults,
            channel_aliases=channel_aliases,
            header_aliases=header_aliases,
        )
        if correction_issues:
            return _failure(
                VisualCorrectionStopReason.POSTCONDITION_FAILED,
                *correction_issues,
                artifact=artifact,
                correction=correction,
                metrics=metrics,
            )

        try:
            final_artifact = self.renderer.render(
                corrected_document.model_copy(deep=True),
                section_id=section_id,
            )
        except VisualRenderError as error:
            return _failure(
                VisualCorrectionStopReason.FINAL_RENDER_FAILED,
                str(error),
                artifact=artifact,
                correction=correction,
                metrics=metrics.model_copy(update={"render_count": 2}),
            )
        return VisualCorrectionResult(
            stop_reason=VisualCorrectionStopReason.CORRECTED,
            artifact=final_artifact,
            corrected_document=corrected_document,
            correction=correction,
            metrics=metrics.model_copy(update={"render_count": 2}),
        )


def _failure(
    reason: VisualCorrectionStopReason,
    *messages: str,
    artifact: SectionRenderArtifact | None = None,
    correction: VisualSectionCorrection | None = None,
    metrics: VisualCorrectionMetrics | None = None,
) -> VisualCorrectionResult:
    """Build one redacted failed terminal result."""
    diagnostics = tuple(
        VisualCorrectionDiagnostic(code=reason.value, message=message)
        for message in messages
        if message.strip()
    )
    return VisualCorrectionResult(
        stop_reason=reason,
        artifact=artifact,
        correction=correction,
        diagnostics=diagnostics,
        metrics=metrics or VisualCorrectionMetrics(),
    )


def _section_count(document: AuthoringDocumentSpec, section_id: str) -> int:
    """Count one canonical section without performing discovery."""
    return sum(section.id == section_id for section in document.sections)


def _validate_correction_capability(
    correction: VisualSectionCorrection,
    registry: CapabilityRegistry,
) -> str | None:
    """Require one canonical, section-scoped, explicitly allowed capability."""
    try:
        spec = registry.get(correction.capability_id)
    except KeyError:
        return f"Unknown visual correction capability {correction.capability_id!r}."
    if spec.capability_id != correction.capability_id:
        return f"Visual correction capability must use canonical id {spec.capability_id!r}."
    if spec.capability_id not in VISUAL_SECTION_CAPABILITIES:
        return f"Visual correction capability {spec.capability_id!r} is not allowed."
    if spec.category != "section" or not spec.supports_v2:
        return (
            f"Visual correction capability {spec.capability_id!r} is not a v2 section capability."
        )
    return None


def _correction_context(
    correction: VisualSectionCorrection,
    section_context: ResolvedSectionContext,
) -> EnrichedSemanticContext:
    """Turn accepted visual semantics into one isolated existing-section task."""
    task = SectionTask(
        goal=correction.requested_adjustment,
        capability_ids=(correction.capability_id,),
        existing_section_hint="host-selected section",
        requirements=(correction.issue, correction.requested_adjustment),
        constraints=(
            "Change only the existing section root: title, subtitle, or depth range.",
            "Do not emit tracks, data sources, bindings, fills, annotations, or report fields.",
        ),
    )
    return EnrichedSemanticContext(
        plan=SemanticPlan(summary="One bounded visual section correction", section_tasks=(task,)),
        sections=(section_context.model_copy(update={"task_index": 0}),),
        report=ReportContext(),
    )


def _available_channels(
    section_context: ResolvedSectionContext,
) -> list[AuthoringChannelCandidate]:
    """Project the already-enriched section channels for neutral resolution."""
    return [
        AuthoringChannelCandidate(
            mnemonic=channel.mnemonic,
            kind=channel.kind,
            aliases=list(channel.aliases),
            unit=channel.unit,
            description=channel.description,
            value_shape=list(channel.shape),
            source_path=source.canonical_path,
        )
        for source in section_context.sources
        for channel in source.channels
    ]


def _semantic_issues(
    document: AuthoringDocumentSpec,
    intent: AuthoringDocumentIntent,
    *,
    section_context: ResolvedSectionContext,
    scaffold: AuthoringDocumentSpec | None,
    defaults: Mapping[str, object] | None,
    channel_aliases: Sequence[AuthoringChannelAlias | Mapping[str, object]],
    header_aliases: Mapping[str, Sequence[str]] | None,
) -> tuple[str, ...]:
    """Use neutral context/reconciliation layers as a read-only verifier."""
    available_channels: Mapping[str, Sequence[AuthoringChannelInput]] = {}
    if section_context.section_id is not None:
        available_channels = {
            section_context.section_id: _available_channels(section_context),
        }
    resolution = resolve_authoring_context(
        intent,
        existing=document,
        scaffold=scaffold,
        defaults=defaults,
        available_channels=available_channels,
        channel_aliases=channel_aliases,
        header_aliases=header_aliases,
    )
    if not resolution.ready:
        return tuple(issue.message for issue in resolution.issues)
    plan = reconcile_authoring(resolution, existing=document)
    if not plan.ready:
        return tuple(issue.message for issue in plan.issues)
    return tuple(operation.reason for operation in plan.operations)


def _validate_root_section_intent(
    intent: AuthoringDocumentIntent,
    section_id: str,
) -> str | None:
    """Reject child, report, removal, and identity mutations from the worker."""
    report_fields = (
        "title",
        "subtitle",
        "output",
        "page",
        "depth",
        "header",
        "tail",
        "remarks",
    )
    if any(getattr(intent, field_name) is not None for field_name in report_fields):
        return "Visual section corrections may not emit report-wide fields."
    if intent.removals or any(
        getattr(intent, field_name) is not None
        for field_name in ("curve_bindings", "raster_bindings", "fills", "annotations")
    ):
        return "Visual section corrections may not emit global children or removals."
    if not isinstance(intent.sections, list) or len(intent.sections) != 1:
        return "Visual section corrections must emit exactly one section fragment."
    section = intent.sections[0]
    if section.section_id != section_id:
        return "Visual section corrections must use the host-selected section target."
    allowed = {"section_id", "title", "subtitle", "depth_range"}
    if section.supplied_fields().difference(allowed):
        return "Visual section corrections may change only section root fields."
    if any(
        getattr(section, field_name) is not None
        for field_name in ("data_source", "tracks", "extensions")
    ):
        return "Visual section corrections may not change section children or sources."
    if not section.supplied_fields().difference({"section_id"}):
        return "Visual section corrections must contain a sparse root mutation."
    return None


def _apply_private(
    document: AuthoringDocumentSpec,
    intent: AuthoringDocumentIntent,
    *,
    section_context: ResolvedSectionContext,
    scaffold: AuthoringDocumentSpec | None,
    defaults: Mapping[str, object] | None,
    channel_aliases: Sequence[AuthoringChannelAlias | Mapping[str, object]],
    header_aliases: Mapping[str, Sequence[str]] | None,
) -> tuple[AuthoringDocumentSpec | None, str | None]:
    """Apply one accepted intent to a private service copy only."""
    existing = AuthoringDocumentSpec.model_validate(deepcopy(document).model_dump(mode="python"))
    available_channels = {}
    if section_context.section_id is not None:
        available_channels[section_context.section_id] = _available_channels(section_context)
    resolution = resolve_authoring_context(
        intent,
        existing=existing,
        scaffold=scaffold,
        defaults=defaults,
        available_channels=available_channels,
        channel_aliases=channel_aliases,
        header_aliases=header_aliases,
    )
    plan = reconcile_authoring(resolution, existing=existing)
    if not plan.ready:
        return None, "; ".join(issue.message for issue in plan.issues)
    service = AuthoringService(existing)
    execution = execute_authoring_plan(service, plan)
    if not execution.success:
        return None, "; ".join(execution.errors) or "Private authoring execution failed."
    validation = service.validate()
    if not validation.valid:
        return None, "; ".join(validation.errors) or "Private document validation failed."
    return service.document, None


def _preservation_error(
    original: AuthoringDocumentSpec,
    corrected: AuthoringDocumentSpec,
    section_id: str,
) -> str | None:
    """Ensure root-only correction did not alter unrelated canonical state."""
    before = original.model_dump(mode="json")
    after = corrected.model_dump(mode="json")
    if {key: value for key, value in before.items() if key != "sections"} != {
        key: value for key, value in after.items() if key != "sections"
    }:
        return "Visual correction changed report-wide canonical state."
    before_sections = {section["id"]: section for section in before["sections"]}
    after_sections = {section["id"]: section for section in after["sections"]}
    if list(before_sections) != list(after_sections):
        return "Visual correction changed section identity or order."
    for current_id, before_section in before_sections.items():
        after_section = after_sections[current_id]
        if current_id != section_id and before_section != after_section:
            return "Visual correction changed a non-target section."
        if current_id == section_id:
            for field_name in ("id", "tracks", "data_source", "extensions"):
                if before_section.get(field_name) != after_section.get(field_name):
                    return f"Visual correction changed target section field {field_name!r}."
    return None


__all__ = [
    "SectionRenderArtifact",
    "SectionRenderImage",
    "SectionRenderer",
    "VisualCorrectionDiagnostic",
    "VisualCorrectionError",
    "VisualCorrectionMetrics",
    "VisualCorrectionResult",
    "VisualCorrectionStopReason",
    "VisualEvaluator",
    "VisualReviewDecision",
    "VisualReviewRequest",
    "VisualRenderError",
    "VisualSectionCorrection",
    "VisualSectionCorrectionCoordinator",
    "VisualReviewError",
    "VISUAL_SECTION_CAPABILITIES",
]
