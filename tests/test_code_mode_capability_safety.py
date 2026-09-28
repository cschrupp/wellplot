"""Tests for the deterministic CM-58.1 reference capability safety layer."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from wellplot.agent.code_mode.capability_safety import (
    CapabilitySafetyFailure,
    ReferenceIntent,
    classify_reference_intent,
    enforce_capability_safety,
)
from wellplot.agent.code_mode.enrichment import (
    EnrichedSemanticContext,
    ReportContext,
    ResolvedSectionContext,
)
from wellplot.agent.code_mode.facade import CodeModeCompileFacade
from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
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


def _plan(*capability_ids: str, summary: str = "section") -> SemanticPlan:
    """Build one valid semantic section plan for safety tests."""
    return SemanticPlan(
        summary=summary,
        section_tasks=(
            SectionTask(goal="plot the requested section", capability_ids=capability_ids),
        ),
    )


def _document() -> AuthoringDocumentSpec:
    """Build the smallest document accepted by the compile facade."""
    return AuthoringDocumentSpec(
        name="cm-58-1",
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


def _successful_section_result() -> ProgramExecutionResult:
    """Build bounded successful section-worker evidence."""
    program = AuthoringProgram(
        source=ProgramSource(text="section = wp.section(title='test')", logical_name="test.wpa")
    )
    return ProgramExecutionResult(
        program=program,
        success=True,
        artifact=ProgramArtifact(
            intent_fragment=AuthoringDocumentIntent(
                sections=[{"section_id": "cm-58-1", "title": "test"}]
            )
        ),
        metrics=ProgramMetrics(),
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Place a depth reference beside the density curve.", ReferenceIntent.EXPLICITLY_REQUESTED),
        ("Use a reference track.", ReferenceIntent.EXPLICITLY_REQUESTED),
        ("Align a depth column with the image.", ReferenceIntent.EXPLICITLY_REQUESTED),
        ("ADD AN EXPLICIT DEPTH REFERENCE!", ReferenceIntent.EXPLICITLY_REQUESTED),
        ("Show the image without a reference column.", ReferenceIntent.EXPLICITLY_FORBIDDEN),
        ("Use no depth track.", ReferenceIntent.EXPLICITLY_FORBIDDEN),
        ("Do not add a reference track.", ReferenceIntent.EXPLICITLY_FORBIDDEN),
        ("Plot the curve against depth.", ReferenceIntent.UNSPECIFIED),
        ("Create an ordinary raster image.", ReferenceIntent.UNSPECIFIED),
        ("Add a reference track, but do not add a reference track.", ReferenceIntent.CONFLICTING),
    ],
)
def test_reference_intent_classifier(text: str, expected: ReferenceIntent) -> None:
    """Classify only bounded explicit reference language."""
    assert classify_reference_intent(text) is expected


def test_bare_depth_is_unspecified() -> None:
    """Depth indexing alone does not request a second reference track."""
    assert classify_reference_intent("Plot the data by depth.") is ReferenceIntent.UNSPECIFIED


def test_repair_removes_reference_when_normal_track_exists() -> None:
    """Remove an inadmissible reference while preserving remaining order."""
    original = _plan(
        "section.log_plot",
        "track.reference",
        "track.normal",
        "binding.curve",
    )
    result = enforce_capability_safety(request="Plot the curve.", plan=original, registry=REGISTRY)
    assert result.safe_plan.section_tasks[0].capability_ids == (
        "section.log_plot",
        "track.normal",
        "binding.curve",
    )
    assert result.actions[0].kind.value == "remove_reference"
    assert result.actions[0].reason == "reference_not_requested"
    assert original.section_tasks[0].capability_ids == (
        "section.log_plot",
        "track.reference",
        "track.normal",
        "binding.curve",
    )


def test_repair_replaces_reference_parent_for_curve() -> None:
    """Replace a reference parent when it is the only valid curve parent."""
    result = enforce_capability_safety(
        request="Plot the curve.",
        plan=_plan("section.log_plot", "track.reference", "binding.curve"),
        registry=REGISTRY,
    )
    assert result.safe_plan.section_tasks[0].capability_ids == (
        "section.log_plot",
        "track.normal",
        "binding.curve",
    )
    assert result.actions[0].kind.value == "replace_reference_with_normal"


def test_repair_removes_reference_beside_array_raster() -> None:
    """Preserve independent array content when removing reference."""
    result = enforce_capability_safety(
        request="Plot the image.",
        plan=_plan(
            "section.log_plot",
            "track.reference",
            "track.array",
            "binding.raster",
        ),
        registry=REGISTRY,
    )
    assert result.safe_plan.section_tasks[0].capability_ids == (
        "section.log_plot",
        "track.array",
        "binding.raster",
    )


def test_explicit_reference_is_preserved() -> None:
    """A request with explicit reference intent passes through unchanged."""
    original = _plan("section.log_plot", "track.reference", "binding.curve")
    result = enforce_capability_safety(
        request="Use an explicit depth reference track.",
        plan=original,
        registry=REGISTRY,
    )
    assert result.safe_plan == original
    assert result.changed is False
    assert result.actions == ()


def test_explicit_forbid_repairs_injected_reference() -> None:
    """Explicit negative intent uses the same safe repair without a model call."""
    result = enforce_capability_safety(
        request="Show the image without a reference column.",
        plan=_plan(
            "section.log_plot",
            "track.reference",
            "track.array",
            "binding.raster",
        ),
        registry=REGISTRY,
    )
    assert result.reference_intent is ReferenceIntent.EXPLICITLY_FORBIDDEN
    assert result.changed is True
    assert result.actions[0].reason == "reference_explicitly_forbidden"


def test_conflicting_reference_intent_fails_closed() -> None:
    """Conflicting explicit instructions are never resolved by guessing."""
    with pytest.raises(CapabilitySafetyFailure) as failure:
        enforce_capability_safety(
            request="Add a reference track, but do not add a reference track.",
            plan=_plan("section.log_plot", "track.reference", "binding.curve"),
            registry=REGISTRY,
        )
    assert failure.value.code == "reference_intent_conflict"


def test_reference_only_section_fails_closed() -> None:
    """Removing the only meaningful section capability is rejected."""
    with pytest.raises(CapabilitySafetyFailure) as failure:
        enforce_capability_safety(
            request="Plot the requested section.",
            plan=_plan("section.log_plot", "track.reference"),
            registry=REGISTRY,
        )
    assert failure.value.code == "reference_repair_would_empty_section"


def test_positive_multi_section_request_is_not_reallocated() -> None:
    """v1 permits positive reference intent without section-level allocation."""
    plan = SemanticPlan(
        summary="multiple sections",
        section_tasks=(
            SectionTask(
                goal="scalar view",
                capability_ids=("section.log_plot", "track.normal", "binding.curve"),
            ),
            SectionTask(
                goal="depth-referenced view",
                capability_ids=("section.log_plot", "track.reference", "binding.curve"),
            ),
        ),
    )
    result = enforce_capability_safety(
        request="Create three views: a scalar curve, a depth-referenced curve, and an image.",
        plan=plan,
        registry=REGISTRY,
    )
    assert result.safe_plan == plan
    assert result.changed is False


def test_repair_preserves_plan_metadata_and_section_order() -> None:
    """Change only reference capability IDs in the original plan structure."""
    plan = SemanticPlan(
        summary="preserve all planner metadata",
        report_task=ReportTask(
            goal="retain report work",
            capability_ids=("report.standard",),
            requirements=("keep the title",),
            constraints=("do not change report work",),
        ),
        section_tasks=(
            SectionTask(
                goal="remove an injected reference",
                capability_ids=(
                    "section.log_plot",
                    "track.reference",
                    "track.normal",
                    "binding.curve",
                ),
                existing_section_hint="first section",
                source_hints=("source-a",),
                requirements=("preserve ordering",),
                constraints=("keep the curve",),
            ),
            SectionTask(
                goal="keep the second section",
                capability_ids=("section.log_plot", "track.array", "binding.raster"),
                source_hints=("source-b",),
            ),
        ),
        unresolved_requirements=("none",),
    )

    result = enforce_capability_safety(
        request="Plot the requested sections.",
        plan=plan,
        registry=REGISTRY,
    )

    assert result.safe_plan.summary == plan.summary
    assert result.safe_plan.report_task == plan.report_task
    assert result.safe_plan.unresolved_requirements == plan.unresolved_requirements
    assert result.safe_plan.section_tasks[0].goal == plan.section_tasks[0].goal
    assert result.safe_plan.section_tasks[0].existing_section_hint == "first section"
    assert result.safe_plan.section_tasks[0].source_hints == ("source-a",)
    assert result.safe_plan.section_tasks[0].requirements == ("preserve ordering",)
    assert result.safe_plan.section_tasks[0].constraints == ("keep the curve",)
    assert result.safe_plan.section_tasks[1] == plan.section_tasks[1]
    assert result.safe_plan.section_tasks[0].capability_ids == (
        "section.log_plot",
        "track.normal",
        "binding.curve",
    )


@pytest.mark.parametrize(
    "case_id",
    [
        "p10-multi-track-cedar-13",
        "p10-mixed-report-boreal-22",
        "p10-mixed-report-kestrel-23",
    ],
)
def test_p10_unexpected_reference_regressions_are_repaired(case_id: str) -> None:
    """Closed P10 unexpected-reference cases are covered without case logic."""
    result = enforce_capability_safety(
        request=f"{case_id} ordinary curve request",
        plan=_plan(
            "section.log_plot",
            "track.reference",
            "track.normal",
            "binding.curve",
        ),
        registry=REGISTRY,
    )
    assert result.changed is True
    assert "track.reference" not in result.safe_plan.section_tasks[0].capability_ids


@pytest.mark.parametrize(
    "case_id",
    [
        "p10-reference-cairn-09",
        "p10-reference-summit-10",
        "p10-reference-fjord-11",
        "p10-reference-prairie-12",
        "p10-multi-track-reef-14",
    ],
)
def test_p10_reference_controls_preserve_reference(case_id: str) -> None:
    """Closed P10 positive-reference controls remain unchanged."""
    plan = _plan("section.log_plot", "track.reference", "binding.curve")
    result = enforce_capability_safety(
        request=f"{case_id}: include an explicit depth reference track",
        plan=plan,
        registry=REGISTRY,
    )
    assert result.safe_plan == plan


def test_p10_explicit_negative_reference_is_repaired() -> None:
    """The closed negative-reference control removes injected reference."""
    result = enforce_capability_safety(
        request="p10-single-lantern-08: show the image without a reference column",
        plan=_plan("section.log_plot", "track.reference", "track.array", "binding.raster"),
        registry=REGISTRY,
    )
    assert result.changed is True
    assert "track.reference" not in result.safe_plan.section_tasks[0].capability_ids


@pytest.mark.parametrize(
    "case_id",
    [
        "p10-multi-track-cedar-13",
        "p10-mixed-report-boreal-22",
        "p10-mixed-report-kestrel-23",
    ],
)
def test_safety_evidence_is_deterministic_and_path_free(case_id: str) -> None:
    """Repeated safety runs yield identical bounded evidence without raw requests."""
    plan = _plan("section.log_plot", "track.reference", "track.normal", "binding.curve")
    first = enforce_capability_safety(
        request=f"{case_id} /tmp/hidden/request.dlis", plan=plan, registry=REGISTRY
    )
    second = enforce_capability_safety(
        request=f"{case_id} /tmp/hidden/request.dlis", plan=plan, registry=REGISTRY
    )
    assert first.evidence() == second.evidence()
    serialized = first.evidence().model_dump_json()
    assert "/tmp/hidden" not in serialized
    assert case_id not in serialized


def test_graph_safety_runs_before_enrichment_and_workers() -> None:
    """A repaired plan is the only plan visible to enrichment and workers."""
    planner = _Planner(
        _plan("section.log_plot", "track.reference", "track.normal", "binding.curve")
    )
    enricher = _RecordingEnricher()
    compiler = _SectionCompiler()
    result = asyncio.run(
        CodeModeCompileFacade(
            CodeModeGraphDependencies(
                planner=planner,
                enricher=enricher,
                report_compiler=_ReportCompiler(),
                section_compiler=compiler,
            )
        ).compile(
            request="Plot the curve.",
            mode="reconstruct",
            document=_document(),
            source_candidates=(),
            timeout_seconds=5.0,
        )
    )
    assert result.success is True
    assert compiler.calls == 1
    assert enricher.plans[0].section_tasks[0].capability_ids == (
        "section.log_plot",
        "track.normal",
        "binding.curve",
    )
    safety_warnings = [item for item in result.diagnostics if item.stage == "capability_safety"]
    assert len(safety_warnings) == 1
    assert safety_warnings[0].code == "capability_safety.reference_removed"
    assert safety_warnings[0].severity.value == "warning"
    assert safety_warnings[0].retryable is False


def test_safety_failure_stops_enrichment_and_workers() -> None:
    """An unsafe repair returns a zero-worker bounded failure."""
    planner = _Planner(_plan("section.log_plot", "track.reference"))
    enricher = _RecordingEnricher()
    compiler = _SectionCompiler()
    result = asyncio.run(
        CodeModeCompileFacade(
            CodeModeGraphDependencies(
                planner=planner,
                enricher=enricher,
                report_compiler=_ReportCompiler(),
                section_compiler=compiler,
            )
        ).compile(
            request="Plot the section.",
            mode="reconstruct",
            document=_document(),
            source_candidates=(),
            timeout_seconds=5.0,
        )
    )
    assert result.success is False
    assert result.merged_intent is None
    assert result.metrics.worker_count == 0
    assert compiler.calls == 0
    assert enricher.plans == []
    assert result.diagnostics[0].stage == "capability_safety"
    assert result.diagnostics[0].code == "capability_safety.reference_repair_would_empty_section"
    assert result.diagnostics[0].retryable is False


def test_revalidation_failure_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transformed plan that fails existing validation is rejected."""
    from wellplot.agent.code_mode import capability_safety
    from wellplot.agent.code_mode.planner import PlannerSemanticError

    def fail_validation(*_args: object, **_kwargs: object) -> None:
        raise PlannerSemanticError("missing_capability_parent", "invalid")

    monkeypatch.setattr(capability_safety, "validate_semantic_plan", fail_validation)
    with pytest.raises(CapabilitySafetyFailure) as failure:
        enforce_capability_safety(
            request="Plot the curve.",
            plan=_plan("section.log_plot", "track.reference", "binding.curve"),
            registry=REGISTRY,
        )
    assert failure.value.code == "reference_repair_invalid"


@dataclass
class _Planner:
    plan_value: SemanticPlan
    registry: object = field(default_factory=create_builtin_registry)

    async def plan(self, **_kwargs: object) -> SemanticPlan:
        """Return one deterministic plan without a provider call."""
        return self.plan_value


@dataclass
class _RecordingEnricher:
    plans: list[SemanticPlan] = field(default_factory=list)

    def enrich(self, *, plan: SemanticPlan, **_kwargs: object) -> EnrichedSemanticContext:
        """Record the plan that crossed the safety boundary."""
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
class _SectionCompiler:
    calls: int = 0

    async def compile(self, **_kwargs: object) -> ProgramExecutionResult:
        """Return one deterministic successful section result."""
        self.calls += 1
        return _successful_section_result()


class _ReportCompiler:
    """Unused report compiler required by graph dependencies."""

    async def compile(self, **_kwargs: object) -> ProgramExecutionResult:
        """Return a bounded report result if accidentally invoked."""
        return _successful_section_result()
