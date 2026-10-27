"""Tests for the isolated Code Mode v2 compile graph."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import pytest

from wellplot.agent.code_mode.enrichment import (
    EnrichedSemanticContext,
    ReportContext,
    ResolvedSectionContext,
)
from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.code_mode.state import WorkerOutcome
from wellplot.agent.code_mode.workflow import (
    CodeModeGraphDependencies,
    build_compile_graph,
    merge_v2_intents,
)
from wellplot.authoring_program.models import (
    AuthoringProgram,
    ProgramArtifact,
    ProgramDiagnostic,
    ProgramExecutionResult,
    ProgramMetrics,
    ProgramSource,
)
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.model.intent import AuthoringDocumentIntent


def _document() -> AuthoringDocumentSpec:
    """Build the smallest canonical document accepted by graph inputs."""
    return AuthoringDocumentSpec(
        name="cm-45",
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


def _section_contexts(plan: SemanticPlan) -> tuple[ResolvedSectionContext, ...]:
    """Build one empty bounded context for each planned section."""
    return tuple(
        ResolvedSectionContext(task_index=index) for index, _task in enumerate(plan.section_tasks)
    )


def _context(plan: SemanticPlan) -> EnrichedSemanticContext:
    """Build deterministic enrichment output without source discovery."""
    return EnrichedSemanticContext(
        plan=plan,
        sections=_section_contexts(plan),
        report=ReportContext(),
    )


def _result(fragment: AuthoringDocumentIntent) -> ProgramExecutionResult:
    """Build successful worker evidence without retaining it in graph state."""
    program = AuthoringProgram(
        source=ProgramSource(text="report = wp.report(title='test')", logical_name="test.wpa")
    )
    return ProgramExecutionResult(
        program=program,
        success=True,
        artifact=ProgramArtifact(intent_fragment=fragment),
        metrics=ProgramMetrics(program_chars=len(program.source.text)),
    )


@dataclass
class _Planner:
    """Fake planner returning one frozen test plan."""

    plan_value: SemanticPlan
    summaries: list[dict[str, object]] = field(default_factory=list)
    temperatures: list[float | None] = field(default_factory=list)
    source_summaries: list[dict[str, object]] = field(default_factory=list)

    async def plan(self, **kwargs: object) -> SemanticPlan:
        """Record bounded planning context and return the configured plan."""
        self.summaries.append(kwargs["current_document_summary"])
        self.temperatures.append(kwargs["temperature"])
        self.source_summaries.append(kwargs["source_summary"])
        return self.plan_value


@dataclass
class _Enricher:
    """Fake host enrichment boundary returning task-local context."""

    contexts: list[EnrichedSemanticContext] = field(default_factory=list)

    def enrich(self, *, plan: SemanticPlan, **_kwargs: object) -> EnrichedSemanticContext:
        """Return explicit context without loading or discovering sources."""
        context = _context(plan)
        self.contexts.append(context)
        return context


@dataclass
class _Workers:
    """Fake workers with controllable completion order and failure."""

    fail_section: int | None = None
    duplicate_sections: bool = False
    completion_order: list[str] = field(default_factory=list)

    async def compile_report(
        self,
        *,
        task: ReportTask,
        **_kwargs: object,
    ) -> ProgramExecutionResult:
        """Finish the report between the two section workers."""
        await asyncio.sleep(0.01)
        self.completion_order.append("report")
        return _result(AuthoringDocumentIntent(title=task.goal))

    async def compile_section(
        self,
        *,
        context: EnrichedSemanticContext,
        **_kwargs: object,
    ) -> ProgramExecutionResult:
        """Delay section zero so section one completes first."""
        index = 0 if "first" in context.plan.summary else 1
        await asyncio.sleep(0.03 if index == 0 else 0.0)
        self.completion_order.append(f"section-{index}")
        if self.fail_section == index:
            diagnostic = ProgramDiagnostic(
                stage="program",
                code="program.dry_run_error",
                message="section worker failed",
            )
            return ProgramExecutionResult(
                program=AuthoringProgram(source=ProgramSource(text="failed")),
                success=False,
                diagnostics=(diagnostic,),
            )
        section_id = "duplicate" if self.duplicate_sections else f"section-{index}"
        return _result(
            AuthoringDocumentIntent(
                sections=[{"section_id": section_id, "title": f"Section {index}"}]
            )
        )


class _ReportAdapter:
    """Adapt the shared fake worker to the report compiler protocol."""

    def __init__(self, workers: _Workers) -> None:
        self.workers = workers

    async def compile(self, **kwargs: object) -> ProgramExecutionResult:
        """Delegate report compilation to the fake worker."""
        return await self.workers.compile_report(**kwargs)


class _SectionAdapter:
    """Adapt the shared fake worker to the section compiler protocol."""

    def __init__(self, workers: _Workers) -> None:
        self.workers = workers

    async def compile(self, **kwargs: object) -> ProgramExecutionResult:
        """Delegate section compilation to the fake worker."""
        return await self.workers.compile_section(**kwargs)


class _ExplodingSectionAdapter:
    """Raise an unexpected worker exception for diagnostic-boundary tests."""

    async def compile(self, **_kwargs: object) -> ProgramExecutionResult:
        """Raise without changing the canonical worker result contract."""
        raise RuntimeError("provider response detail must not be persisted")


def _graph(
    plan: SemanticPlan,
    workers: _Workers,
    planner: _Planner | None = None,
    diagnostic_callback: Callable[[Mapping[str, object]], None] | None = None,
    section_compiler: object | None = None,
) -> object:
    """Build a graph with host fakes at every v2 boundary."""
    dependencies = CodeModeGraphDependencies(
        planner=planner or _Planner(plan),  # type: ignore[arg-type]
        enricher=_Enricher(),  # type: ignore[arg-type]
        report_compiler=_ReportAdapter(workers),  # type: ignore[arg-type]
        section_compiler=section_compiler or _SectionAdapter(workers),  # type: ignore[arg-type]
        diagnostic_callback=diagnostic_callback,
    )
    return build_compile_graph(dependencies)


def _state(plan: SemanticPlan) -> dict[str, object]:
    """Build JSON-safe graph input state."""
    return {
        "request": "compile the requested work",
        "mode": "reconstruct",
        "document": _document().model_dump(mode="json"),
        "source_candidates": [],
        "timeout_seconds": 5.0,
        "worker_outcomes": [],
        "diagnostics": [],
        "merged_intent": {},
    }


def _invoke(plan: SemanticPlan, workers: _Workers) -> dict[str, object]:
    """Invoke the async graph through its native ainvoke entry point."""
    return asyncio.run(_graph(plan, workers).ainvoke(_state(plan)))


def test_graph_merges_report_and_sections_in_plan_order() -> None:
    """Reversed asynchronous completion does not change canonical merge order."""
    plan = SemanticPlan(
        summary="multi-section plan",
        report_task=ReportTask(goal="Report title", capability_ids=("report.standard",)),
        section_tasks=(
            SectionTask(
                goal="first section",
                capability_ids=("section.log_plot",),
                existing_section_hint=None,
            ),
            SectionTask(
                goal="second section",
                capability_ids=("section.log_plot",),
                existing_section_hint=None,
            ),
        ),
    )
    workers = _Workers()
    result = _invoke(plan, workers)

    assert workers.completion_order == ["section-1", "report", "section-0"]
    assert [section["section_id"] for section in result["merged_intent"]["sections"]] == [
        "section-0",
        "section-1",
    ]
    assert result["merged_intent"]["title"] == "Report title"
    assert "report = wp.report" not in str(result["worker_outcomes"])


def test_graph_supports_report_only_and_section_only_plans() -> None:
    """Both valid planner topologies dispatch only their real work units."""
    report_plan = SemanticPlan(
        summary="report only",
        report_task=ReportTask(goal="Report title", capability_ids=("report.standard",)),
    )
    report_result = _invoke(report_plan, _Workers())
    assert report_result["merged_intent"]["title"] == "Report title"

    section_plan = SemanticPlan(
        summary="section only",
        section_tasks=(
            SectionTask(
                goal="first section",
                capability_ids=("section.log_plot",),
                existing_section_hint=None,
            ),
        ),
    )
    section_result = _invoke(section_plan, _Workers())
    assert section_result["merged_intent"]["sections"][0]["section_id"] == "section-0"


def test_graph_reports_unexpected_worker_exception_before_reraising() -> None:
    """Unexpected compile exceptions are observable without changing propagation."""
    plan = SemanticPlan(
        summary="section only",
        section_tasks=(
            SectionTask(
                goal="first section",
                capability_ids=("section.log_plot",),
                existing_section_hint=None,
            ),
        ),
    )
    events: list[Mapping[str, object]] = []
    with pytest.raises(RuntimeError, match="provider response detail"):
        asyncio.run(
            _graph(
                plan,
                _Workers(),
                diagnostic_callback=events.append,
                section_compiler=_ExplodingSectionAdapter(),
            ).ainvoke(_state(plan))
        )
    assert events == [
        {
            "event": "worker_exception",
            "worker_kind": "section",
            "plan_order": 1,
            "stage": "compile_worker",
            "exception_type": "RuntimeError",
            "exception_module": "builtins",
            "provider_call_in_flight": None,
            "provider_call_state": "UNKNOWN",
        }
    ]


def test_graph_plans_at_zero_and_keeps_source_summary_path_free() -> None:
    """Planner sampling is fixed while worker configuration remains separate."""
    plan = SemanticPlan(
        summary="section only",
        section_tasks=(
            SectionTask(
                goal="first section",
                capability_ids=("section.log_plot",),
                existing_section_hint=None,
            ),
        ),
    )
    planner = _Planner(plan)
    state = _state(plan)
    state["source_candidates"] = [
        {
            "candidate_id": "secret-source-id",
            "root_id": "input",
            "path": "/secret/main.las",
            "labels": ["main pass"],
            "inspection_state": "inspected",
            "channels": [{"mnemonic": "GR", "kind": "scalar", "unit": "gAPI"}],
        }
    ]

    asyncio.run(_graph(plan, _Workers(), planner).ainvoke(state))

    assert planner.temperatures == [0.0]
    assert planner.source_summaries == [
        {
            "version": "cm56r3.source-summary.v1",
            "sources": [
                {
                    "labels": ["main pass"],
                    "channels": [{"mnemonic": "GR", "kind": "scalar", "unit": "gAPI"}],
                    "inspection_state": "inspected",
                }
            ],
        }
    ]


def test_graph_planner_context_exposes_safe_existing_section_hints() -> None:
    """Planner context includes titles without exposing nested canonical state."""
    plan = SemanticPlan(
        summary="section only",
        section_tasks=(
            SectionTask(
                goal="update", capability_ids=("section.log_plot",), existing_section_hint=None
            ),
        ),
    )
    planner = _Planner(plan)

    asyncio.run(_graph(plan, _Workers(), planner).ainvoke(_state(plan)))

    assert planner.summaries[0]["existing_section_hints"] == [
        {"title": "Existing section", "subtitle": None}
    ]
    assert planner.summaries[0]["revision_inventory"] == [
        {
            "title": "Existing section",
            "subtitle": None,
            "depth_range": None,
            "tracks": [
                {
                    "title": "Existing track",
                    "kind": "normal",
                    "width_mm": 20.0,
                    "bindings": [],
                }
            ],
        }
    ]
    inventory_text = json.dumps(planner.summaries[0]["revision_inventory"], sort_keys=True)
    assert "existing-track" not in inventory_text
    assert "section_id" not in inventory_text


def test_graph_failure_is_atomic_and_keeps_bounded_diagnostics() -> None:
    """A failed sibling prevents merged output even when others succeed."""
    plan = SemanticPlan(
        summary="failure plan",
        section_tasks=(
            SectionTask(
                goal="first section",
                capability_ids=("section.log_plot",),
                existing_section_hint=None,
            ),
            SectionTask(
                goal="second section",
                capability_ids=("section.log_plot",),
                existing_section_hint=None,
            ),
        ),
    )
    result = _invoke(plan, _Workers(fail_section=1))

    assert result["merged_intent"] == {}
    assert json.loads(result["diagnostics"][0])["code"] == "program.dry_run_error"


def test_graph_rejects_duplicate_section_id_at_merge() -> None:
    """Parallel workers cannot silently share a newly allocated section identity."""
    plan = SemanticPlan(
        summary="duplicate plan",
        section_tasks=(
            SectionTask(
                goal="first section",
                capability_ids=("section.log_plot",),
                existing_section_hint=None,
            ),
            SectionTask(
                goal="second section",
                capability_ids=("section.log_plot",),
                existing_section_hint=None,
            ),
        ),
    )

    with pytest.raises(ValueError, match="Duplicate v2 section identity"):
        _invoke(plan, _Workers(duplicate_sections=True))


def test_worker_outcome_does_not_accept_generated_source() -> None:
    """The reducer contract has no field for provider program source text."""
    with pytest.raises(ValueError):
        WorkerOutcome.model_validate(
            {
                "kind": "report",
                "plan_order": 0,
                "success": True,
                "program_source": "report = wp.report()",
                "intent_fragment": {"title": "Report"},
            }
        )


def test_v2_merge_rejects_conflicting_root_fields() -> None:
    """The local v2 merge remains deterministic for overlapping report fields."""
    with pytest.raises(ValueError, match="Conflicting v2 intent field 'title'"):
        merge_v2_intents(
            (
                AuthoringDocumentIntent(title="one"),
                AuthoringDocumentIntent(title="two"),
            )
        )
