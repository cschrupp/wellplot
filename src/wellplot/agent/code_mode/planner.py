"""Static semantic planning for the Code Mode v2 authoring path."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ...capabilities import CapabilityRegistry
from ..providers.base import (
    ModelBackendProtocol,
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
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> SemanticPlan:
        """Make exactly one structured provider call for a semantic plan."""
        if not isinstance(request, str) or not request.strip():
            raise ValueError("Planning request must be a non-empty string.")

        context = {
            "request": request,
            "mode": mode,
            "current_document_summary": dict(current_document_summary or {}),
            "capabilities": _planning_catalog(self.registry),
        }
        provider_request = StructuredGenerationRequest(
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
        generated = await self.backend.generate_structured(
            provider_request,
            response_model=SemanticPlan,
        )
        plan = SemanticPlan.model_validate(generated.value)
        return validate_semantic_plan(plan, self.registry)


def validate_semantic_plan(plan: SemanticPlan, registry: CapabilityRegistry) -> SemanticPlan:
    """Validate selected capabilities without resolving document structure."""
    if plan.report_task is not None:
        _validate_capabilities(
            plan.report_task.capability_ids,
            registry,
            task_kind="report",
        )

    for task in plan.section_tasks:
        specs = _validate_capabilities(task.capability_ids, registry, task_kind="section")
        categories = {spec.category for spec in specs}
        if "section" not in categories:
            raise ValueError(
                "Each SectionTask must select at least one registered section capability."
            )
        if "report" in categories:
            raise ValueError("A SectionTask cannot select a report capability.")
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
            raise ValueError(f"Unknown capability id {capability_id!r}.") from exc
        if spec.capability_id != capability_id:
            raise ValueError(
                f"Capability selection must use canonical id {spec.capability_id!r}, "
                f"not alias {capability_id!r}."
            )
        if task_kind == "report" and spec.category != "report":
            raise ValueError(
                f"ReportTask capability {capability_id!r} has category {spec.category!r}; "
                "only report capabilities are allowed."
            )
        specs.append(spec)
    return tuple(specs)


def _planning_catalog(registry: CapabilityRegistry) -> tuple[dict[str, object], ...]:
    """Expose only static semantic capability descriptors to the provider."""
    catalog: list[dict[str, object]] = []
    for descriptor in registry.planning_catalog():
        catalog.append(
            {
                "id": descriptor["id"],
                "category": descriptor["category"],
                "description": descriptor["description"],
                "planning_hints": descriptor.get("planning_hints", []),
                "schema_version": descriptor.get("schema_version", "1"),
            }
        )
    return tuple(catalog)


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
    "ReportTask",
    "SectionTask",
    "SemanticPlan",
    "SemanticPlanner",
    "validate_semantic_plan",
]
