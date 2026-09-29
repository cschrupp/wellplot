"""Tests for the deterministic CM-58.3 section-leaf safety layer."""

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
from wellplot.agent.code_mode.planner import (
    PlannerSemanticError,
    ReportTask,
    SectionTask,
    SemanticPlan,
)
from wellplot.agent.code_mode.section_leaf_safety import (
    SECTION_LEAF_POLICY_VERSION,
    SectionLeafSafetyActionKind,
    SectionLeafSafetyFailure,
    enforce_section_leaf_safety,
    project_section_leaf_request,
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


def _task(*capability_ids: str) -> SectionTask:
    """Build one semantic section task."""
    return SectionTask(goal="plot the requested view", capability_ids=capability_ids)


def _plan(
    *tasks: SectionTask,
    report: ReportTask | None = None,
) -> SemanticPlan:
    """Build one valid semantic plan."""
    return SemanticPlan(summary="section leaf test", report_task=report, section_tasks=tasks)


def test_request_projection_is_bounded_and_deterministic() -> None:
    """Only four booleans are retained from normalized request semantics."""
    evidence = project_section_leaf_request("Add the REVIEW note at /tmp/private and a WAVEFORM.")
    assert evidence.model_dump() == {
        "curve_explicit": False,
        "raster_explicit": True,
        "section_annotation_explicit": False,
        "report_note_explicit": True,
    }
    assert "/tmp/private" not in evidence.model_dump_json()


def test_prairie_raster_only_curve_binding_is_removed() -> None:
    """A raster-only reference section loses only the stray curve binding."""
    plan = _plan(
        _task(
            "section.log_plot",
            "track.reference",
            "track.array",
            "binding.raster",
            "binding.curve",
        )
    )
    result = enforce_section_leaf_safety(
        request=(
            "Keep the Prairie waveform image synchronized with an explicit depth reference track."
        ),
        plan=plan,
        registry=REGISTRY,
    )
    assert result.safe_plan.section_tasks[0].capability_ids == (
        "section.log_plot",
        "track.reference",
        "track.array",
        "binding.raster",
    )
    assert result.actions[0].kind is SectionLeafSafetyActionKind.REMOVE_RASTER_ONLY_CURVE_BINDING


@pytest.mark.parametrize(
    "request_text",
    [
        "Build one view containing a scalar curve and an image track.",
        "Keep the gamma response and resistivity response together.",
    ],
)
def test_curve_positive_and_mesa_controls_are_unchanged(request_text: str) -> None:
    """Curve evidence or no raster evidence prevents asymmetric pruning."""
    plan = _plan(_task("section.log_plot", "track.array", "binding.raster", "binding.curve"))
    result = enforce_section_leaf_safety(request=request_text, plan=plan, registry=REGISTRY)
    assert result.safe_plan == plan
    assert result.actions == ()


def test_raster_only_normal_track_ambiguity_fails_closed() -> None:
    """A normal-track structure is not reduced by a leaf-only repair."""
    plan = _plan(
        _task("section.log_plot", "track.normal", "track.array", "binding.raster", "binding.curve")
    )
    with pytest.raises(SectionLeafSafetyFailure) as failure:
        enforce_section_leaf_safety(request="Create an image track.", plan=plan, registry=REGISTRY)
    assert failure.value.code == "raster_only_scalar_structure_ambiguous"


def test_report_note_annotation_leakage_is_removed() -> None:
    """Report-note semantics do not create section annotation work."""
    plan = _plan(
        _task(
            "section.log_plot",
            "track.normal",
            "binding.curve",
            "track.array",
            "binding.raster",
            "track.annotation",
            "annotation.typed",
        ),
        report=ReportTask(goal="prepare report", capability_ids=("report.standard",)),
    )
    result = enforce_section_leaf_safety(
        request=(
            "Add the Alpine review note Dual response check and make one combined panel with "
            "a scalar curve and an acoustic image."
        ),
        plan=plan,
        registry=REGISTRY,
    )
    assert result.safe_plan.section_tasks[0].capability_ids == (
        "section.log_plot",
        "track.normal",
        "binding.curve",
        "track.array",
        "binding.raster",
    )
    assert result.actions[0].kind is (
        SectionLeafSafetyActionKind.REMOVE_REPORT_NOTE_ANNOTATION_LEAKAGE
    )


def test_explicit_section_annotation_is_preserved() -> None:
    """A direct annotation request protects annotation capabilities."""
    plan = _plan(_task("section.log_plot", "track.normal", "track.annotation", "annotation.typed"))
    result = enforce_section_leaf_safety(
        request=(
            "Add the review note Approved and annotate the curve with a marker at the interval top."
        ),
        plan=plan,
        registry=REGISTRY,
    )
    assert result.safe_plan == plan


def test_annotation_only_pruning_fails_closed() -> None:
    """The layer never deletes a section to remove annotation leakage."""
    plan = _plan(_task("section.log_plot", "track.annotation", "annotation.typed"))
    with pytest.raises(SectionLeafSafetyFailure) as failure:
        enforce_section_leaf_safety(
            request="Add the report note Approved.",
            plan=plan,
            registry=REGISTRY,
        )
    assert failure.value.code == "annotation_prune_would_empty_section"


def test_lichen_section_allocation_is_not_repaired() -> None:
    """Section-local allocation remains outside CM-58.3 authority."""
    plan = _plan(_task("section.log_plot", "track.reference", "binding.curve"))
    result = enforce_section_leaf_safety(
        request="Create three views: a scalar curve, a depth-referenced curve, and an image.",
        plan=plan,
        registry=REGISTRY,
    )
    assert result.safe_plan == plan
    assert "track.normal" not in result.safe_plan.section_tasks[0].capability_ids


def test_repair_actions_are_ordered_and_revalidated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both repairs run in rule order and validation is mandatory."""
    plan = _plan(
        _task(
            "section.log_plot",
            "track.reference",
            "track.array",
            "binding.raster",
            "binding.curve",
            "track.annotation",
            "annotation.typed",
        )
    )
    result = enforce_section_leaf_safety(
        request="Add the report note Approved to the waveform image.",
        plan=plan,
        registry=REGISTRY,
    )
    assert [action.kind for action in result.actions] == [
        SectionLeafSafetyActionKind.REMOVE_RASTER_ONLY_CURVE_BINDING,
        SectionLeafSafetyActionKind.REMOVE_REPORT_NOTE_ANNOTATION_LEAKAGE,
    ]
    assert result.safe_plan.section_tasks[0].capability_ids == (
        "section.log_plot",
        "track.reference",
        "track.array",
        "binding.raster",
    )

    import wellplot.agent.code_mode.section_leaf_safety as module

    def reject(*_args: object, **_kwargs: object) -> None:
        raise PlannerSemanticError("forced_failure", "unexpected")

    monkeypatch.setattr(module, "validate_semantic_plan", reject)
    with pytest.raises(SectionLeafSafetyFailure) as failure:
        enforce_section_leaf_safety(
            request="Keep the waveform image with the report note Approved.",
            plan=plan,
            registry=REGISTRY,
        )
    assert failure.value.code == "section_leaf_repair_invalid"


@dataclass
class _Planner:
    """Deterministic planner double for graph composition tests."""

    plan_value: SemanticPlan
    registry: object = field(default_factory=create_builtin_registry)

    async def plan(self, **_kwargs: object) -> SemanticPlan:
        """Return the configured plan without provider activity."""
        return self.plan_value


@dataclass
class _Enricher:
    """Capture the plan crossing all three safety layers."""

    plans: list[SemanticPlan] = field(default_factory=list)

    def enrich(self, *, plan: SemanticPlan, **_kwargs: object) -> EnrichedSemanticContext:
        """Return bounded empty contexts for every surviving section."""
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
    """Capture worker execution after safety layers complete."""

    report_calls: list[ReportTask] = field(default_factory=list)
    section_calls: list[SectionTask] = field(default_factory=list)

    async def compile_report(
        self, *, task: ReportTask, **_kwargs: object
    ) -> ProgramExecutionResult:
        """Return one successful report fragment."""
        self.report_calls.append(task)
        return ProgramExecutionResult(
            program=AuthoringProgram(source=ProgramSource(text="report", logical_name="test.wpa")),
            success=True,
            artifact=ProgramArtifact(intent_fragment=AuthoringDocumentIntent(title="report")),
            metrics=ProgramMetrics(),
        )

    async def compile_section(
        self,
        *,
        context: ResolvedSectionContext,
        **_kwargs: object,
    ) -> ProgramExecutionResult:
        """Return one successful section fragment."""
        del context
        self.section_calls.append(_task("section.log_plot", "track.array", "binding.raster"))
        return ProgramExecutionResult(
            program=AuthoringProgram(source=ProgramSource(text="section", logical_name="test.wpa")),
            success=True,
            artifact=ProgramArtifact(
                intent_fragment=AuthoringDocumentIntent(
                    sections=[{"section_id": "section", "title": "section"}]
                )
            ),
            metrics=ProgramMetrics(),
        )


class _ReportAdapter:
    """Adapt the fake report worker to the production compiler protocol."""

    def __init__(self, workers: _Workers) -> None:
        self.workers = workers

    async def compile(self, **kwargs: object) -> ProgramExecutionResult:
        """Delegate report compilation."""
        return await self.workers.compile_report(**kwargs)


class _SectionAdapter:
    """Adapt the fake section worker to the production compiler protocol."""

    def __init__(self, workers: _Workers) -> None:
        self.workers = workers

    async def compile(self, **kwargs: object) -> ProgramExecutionResult:
        """Delegate section compilation."""
        return await self.workers.compile_section(**kwargs)


def _document() -> AuthoringDocumentSpec:
    """Build the smallest document accepted by the facade."""
    return AuthoringDocumentSpec(
        name="cm-58-3",
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


def test_three_safety_layers_run_in_order_before_enrichment() -> None:
    """Composition retains all bounded warnings and the final safe plan."""
    plan = _plan(
        _task(
            "section.log_plot",
            "track.reference",
            "binding.curve",
            "track.annotation",
            "annotation.typed",
        ),
        report=ReportTask(goal="prepare the report"),
    )
    workers = _Workers()
    enricher = _Enricher()
    result = asyncio.run(
        CodeModeCompileFacade(
            CodeModeGraphDependencies(
                planner=_Planner(plan),
                enricher=enricher,
                report_compiler=_ReportAdapter(workers),
                section_compiler=_SectionAdapter(workers),
            )
        ).compile(
            request="Prepare a report note Approved and show a scalar curve.",
            mode="reconstruct",
            document=_document(),
            source_candidates=(),
            timeout_seconds=5.0,
        )
    )
    assert result.success is True
    assert [diagnostic.stage for diagnostic in result.diagnostics] == [
        "capability_safety",
        "report_boundary_safety",
        "section_leaf_safety",
    ]
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "capability_safety.reference_replaced_with_normal",
        "report_boundary_safety.report_standard_added",
        "section_leaf_safety.report_note_annotation_removed",
    ]
    assert enricher.plans[0].section_tasks[0].capability_ids == (
        "section.log_plot",
        "track.normal",
        "binding.curve",
    )
    assert workers.report_calls[0].capability_ids == ("report.standard",)
    assert len(workers.section_calls) == 1


def test_section_leaf_failure_stops_enrichment_and_workers() -> None:
    """A CM-58.3 failure is terminal before enrichment."""
    plan = _plan(
        _task("section.log_plot", "track.normal", "track.array", "binding.raster", "binding.curve")
    )
    workers = _Workers()
    enricher = _Enricher()
    result = asyncio.run(
        CodeModeCompileFacade(
            CodeModeGraphDependencies(
                planner=_Planner(plan),
                enricher=enricher,
                report_compiler=_ReportAdapter(workers),
                section_compiler=_SectionAdapter(workers),
            )
        ).compile(
            request="Create an image track.",
            mode="reconstruct",
            document=_document(),
            source_candidates=(),
            timeout_seconds=5.0,
        )
    )
    assert result.success is False
    assert result.metrics.worker_count == 0
    assert enricher.plans == []
    assert workers.report_calls == []
    assert workers.section_calls == []
    assert result.diagnostics[0].code == (
        "section_leaf_safety.raster_only_scalar_structure_ambiguous"
    )


def test_policy_version_is_frozen() -> None:
    """The graph evidence exposes the reviewed CM-58.3 policy version."""
    result = enforce_section_leaf_safety(
        request="Create an image track.",
        plan=_plan(_task("section.log_plot", "track.array", "binding.raster")),
        registry=REGISTRY,
    )
    assert result.evidence().policy_version == SECTION_LEAF_POLICY_VERSION
