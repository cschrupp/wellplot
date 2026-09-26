"""CM-40 tests for the static semantic planner contract."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel, ValidationError

from wellplot.agent.code_mode.planner import (
    PlannerSemanticError,
    PlannerSemanticFailure,
    ReportTask,
    SectionTask,
    SemanticPlan,
    SemanticPlanner,
    _correction_request,
    _safe_task_for_correction,
    validate_semantic_plan,
)
from wellplot.agent.providers.base import (
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.capabilities import CapabilityRegistry, CapabilitySpec, create_builtin_registry


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


def test_planner_receives_path_free_source_summary_as_separate_context() -> None:
    """Source labels and channel facts are separate from the natural request."""
    backend = _RecordedBackend(_plan_payload())
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    asyncio.run(
        planner.plan(
            request="Build the main pass.",
            mode="reconstruct",
            source_summary={
                "version": "test.v1",
                "sources": [
                    {
                        "candidate_id": "secret-source-id",
                        "path": "/secret/CBL.dlis",
                        "labels": ["main pass"],
                        "channels": [{"mnemonic": "CBL", "kind": "scalar"}],
                    }
                ],
            },
            timeout_seconds=5.0,
        )
    )

    prompt = backend.requests[0].user_prompt
    assert '"labels":["main pass"]' in prompt
    assert '"mnemonic":"CBL"' in prompt
    assert "secret-source-id" not in prompt
    assert "/secret/CBL.dlis" not in prompt


def test_planner_prompt_defines_source_and_scientific_preservation() -> None:
    """The planner contract requires worker-relevant semantics to survive planning."""
    backend = _RecordedBackend(_plan_payload())
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    asyncio.run(
        planner.plan(
            request="Build the CBL quicklook.",
            mode="reconstruct",
            timeout_seconds=5.0,
        )
    )

    prompt = backend.requests[0].system_prompt
    assert "SectionTask.source_hints" in prompt
    assert "numeric bounds" in prompt
    assert "repeated binding requests" in prompt
    assert "sample-axis" in prompt


def test_planner_catalog_exposes_only_structural_parent_metadata() -> None:
    """The planner sees registry relationships but not worker implementation data."""
    backend = _RecordedBackend(_plan_payload())
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    asyncio.run(
        planner.plan(
            request="Build the CBL quicklook.",
            mode="reconstruct",
            timeout_seconds=5.0,
        )
    )

    context = json.loads(backend.requests[0].user_prompt.split("Context:\n", 1)[1])
    catalog = {entry["id"]: entry for entry in context["capabilities"]}
    assert catalog["binding.raster"]["allowed_parents"] == ["track.array"]
    assert catalog["binding.curve"]["allowed_parents"] == [
        "track.normal",
        "track.reference",
    ]
    forbidden_fields = {
        "semantic_metadata",
        "worker_hints",
        "arguments_schema",
        "artifact_schema",
        "examples",
        "handler",
        "compiler",
    }
    assert not forbidden_fields.intersection(key for entry in catalog.values() for key in entry)


def test_planner_prompt_defines_complete_unique_capability_types() -> None:
    """The generic prompt explains closure without benchmark-specific examples."""
    backend = _RecordedBackend(_plan_payload())
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    asyncio.run(
        planner.plan(
            request="Build a section.",
            mode="reconstruct",
            timeout_seconds=5.0,
        )
    )

    prompt = backend.requests[0].system_prompt
    assert "complete set of capability types" in prompt
    assert "not requested object instances" in prompt
    assert "at most once" in prompt
    assert "allowed parent capabilities" in prompt
    assert "Do not add capabilities for semantics that were not requested" in prompt
    assert not any(value in prompt for value in ("CM-57C", "curve_linear_new_values", "CBL", "VDL"))


def test_initial_and_correction_catalogs_include_the_same_structural_metadata() -> None:
    """Semantic correction uses the same planner-safe catalog as initial planning."""
    invalid = _plan_payload()
    invalid["section_tasks"] = (
        {
            **invalid["section_tasks"][0],
            "capability_ids": (
                "section.log_plot",
                "binding.curve",
                "binding.curve",
            ),
        },
    )
    backend = _SequenceBackend(responses=[invalid, _plan_payload()])
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    asyncio.run(
        planner.plan(
            request="Build a section.",
            mode="reconstruct",
            timeout_seconds=5.0,
        )
    )

    initial = json.loads(backend.requests[0].user_prompt.split("Context:\n", 1)[1])
    correction = json.loads(backend.requests[1].user_prompt.split("Correction context:\n", 1)[1])
    assert correction["capabilities"] == initial["capabilities"]
    assert correction["previous_plan"]["section_tasks"][0]["capability_ids"] == [
        "section.log_plot",
        "binding.curve",
        "binding.curve",
    ]


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
    assert "Add a CBL presentation section." in correction_prompt
    assert "Show the main CBL and VDL interpretation." in correction_prompt
    assert "Include depth and cement-bond measurements." in correction_prompt
    assert "Keep the section readable." in correction_prompt
    assert "source_hints" in correction_prompt
    assert "use the staged CBL DLIS" in correction_prompt
    assert "existing_section_hint" not in correction_prompt


def test_section_correction_projection_preserves_source_and_scientific_requirements() -> None:
    """Section correction context retains semantic clues without host identities."""
    task = SectionTask(
        goal="Build the secondary section.",
        capability_ids=("section.log_plot",),
        source_hints=("secondary source", "/secret/well/repeat.dlis"),
        requirements=(
            "Bind CBL twice with scales 0 to 100 and 0 to 10.",
            "Use source origin 40, source step 10, and 7 ticks.",
        ),
        constraints=("Keep the 200-400 scale reversed.",),
    )

    projected = _safe_task_for_correction(task)

    assert projected["source_hints"] == ["secondary source", "[redacted-path]"]
    assert projected["requirements"] == [
        "Bind CBL twice with scales 0 to 100 and 0 to 10.",
        "Use source origin 40, source step 10, and 7 ticks.",
    ]
    assert projected["constraints"] == ["Keep the 200-400 scale reversed."]


def test_report_correction_projection_does_not_add_source_hints() -> None:
    """Report correction context remains free of section-only source hints."""
    projected = _safe_task_for_correction(
        ReportTask(
            goal="Update the report.",
            requirements=("Keep the 0 to 100 scale.",),
        )
    )

    assert "source_hints" not in projected


def test_correction_request_preserves_redacted_original_semantics() -> None:
    """Semantic correction sees safe original evidence without exposing paths."""
    request = "Use C:\\logs\\well.las, GR 0 to 150, TT 200-400 reverse, 7 ticks."
    plan = SemanticPlan(
        summary="Build a section.",
        section_tasks=(
            SectionTask(
                goal="Build the section.",
                capability_ids=("section.log_plot",),
                source_hints=("main source",),
                requirements=("Preserve 0 to 150.",),
            ),
        ),
    )

    correction = _correction_request(
        mode="reconstruct",
        request=request,
        previous_plan=plan,
        diagnostic=PlannerSemanticError("unknown_capability", "Unknown capability id."),
        registry=create_builtin_registry(),
        timeout_seconds=5.0,
        temperature=0.0,
        max_output_tokens=1000,
    )

    assert "[redacted-path]" in correction.user_prompt
    assert "C:\\logs\\well.las" not in correction.user_prompt
    assert "GR 0 to 150" in correction.user_prompt
    assert "TT 200-400 reverse" in correction.user_prompt
    assert "7 ticks" in correction.user_prompt
    assert "main source" in correction.user_prompt


def test_correction_request_preserves_the_separate_source_summary() -> None:
    """Semantic correction receives the same bounded source facts."""
    plan = SemanticPlan(
        summary="Build a section.",
        section_tasks=(
            SectionTask(goal="Build the section.", capability_ids=("section.log_plot",)),
        ),
    )
    correction = _correction_request(
        mode="reconstruct",
        request="Build the section.",
        source_summary={"sources": [{"labels": ["main pass"], "channels": []}]},
        previous_plan=plan,
        diagnostic=PlannerSemanticError("unknown_capability", "Unknown capability id."),
        registry=create_builtin_registry(),
        timeout_seconds=5.0,
        temperature=0.0,
        max_output_tokens=1000,
    )

    assert '"labels":["main pass"]' in correction.user_prompt


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


def test_planner_retries_one_invalid_structured_response() -> None:
    """One provider invalid-response failure gets one normal planning retry."""
    backend = _SequenceBackend(
        responses=[
            ProviderRequestError(
                ProviderFailureCategory.INVALID_RESPONSE,
                "Planner returned invalid structured output.",
            ),
            _plan_payload(),
        ]
    )
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    result = asyncio.run(
        planner.plan(request="Build the CBL quicklook.", mode="reconstruct", timeout_seconds=5.0)
    )

    assert result == SemanticPlan.model_validate(_plan_payload())
    assert len(backend.requests) == 2
    assert backend.requests[0].user_prompt == backend.requests[1].user_prompt


def test_planner_stops_after_two_invalid_structured_responses() -> None:
    """Two invalid structured responses stop without a third provider call."""
    failure = ProviderRequestError(
        ProviderFailureCategory.INVALID_RESPONSE,
        "Planner returned invalid structured output.",
    )
    backend = _SequenceBackend(responses=[failure, failure])
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    with pytest.raises(ProviderRequestError):
        asyncio.run(
            planner.plan(
                request="Build the CBL quicklook.", mode="reconstruct", timeout_seconds=5.0
            )
        )

    assert len(backend.requests) == 2


def test_planner_invalid_response_then_semantic_failure_stays_bounded() -> None:
    """A retried plan with semantic errors cannot open a third correction call."""
    failure = ProviderRequestError(
        ProviderFailureCategory.INVALID_RESPONSE,
        "Planner returned invalid structured output.",
    )
    backend = _SequenceBackend(responses=[failure, _invalid_plan_payload("unknown_capability")])
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    with pytest.raises(PlannerSemanticFailure):
        asyncio.run(
            planner.plan(
                request="Build the CBL quicklook.", mode="reconstruct", timeout_seconds=5.0
            )
        )

    assert len(backend.requests) == 2


def test_planner_semantic_failure_then_invalid_response_stays_bounded() -> None:
    """A semantic correction that fails provider validation remains provider-owned."""
    failure = ProviderRequestError(
        ProviderFailureCategory.INVALID_RESPONSE,
        "Planner returned invalid structured output.",
    )
    backend = _SequenceBackend(responses=[_invalid_plan_payload("unknown_capability"), failure])
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    with pytest.raises(ProviderRequestError):
        asyncio.run(
            planner.plan(
                request="Build the CBL quicklook.", mode="reconstruct", timeout_seconds=5.0
            )
        )

    assert len(backend.requests) == 2


@pytest.mark.parametrize(
    "category",
    (
        ProviderFailureCategory.AUTHENTICATION,
        ProviderFailureCategory.TIMEOUT,
        ProviderFailureCategory.RATE_LIMIT,
        ProviderFailureCategory.TRANSPORT,
        ProviderFailureCategory.CONFIGURATION,
        ProviderFailureCategory.PROVIDER_REJECTED,
    ),
)
def test_planner_does_not_retry_non_invalid_provider_failures(
    category: ProviderFailureCategory,
) -> None:
    """Only invalid structured output receives planner-level recovery."""
    backend = _SequenceBackend(
        responses=[ProviderRequestError(category, "Planner provider failure.")]
    )
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    with pytest.raises(ProviderRequestError):
        asyncio.run(
            planner.plan(
                request="Build the CBL quicklook.", mode="reconstruct", timeout_seconds=5.0
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


def _section_plan(capability_ids: tuple[str, ...]) -> SemanticPlan:
    """Build a minimal section plan for structural capability validation tests."""
    return SemanticPlan(
        summary="Validate a section capability set.",
        section_tasks=(
            SectionTask(
                goal="Represent the requested section.",
                capability_ids=capability_ids,
            ),
        ),
    )


@pytest.mark.parametrize(
    "capability_ids",
    (
        ("section.log_plot",),
        ("section.log_plot", "track.normal", "binding.curve"),
        ("section.log_plot", "track.reference", "binding.curve"),
        ("section.log_plot", "track.array", "binding.raster"),
        (
            "binding.raster",
            "section.log_plot",
            "track.array",
            "track.normal",
            "binding.curve",
        ),
    ),
)
def test_selected_capability_parent_closure_accepts_valid_sets(
    capability_ids: tuple[str, ...],
) -> None:
    """Parent validation is generic and independent of capability ordering."""
    registry = create_builtin_registry()

    assert validate_semantic_plan(_section_plan(capability_ids), registry)


@pytest.mark.parametrize(
    "capability_ids, expected_parents",
    (
        (("section.log_plot", "binding.raster"), ("track.array",)),
        (("section.log_plot", "binding.curve"), ("track.normal", "track.reference")),
    ),
)
def test_selected_capability_parent_closure_reports_missing_parent(
    capability_ids: tuple[str, ...],
    expected_parents: tuple[str, ...],
) -> None:
    """Missing structural parents fail without host-side parent selection."""
    with pytest.raises(PlannerSemanticError) as caught:
        validate_semantic_plan(_section_plan(capability_ids), create_builtin_registry())

    assert caught.value.code == "missing_capability_parent"
    for parent in expected_parents:
        assert parent in caught.value.safe_message


def test_duplicate_section_capability_is_not_silently_deduplicated() -> None:
    """Repeated capability types remain planner evidence and fail validation."""
    plan = _section_plan(("section.log_plot", "track.normal", "binding.curve", "binding.curve"))

    with pytest.raises(PlannerSemanticError) as caught:
        validate_semantic_plan(plan, create_builtin_registry())

    assert caught.value.code == "duplicate_capability"


def test_duplicate_report_capability_is_rejected() -> None:
    """The unique-type rule applies to report work as well as section work."""
    plan = SemanticPlan(
        summary="Duplicate report capability.",
        report_task=ReportTask(
            goal="Update the report.",
            capability_ids=("report.standard", "report.standard"),
        ),
    )

    with pytest.raises(PlannerSemanticError) as caught:
        validate_semantic_plan(plan, create_builtin_registry())

    assert caught.value.code == "duplicate_capability"


def test_duplicate_plan_enters_correction_without_host_normalization() -> None:
    """A duplicate is corrected by the bounded planner path, not by the host."""
    invalid = _plan_payload()
    invalid["section_tasks"] = (
        {
            **invalid["section_tasks"][0],
            "capability_ids": (
                "section.log_plot",
                "track.normal",
                "binding.curve",
                "binding.curve",
            ),
        },
    )
    backend = _SequenceBackend(responses=[invalid, _plan_payload()])
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    result = asyncio.run(
        planner.plan(request="Build a section.", mode="reconstruct", timeout_seconds=5.0)
    )

    assert result == SemanticPlan.model_validate(_plan_payload())
    assert len(backend.requests) == 2
    correction = json.loads(backend.requests[1].user_prompt.split("Correction context:\n", 1)[1])
    assert correction["diagnostic"]["code"] == "duplicate_capability"
    assert correction["previous_plan"]["section_tasks"][0]["capability_ids"][-2:] == [
        "binding.curve",
        "binding.curve",
    ]


def test_missing_parent_enters_correction_without_host_injection() -> None:
    """A parent gap is corrected by the planner rather than closed deterministically."""
    invalid = _plan_payload()
    invalid["section_tasks"] = (
        {
            **invalid["section_tasks"][0],
            "capability_ids": ("section.log_plot", "binding.raster"),
        },
    )
    corrected = _plan_payload()
    corrected["section_tasks"] = (
        {
            **corrected["section_tasks"][0],
            "capability_ids": ("section.log_plot", "track.array", "binding.raster"),
        },
    )
    backend = _SequenceBackend(responses=[invalid, corrected])
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    result = asyncio.run(
        planner.plan(request="Build a section.", mode="reconstruct", timeout_seconds=5.0)
    )

    assert result == SemanticPlan.model_validate(corrected)
    assert len(backend.requests) == 2
    correction = json.loads(backend.requests[1].user_prompt.split("Correction context:\n", 1)[1])
    assert correction["diagnostic"]["code"] == "missing_capability_parent"
    assert correction["diagnostic"]["message"]
    assert correction["previous_plan"]["section_tasks"][0]["capability_ids"] == [
        "section.log_plot",
        "binding.raster",
    ]


def test_invalid_duplicate_correction_stays_bounded() -> None:
    """A duplicate surviving correction becomes a bounded typed failure."""
    invalid = _plan_payload()
    invalid["section_tasks"] = (
        {
            **invalid["section_tasks"][0],
            "capability_ids": ("section.log_plot", "binding.curve", "binding.curve"),
        },
    )
    backend = _SequenceBackend(responses=[invalid, invalid])
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    with pytest.raises(PlannerSemanticFailure) as caught:
        asyncio.run(
            planner.plan(request="Build a section.", mode="reconstruct", timeout_seconds=5.0)
        )

    assert caught.value.code == "duplicate_capability"
    assert len(backend.requests) == 2


def test_invalid_parent_correction_stays_bounded() -> None:
    """A parent gap surviving correction becomes a bounded typed failure."""
    invalid = _plan_payload()
    invalid["section_tasks"] = (
        {
            **invalid["section_tasks"][0],
            "capability_ids": ("section.log_plot", "binding.raster"),
        },
    )
    backend = _SequenceBackend(responses=[invalid, invalid])
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())

    with pytest.raises(PlannerSemanticFailure) as caught:
        asyncio.run(
            planner.plan(request="Build a section.", mode="reconstruct", timeout_seconds=5.0)
        )

    assert caught.value.code == "missing_capability_parent"
    assert len(backend.requests) == 2


def _synthetic_registry() -> CapabilityRegistry:
    """Return a test-only capability graph for plugin-style closure checks."""
    return CapabilityRegistry(
        (
            CapabilitySpec(
                capability_id="section.synthetic",
                category="section",
                description="Synthetic section capability.",
                artifact_model=BaseModel,
                compiler=lambda _artifact: None,
            ),
            CapabilitySpec(
                capability_id="track.synthetic",
                category="track",
                description="Synthetic track capability.",
                artifact_model=BaseModel,
                compiler=lambda _artifact: None,
                allowed_parents=("section.synthetic",),
            ),
            CapabilitySpec(
                capability_id="binding.synthetic",
                category="binding",
                description="Synthetic binding capability.",
                artifact_model=BaseModel,
                compiler=lambda _artifact: None,
                allowed_parents=("track.synthetic",),
            ),
        )
    )


def test_parent_closure_uses_registry_metadata_for_synthetic_capabilities() -> None:
    """Plugin-style parent relationships need no built-in capability branches."""
    registry = _synthetic_registry()
    incomplete = _section_plan(("section.synthetic", "binding.synthetic"))
    complete = _section_plan(("section.synthetic", "track.synthetic", "binding.synthetic"))

    with pytest.raises(PlannerSemanticError) as caught:
        validate_semantic_plan(incomplete, registry)
    assert caught.value.code == "missing_capability_parent"
    assert validate_semantic_plan(complete, registry) == complete


def test_mixed_report_and_section_work_remains_valid() -> None:
    """Planner capability validation does not impose report/section exclusivity."""
    plan = SemanticPlan(
        summary="Update the report and add one section.",
        report_task=ReportTask(
            goal="Update the report.",
            capability_ids=("report.standard",),
        ),
        section_tasks=(
            SectionTask(
                goal="Add a curve section.",
                capability_ids=("section.log_plot", "track.normal", "binding.curve"),
            ),
        ),
    )

    assert validate_semantic_plan(plan, create_builtin_registry()) == plan


def test_unresolved_requirements_remain_legal() -> None:
    """Planner remediation does not redefine unresolved semantic requirements."""
    plan = SemanticPlan(
        summary="Keep one unsupported request visible.",
        section_tasks=(
            SectionTask(
                goal="Add a curve section.",
                capability_ids=("section.log_plot", "track.normal", "binding.curve"),
            ),
        ),
        unresolved_requirements=("Keep the unsupported detail visible.",),
    )

    assert validate_semantic_plan(plan, create_builtin_registry()) == plan


def test_semantic_planner_does_not_require_a_specific_registry_implementation() -> None:
    """Host validation works with any registry containing the static capability IDs."""
    registry = CapabilityRegistry(tuple(create_builtin_registry()))
    plan = SemanticPlan.model_validate(_plan_payload())

    assert validate_semantic_plan(plan, registry) == plan
