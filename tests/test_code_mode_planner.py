"""CM-40 tests for the static semantic planner contract."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel, ValidationError

from wellplot.agent.code_mode.planner import (
    PlannerSemanticFailure,
    ReportTask,
    SectionTask,
    SemanticPlan,
    SemanticPlanner,
    validate_semantic_plan,
)
from wellplot.agent.providers.base import (
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry


@dataclass
class _RecordedBackend:
    """Fake structured backend that records the single planner request."""

    payload: object
    requests: list[StructuredGenerationRequest] = field(default_factory=list)
    response_models: list[type[BaseModel]] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Validate the recorded response through the supplied static model."""
        self.requests.append(request)
        self.response_models.append(response_model)
        return StructuredGenerationResult(
            value=response_model.model_validate(self.payload),
            metrics=ProviderMetrics(),
        )

    async def generate_program(self, request: object) -> object:
        """Keep the fake explicit if the planner accidentally uses program generation."""
        raise AssertionError(f"Unexpected program generation request: {request!r}")


@dataclass
class _SequenceBackend:
    """Fake structured backend returning one configured response per call."""

    responses: list[object]
    requests: list[StructuredGenerationRequest] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Return the next response or raise its configured exception."""
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return StructuredGenerationResult(
            value=response_model.model_validate(response),
            metrics=ProviderMetrics(),
        )

    async def generate_program(self, request: object) -> object:
        """Keep the fake explicit if the planner accidentally uses programs."""
        raise AssertionError(f"Unexpected program generation request: {request!r}")


def _plan_payload() -> dict[str, object]:
    """Return a semantic plan without canonical document identities."""
    return {
        "summary": "Add a CBL presentation section.",
        "report_task": {
            "goal": "Preserve the existing report heading.",
            "capability_ids": ("report.standard",),
            "requirements": ("Keep the current heading layout.",),
        },
        "section_tasks": (
            {
                "goal": "Show the main CBL and VDL interpretation.",
                "capability_ids": ("section.log_plot", "track.normal", "binding.curve"),
                "existing_section_hint": "the existing main CBL presentation section",
                "source_hints": ("use the staged CBL DLIS",),
                "requirements": ("Include depth and cement-bond measurements.",),
                "constraints": ("Keep the section readable.",),
            },
        ),
        "unresolved_requirements": (),
    }


def test_semantic_schema_contains_no_document_identity_fields() -> None:
    """The static v2 schema cannot ask the provider for canonical object IDs."""
    schema_text = json.dumps(SemanticPlan.model_json_schema(), sort_keys=True)
    forbidden = {
        "component_id",
        "target_id",
        "parent_component_id",
        "binding_id",
        "section_id",
        "source_path",
        "source_format",
        "slot_id",
        "data_source",
        "components",
    }

    assert not forbidden.intersection(schema_text)
    assert "existing_section_hint" in schema_text
    assert "capability_ids" in schema_text


def test_semantic_models_are_strict_and_frozen() -> None:
    """Planner contracts reject extras and mutation rather than repairing them."""
    with pytest.raises(ValidationError):
        SectionTask.model_validate(
            {
                "goal": "Show CBL.",
                "capability_ids": ("section.log_plot",),
                "section_id": "main_pass",
            }
        )

    task = ReportTask(goal="Preserve the report.")
    with pytest.raises(ValidationError):
        task.goal = "Mutate the plan"  # type: ignore[misc]


def test_semantic_plan_allows_report_only_work() -> None:
    """Report workers can be planned without inventing a section task."""
    plan = SemanticPlan(
        summary="Update the report heading.",
        report_task=ReportTask(goal="Update the report heading."),
    )

    assert plan.section_tasks == ()


def test_semantic_plan_rejects_empty_work() -> None:
    """A plan without report or section work is not executable."""
    with pytest.raises(ValidationError, match="report task or section tasks"):
        SemanticPlan(summary="No work")


def test_planner_makes_one_static_structured_call() -> None:
    """Normal planning uses one fixed response model and no source discovery."""
    backend = _RecordedBackend(_plan_payload())
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    result = asyncio.run(
        planner.plan(
            request="Build the CBL quicklook.",
            mode="reconstruct",
            current_document_summary={"sections": ["existing CBL presentation section"]},
            timeout_seconds=5.0,
            temperature=0.0,
        )
    )

    assert result.section_tasks[0].existing_section_hint == (
        "the existing main CBL presentation section"
    )
    assert len(backend.requests) == 1
    assert backend.response_models == [SemanticPlan]
    prompt = backend.requests[0].user_prompt
    assert "source_manifest" not in prompt
    assert "source_path" not in prompt
    assert "main_pass" not in prompt
    assert "binding_id" not in prompt


def test_planner_preserves_revise_mode_as_semantic_context() -> None:
    """Revision mode is sent to the provider without identity-bearing state."""
    backend = _RecordedBackend(_plan_payload())
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    asyncio.run(
        planner.plan(
            request="Change the CBL display.",
            mode="revise",
            timeout_seconds=5.0,
        )
    )

    assert '"mode":"revise"' in backend.requests[0].user_prompt


def _invalid_plan_payload(kind: str) -> dict[str, object]:
    """Return one structurally valid plan with one semantic error."""
    payload = _plan_payload()
    if kind == "unknown_capability":
        payload["section_tasks"] = (
            {
                **payload["section_tasks"][0],
                "capability_ids": ("missing",),
            },
        )
    elif kind == "noncanonical_capability":
        payload["section_tasks"] = (
            {
                **payload["section_tasks"][0],
                "capability_ids": ("normal track",),
            },
        )
    elif kind == "wrong_task_category":
        payload["section_tasks"] = (
            {
                **payload["section_tasks"][0],
                "capability_ids": ("track.normal", "report.standard"),
            },
        )
    elif kind == "missing_section_capability":
        payload["section_tasks"] = (
            {
                **payload["section_tasks"][0],
                "capability_ids": ("track.normal",),
            },
        )
    else:
        raise AssertionError(f"Unknown fixture kind: {kind}")
    return payload


@pytest.mark.parametrize(
    "kind",
    (
        "unknown_capability",
        "noncanonical_capability",
        "wrong_task_category",
        "missing_section_capability",
    ),
)
def test_planner_corrects_each_typed_semantic_error_once(kind: str) -> None:
    """Each expected provider semantic error gets exactly one correction call."""
    backend = _SequenceBackend(responses=[_invalid_plan_payload(kind), _plan_payload()])
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    result = asyncio.run(
        planner.plan(
            request="Build the CBL quicklook.",
            mode="reconstruct",
            timeout_seconds=5.0,
        )
    )

    assert result == SemanticPlan.model_validate(_plan_payload())
    assert len(backend.requests) == 2
    correction_prompt = backend.requests[1].user_prompt
    assert "capabilities" in correction_prompt
    assert "source_hints" not in correction_prompt
    assert "existing_section_hint" not in correction_prompt


def test_planner_returns_bounded_failure_after_invalid_correction() -> None:
    """A second semantic failure stops planning without a third generation."""
    backend = _SequenceBackend(
        responses=[
            _invalid_plan_payload("unknown_capability"),
            _invalid_plan_payload("unknown_capability"),
        ]
    )
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    with pytest.raises(PlannerSemanticFailure) as caught:
        asyncio.run(
            planner.plan(
                request="Build the CBL quicklook.",
                mode="reconstruct",
                timeout_seconds=5.0,
            )
        )

    assert caught.value.code == "unknown_capability"
    assert len(backend.requests) == 2


def test_planner_provider_failure_does_not_trigger_correction() -> None:
    """Provider failures remain single-call failures without semantic retry."""
    failure = ProviderRequestError(
        ProviderFailureCategory.TIMEOUT,
        "Planner request timed out.",
    )
    backend = _SequenceBackend(responses=[failure])
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    with pytest.raises(ProviderRequestError):
        asyncio.run(
            planner.plan(
                request="Build the CBL quicklook.",
                mode="reconstruct",
                timeout_seconds=5.0,
            )
        )

    assert len(backend.requests) == 1


def test_planner_unexpected_backend_failure_propagates() -> None:
    """Unexpected backend defects are not classified as semantic corrections."""
    backend = _SequenceBackend(responses=[RuntimeError("programming defect")])
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    with pytest.raises(RuntimeError, match="programming defect"):
        asyncio.run(
            planner.plan(
                request="Build the CBL quicklook.",
                mode="reconstruct",
                timeout_seconds=5.0,
            )
        )

    assert len(backend.requests) == 1


def test_semantic_plan_rejects_unknown_and_wrong_category_capabilities() -> None:
    """Capability failures are deterministic and do not trigger another model call."""
    registry = create_builtin_registry()
    section_task = SectionTask(
        goal="Show a log section.",
        capability_ids=("section.log_plot",),
    )

    with pytest.raises(ValueError, match="Unknown capability id"):
        validate_semantic_plan(
            SemanticPlan(
                summary="Invalid plan",
                section_tasks=(section_task.model_copy(update={"capability_ids": ("missing",)}),),
            ),
            registry,
        )

    with pytest.raises(ValueError, match="only report capabilities"):
        validate_semantic_plan(
            SemanticPlan(
                summary="Invalid report plan",
                report_task=ReportTask(
                    goal="Change the report.",
                    capability_ids=("track.normal",),
                ),
                section_tasks=(section_task,),
            ),
            registry,
        )

    with pytest.raises(ValueError, match="section capability"):
        validate_semantic_plan(
            SemanticPlan(
                summary="Invalid section plan",
                section_tasks=(
                    SectionTask(
                        goal="Show a track.",
                        capability_ids=("track.normal",),
                    ),
                ),
            ),
            registry,
        )


def test_semantic_planner_does_not_require_a_specific_registry_implementation() -> None:
    """Host validation works with any registry containing the static capability IDs."""
    registry = CapabilityRegistry(tuple(create_builtin_registry()))
    plan = SemanticPlan.model_validate(_plan_payload())

    assert validate_semantic_plan(plan, registry) == plan
