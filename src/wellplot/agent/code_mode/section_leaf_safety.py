"""Deterministic safety checks for cross-domain section leaf capabilities."""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ...capabilities import CapabilityRegistry
from .planner import PlannerSemanticError, SectionTask, SemanticPlan, validate_semantic_plan

SECTION_LEAF_POLICY_VERSION = "cm58.section-leaf-admissibility.v1"

_SECTION_CAPABILITY = "section.log_plot"
_NORMAL_CAPABILITY = "track.normal"
_REFERENCE_CAPABILITY = "track.reference"
_ARRAY_CAPABILITY = "track.array"
_CURVE_CAPABILITY = "binding.curve"
_RASTER_CAPABILITY = "binding.raster"
_ANNOTATION_TRACK_CAPABILITY = "track.annotation"
_ANNOTATION_CAPABILITY = "annotation.typed"
_MEANINGFUL_SECTION_CAPABILITIES = frozenset(
    {
        _NORMAL_CAPABILITY,
        _REFERENCE_CAPABILITY,
        _ARRAY_CAPABILITY,
        _CURVE_CAPABILITY,
        _RASTER_CAPABILITY,
        "fill.curve",
    }
)


class _SectionLeafModel(BaseModel):
    """Strict immutable configuration for section-leaf evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SectionLeafRequestEvidence(_SectionLeafModel):
    """Bounded request facts used by the two authorized leakage rules."""

    curve_explicit: bool
    raster_explicit: bool
    section_annotation_explicit: bool
    report_note_explicit: bool


class SectionLeafSafetyActionKind(StrEnum):
    """Deterministic section-leaf transformations available in v1."""

    REMOVE_RASTER_ONLY_CURVE_BINDING = "remove_raster_only_curve_binding"
    REMOVE_REPORT_NOTE_ANNOTATION_LEAKAGE = "remove_report_note_annotation_leakage"


class SectionLeafSafetyAction(_SectionLeafModel):
    """One bounded section-leaf repair action."""

    kind: SectionLeafSafetyActionKind
    section_index: int = Field(ge=0)
    reason: Literal[
        "curve_binding_not_supported_by_raster_only_request",
        "report_note_not_section_annotation",
    ]


class SectionLeafSafetyEvidence(_SectionLeafModel):
    """Provider-free evidence safe to retain in graph state."""

    policy_version: Literal[SECTION_LEAF_POLICY_VERSION] = SECTION_LEAF_POLICY_VERSION
    request_evidence: SectionLeafRequestEvidence
    changed: bool
    actions: tuple[SectionLeafSafetyAction, ...] = ()


class SectionLeafSafetyResult(_SectionLeafModel):
    """Validated plan and bounded evidence returned by the safety layer."""

    policy_version: Literal[SECTION_LEAF_POLICY_VERSION] = SECTION_LEAF_POLICY_VERSION
    safe_plan: SemanticPlan
    request_evidence: SectionLeafRequestEvidence
    changed: bool
    actions: tuple[SectionLeafSafetyAction, ...] = ()

    def evidence(self) -> SectionLeafSafetyEvidence:
        """Return graph-safe evidence without retaining the safe plan."""
        return SectionLeafSafetyEvidence(
            policy_version=self.policy_version,
            request_evidence=self.request_evidence,
            changed=self.changed,
            actions=self.actions,
        )


class SectionLeafSafetyFailure(RuntimeError):
    """Terminal deterministic failure from an unsafe section-leaf repair."""

    def __init__(self, code: str, safe_message: str) -> None:
        """Initialize a bounded provider-neutral failure."""
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


def _normalize_request(request: str) -> str:
    """Normalize request text without retaining or returning the input."""
    normalized = unicodedata.normalize("NFKC", request).casefold()
    normalized = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )
    return re.sub(r"\s+", " ", normalized).strip()


def _contains_any_signal(text: str, signals: tuple[str, ...]) -> bool:
    """Match bounded whole-word signals after deterministic normalization."""
    return any(re.search(rf"(?<!\w){re.escape(signal)}(?!\w)", text) for signal in signals)


_CURVE_SIGNALS = (
    "curve",
    "curves",
    "scalar",
    "scalar curve",
    "scalar curves",
    "regular track",
    "regular tracks",
    "ordinary track",
    "ordinary tracks",
)
_RASTER_SIGNALS = (
    "image",
    "images",
    "waveform",
    "waveforms",
    "raster",
    "rasters",
    "array track",
    "array tracks",
    "array display",
)
_SECTION_ANNOTATION_SIGNALS = (
    "annotation",
    "annotations",
    "annotate",
    "annotated",
    "marker",
    "markers",
    "callout",
    "callouts",
    "plot annotation",
    "track annotation",
    "annotation track",
)
_REPORT_NOTE_SIGNALS = (
    "report note",
    "review note",
    "memo note",
    "completion note",
    "add the note",
    "include the note",
    "remark",
    "report remark",
)


def project_section_leaf_request(request: str) -> SectionLeafRequestEvidence:
    """Project only the bounded request facts needed by CM-58.3."""
    if not isinstance(request, str):
        raise TypeError("Section-leaf request evidence requires text.")
    text = _normalize_request(request)
    return SectionLeafRequestEvidence(
        curve_explicit=_contains_any_signal(text, _CURVE_SIGNALS),
        raster_explicit=_contains_any_signal(text, _RASTER_SIGNALS),
        section_annotation_explicit=_contains_any_signal(text, _SECTION_ANNOTATION_SIGNALS),
        report_note_explicit=_contains_any_signal(text, _REPORT_NOTE_SIGNALS),
    )


def _has_all(capabilities: tuple[str, ...], required: frozenset[str]) -> bool:
    """Check capability membership without changing provider order."""
    return required.issubset(capabilities)


def _replace_capabilities(task: SectionTask, capability_ids: list[str]) -> SectionTask:
    """Copy one task while changing only its capability tuple."""
    return task.model_copy(update={"capability_ids": tuple(capability_ids)})


def _apply_raster_only_rule(
    task: SectionTask,
    *,
    section_index: int,
    evidence: SectionLeafRequestEvidence,
) -> tuple[SectionTask, SectionLeafSafetyAction | None]:
    """Remove one stray curve binding only under the high-confidence signature."""
    capabilities = task.capability_ids
    signature = _has_all(
        capabilities,
        frozenset({_ARRAY_CAPABILITY, _RASTER_CAPABILITY, _CURVE_CAPABILITY}),
    )
    if not (evidence.raster_explicit and not evidence.curve_explicit and signature):
        return task, None
    if _NORMAL_CAPABILITY in capabilities:
        raise SectionLeafSafetyFailure(
            "raster_only_scalar_structure_ambiguous",
            "Raster-only request has an ambiguous normal-track curve structure.",
        )
    return (
        _replace_capabilities(task, [item for item in capabilities if item != _CURVE_CAPABILITY]),
        SectionLeafSafetyAction(
            kind=SectionLeafSafetyActionKind.REMOVE_RASTER_ONLY_CURVE_BINDING,
            section_index=section_index,
            reason="curve_binding_not_supported_by_raster_only_request",
        ),
    )


def _apply_annotation_rule(
    task: SectionTask,
    *,
    section_index: int,
    evidence: SectionLeafRequestEvidence,
) -> tuple[SectionTask, SectionLeafSafetyAction | None]:
    """Remove report-note annotation leakage without emptying a section."""
    capabilities = task.capability_ids
    annotation_capabilities = {
        _ANNOTATION_TRACK_CAPABILITY,
        _ANNOTATION_CAPABILITY,
    }
    if not (
        evidence.report_note_explicit
        and not evidence.section_annotation_explicit
        and annotation_capabilities.intersection(capabilities)
    ):
        return task, None
    if not _MEANINGFUL_SECTION_CAPABILITIES.intersection(capabilities):
        raise SectionLeafSafetyFailure(
            "annotation_prune_would_empty_section",
            "Removing report-note annotation leakage would empty the section.",
        )
    return (
        _replace_capabilities(
            task,
            [item for item in capabilities if item not in annotation_capabilities],
        ),
        SectionLeafSafetyAction(
            kind=SectionLeafSafetyActionKind.REMOVE_REPORT_NOTE_ANNOTATION_LEAKAGE,
            section_index=section_index,
            reason="report_note_not_section_annotation",
        ),
    )


def _revalidate(
    plan: SemanticPlan,
    *,
    registry: CapabilityRegistry,
) -> SemanticPlan:
    """Reconstruct and validate a transformed semantic plan."""
    try:
        validated_plan = SemanticPlan.model_validate(plan.model_dump(mode="python"))
        validate_semantic_plan(validated_plan, registry)
    except (PlannerSemanticError, ValidationError) as error:
        raise SectionLeafSafetyFailure(
            "section_leaf_repair_invalid",
            "Deterministic section-leaf repair produced an invalid semantic plan.",
        ) from error
    return validated_plan


def enforce_section_leaf_safety(
    *,
    request: str,
    plan: SemanticPlan,
    registry: CapabilityRegistry,
) -> SectionLeafSafetyResult:
    """Enforce v1 section-leaf admissibility before semantic enrichment."""
    evidence = project_section_leaf_request(request)
    repaired_tasks: list[SectionTask] = []
    actions: list[SectionLeafSafetyAction] = []
    changed = False
    for section_index, task in enumerate(plan.section_tasks):
        repaired_task, action = _apply_raster_only_rule(
            task,
            section_index=section_index,
            evidence=evidence,
        )
        if action is not None:
            actions.append(action)
            changed = True
        repaired_task, action = _apply_annotation_rule(
            repaired_task,
            section_index=section_index,
            evidence=evidence,
        )
        if action is not None:
            actions.append(action)
            changed = True
        repaired_tasks.append(repaired_task)

    if not changed:
        return SectionLeafSafetyResult(
            safe_plan=plan,
            request_evidence=evidence,
            changed=False,
        )

    repaired_plan = plan.model_copy(update={"section_tasks": tuple(repaired_tasks)})
    validated_plan = _revalidate(repaired_plan, registry=registry)
    return SectionLeafSafetyResult(
        safe_plan=validated_plan,
        request_evidence=evidence,
        changed=True,
        actions=tuple(actions),
    )


__all__ = [
    "SECTION_LEAF_POLICY_VERSION",
    "SectionLeafRequestEvidence",
    "SectionLeafSafetyAction",
    "SectionLeafSafetyActionKind",
    "SectionLeafSafetyEvidence",
    "SectionLeafSafetyFailure",
    "SectionLeafSafetyResult",
    "enforce_section_leaf_safety",
    "project_section_leaf_request",
]
