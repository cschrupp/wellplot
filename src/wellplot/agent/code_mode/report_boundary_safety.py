"""Deterministic post-planner report-boundary admissibility checks."""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from ...capabilities import CapabilityRegistry
from .planner import PlannerSemanticError, SemanticPlan, validate_semantic_plan

REPORT_BOUNDARY_POLICY_VERSION = "cm58.report-boundary.v2"
_REPORT_CAPABILITY = "report.standard"


class ReportBoundaryIntent(StrEnum):
    """Classified report-versus-section intent from the original request."""

    REPORT_ONLY = "report_only"
    SECTION_ONLY = "section_only"
    MIXED = "mixed"
    UNSPECIFIED = "unspecified"


class ReportBoundaryActionKind(StrEnum):
    """Deterministic report-boundary transformations."""

    ADD_REPORT_STANDARD = "add_report_standard"
    REMOVE_REPORT_TASK = "remove_report_task"


class _ReportBoundaryModel(BaseModel):
    """Strict immutable model configuration for report-boundary evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ReportBoundaryAction(_ReportBoundaryModel):
    """One bounded report-boundary repair action."""

    kind: ReportBoundaryActionKind
    reason: Literal[
        "explicit_report_intent_missing_capability",
        "explicit_section_only_intent",
    ]


class ReportBoundarySafetyEvidence(_ReportBoundaryModel):
    """Provider-free evidence safe to retain in graph state."""

    policy_version: Literal[REPORT_BOUNDARY_POLICY_VERSION] = REPORT_BOUNDARY_POLICY_VERSION
    intent: ReportBoundaryIntent
    changed: bool
    actions: tuple[ReportBoundaryAction, ...] = ()


class ReportBoundarySafetyResult(_ReportBoundaryModel):
    """Validated plan and bounded evidence returned by the safety layer."""

    policy_version: Literal[REPORT_BOUNDARY_POLICY_VERSION] = REPORT_BOUNDARY_POLICY_VERSION
    safe_plan: SemanticPlan
    intent: ReportBoundaryIntent
    changed: bool
    actions: tuple[ReportBoundaryAction, ...] = ()

    def evidence(self) -> ReportBoundarySafetyEvidence:
        """Return graph-safe evidence without retaining the safe plan."""
        return ReportBoundarySafetyEvidence(
            policy_version=self.policy_version,
            intent=self.intent,
            changed=self.changed,
            actions=self.actions,
        )


class ReportBoundarySafetyFailure(RuntimeError):
    """Terminal deterministic failure from an unsafe report-boundary repair."""

    def __init__(self, code: str, safe_message: str) -> None:
        """Initialize a bounded provider-neutral failure."""
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


_REPORT_SIGNALS = (
    "report",
    "report cover",
    "memo",
    "brief",
    "handover brief",
    "packet",
    "field review packet",
    "completion summary",
    "interpretation summary",
    "review summary",
    "heading",
    "subtitle",
    "prepared by",
    "preparer",
    "report title",
    "report header",
    "header field",
    "page size",
    "page orientation",
    "service title",
    "output dpi",
    "report note",
    "review note",
    "remark",
)
_SECTION_SIGNALS = (
    "section",
    "sections",
    "panel",
    "panels",
    "view",
    "views",
    "track",
    "tracks",
    "curve",
    "curves",
    "image",
    "images",
    "waveform",
    "waveforms",
    "raster",
    "rasters",
    "plot",
    "plots",
    "log view",
    "log views",
    "log display",
    "log displays",
)
_SECTION_DISPLAY_SIGNALS = (
    "scalar display",
    "scalar displays",
    "shared display",
    "shared displays",
)


def _normalize_request(request: str) -> str:
    """Normalize request text without retaining or returning the input."""
    normalized = unicodedata.normalize("NFKC", request).casefold()
    normalized = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )
    return re.sub(r"\s+", " ", normalized).strip()


def _contains_signal(text: str, signal: str) -> bool:
    """Match one whole-word signal after deterministic normalization."""
    return re.search(rf"(?<!\w){re.escape(signal)}(?!\w)", text) is not None


def classify_report_boundary_intent(request: str) -> ReportBoundaryIntent:
    """Classify report and section intent using only the original request."""
    if not isinstance(request, str):
        raise TypeError("Report-boundary classification requires text.")
    text = _normalize_request(request)
    report_requested = any(_contains_signal(text, signal) for signal in _REPORT_SIGNALS)
    section_requested = any(
        _contains_signal(text, signal) for signal in (*_SECTION_SIGNALS, *_SECTION_DISPLAY_SIGNALS)
    )
    if report_requested and section_requested:
        return ReportBoundaryIntent.MIXED
    if report_requested:
        return ReportBoundaryIntent.REPORT_ONLY
    if section_requested:
        return ReportBoundaryIntent.SECTION_ONLY
    return ReportBoundaryIntent.UNSPECIFIED


def _repair_report_capability(
    plan: SemanticPlan,
    *,
    intent: ReportBoundaryIntent,
    registry: CapabilityRegistry,
) -> ReportBoundarySafetyResult:
    """Add the core report capability while preserving report semantics."""
    report_task = plan.report_task
    if report_task is None:
        code = (
            "report_task_missing_for_explicit_report_intent"
            if intent is ReportBoundaryIntent.REPORT_ONLY
            else "report_task_missing_for_mixed_intent"
        )
        raise ReportBoundarySafetyFailure(
            code,
            "Explicit report intent has no planner-created report task to repair.",
        )
    if not report_task.capability_ids:
        repaired_task = report_task.model_copy(update={"capability_ids": (_REPORT_CAPABILITY,)})
        repaired_plan = plan.model_copy(update={"report_task": repaired_task})
        return _validated_repair(
            repaired_plan,
            registry=registry,
            intent=intent,
            action=ReportBoundaryAction(
                kind=ReportBoundaryActionKind.ADD_REPORT_STANDARD,
                reason="explicit_report_intent_missing_capability",
            ),
        )
    if _REPORT_CAPABILITY not in report_task.capability_ids:
        raise ReportBoundarySafetyFailure(
            "report_standard_missing_from_nonempty_report_task",
            "Explicit report intent selected an unsupported report capability set.",
        )
    return ReportBoundarySafetyResult(
        safe_plan=plan,
        intent=intent,
        changed=False,
    )


def _validated_repair(
    plan: SemanticPlan,
    *,
    registry: CapabilityRegistry,
    intent: ReportBoundaryIntent,
    action: ReportBoundaryAction,
) -> ReportBoundarySafetyResult:
    """Rebuild and semantically validate one modified plan."""
    try:
        validated_plan = SemanticPlan.model_validate(plan.model_dump(mode="python"))
        validate_semantic_plan(validated_plan, registry)
    except (PlannerSemanticError, ValidationError) as error:
        raise ReportBoundarySafetyFailure(
            "report_boundary_repair_invalid",
            "Deterministic report-boundary repair produced an invalid semantic plan.",
        ) from error
    return ReportBoundarySafetyResult(
        safe_plan=validated_plan,
        intent=intent,
        changed=True,
        actions=(action,),
    )


def _remove_report_task(
    plan: SemanticPlan,
    *,
    registry: CapabilityRegistry,
) -> ReportBoundarySafetyResult:
    """Remove an unrequested report task while preserving all sections."""
    if not plan.section_tasks:
        raise ReportBoundarySafetyFailure(
            "report_removal_would_empty_plan",
            "An unrequested report task cannot be removed because no section work remains.",
        )
    repaired_plan = plan.model_copy(update={"report_task": None})
    return _validated_repair(
        repaired_plan,
        registry=registry,
        intent=ReportBoundaryIntent.SECTION_ONLY,
        action=ReportBoundaryAction(
            kind=ReportBoundaryActionKind.REMOVE_REPORT_TASK,
            reason="explicit_section_only_intent",
        ),
    )


def enforce_report_boundary_safety(
    *,
    request: str,
    plan: SemanticPlan,
    registry: CapabilityRegistry,
) -> ReportBoundarySafetyResult:
    """Enforce v2 report-boundary admissibility before semantic enrichment."""
    intent = classify_report_boundary_intent(request)
    report_task = plan.report_task

    if intent is ReportBoundaryIntent.REPORT_ONLY:
        if report_task is None:
            raise ReportBoundarySafetyFailure(
                "report_task_missing_for_explicit_report_intent",
                "Explicit report intent has no planner-created report task to repair.",
            )
        if plan.section_tasks:
            raise ReportBoundarySafetyFailure(
                "unexpected_section_work_for_report_only",
                "Report-only intent produced unexpected section work.",
            )
        return _repair_report_capability(plan, intent=intent, registry=registry)

    if intent is ReportBoundaryIntent.MIXED:
        if report_task is None:
            raise ReportBoundarySafetyFailure(
                "report_task_missing_for_mixed_intent",
                "Mixed intent has no planner-created report task to repair.",
            )
        if not plan.section_tasks:
            raise ReportBoundarySafetyFailure(
                "section_task_missing_for_mixed_intent",
                "Mixed intent has no planner-created section task.",
            )
        return _repair_report_capability(plan, intent=intent, registry=registry)

    if intent is ReportBoundaryIntent.SECTION_ONLY and report_task is not None:
        return _remove_report_task(plan, registry=registry)

    if (
        intent is ReportBoundaryIntent.UNSPECIFIED
        and report_task is not None
        and not report_task.capability_ids
    ):
        raise ReportBoundarySafetyFailure(
            "empty_report_task_with_unspecified_intent",
            "An empty report task cannot be resolved without explicit report intent.",
        )

    return ReportBoundarySafetyResult(
        safe_plan=plan,
        intent=intent,
        changed=False,
    )


__all__ = [
    "REPORT_BOUNDARY_POLICY_VERSION",
    "ReportBoundaryAction",
    "ReportBoundaryActionKind",
    "ReportBoundaryIntent",
    "ReportBoundarySafetyEvidence",
    "ReportBoundarySafetyFailure",
    "ReportBoundarySafetyResult",
    "classify_report_boundary_intent",
    "enforce_report_boundary_safety",
]
