"""Static semantic planning for the Code Mode v2 authoring path."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ...capabilities import CapabilityRegistry
from ..providers.base import (
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderRequestError,
    StructuredGenerationRequest,
)

CompilationMode = Literal["reconstruct", "revise"]


class _SemanticModel(BaseModel):
    """Shared strict configuration for planner response models."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class ReportTask(_SemanticModel):
    """Semantic requirements for report-wide work."""

    goal: str = Field(min_length=1)
    capability_ids: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("capability_ids", "requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject blank semantic entries while preserving provider order."""
        _require_nonempty_items(values)
        return values


class SectionTask(_SemanticModel):
    """Semantic requirements for one independently compilable section task."""

    goal: str = Field(min_length=1)
    capability_ids: tuple[str, ...] = Field(min_length=1)
    existing_section_hint: str | None = Field(default=None, min_length=1)
    source_hints: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("capability_ids", "source_hints", "requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject blank semantic entries while preserving provider order."""
        _require_nonempty_items(values)
        return values


class PlannerSemanticError(ValueError):
    """One expected semantic error in provider-produced planner output."""

    def __init__(self, code: str, safe_message: str) -> None:
        """Initialize a stable, provider-safe correction diagnostic."""
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


class PlannerSemanticFailure(RuntimeError):
    """Final bounded planner failure after one semantic correction attempt."""

    def __init__(self, code: str, safe_message: str) -> None:
        """Initialize a stable terminal planner diagnostic."""
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


class SemanticPlan(_SemanticModel):
    """Small planner result that describes work without document mechanics."""

    summary: str = Field(min_length=1)
    report_task: ReportTask | None = None
    section_tasks: tuple[SectionTask, ...] = ()
    unresolved_requirements: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_work_units(self) -> SemanticPlan:
        """Require at least one report or section work unit."""
        if self.report_task is None and not self.section_tasks:
            raise ValueError("SemanticPlan must contain a report task or section tasks.")
        return self

    @field_validator("unresolved_requirements")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject blank unresolved requirements."""
        _require_nonempty_items(values)
        return values


@dataclass(frozen=True, slots=True)
class SemanticPlanner:
    """Generate and validate one static semantic plan."""

    backend: ModelBackendProtocol
    registry: CapabilityRegistry

    async def plan(
        self,
        *,
        request: str,
        mode: CompilationMode,
        current_document_summary: Mapping[str, object] | None = None,
        source_summary: Mapping[str, object] | None = None,
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> SemanticPlan:
        """Make at most two bounded structured calls for a semantic plan."""
        if not isinstance(request, str) or not request.strip():
            raise ValueError("Planning request must be a non-empty string.")

        context = {
            "request": request,
            "mode": mode,
            "current_document_summary": dict(current_document_summary or {}),
            "source_summary": _safe_source_summary(source_summary),
            "capabilities": _planning_catalog(self.registry),
        }
        invalid_response_retry_used = False
        try:
            generated = await self.backend.generate_structured(
                _planning_request(
                    context=context,
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
                response_model=SemanticPlan,
            )
        except ProviderRequestError as error:
            if error.category is not ProviderFailureCategory.INVALID_RESPONSE:
                raise
            invalid_response_retry_used = True
            generated = await self.backend.generate_structured(
                _planning_request(
                    context=context,
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
                response_model=SemanticPlan,
            )
        plan = SemanticPlan.model_validate(generated.value)
        try:
            return validate_semantic_plan(plan, self.registry)
        except PlannerSemanticError as first_error:
            if invalid_response_retry_used:
                raise PlannerSemanticFailure(
                    first_error.code,
                    "Planner returned a semantically invalid plan after one correction.",
                ) from first_error
            corrected = await self.backend.generate_structured(
                _correction_request(
                    mode=mode,
                    request=request,
                    source_summary=source_summary,
                    previous_plan=plan,
                    diagnostic=first_error,
                    registry=self.registry,
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
                response_model=SemanticPlan,
            )
            corrected_plan = SemanticPlan.model_validate(corrected.value)
            try:
                return validate_semantic_plan(corrected_plan, self.registry)
            except PlannerSemanticError as second_error:
                raise PlannerSemanticFailure(
                    second_error.code,
                    "Planner returned a semantically invalid plan after one correction.",
                ) from second_error


def validate_semantic_plan(plan: SemanticPlan, registry: CapabilityRegistry) -> SemanticPlan:
    """Validate selected capabilities without resolving document structure."""
    if plan.report_task is not None:
        report_specs = _validate_capabilities(
            plan.report_task.capability_ids,
            registry,
            task_kind="report",
        )
        _validate_unique_capabilities(plan.report_task.capability_ids)
        _validate_parent_closure(report_specs, plan.report_task.capability_ids)

    for task in plan.section_tasks:
        specs = _validate_capabilities(task.capability_ids, registry, task_kind="section")
        _validate_unique_capabilities(task.capability_ids)
        categories = {spec.category for spec in specs}
        if "section" not in categories:
            raise PlannerSemanticError(
                "missing_section_capability",
                "Each SectionTask must select at least one registered section capability.",
            )
        if "report" in categories:
            raise PlannerSemanticError(
                "wrong_task_category",
                "SectionTask selected a report capability.",
            )
        _validate_parent_closure(specs, task.capability_ids)
    return plan


def _validate_capabilities(
    capability_ids: tuple[str, ...],
    registry: CapabilityRegistry,
    *,
    task_kind: Literal["report", "section"],
) -> tuple[object, ...]:
    """Resolve canonical capability IDs and enforce task-level categories."""
    specs = []
    for capability_id in capability_ids:
        try:
            spec = registry.get(capability_id)
        except KeyError as exc:
            raise PlannerSemanticError(
                "unknown_capability",
                "Unknown capability id selected by planner.",
            ) from exc
        if spec.capability_id != capability_id:
            raise PlannerSemanticError(
                "noncanonical_capability",
                "Planner selected a non-canonical capability identifier.",
            )
        if task_kind == "report" and spec.category != "report":
            raise PlannerSemanticError(
                "wrong_task_category",
                (
                    "ReportTask selected a non-report capability; only report capabilities "
                    "are allowed."
                ),
            )
        specs.append(spec)
    return tuple(specs)


def _validate_unique_capabilities(capability_ids: tuple[str, ...]) -> None:
    """Reject repeated canonical capability types without normalizing them."""
    if len(capability_ids) == len(set(capability_ids)):
        return
    raise PlannerSemanticError(
        "duplicate_capability",
        "A semantic task selected the same capability type more than once.",
    )


def _validate_parent_closure(
    specs: tuple[object, ...],
    capability_ids: tuple[str, ...],
) -> None:
    """Require every selected capability to include one registered parent."""
    selected = set(capability_ids)
    for spec in specs:
        allowed_parents = tuple(getattr(spec, "allowed_parents", ()))
        if not allowed_parents or selected.intersection(allowed_parents):
            continue
        parent_text = ", ".join(allowed_parents)
        raise PlannerSemanticError(
            "missing_capability_parent",
            f"Capability {spec.capability_id!r} requires one selected parent capability "
            f"from: {parent_text}.",
        )


def _planning_catalog(registry: CapabilityRegistry) -> tuple[dict[str, object], ...]:
    """Expose only static semantic capability descriptors to the provider."""
    catalog: list[dict[str, object]] = []
    for descriptor in registry.planning_catalog():
        catalog.append(
            {
                "id": descriptor["id"],
                "category": descriptor["category"],
                "description": descriptor["description"],
                "allowed_parents": descriptor.get("allowed_parents", []),
                "planning_hints": descriptor.get("planning_hints", []),
                "schema_version": descriptor.get("schema_version", "1"),
            }
        )
    return tuple(catalog)


def _planning_request(
    *,
    context: Mapping[str, object],
    timeout_seconds: float,
    temperature: float | None,
    max_output_tokens: int | None,
) -> StructuredGenerationRequest:
    """Build the single initial structured planner request."""
    return StructuredGenerationRequest(
        system_prompt=_PLANNER_SYSTEM_PROMPT,
        user_prompt=(
            "Create one SemanticPlan for this request. Return only the supplied "
            "structured response model.\n\nContext:\n"
            + json.dumps(context, sort_keys=True, separators=(",", ":"))
        ),
        timeout_seconds=timeout_seconds,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _correction_request(
    *,
    mode: CompilationMode,
    request: str,
    source_summary: Mapping[str, object] | None = None,
    previous_plan: SemanticPlan,
    diagnostic: PlannerSemanticError,
    registry: CapabilityRegistry,
    timeout_seconds: float,
    temperature: float | None,
    max_output_tokens: int | None,
) -> StructuredGenerationRequest:
    """Build one bounded correction request without host identities."""
    context = {
        "mode": mode,
        "original_request": _safe_correction_text(request),
        "source_summary": _safe_source_summary(source_summary),
        "capabilities": _planning_catalog(registry),
        "previous_plan": _safe_plan_for_correction(previous_plan),
        "diagnostic": {
            "code": diagnostic.code,
            "message": diagnostic.safe_message,
        },
    }
    return StructuredGenerationRequest(
        system_prompt=_PLANNER_SYSTEM_PROMPT,
        user_prompt=(
            "Correct the previous SemanticPlan using the original request, the "
            "previous plan, the diagnostic, and the capability catalogue. Preserve "
            "all explicit source and scientific semantics while correcting the "
            "reported problem. Return the corrected structured response model."
            "\n\nCorrection context:\n" + json.dumps(context, sort_keys=True, separators=(",", ":"))
        ),
        timeout_seconds=timeout_seconds,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _safe_plan_for_correction(plan: SemanticPlan) -> dict[str, object]:
    """Project semantic intent without host identities or canonical source IDs."""
    report_task = None if plan.report_task is None else _safe_task_for_correction(plan.report_task)
    return {
        "summary": _safe_correction_text(plan.summary),
        "report_task": report_task,
        "section_tasks": [_safe_task_for_correction(task) for task in plan.section_tasks],
    }


def _safe_task_for_correction(task: ReportTask | SectionTask) -> dict[str, object]:
    """Preserve semantic task text while excluding host-owned selection fields."""
    payload: dict[str, object] = {
        "goal": _safe_correction_text(task.goal),
        "capability_ids": list(task.capability_ids),
        "requirements": [_safe_correction_text(value) for value in task.requirements],
        "constraints": [_safe_correction_text(value) for value in task.constraints],
    }
    if isinstance(task, SectionTask):
        payload["source_hints"] = [_safe_correction_text(value) for value in task.source_hints]
    return payload


def _safe_correction_text(value: str) -> str:
    """Redact path-shaped text from provider-controlled semantic prose."""
    return re.sub(r"(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s,;]+", "[redacted-path]", value)


def _safe_source_summary(summary: Mapping[str, object] | None) -> dict[str, object]:
    """Project host source facts without IDs, paths, or parser details."""
    if summary is None:
        return {"version": "1", "sources": []}
    raw_sources = summary.get("sources", ())
    if not isinstance(raw_sources, (list, tuple)):
        raise ValueError("Source summary sources must be a sequence.")

    sources: list[dict[str, object]] = []
    for raw_source in raw_sources:
        if not isinstance(raw_source, Mapping):
            raise ValueError("Source summary entries must be mappings.")
        raw_labels = raw_source.get("labels", ())
        raw_channels = raw_source.get("channels", ())
        if not isinstance(raw_labels, (list, tuple)):
            raise ValueError("Source summary labels must be a sequence.")
        if not isinstance(raw_channels, (list, tuple)):
            raise ValueError("Source summary channels must be a sequence.")

        channels: list[dict[str, str]] = []
        for raw_channel in raw_channels:
            if not isinstance(raw_channel, Mapping):
                raise ValueError("Source summary channels must be mappings.")
            mnemonic = raw_channel.get("mnemonic")
            kind = raw_channel.get("kind")
            if not isinstance(mnemonic, str) or not mnemonic.strip():
                raise ValueError("Source summary channel mnemonics must be non-empty text.")
            if not isinstance(kind, str) or not kind.strip():
                raise ValueError("Source summary channel kinds must be non-empty text.")
            channels.append(
                {
                    "mnemonic": _safe_correction_text(mnemonic),
                    "kind": _safe_correction_text(kind),
                }
            )

        labels = [
            _safe_correction_text(label)
            for label in raw_labels
            if isinstance(label, str) and label.strip()
        ]
        sources.append({"labels": labels, "channels": channels})

    version = summary.get("version", "1")
    return {
        "version": _safe_correction_text(str(version)),
        "sources": sources,
    }


def _require_nonempty_items(values: tuple[str, ...]) -> None:
    """Require each semantic list item to contain meaningful text."""
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("Semantic text collections cannot contain blank items.")


_PLANNER_SYSTEM_PROMPT = """You are the semantic planning stage of Wellplot Code Mode v2.
Describe semantic work units only. Do not emit document object IDs, section IDs,
track IDs, binding IDs, component trees, parent relationships, operation order,
insert positions, source paths, source formats, header slot IDs, or data-source
objects. Do not describe SDK calls or mutation steps.

Select capability IDs exactly as listed in the static capability catalogue. A
SectionTask describes what one logical section should accomplish; its list order
does not specify document order or execution order. Existing-section hints are
advisory natural-language clues only and are resolved later by host code.

For each work unit, select the complete set of capability types needed to
represent the requested structure. Capability IDs identify capability types,
not requested object instances; list each capability ID at most once. When a
selected capability declares allowed parent capabilities, select an appropriate
allowed parent needed to contain it, applying the same rule through the
structural capability hierarchy. Do not add capabilities for semantics that were not requested.

When a section request identifies or distinguishes a source, pass, run, or other
input source in natural language, preserve that clue in SectionTask.source_hints.
Source hints are ordered semantic clues for later host resolution. Do not emit
filesystem paths, source formats, host candidate IDs, or invented source
identities. Keep source clues attached to the section they describe.
When the bounded source summary contains multiple sources and the request selects
one of them, copy one supplied source label exactly into source_hints; do not
paraphrase, abbreviate, or invent a source label. The host resolves that label
against its explicit candidates later.

Preserve explicit scientific requirements needed by downstream section work,
including channel names, repeated binding requests, track kinds, scale types,
numeric bounds, units, reverse direction, raster profiles, and sample-axis
values such as origin, step, limits, and tick count. Do not summarize away
explicit values or categorical semantics that a downstream worker needs without
the original request. Use requirements and constraints for this semantic text;
do not emit document mechanics or implementation details.

Report-only requests must use report_task with an empty section_tasks collection;
do not invent a dummy section task.

In revise mode, include only materially changed or newly requested semantic
work. Omitted report or section areas are preserved by later deterministic
stages. Preserve explicit user requirements and constraints verbatim where
possible. Put unsupported requests in unresolved_requirements instead of
inventing capabilities or identities.
"""


__all__ = [
    "CompilationMode",
    "PlannerSemanticError",
    "PlannerSemanticFailure",
    "ReportTask",
    "SectionTask",
    "SemanticPlan",
    "SemanticPlanner",
    "validate_semantic_plan",
]
