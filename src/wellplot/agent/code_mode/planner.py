"""Static semantic planning for the Code Mode v2 authoring path."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ...capabilities import CapabilityRegistry
from ..providers.base import (
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderRequestError,
    StructuredGenerationRequest,
)
from ..providers.response_diagnostics import (
    ProviderResponseFailureReason,
    StructuredResponseProviderError,
)
from .obligations import (
    RequestObligation,
    extract_supported_obligations,
    verify_anchor_coverage,
    verify_obligation_spans,
)

CompilationMode = Literal["reconstruct", "revise"]

_SCHEMA_CORRECTION_INSTRUCTION = (
    "Retry the SemanticPlan because the previous response was valid JSON but did not "
    "conform to the supplied structured response model. Return exactly one object "
    "matching the supplied response schema. Do not add undeclared fields. Use the "
    "required field types and satisfy all required non-empty fields. Do not describe "
    "the correction or include prose outside the structured response."
)


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
    obligations: tuple[RequestObligation, ...] = ()

    @field_validator("capability_ids", "requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject blank semantic entries while preserving provider order."""
        _require_nonempty_items(values)
        return values


def _require_section_hint_in_schema(schema: dict[str, object]) -> None:
    """Keep direct Python fixtures ergonomic while requiring provider key presence."""
    required = schema.setdefault("required", [])
    if isinstance(required, list) and "existing_section_hint" not in required:
        required.append("existing_section_hint")


class SectionTask(_SemanticModel):
    """Semantic requirements for one independently compilable section task."""

    goal: str = Field(min_length=1)
    capability_ids: tuple[str, ...] = Field(min_length=1)
    # The key is part of the provider contract even when reconstruction has no
    # existing target.  Revisions reject the explicit null during validation.
    existing_section_hint: str | None = Field(default=None, min_length=1)
    source_hints: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    obligations: tuple[RequestObligation, ...] = ()

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        json_schema_extra=_require_section_hint_in_schema,
    )

    @classmethod
    def model_validate(cls, obj: object, **kwargs: object) -> SectionTask:
        """Reject omitted revision keys when validating provider-shaped mappings."""
        if isinstance(obj, Mapping) and "existing_section_hint" not in obj:
            raise _missing_section_hint_error(obj)
        return super().model_validate(obj, **kwargs)

    @field_validator("capability_ids", "source_hints", "requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject blank semantic entries while preserving provider order."""
        _require_nonempty_items(values)
        return values


class _PlannerWireReportTask(_SemanticModel):
    """Provider-facing report task without host-owned provenance."""

    goal: str = Field(min_length=1)
    capability_ids: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("capability_ids", "requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Keep wire text collections aligned with canonical validation."""
        _require_nonempty_items(values)
        return values


class _PlannerWireSectionTask(_SemanticModel):
    """Provider-facing section task without host-owned provenance."""

    goal: str = Field(min_length=1)
    capability_ids: tuple[str, ...] = Field(min_length=1)
    existing_section_hint: str | None = Field(default=None, min_length=1)
    source_hints: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        json_schema_extra=_require_section_hint_in_schema,
    )

    @classmethod
    def model_validate(cls, obj: object, **kwargs: object) -> _PlannerWireSectionTask:
        """Require the explicit section-target key at the wire boundary."""
        if isinstance(obj, Mapping) and "existing_section_hint" not in obj:
            raise _missing_section_hint_error(obj)
        return super().model_validate(obj, **kwargs)

    @field_validator("capability_ids", "source_hints", "requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Keep wire text collections aligned with canonical validation."""
        _require_nonempty_items(values)
        return values


class _PlannerWirePlan(_SemanticModel):
    """Provider-facing semantic plan containing no deterministic provenance."""

    summary: str = Field(min_length=1)
    report_task: _PlannerWireReportTask | None = None
    section_tasks: tuple[_PlannerWireSectionTask, ...] = ()
    unresolved_requirements: tuple[str, ...] = ()

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        json_schema_extra=lambda schema: _add_work_unit_schema_constraint(schema),
    )

    @classmethod
    def model_validate(cls, obj: object, **kwargs: object) -> _PlannerWirePlan:
        """Apply the required section-target key check to wire mappings."""
        if isinstance(obj, Mapping):
            section_tasks = obj.get("section_tasks", ())
            if isinstance(section_tasks, (list, tuple)):
                for task in section_tasks:
                    if isinstance(task, Mapping) and "existing_section_hint" not in task:
                        raise _missing_section_hint_error(task)
        return super().model_validate(obj, **kwargs)

    @model_validator(mode="after")
    def validate_work_units(self) -> _PlannerWirePlan:
        """Keep the canonical executable-work invariant at the wire boundary."""
        if self.report_task is None and not self.section_tasks:
            raise ValueError("SemanticPlan must contain a report task or section tasks.")
        return self

    @field_validator("unresolved_requirements")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Keep unresolved requirement validation aligned with the canonical model."""
        _require_nonempty_items(values)
        return values


class PlannerSemanticError(ValueError):
    """One expected semantic error in provider-produced planner output."""

    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        affected_paths: tuple[str, ...] = (),
    ) -> None:
        """Initialize a stable, provider-safe correction diagnostic."""
        self.code = code
        self.safe_message = safe_message
        self.affected_paths = affected_paths or _default_repair_scope(code)
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
    obligations: tuple[RequestObligation, ...] = ()

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        json_schema_extra=lambda schema: _add_work_unit_schema_constraint(schema),
    )

    @classmethod
    def model_validate(cls, obj: object, **kwargs: object) -> SemanticPlan:
        """Apply the required revision-key check to nested provider mappings."""
        if isinstance(obj, Mapping):
            section_tasks = obj.get("section_tasks", ())
            if isinstance(section_tasks, (list, tuple)):
                for task in section_tasks:
                    if isinstance(task, Mapping) and "existing_section_hint" not in task:
                        raise _missing_section_hint_error(task)
        return super().model_validate(obj, **kwargs)

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


def _add_work_unit_schema_constraint(schema: dict[str, object]) -> None:
    """Require an executable report or non-empty section work unit."""
    constraints = schema.setdefault("allOf", [])
    if not isinstance(constraints, list):
        raise TypeError("SemanticPlan schema allOf must be a list.")
    constraints.append(
        {
            "anyOf": [
                {
                    "required": ["report_task"],
                    "properties": {
                        "report_task": {"not": {"type": "null"}},
                    },
                },
                {
                    "required": ["section_tasks"],
                    "properties": {
                        "section_tasks": {"type": "array", "minItems": 1},
                    },
                },
            ]
        }
    )


def _canonical_plan_from_wire(wire_plan: _PlannerWirePlan) -> SemanticPlan:
    """Convert one provider DTO into the canonical validated plan exactly once."""
    return SemanticPlan.model_validate(wire_plan.model_dump(mode="python"))


def _missing_section_hint_error(input_value: object) -> ValidationError:
    """Build the standard Pydantic missing-field error for provider mappings."""
    return ValidationError.from_exception_data(
        "SectionTask",
        [
            {
                "type": "missing",
                "loc": ("existing_section_hint",),
                "input": input_value,
            }
        ],
    )


def _default_repair_scope(code: str) -> tuple[str, ...]:
    """Return the narrow canonical path scope for one semantic diagnostic."""
    if code == "missing_existing_section_hint":
        return ("/section_tasks/*/existing_section_hint",)
    if code in {
        "unknown_capability",
        "noncanonical_capability",
        "duplicate_capability",
        "ambiguous_capability_parent",
        "noncanonical_capability_parent",
        "missing_capability_parent",
        "missing_section_capability",
        "wrong_task_category",
    }:
        return ("/report_task/capability_ids", "/section_tasks/*/capability_ids")
    if code == "planner_extraction_coverage":
        return ("/report_task/requirements", "/section_tasks/*/requirements")
    return ()


def _assert_correction_scope(
    before: SemanticPlan,
    after: SemanticPlan,
    diagnostic: PlannerSemanticError,
) -> None:
    """Reject any correction that changes a path outside its typed scope."""
    changed_paths = _semantic_plan_changed_paths(
        before.model_dump(mode="json"),
        after.model_dump(mode="json"),
    )
    if all(_path_matches_scope(path, diagnostic.affected_paths) for path in changed_paths):
        return
    unauthorized = [
        path for path in changed_paths if not _path_matches_scope(path, diagnostic.affected_paths)
    ]
    raise PlannerSemanticFailure(
        "unauthorized_correction_change",
        "Semantic correction changed paths outside its authorized repair scope: "
        + ", ".join(unauthorized),
    )


def _semantic_plan_changed_paths(
    before: object,
    after: object,
    path: str = "",
) -> tuple[str, ...]:
    """Return deterministic JSON-pointer-like leaf paths changed by a correction."""
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        paths: list[str] = []
        for key in sorted(set(before) | set(after)):
            child = f"{path}/{key}"
            if key not in before or key not in after:
                paths.append(child)
            else:
                paths.extend(_semantic_plan_changed_paths(before[key], after[key], child))
        return tuple(paths)
    if isinstance(before, list) and isinstance(after, list):
        paths = []
        for index in range(max(len(before), len(after))):
            child = f"{path}/{index}"
            if index >= len(before) or index >= len(after):
                paths.append(child)
            else:
                paths.extend(_semantic_plan_changed_paths(before[index], after[index], child))
        return tuple(paths)
    return () if before == after else (path or "/",)


def _path_matches_scope(path: str, scopes: tuple[str, ...]) -> bool:
    """Match one changed path against a scope with one-segment wildcards."""
    path_parts = path.strip("/").split("/") if path.strip("/") else []
    for scope in scopes:
        scope_parts = scope.strip("/").split("/") if scope.strip("/") else []
        if len(path_parts) < len(scope_parts):
            continue
        if all(
            expected == "*" or expected == actual
            for expected, actual in zip(scope_parts, path_parts, strict=False)
        ):
            # A declared field scope authorizes changes within that semantic
            # collection, including list-element additions/removals.
            return True
    return False


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
                response_model=_PlannerWirePlan,
            )
        except ProviderRequestError as error:
            if error.category is not ProviderFailureCategory.INVALID_RESPONSE:
                raise
            invalid_response_retry_used = True
            if (
                isinstance(error, StructuredResponseProviderError)
                and error.response_reason is ProviderResponseFailureReason.SCHEMA_VALIDATION
            ):
                retry_request = _schema_correction_request(
                    context=context,
                    diagnostic=_schema_failure_diagnostic(error),
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )
            else:
                retry_request = _planning_request(
                    context=context,
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )
            generated = await self.backend.generate_structured(
                retry_request,
                response_model=_PlannerWirePlan,
            )
        plan = _canonical_plan_from_wire(generated.value)
        plan = _attach_request_obligations(plan, request)
        try:
            _validate_extraction_coverage(plan)
            return validate_semantic_plan(plan, self.registry, mode=mode)
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
                    current_document_summary=current_document_summary,
                    source_summary=source_summary,
                    previous_plan=plan,
                    diagnostic=first_error,
                    registry=self.registry,
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
                response_model=_PlannerWirePlan,
            )
            corrected_plan = _canonical_plan_from_wire(corrected.value)
            corrected_plan = _attach_request_obligations(corrected_plan, request)
            try:
                _assert_correction_scope(plan, corrected_plan, first_error)
            except PlannerSemanticFailure:
                raise
            try:
                _validate_extraction_coverage(corrected_plan)
                return validate_semantic_plan(corrected_plan, self.registry, mode=mode)
            except PlannerSemanticError as second_error:
                raise PlannerSemanticFailure(
                    second_error.code,
                    "Planner returned a semantically invalid plan after one correction.",
                ) from second_error


def _attach_request_obligations(plan: SemanticPlan, request: str) -> SemanticPlan:
    """Attach host-extracted obligations without trusting provider restatement."""
    obligations = extract_supported_obligations(request)
    verify_obligation_spans(request, obligations)
    verify_anchor_coverage(request, obligations)
    report = plan.report_task
    if report is not None:
        report = report.model_copy(
            update={
                "obligations": tuple(
                    item for item in obligations if item.owner_kind.value == "report"
                )
            }
        )
    non_report = tuple(item for item in obligations if item.owner_kind.value != "report")
    section_count = len(plan.section_tasks)
    sections = tuple(
        task.model_copy(
            update={
                "obligations": _partition_task_obligations(
                    task,
                    non_report,
                    section_count=section_count,
                    authoritative_request=request,
                )
            }
        )
        for task in plan.section_tasks
    )
    return plan.model_copy(
        update={"report_task": report, "section_tasks": sections, "obligations": obligations}
    )


def _partition_task_obligations(
    task: SectionTask,
    obligations: tuple[RequestObligation, ...],
    *,
    section_count: int,
    authoritative_request: str,
) -> tuple[RequestObligation, ...]:
    """Bind facts to one task without broadcasting request-wide assertions."""
    repeated_pass_request = bool(
        re.search(r"\bfor\s+each\s+(?:pass|section)\b", authoritative_request, re.IGNORECASE)
    )
    task_text = " ".join(
        (
            task.goal,
            task.existing_section_hint or "",
            *task.source_hints,
            *(
                requirement
                for requirement in task.requirements
                if requirement.strip().casefold() != authoritative_request.strip().casefold()
            ),
            *task.constraints,
        )
    ).casefold()
    selected: list[RequestObligation] = []
    for item in obligations:
        owner = item.owner_ref.casefold()
        value = "" if item.value is None else str(item.value).casefold()
        if item.scope == "global" or (
            repeated_pass_request
            and "pass" in task_text
            and item.owner_kind.value in {"track", "binding"}
        ):
            selected.append(item)
        elif owner == "request":
            if section_count == 1 or value in task_text:
                selected.append(item)
        elif owner in task_text or value in task_text:
            selected.append(item)
    return tuple(selected)


def _validate_extraction_coverage(plan: SemanticPlan) -> None:
    """Reject plans that drop a supported value or its request-local owner."""
    report_text = " ".join(
        (
            plan.report_task.goal if plan.report_task else "",
            *(plan.report_task.requirements if plan.report_task else ()),
            *(plan.report_task.constraints if plan.report_task else ()),
        )
    ).casefold()
    for obligation in plan.obligations:
        if obligation.owner_kind.value == "report":
            if obligation not in (plan.report_task.obligations if plan.report_task else ()):
                raise PlannerSemanticError(
                    "planner_extraction_coverage",
                    "Planner report ownership was missing or ambiguous.",
                    affected_paths=("/report_task/requirements",),
                )
            searchable = report_text
        else:
            assigned = [task for task in plan.section_tasks if obligation in task.obligations]
            expected_assignments = len(plan.section_tasks) if obligation.scope == "global" else 1
            repeated_task_assignment = (
                obligation.scope == "task"
                and obligation.owner_kind.value in {"track", "binding"}
                and len(assigned) > 1
                and all(
                    "pass"
                    in f"{task.goal} {task.existing_section_hint or ''}".casefold()
                    for task in assigned
                )
            )
            if len(assigned) != expected_assignments and not repeated_task_assignment:
                raise PlannerSemanticError(
                    "planner_extraction_coverage",
                    "Planner obligation ownership was missing or ambiguous.",
                    affected_paths=("/section_tasks/*/requirements",),
                )
            task = assigned[0]
            searchable = " ".join(
                (
                    task.goal,
                    task.existing_section_hint or "",
                    *task.source_hints,
                    *task.requirements,
                    *task.constraints,
                )
            ).casefold()
        value = "" if obligation.value is None else str(obligation.value).casefold()
        owner = obligation.owner_ref.casefold()
        if owner == "request" or obligation.scope == "global":
            continue
        if owner in searchable and (not value or value in searchable):
            continue
        raise PlannerSemanticError(
            "planner_extraction_coverage",
            "Planner output did not retain a supported request obligation.",
            affected_paths=("/report_task/requirements", "/section_tasks/*/requirements"),
        )


def validate_semantic_plan(
    plan: SemanticPlan,
    registry: CapabilityRegistry,
    *,
    mode: CompilationMode = "reconstruct",
) -> SemanticPlan:
    """Validate capabilities and revision target contracts without host resolution."""
    closed_report_task = None
    if plan.report_task is not None:
        _validate_capabilities(
            plan.report_task.capability_ids,
            registry,
            task_kind="report",
        )
        _validate_unique_capabilities(plan.report_task.capability_ids)
        closed_report_task = plan.report_task.model_copy(
            update={
                "capability_ids": _close_capability_parents(
                    plan.report_task.capability_ids,
                    registry,
                    task_path="/report_task/capability_ids",
                )
            }
        )

    closed_section_tasks: list[SectionTask] = []
    for task in plan.section_tasks:
        if mode == "revise" and task.existing_section_hint is None:
            raise PlannerSemanticError(
                "missing_existing_section_hint",
                (
                    "Revision SectionTasks must identify an existing section with a "
                    "natural-language hint."
                ),
            )
        _validate_capabilities(task.capability_ids, registry, task_kind="section")
        _validate_unique_capabilities(task.capability_ids)
        closed_capabilities = _close_capability_parents(
            task.capability_ids,
            registry,
            task_path="/section_tasks/*/capability_ids",
        )
        closed_specs = _validate_capabilities(
            closed_capabilities,
            registry,
            task_kind="section",
        )
        categories = {spec.category for spec in closed_specs}
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
        closed_section_tasks.append(task.model_copy(update={"capability_ids": closed_capabilities}))
    if closed_report_task is None and not closed_section_tasks:
        return plan
    return plan.model_copy(
        update={
            "report_task": closed_report_task,
            "section_tasks": tuple(closed_section_tasks),
        }
    )


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


def _close_capability_parents(
    capability_ids: tuple[str, ...],
    registry: CapabilityRegistry,
    *,
    task_path: str,
) -> tuple[str, ...]:
    """Add only uniquely determined parents while preserving provider order."""
    ordered = list(capability_ids)
    selected = set(ordered)
    additions: list[str] = []
    cursor = 0
    while cursor < len(ordered):
        capability_id = ordered[cursor]
        spec = registry.get(capability_id)
        allowed_parents = tuple(getattr(spec, "allowed_parents", ()))
        if allowed_parents and not selected.intersection(allowed_parents):
            if len(allowed_parents) != 1:
                parent_text = ", ".join(allowed_parents)
                raise PlannerSemanticError(
                    "ambiguous_capability_parent",
                    f"Capability {spec.capability_id!r} requires one selected parent "
                    f"from the legal alternatives: {parent_text}.",
                    affected_paths=(task_path,),
                )
            parent = allowed_parents[0]
            parent_spec = registry.get(parent)
            if parent_spec.capability_id != parent:
                raise PlannerSemanticError(
                    "noncanonical_capability_parent",
                    "A capability parent resolved to a non-canonical identifier.",
                    affected_paths=(task_path,),
                )
            selected.add(parent)
            additions.append(parent)
            ordered.append(parent)
        cursor += 1
    return (*capability_ids, *sorted(set(additions) - set(capability_ids)))


def _validate_parent_closure(
    specs: tuple[object, ...],
    capability_ids: tuple[str, ...],
) -> None:
    """Retained compatibility helper for callers auditing a closed selection."""
    selected = set(capability_ids)
    for spec in specs:
        allowed_parents = tuple(getattr(spec, "allowed_parents", ()))
        if allowed_parents and not selected.intersection(allowed_parents):
            raise PlannerSemanticError(
                "missing_capability_parent",
                f"Capability {spec.capability_id!r} has no selected legal parent.",
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


def _schema_correction_request(
    *,
    context: Mapping[str, object],
    diagnostic: Mapping[str, str] | None = None,
    timeout_seconds: float,
    temperature: float | None,
    max_output_tokens: int | None,
) -> StructuredGenerationRequest:
    """Build one bounded retry for a schema-validation response failure."""
    return StructuredGenerationRequest(
        system_prompt=_PLANNER_SYSTEM_PROMPT,
        user_prompt=(
            _SCHEMA_CORRECTION_INSTRUCTION
            + "\n\nSchema correction context:\n"
            + json.dumps(
                {
                    "context": context,
                    "diagnostic": dict(diagnostic or {}),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        ),
        timeout_seconds=timeout_seconds,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _schema_failure_diagnostic(error: Exception) -> dict[str, str]:
    """Return bounded structural feedback without exposing provider payloads."""
    if isinstance(error, StructuredResponseProviderError):
        shape = error.validation_shape
        if shape is not None and any(
            issue.error_type == "value_error" and issue.location == ("$root",)
            for issue in shape.issues
        ):
            return {
                "code": "missing_executable_work_unit",
                "message": (
                    "SemanticPlan requires a non-null report_task or at least one "
                    "section_tasks item."
                ),
            }
    return {
        "code": "schema_validation",
        "message": "Return one object that satisfies the structured response model.",
    }


def _correction_request(
    *,
    mode: CompilationMode,
    request: str,
    current_document_summary: Mapping[str, object] | None = None,
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
        "current_document_summary": _safe_document_summary(current_document_summary),
        "source_summary": _safe_source_summary(source_summary),
        "capabilities": _planning_catalog(registry),
        "previous_plan": _safe_plan_for_correction(previous_plan),
        "diagnostic": {
            "code": diagnostic.code,
            "message": diagnostic.safe_message,
            "affected_paths": list(diagnostic.affected_paths),
            "authorized_repair_scope": list(diagnostic.affected_paths),
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
    """Preserve semantic text and safe natural-language target clues for correction."""
    payload: dict[str, object] = {
        "goal": _safe_correction_text(task.goal),
        "capability_ids": list(task.capability_ids),
        "existing_section_hint": (
            None
            if not isinstance(task, SectionTask) or task.existing_section_hint is None
            else _safe_correction_text(task.existing_section_hint)
        ),
        "requirements": [_safe_correction_text(value) for value in task.requirements],
        "constraints": [_safe_correction_text(value) for value in task.constraints],
    }
    if isinstance(task, SectionTask):
        payload["source_hints"] = [_safe_correction_text(value) for value in task.source_hints]
    else:
        payload.pop("existing_section_hint")
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
        inspection_state = raw_source.get("inspection_state", "not_inspected")
        if inspection_state not in {"inspected", "not_inspected", "unavailable"}:
            raise ValueError("Source inspection state is invalid.")
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
        sources.append(
            {
                "labels": labels,
                "channels": channels,
                "inspection_state": inspection_state,
            }
        )

    version = summary.get("version", "1")
    return {
        "version": _safe_correction_text(str(version)),
        "sources": sources,
    }


def _safe_document_summary(summary: Mapping[str, object] | None) -> dict[str, object]:
    """Project semantic revision facts without canonical host identities."""
    if summary is None:
        return {"existing_section_hints": []}
    raw_hints = summary.get("existing_section_hints", ())
    if not isinstance(raw_hints, (list, tuple)):
        raise ValueError("Document summary existing section hints must be a sequence.")

    hints: list[dict[str, str | None]] = []
    for raw_hint in raw_hints:
        if not isinstance(raw_hint, Mapping):
            raise ValueError("Document summary section hints must be mappings.")
        title = raw_hint.get("title")
        subtitle = raw_hint.get("subtitle")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Document summary section hint titles must be non-empty text.")
        if subtitle is not None and not isinstance(subtitle, str):
            raise ValueError("Document summary section hint subtitles must be text or null.")
        hints.append(
            {
                "title": _safe_correction_text(title),
                "subtitle": (None if subtitle is None else _safe_correction_text(subtitle)),
            }
        )
    raw_inventory = summary.get("revision_inventory")
    if raw_inventory is None:
        return {"existing_section_hints": hints}
    if not isinstance(raw_inventory, (list, tuple)):
        raise ValueError("Document revision inventory must be a sequence.")
    inventory: list[dict[str, object]] = []
    for raw_section in raw_inventory:
        if not isinstance(raw_section, Mapping):
            raise ValueError("Document revision inventory entries must be mappings.")
        tracks = raw_section.get("tracks", ())
        if not isinstance(tracks, (list, tuple)):
            raise ValueError("Document revision inventory tracks must be a sequence.")
        safe_tracks: list[dict[str, object]] = []
        for raw_track in tracks:
            if not isinstance(raw_track, Mapping):
                raise ValueError("Document revision inventory tracks must be mappings.")
            bindings = raw_track.get("bindings", ())
            if not isinstance(bindings, (list, tuple)):
                raise ValueError("Document revision inventory bindings must be a sequence.")
            safe_bindings = []
            for raw_binding in bindings:
                if not isinstance(raw_binding, Mapping):
                    raise ValueError("Document revision inventory bindings must be mappings.")
                safe_bindings.append(
                    {
                        "kind": _safe_correction_text(str(raw_binding.get("kind", ""))),
                        "channel": _safe_correction_text(str(raw_binding.get("channel", ""))),
                        "label": (
                            None
                            if raw_binding.get("label") is None
                            else _safe_correction_text(str(raw_binding.get("label")))
                        ),
                        "scale": raw_binding.get("scale"),
                    }
                )
            safe_tracks.append(
                {
                    "title": _safe_correction_text(str(raw_track.get("title", ""))),
                    "kind": _safe_correction_text(str(raw_track.get("kind", ""))),
                    "width_mm": raw_track.get("width_mm"),
                    "bindings": safe_bindings,
                }
            )
        inventory.append(
            {
                "title": _safe_correction_text(str(raw_section.get("title", ""))),
                "subtitle": (
                    None
                    if raw_section.get("subtitle") is None
                    else _safe_correction_text(str(raw_section.get("subtitle")))
                ),
                "depth_range": raw_section.get("depth_range"),
                "tracks": safe_tracks,
            }
        )
    return {"existing_section_hints": hints, "revision_inventory": inventory}


def _require_nonempty_items(values: tuple[str, ...]) -> None:
    """Require each semantic list item to contain meaningful text."""
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("Semantic text collections cannot contain blank items.")


_PLANNER_SYSTEM_PROMPT = """You are the semantic planning stage of Wellplot Code Mode v2.
Describe semantic work units only. Do not emit document object IDs, section IDs,
track IDs, binding IDs, component trees, parent relationships, operation order,
insert positions, source paths, source formats, header slot IDs, or data-source
objects. Do not describe SDK calls or mutation steps. Do not emit request hashes,
span hashes, byte offsets, or other provenance; the host derives those facts from
the authoritative request.

The response must contain at least one executable work unit: a non-null
report_task or a non-empty section_tasks array. A summary alone is never an
executable plan. For a section edit, include one SectionTask with the required
existing_section_hint key, including an explicit null only when reconstruction
has no existing target.

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
In revise mode, every SectionTask must include an existing_section_hint. Copy an
exact supplied section title or subtitle from current_document_summary's
existing_section_hints; do not leave the hint null and do not invent a section
identity. Revision workers cannot safely target an existing section without this
host-resolvable natural-language clue.
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
