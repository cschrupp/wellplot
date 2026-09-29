"""Tests for the deterministic CM-58.2 report-boundary safety layer."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from wellplot.agent.code_mode.enrichment import (
    EnrichedSemanticContext,
    ReportContext,
    ResolvedSectionContext,
)
from wellplot.agent.code_mode.facade import CodeModeCompileFacade
from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.code_mode.report_boundary_safety import (
    ReportBoundaryActionKind,
    ReportBoundaryIntent,
    ReportBoundarySafetyFailure,
    classify_report_boundary_intent,
    enforce_report_boundary_safety,
)
from wellplot.agent.code_mode.workflow import CodeModeGraphDependencies
from wellplot.authoring_program.models import (
    AuthoringProgram,
    ProgramArtifact,
    ProgramExecutionResult,
    ProgramMetrics,
    ProgramSource,
)
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.model.intent import AuthoringDocumentIntent

REGISTRY = create_builtin_registry()


def _section_task(
    *capability_ids: str,
    goal: str = "plot the requested section",
) -> SectionTask:
    """Build one valid section task for boundary tests."""
    return SectionTask(goal=goal, capability_ids=capability_ids)


def _plan(
    *,
    report_task: ReportTask | None = None,
    section_tasks: tuple[SectionTask, ...] = (),
    summary: str = "boundary test",
) -> SemanticPlan:
    """Build one semantic plan accepted by the static planner model."""
    return SemanticPlan(
        summary=summary,
        report_task=report_task,
        section_tasks=section_tasks,
    )


def _document() -> AuthoringDocumentSpec:
    """Build the smallest document accepted by the compile facade."""
    return AuthoringDocumentSpec(
        name="cm-58-2",
        title="Current report",
        sections=[
            {
                "id": "existing",
                "title": "Existing section",
                "tracks": [
                    {
                        "id": "existing-track",
                        "title": "Existing track",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                ],
            }
        ],
    )


def _successful_result(title: str, *, section: bool = False) -> ProgramExecutionResult:
    """Build bounded successful worker evidence."""
    program = AuthoringProgram(
        source=ProgramSource(text="artifact = wp.section()", logical_name="test.wpa")
    )
    intent = AuthoringDocumentIntent(title=title)
    if section:
        intent = AuthoringDocumentIntent(
            sections=[{"section_id": "test-section", "title": title}],
        )
    return ProgramExecutionResult(
        program=program,
        success=True,
        artifact=ProgramArtifact(
            intent_fragment=intent,
        ),
        metrics=ProgramMetrics(),
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Prepare a handover brief with the heading Final Integrity.", "report_only"),
        ("Set up a report cover with subtitle Final Interpretation.", "report_only"),
        ("Prepare a memo.", "report_only"),
        ("Write a completion summary.", "report_only"),
        ("Set the heading to Final Integrity.", "report_only"),
        ("Add prepared by Carlos.", "report_only"),
        ("Set the preparer field.", "report_only"),
        ("Show the density curve in one log view.", "section_only"),
        ("Create an ordinary image panel.", "section_only"),
        ("Create independent log sections for gamma and resistivity.", "section_only"),
        ("Prepare an image memo and add one waveform display.", "mixed"),
        ("Set the packet heading to Crossplot Brief and provide two panels.", "mixed"),
        ("Prepare a brief and show the density curve.", "mixed"),
        ("Make the requested changes.", "unspecified"),
        ("Set the title.", "unspecified"),
        ("Set the summary.", "unspecified"),
        ("PREPARE A MEMO, THEN ADD A PANEL!", "mixed"),
        ("Prepare a handover-brief with a report-header.", "report_only"),
        (
            "Show the Fig interval permeability response as one scalar display.",
            "section_only",
        ),
        (
            "Keep a depth marker alongside the Linden resistivity trace in a shared display.",
            "section_only",
        ),
    ],
)
def test_report_boundary_classifier(text: str, expected: str) -> None:
    """Classify bounded report and section signals deterministically."""
    assert classify_report_boundary_intent(text) is ReportBoundaryIntent(expected)


@pytest.mark.parametrize(
    "text",
    [
        "Display the report title Pressure Review.",
        "Display the preparer name on the report cover.",
        "Display the report heading Completion Review.",
        "Use the display name Final Interpretation for the report title.",
    ],
)
def test_bare_display_does_not_create_section_intent(text: str) -> None:
    """Generic display language remains report-only when report signals exist."""
    assert classify_report_boundary_intent(text) is ReportBoundaryIntent.REPORT_ONLY


def test_bare_response_does_not_create_section_intent() -> None:
    """Response is not an independent section signal."""
    assert (
        classify_report_boundary_intent(
            "Summarize the permeability response in the completion report."
        )
        is ReportBoundaryIntent.REPORT_ONLY
    )


def test_bare_trace_does_not_create_section_intent() -> None:
    """Trace is not an independent section signal."""
    assert (
        classify_report_boundary_intent("Review the resistivity trace for the completion summary.")
        is ReportBoundaryIntent.REPORT_ONLY
    )


def test_scalar_display_mixed_intent_preserves_both_domains() -> None:
    """A report note plus scalar display remains mixed intent."""
    assert (
        classify_report_boundary_intent(
            "Add the review note Accepted and show the permeability response as one scalar display."
        )
        is ReportBoundaryIntent.MIXED
    )


def test_report_boundary_evidence_is_normalized_and_path_free() -> None:
    """Evidence contains no normalized request or path-shaped text."""
    plan = _plan(report_task=ReportTask(goal="prepare a report", capability_ids=()))
    first = enforce_report_boundary_safety(
        request="Prepare a REPORT at /tmp/hidden/report.pdf with a heading.",
        plan=plan,
        registry=REGISTRY,
    )
    second = enforce_report_boundary_safety(
        request="Prepare a REPORT at /tmp/hidden/report.pdf with a heading.",
        plan=plan,
        registry=REGISTRY,
    )
    assert first.evidence() == second.evidence()
    serialized = first.evidence().model_dump_json()
    assert "/tmp/hidden" not in serialized
    assert "prepare a report" not in serialized


def test_aurora_empty_report_task_gains_standard() -> None:
    """Repair the protected P10 empty report-capability class."""
    plan = _plan(
        report_task=ReportTask(
            goal="prepare the handover brief",
            requirements=("include the final heading",),
            constraints=("keep report-wide settings",),
        )
    )
    result = enforce_report_boundary_safety(
        request="Prepare a handover brief with the heading Final Integrity.",
        plan=plan,
        registry=REGISTRY,
    )
    assert result.safe_plan.report_task is not None
    assert result.safe_plan.report_task.capability_ids == ("report.standard",)
    assert result.actions[0].kind is ReportBoundaryActionKind.ADD_REPORT_STANDARD
    assert result.changed is True


def test_existing_report_task_passes_unchanged() -> None:
    """A valid explicit report task is not normalized or duplicated."""
    plan = _plan(
        report_task=ReportTask(goal="prepare the memo", capability_ids=("report.standard",))
    )
    result = enforce_report_boundary_safety(
        request="Prepare a memo.",
        plan=plan,
        registry=REGISTRY,
    )
    assert result.safe_plan == plan
    assert result.changed is False
    assert result.actions == ()


def test_report_only_missing_task_fails_closed() -> None:
    """Report semantics are not synthesized from the request."""
    plan = _plan(
        section_tasks=(_section_task("section.log_plot", "track.normal", "binding.curve"),)
    )
    with pytest.raises(ReportBoundarySafetyFailure) as failure:
        enforce_report_boundary_safety(
            request="Prepare a handover brief with the heading Final Integrity.",
            plan=plan,
            registry=REGISTRY,
        )
    assert failure.value.code == "report_task_missing_for_explicit_report_intent"


def test_report_only_section_contamination_fails_closed() -> None:
    """Report-only intent does not delete potentially substantive sections."""
    plan = _plan(
        report_task=ReportTask(goal="prepare the report", capability_ids=("report.standard",)),
        section_tasks=(_section_task("section.log_plot", "track.normal", "binding.curve"),),
    )
    with pytest.raises(ReportBoundarySafetyFailure) as failure:
        enforce_report_boundary_safety(
            request="Prepare a completion summary.",
            plan=plan,
            registry=REGISTRY,
        )
    assert failure.value.code == "unexpected_section_work_for_report_only"


def test_report_only_nonempty_unsupported_report_capability_fails() -> None:
    """Explicit report intent does not silently append to another capability set."""
    plan = _plan(
        report_task=ReportTask(goal="prepare the report", capability_ids=("report.standard",))
    )
    invalid = plan.model_copy(
        update={
            "report_task": plan.report_task.model_copy(
                update={"capability_ids": ("report.unknown",)}
            )
        }
    )
    with pytest.raises(ReportBoundarySafetyFailure) as failure:
        enforce_report_boundary_safety(
            request="Prepare a report.",
            plan=invalid,
            registry=REGISTRY,
        )
    assert failure.value.code == "report_standard_missing_from_nonempty_report_task"


def test_mixed_empty_report_capabilities_gain_standard_only() -> None:
    """Mixed repair changes report capability selection and no section fields."""
    section = _section_task("section.log_plot", "track.normal", "binding.curve")
    plan = _plan(
        report_task=ReportTask(goal="prepare the memo", requirements=("add heading",)),
        section_tasks=(section,),
    )
    result = enforce_report_boundary_safety(
        request="Prepare an image memo and add one waveform display.",
        plan=plan,
        registry=REGISTRY,
    )
    assert result.safe_plan.section_tasks == (section,)
    assert result.safe_plan.report_task is not None
    assert result.safe_plan.report_task.requirements == ("add heading",)
    assert result.safe_plan.report_task.capability_ids == ("report.standard",)


def test_mixed_missing_report_task_fails_closed() -> None:
    """Mixed intent cannot synthesize a missing report work unit."""
    plan = _plan(
        section_tasks=(_section_task("section.log_plot", "track.normal", "binding.curve"),)
    )
    with pytest.raises(ReportBoundarySafetyFailure) as failure:
        enforce_report_boundary_safety(
            request="Prepare an image memo and add one waveform display.",
            plan=plan,
            registry=REGISTRY,
        )
    assert failure.value.code == "report_task_missing_for_mixed_intent"


def test_mixed_missing_section_task_fails_closed() -> None:
    """Mixed intent cannot synthesize a missing section work unit."""
    plan = _plan(report_task=ReportTask(goal="prepare the memo", capability_ids=()))
    with pytest.raises(ReportBoundarySafetyFailure) as failure:
        enforce_report_boundary_safety(
            request="Prepare an image memo and add one waveform display.",
            plan=plan,
            registry=REGISTRY,
        )
    assert failure.value.code == "section_task_missing_for_mixed_intent"


@pytest.mark.parametrize("capability_ids", [(), ("report.standard",)])
def test_section_only_spurious_report_task_is_removed(capability_ids: tuple[str, ...]) -> None:
    """Section-only intent removes both empty and selected report tasks."""
    section = _section_task("section.log_plot", "track.normal", "binding.curve")
    plan = _plan(
        report_task=ReportTask(goal="spurious report", capability_ids=capability_ids),
        section_tasks=(section,),
    )
    result = enforce_report_boundary_safety(
        request="Show the density curve in one log view.",
        plan=plan,
        registry=REGISTRY,
    )
    assert result.safe_plan.report_task is None
    assert result.safe_plan.section_tasks == (section,)
    assert result.actions[0].kind is ReportBoundaryActionKind.REMOVE_REPORT_TASK


@pytest.mark.parametrize(
    ("request_text", "section"),
    [
        (
            "Show the Fig interval permeability response as one scalar display.",
            ("section.log_plot", "track.normal", "binding.curve"),
        ),
        (
            "Keep a depth marker alongside the Linden resistivity trace in a shared display.",
            ("section.log_plot", "track.reference", "track.normal", "binding.curve"),
        ),
    ],
)
def test_cm59a_spurious_report_task_is_removed_for_new_display_phrases(
    request_text: str,
    section: tuple[str, ...],
) -> None:
    """The demonstrated Fig/Linden residual plans lose only report work."""
    section_task = _section_task(*section)
    plan = _plan(
        report_task=ReportTask(goal="spurious report", capability_ids=("report.standard",)),
        section_tasks=(section_task,),
    )
    result = enforce_report_boundary_safety(request=request_text, plan=plan, registry=REGISTRY)
    assert result.intent is ReportBoundaryIntent.SECTION_ONLY
    assert result.actions[0].kind is ReportBoundaryActionKind.REMOVE_REPORT_TASK
    assert result.safe_plan.report_task is None
    assert result.safe_plan.section_tasks == (section_task,)
    assert result.safe_plan.model_dump(mode="json")["section_tasks"] == [
        section_task.model_dump(mode="json")
    ]


@pytest.mark.parametrize(
    ("request_text", "section"),
    [
        (
            "Show the Fig interval permeability response as one scalar display.",
            ("section.log_plot", "track.normal", "binding.curve"),
        ),
        (
            "Keep a depth marker alongside the Linden resistivity trace in a shared display.",
            ("section.log_plot", "track.reference", "track.normal", "binding.curve"),
        ),
    ],
)
def test_cm59a_correct_display_plans_are_no_ops(
    request_text: str,
    section: tuple[str, ...],
) -> None:
    """Correct section-only plans remain semantically identical under v2."""
    plan = _plan(section_tasks=(_section_task(*section),))
    result = enforce_report_boundary_safety(request=request_text, plan=plan, registry=REGISTRY)
    assert result.intent is ReportBoundaryIntent.SECTION_ONLY
    assert result.changed is False
    assert result.actions == ()
    assert result.safe_plan == plan


def test_report_boundary_policy_is_v2() -> None:
    """New report-boundary evidence identifies the revised policy."""
    plan = _plan(section_tasks=(_section_task("section.log_plot", "track.normal"),))
    result = enforce_report_boundary_safety(
        request="Show one scalar display.",
        plan=plan,
        registry=REGISTRY,
    )
    assert result.policy_version == "cm58.report-boundary.v2"
    assert result.evidence().policy_version == "cm58.report-boundary.v2"


def test_section_only_report_removal_would_empty_plan_fails() -> None:
    """Never return a plan with no work units after report removal."""
    plan = _plan(report_task=ReportTask(goal="spurious report", capability_ids=()))
    with pytest.raises(ReportBoundarySafetyFailure) as failure:
        enforce_report_boundary_safety(
            request="Show the density curve in one log view.",
            plan=plan,
            registry=REGISTRY,
        )
    assert failure.value.code == "report_removal_would_empty_plan"


def test_unspecified_empty_report_task_fails_without_guessing() -> None:
    """An empty report task is ambiguous when request intent is unspecified."""
    with pytest.raises(ReportBoundarySafetyFailure) as failure:
        enforce_report_boundary_safety(
            request="Make the requested changes.",
            plan=_plan(report_task=ReportTask(goal="unclear report")),
            registry=REGISTRY,
        )
    assert failure.value.code == "empty_report_task_with_unspecified_intent"


def test_unspecified_valid_report_task_passes() -> None:
    """A complete report task is not second-guessed without explicit intent."""
    plan = _plan(
        report_task=ReportTask(goal="update metadata", capability_ids=("report.standard",))
    )
    result = enforce_report_boundary_safety(
        request="Make the requested changes.",
        plan=plan,
        registry=REGISTRY,
    )
    assert result.safe_plan == plan
    assert result.changed is False


@pytest.mark.parametrize(
    "text",
    [
        "p10-report-ember-02: prepare a valid report.",
        "p10-report-cobalt-03: prepare a valid report.",
        "p10-report-mariner-04: prepare a valid report.",
    ],
)
def test_p10_report_controls_preserve_valid_report_tasks(text: str) -> None:
    """P10 report-only controls remain unchanged when already valid."""
    plan = _plan(report_task=ReportTask(goal="prepare report", capability_ids=("report.standard",)))
    result = enforce_report_boundary_safety(request=text, plan=plan, registry=REGISTRY)
    assert result.safe_plan == plan
    assert result.changed is False


@pytest.mark.parametrize(
    "text",
    [
        "p10-mixed-report-sierra-21: prepare a packet and add one panel.",
        "p10-mixed-report-boreal-22: write a memo and show one curve.",
        "p10-mixed-report-kestrel-23: set the heading and add a waveform.",
        "p10-mixed-report-alpine-24: prepare a report and plot an image.",
    ],
)
def test_p10_mixed_controls_are_mixed(text: str) -> None:
    """P10 mixed controls require both report and section work."""
    assert classify_report_boundary_intent(text) is ReportBoundaryIntent.MIXED


def test_repair_preserves_all_plan_semantics_and_is_immutable() -> None:
    """Only report capability selection changes during an add repair."""
    section = _section_task("section.log_plot", "track.normal", "binding.curve")
    plan = SemanticPlan(
        summary="preserve this summary",
        report_task=ReportTask(
            goal="preserve this report goal",
            requirements=("keep heading",),
            constraints=("keep page",),
        ),
        section_tasks=(section,),
        unresolved_requirements=("none",),
    )
    result = enforce_report_boundary_safety(
        request=(
            "Prepare a handover brief with the heading Final Integrity and show the density curve."
        ),
        plan=plan,
        registry=REGISTRY,
    )
    assert plan.report_task is not None
    assert plan.report_task.capability_ids == ()
    assert result.safe_plan.summary == plan.summary
    assert result.safe_plan.report_task is not None
    assert result.safe_plan.report_task.goal == plan.report_task.goal
    assert result.safe_plan.report_task.requirements == plan.report_task.requirements
    assert result.safe_plan.report_task.constraints == plan.report_task.constraints
    assert result.safe_plan.section_tasks == plan.section_tasks
    assert result.safe_plan.unresolved_requirements == plan.unresolved_requirements


def test_revalidation_failure_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transformed plan that fails existing validation is rejected."""
    from wellplot.agent.code_mode import report_boundary_safety
    from wellplot.agent.code_mode.planner import PlannerSemanticError

    def fail_validation(*_args: object, **_kwargs: object) -> None:
        raise PlannerSemanticError("invalid", "invalid")

    monkeypatch.setattr(report_boundary_safety, "validate_semantic_plan", fail_validation)
    with pytest.raises(ReportBoundarySafetyFailure) as failure:
        enforce_report_boundary_safety(
            request="Prepare a handover brief.",
            plan=_plan(report_task=ReportTask(goal="prepare report")),
            registry=REGISTRY,
        )
    assert failure.value.code == "report_boundary_repair_invalid"


def test_safety_evidence_is_deterministic_and_path_free() -> None:
    """Repeated identical repairs yield identical bounded evidence."""
    plan = _plan(report_task=ReportTask(goal="prepare report"))
    first = enforce_report_boundary_safety(
        request="Prepare a memo at C:\\private\\report.pdf.",
        plan=plan,
        registry=REGISTRY,
    )
    second = enforce_report_boundary_safety(
        request="Prepare a memo at C:\\private\\report.pdf.",
        plan=plan,
        registry=REGISTRY,
    )
    assert first.evidence() == second.evidence()
    assert "private" not in first.evidence().model_dump_json()


@dataclass
class _Planner:
    """Deterministic planner double with the production registry seam."""

    plan_value: SemanticPlan
    registry: object = field(default_factory=create_builtin_registry)
    calls: int = 0

    async def plan(self, **_kwargs: object) -> SemanticPlan:
        """Return the configured plan without a provider call."""
        self.calls += 1
        return self.plan_value


@dataclass
class _Enricher:
    """Record the final plan that crosses both safety boundaries."""

    plans: list[SemanticPlan] = field(default_factory=list)

    def enrich(self, *, plan: SemanticPlan, **_kwargs: object) -> EnrichedSemanticContext:
        """Return bounded report and section context for the repaired plan."""
        self.plans.append(plan)
        return EnrichedSemanticContext(
            plan=plan,
            sections=tuple(
                ResolvedSectionContext(task_index=index)
                for index, _task in enumerate(plan.section_tasks)
            ),
            report=ReportContext(),
        )


@dataclass
class _Workers:
    """Count deterministic report and section worker invocations."""

    report_calls: list[ReportTask] = field(default_factory=list)
    section_calls: list[SectionTask] = field(default_factory=list)

    async def compile_report(
        self, *, task: ReportTask, **_kwargs: object
    ) -> ProgramExecutionResult:
        """Return one successful report result."""
        self.report_calls.append(task)
        return _successful_result("report")

    async def compile_section(
        self,
        *,
        context: ResolvedSectionContext,
        **_kwargs: object,
    ) -> ProgramExecutionResult:
        """Return one successful section result."""
        del context
        self.section_calls.append(
            _section_task("section.log_plot", "track.normal", "binding.curve")
        )
        return _successful_result("section", section=True)


class _ReportAdapter:
    """Adapt deterministic workers to the report compiler boundary."""

    def __init__(self, workers: _Workers) -> None:
        self.workers = workers

    async def compile(self, **kwargs: object) -> ProgramExecutionResult:
        """Delegate to the report worker double."""
        return await self.workers.compile_report(**kwargs)


class _SectionAdapter:
    """Adapt deterministic workers to the section compiler boundary."""

    def __init__(self, workers: _Workers) -> None:
        self.workers = workers

    async def compile(self, **kwargs: object) -> ProgramExecutionResult:
        """Delegate to the section worker double."""
        return await self.workers.compile_section(**kwargs)


def _compile(
    plan: SemanticPlan,
    request: str,
    workers: _Workers,
    enricher: _Enricher,
) -> object:
    """Run the production graph with deterministic worker doubles."""
    return asyncio.run(
        CodeModeCompileFacade(
            CodeModeGraphDependencies(
                planner=_Planner(plan),
                enricher=enricher,
                report_compiler=_ReportAdapter(workers),
                section_compiler=_SectionAdapter(workers),
            )
        ).compile(
            request=request,
            mode="reconstruct",
            document=_document(),
            source_candidates=(),
            timeout_seconds=5.0,
        )
    )


def test_graph_report_repair_runs_before_report_worker() -> None:
    """Aurora-class repair reaches the report worker with report.standard."""
    plan = _plan(report_task=ReportTask(goal="prepare report"))
    workers = _Workers()
    enricher = _Enricher()
    result = _compile(
        plan,
        "Prepare a handover brief with the heading Final Integrity.",
        workers,
        enricher,
    )
    assert result.success is True
    assert len(workers.report_calls) == 1
    assert workers.report_calls[0].capability_ids == ("report.standard",)
    assert workers.section_calls == []
    assert enricher.plans[0].report_task is not None
    assert any(
        diagnostic.code == "report_boundary_safety.report_standard_added"
        for diagnostic in result.diagnostics
    )


def test_graph_section_only_cleanup_skips_report_worker() -> None:
    """Section-only repair removes the report work before dispatch."""
    plan = _plan(
        report_task=ReportTask(goal="spurious report", capability_ids=("report.standard",)),
        section_tasks=(_section_task("section.log_plot", "track.normal", "binding.curve"),),
    )
    workers = _Workers()
    enricher = _Enricher()
    result = _compile(plan, "Show the density curve in one log view.", workers, enricher)
    assert result.success is True
    assert workers.report_calls == []
    assert len(workers.section_calls) == 1
    assert enricher.plans[0].report_task is None
    assert any(
        diagnostic.code == "report_boundary_safety.unrequested_report_task_removed"
        for diagnostic in result.diagnostics
    )


def test_graph_mixed_repair_keeps_both_work_units() -> None:
    """Mixed intent adds the report capability without changing section work."""
    section = _section_task("section.log_plot", "track.normal", "binding.curve")
    plan = _plan(report_task=ReportTask(goal="prepare memo"), section_tasks=(section,))
    workers = _Workers()
    enricher = _Enricher()
    result = _compile(
        plan,
        "Prepare an image memo and add one waveform display.",
        workers,
        enricher,
    )
    assert result.success is True
    assert len(workers.report_calls) == 1
    assert len(workers.section_calls) == 1
    assert enricher.plans[0].section_tasks == (section,)


def test_graph_report_boundary_failure_stops_enrichment_and_workers() -> None:
    """Missing explicit report work fails before enrichment or dispatch."""
    plan = _plan(
        section_tasks=(_section_task("section.log_plot", "track.normal", "binding.curve"),)
    )
    workers = _Workers()
    enricher = _Enricher()
    result = _compile(
        plan,
        "Prepare a handover brief with the heading Final Integrity.",
        workers,
        enricher,
    )
    assert result.success is False
    assert result.merged_intent is None
    assert result.metrics.worker_count == 0
    assert workers.report_calls == []
    assert workers.section_calls == []
    assert enricher.plans == []
    assert result.diagnostics[0].stage == "report_boundary_safety"
    assert result.diagnostics[0].code == (
        "report_boundary_safety.report_task_missing_for_explicit_report_intent"
    )


def test_reference_safety_failure_prevents_report_boundary_and_workers() -> None:
    """The first safety layer remains terminal and prevents the second layer."""
    plan = _plan(
        report_task=ReportTask(goal="spurious report", capability_ids=("report.standard",)),
        section_tasks=(_section_task("section.log_plot", "track.reference"),),
    )
    workers = _Workers()
    enricher = _Enricher()
    result = _compile(plan, "Show the curve in one log view.", workers, enricher)
    assert result.success is False
    assert result.metrics.worker_count == 0
    assert workers.report_calls == []
    assert workers.section_calls == []
    assert enricher.plans == []
    assert result.diagnostics[0].stage == "capability_safety"
    assert not any(
        diagnostic.stage == "report_boundary_safety" for diagnostic in result.diagnostics
    )


def test_composed_safety_layers_preserve_order_and_emit_both_warnings() -> None:
    """CM-58.1 runs before CM-58.2 and both repairs reach enrichment."""
    section = _section_task(
        "section.log_plot",
        "track.reference",
        "track.normal",
        "binding.curve",
    )
    plan = _plan(
        report_task=ReportTask(goal="spurious report", capability_ids=("report.standard",)),
        section_tasks=(section,),
    )
    workers = _Workers()
    enricher = _Enricher()
    result = _compile(plan, "Show the curve in one log view.", workers, enricher)
    assert result.success is True
    assert workers.report_calls == []
    assert enricher.plans[0].report_task is None
    assert enricher.plans[0].section_tasks[0].capability_ids == (
        "section.log_plot",
        "track.normal",
        "binding.curve",
    )
    safety_stages = [
        diagnostic.stage
        for diagnostic in result.diagnostics
        if diagnostic.stage in {"capability_safety", "report_boundary_safety"}
    ]
    assert safety_stages == ["capability_safety", "report_boundary_safety"]
