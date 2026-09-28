"""Deterministic post-planner capability admissibility checks."""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...capabilities import CapabilityRegistry
from .planner import PlannerSemanticError, SectionTask, SemanticPlan, validate_semantic_plan

REFERENCE_POLICY_VERSION = "cm58.reference-admissibility.v1"
_REFERENCE_CAPABILITY = "track.reference"
_NORMAL_CAPABILITY = "track.normal"
_ARRAY_CAPABILITY = "track.array"
_RASTER_CAPABILITY = "binding.raster"
_CURVE_CAPABILITY = "binding.curve"


class ReferenceIntent(StrEnum):
    """Classified reference-track intent from the original user request."""

    EXPLICITLY_REQUESTED = "explicitly_requested"
    EXPLICITLY_FORBIDDEN = "explicitly_forbidden"
    UNSPECIFIED = "unspecified"
    CONFLICTING = "conflicting"


class CapabilitySafetyActionKind(StrEnum):
    """Deterministic transformations available to the safety layer."""

    REMOVE_REFERENCE = "remove_reference"
    REPLACE_REFERENCE_WITH_NORMAL = "replace_reference_with_normal"


class _SafetyModel(BaseModel):
    """Strict immutable model configuration for safety evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CapabilitySafetyAction(_SafetyModel):
    """One bounded reference-capability repair action."""

    kind: CapabilitySafetyActionKind
    section_index: int = Field(ge=0)
    reason: Literal["reference_not_requested", "reference_explicitly_forbidden"]


class CapabilitySafetyEvidence(_SafetyModel):
    """Provider-free evidence safe to retain in graph state."""

    policy_version: Literal[REFERENCE_POLICY_VERSION] = REFERENCE_POLICY_VERSION
    reference_intent: ReferenceIntent
    changed: bool
    actions: tuple[CapabilitySafetyAction, ...] = ()


class CapabilitySafetyResult(_SafetyModel):
    """Validated plan and bounded evidence returned by the safety layer."""

    policy_version: Literal[REFERENCE_POLICY_VERSION] = REFERENCE_POLICY_VERSION
    safe_plan: SemanticPlan
    reference_intent: ReferenceIntent
    changed: bool
    actions: tuple[CapabilitySafetyAction, ...] = ()

    def evidence(self) -> CapabilitySafetyEvidence:
        """Return graph-safe evidence without retaining the safe plan."""
        return CapabilitySafetyEvidence(
            policy_version=self.policy_version,
            reference_intent=self.reference_intent,
            changed=self.changed,
            actions=self.actions,
        )


class CapabilitySafetyFailure(RuntimeError):
    """Terminal deterministic failure from an unsafe reference repair."""

    def __init__(self, code: str, safe_message: str) -> None:
        """Initialize a bounded provider-neutral failure."""
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


_POSITIVE_REFERENCE_PHRASES = (
    "depth reference",
    "reference track",
    "reference column",
    "reference lane",
    "depth track",
    "depth column",
    "depth lane",
    "depth marker",
    "depth ruler",
    "depth referenced",
)
_NEGATIVE_REFERENCE_PATTERNS = (
    r"\bwithout(?: a| an| the)? reference column\b",
    r"\bwithout(?: a| an| the)? depth track\b",
    r"\bno reference track\b",
    r"\bno(?: a| an| the)? depth track\b",
    r"\bno depth column\b",
    r"\bomit(?: the| a| an)? reference track\b",
    r"\bexclude(?: the| a| an)? depth reference\b",
    r"\bdo not add(?: the| a| an)? reference track\b",
    r"\bdo not include(?: the| a| an)? depth column\b",
)


def _normalize_request(request: str) -> str:
    """Normalize Unicode and punctuation without retaining the request."""
    normalized = unicodedata.normalize("NFKC", request).casefold()
    return "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )


def _positive_matches(text: str) -> list[re.Match[str]]:
    """Find bounded positive reference phrases."""
    return [
        match
        for phrase in _POSITIVE_REFERENCE_PHRASES
        for match in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", text)
    ]


def _negative_matches(text: str) -> list[re.Match[str]]:
    """Find bounded negative reference constructions."""
    return [
        match for pattern in _NEGATIVE_REFERENCE_PATTERNS for match in re.finditer(pattern, text)
    ]


def classify_reference_intent(request: str) -> ReferenceIntent:
    """Classify explicit reference intent without using planner-generated prose."""
    if not isinstance(request, str):
        raise TypeError("Reference intent classification requires text.")
    text = _normalize_request(request)
    negative = _negative_matches(text)
    positive = _positive_matches(text)
    independent_positive = [
        match
        for match in positive
        if not any(
            match.start() < other.end() and other.start() < match.end() for other in negative
        )
    ]
    if negative and independent_positive:
        return ReferenceIntent.CONFLICTING
    if negative:
        return ReferenceIntent.EXPLICITLY_FORBIDDEN
    if positive:
        return ReferenceIntent.EXPLICITLY_REQUESTED
    return ReferenceIntent.UNSPECIFIED


def _replace_task_capabilities(
    task: SectionTask,
    *,
    section_index: int,
    reason: Literal["reference_not_requested", "reference_explicitly_forbidden"],
) -> tuple[SectionTask, CapabilitySafetyAction]:
    """Repair one task while preserving all non-reference capability order."""
    capability_ids = list(task.capability_ids)
    if _NORMAL_CAPABILITY in capability_ids or (
        _ARRAY_CAPABILITY in capability_ids and _RASTER_CAPABILITY in capability_ids
    ):
        repaired_ids = [item for item in capability_ids if item != _REFERENCE_CAPABILITY]
        action_kind = CapabilitySafetyActionKind.REMOVE_REFERENCE
    elif _CURVE_CAPABILITY in capability_ids:
        repaired_ids = [
            _NORMAL_CAPABILITY if item == _REFERENCE_CAPABILITY else item for item in capability_ids
        ]
        action_kind = CapabilitySafetyActionKind.REPLACE_REFERENCE_WITH_NORMAL
    else:
        raise CapabilitySafetyFailure(
            "reference_repair_would_empty_section",
            "Reference capability cannot be removed without emptying the section.",
        )
    return (
        task.model_copy(update={"capability_ids": tuple(repaired_ids)}),
        CapabilitySafetyAction(kind=action_kind, section_index=section_index, reason=reason),
    )


def enforce_capability_safety(
    *,
    request: str,
    plan: SemanticPlan,
    registry: CapabilityRegistry,
) -> CapabilitySafetyResult:
    """Enforce v1 reference admissibility before semantic enrichment."""
    intent = classify_reference_intent(request)
    has_reference = any(_REFERENCE_CAPABILITY in task.capability_ids for task in plan.section_tasks)
    if intent is ReferenceIntent.EXPLICITLY_REQUESTED or not has_reference:
        return CapabilitySafetyResult(
            safe_plan=plan,
            reference_intent=intent,
            changed=False,
        )
    if intent is ReferenceIntent.CONFLICTING:
        raise CapabilitySafetyFailure(
            "reference_intent_conflict",
            "Conflicting reference instructions cannot be resolved deterministically.",
        )

    reason: Literal["reference_not_requested", "reference_explicitly_forbidden"]
    if intent is ReferenceIntent.EXPLICITLY_FORBIDDEN:
        reason = "reference_explicitly_forbidden"
    else:
        reason = "reference_not_requested"
    repaired_tasks: list[SectionTask] = []
    actions: list[CapabilitySafetyAction] = []
    for section_index, task in enumerate(plan.section_tasks):
        if _REFERENCE_CAPABILITY not in task.capability_ids:
            repaired_tasks.append(task)
            continue
        repaired_task, action = _replace_task_capabilities(
            task,
            section_index=section_index,
            reason=reason,
        )
        repaired_tasks.append(repaired_task)
        actions.append(action)

    repaired_plan = plan.model_copy(update={"section_tasks": tuple(repaired_tasks)})
    try:
        validate_semantic_plan(repaired_plan, registry)
    except PlannerSemanticError as error:
        raise CapabilitySafetyFailure(
            "reference_repair_invalid",
            "Deterministic reference repair produced an invalid semantic plan.",
        ) from error
    return CapabilitySafetyResult(
        safe_plan=repaired_plan,
        reference_intent=intent,
        changed=True,
        actions=tuple(actions),
    )


__all__ = [
    "CapabilitySafetyAction",
    "CapabilitySafetyActionKind",
    "CapabilitySafetyEvidence",
    "CapabilitySafetyFailure",
    "CapabilitySafetyResult",
    "REFERENCE_POLICY_VERSION",
    "ReferenceIntent",
    "classify_reference_intent",
    "enforce_capability_safety",
]
