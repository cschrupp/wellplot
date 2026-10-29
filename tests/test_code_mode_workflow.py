"""Tests for the isolated Code Mode v2 compile graph."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import pytest
from langgraph.errors import NodeCancelledError

from wellplot.agent.code_mode import workflow as workflow_module
from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    EnrichedSemanticContext,
    EnrichmentErrorCode,
    ReportContext,
    ResolvedSectionContext,
    SemanticEnrichmentError,
    SourceContext,
)
from wellplot.agent.code_mode.facade import CodeModeCompileFacade
from wellplot.agent.code_mode.obligations import ObligationState, compile_request_contract
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

_SECTION_WORK_REQUEST = (
    "Track Example: normal, width 25 mm.\n"
    "On Example: GR -> Example, linear 0..150, #111111, width 1."
)


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
    """Build bounded source context for each planned section."""
    source = SourceContext(
        candidate_id="source-1",
        labels=("fixture.las",),
        canonical_path="/fixture.las",
        source_format="las",
        channels=(ChannelContext(mnemonic="GR", kind="scalar", unit="gAPI"),),
    )
    return tuple(
        ResolvedSectionContext(task_index=index, sources=(source,))
        for index, _task in enumerate(plan.section_tasks)
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
        obligations = compile_request_contract(str(kwargs["request"])).requirements.requirements
        tasks = tuple(
            task if task.obligations else task.model_copy(update={"obligations": obligations})
            for task in self.plan_value.section_tasks
        )
        return self.plan_value.model_copy(update={"section_tasks": tasks})


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


class _CancellingSectionAdapter:
    """Propagate sibling cancellation without emitting worker failure evidence."""

    async def compile(self, **_kwargs: object) -> ProgramExecutionResult:
        """Raise the cancellation unchanged at the worker boundary."""
        raise asyncio.CancelledError


def _graph(
    plan: SemanticPlan,
    workers: _Workers,
    planner: _Planner | None = None,
    diagnostic_callback: Callable[[Mapping[str, object]], None] | None = None,
    section_compiler: object | None = None,
    trace_callback: Callable[[Mapping[str, object]], None] | None = None,
    enricher: object | None = None,
) -> object:
    """Build a graph with host fakes at every v2 boundary."""
    dependencies = CodeModeGraphDependencies(
        planner=planner or _Planner(plan),  # type: ignore[arg-type]
        enricher=enricher or _Enricher(),  # type: ignore[arg-type]
        report_compiler=_ReportAdapter(workers),  # type: ignore[arg-type]
        section_compiler=section_compiler or _SectionAdapter(workers),  # type: ignore[arg-type]
        diagnostic_callback=diagnostic_callback,
        trace_callback=trace_callback,
    )
    return build_compile_graph(dependencies)


def _state(plan: SemanticPlan) -> dict[str, object]:
    """Build JSON-safe graph input state."""
    request_parts: list[str] = []
    if plan.report_task is not None:
        request_parts.append("Set the report title to Current report.")
    if plan.section_tasks:
        request_parts.append(_SECTION_WORK_REQUEST)
    request = " ".join(request_parts)
    return {
        "request": request,
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


@pytest.mark.parametrize(
    ("stage_function", "stage_event", "failure"),
    (
        (
            "enforce_capability_safety",
            "CAPABILITY_SAFETY_FAIL",
            lambda: workflow_module.CapabilitySafetyFailure(
                "synthetic_capability_failure", "bounded capability failure"
            ),
        ),
        (
            "enforce_report_boundary_safety",
            "REPORT_BOUNDARY_FAIL",
            lambda: workflow_module.ReportBoundarySafetyFailure(
                "synthetic_report_failure", "bounded report failure"
            ),
        ),
        (
            "enforce_section_leaf_safety",
            "SECTION_LEAF_FAIL",
            lambda: workflow_module.SectionLeafSafetyFailure(
                "synthetic_leaf_failure", "bounded leaf failure"
            ),
        ),
    ),
)
def test_pre_dispatch_safety_failures_emit_stage_trace(
    monkeypatch: pytest.MonkeyPatch,
    stage_function: str,
    stage_event: str,
    failure: Callable[[], Exception],
) -> None:
    """Expected deterministic safety failures are traced and re-raised unchanged."""
    error = failure()
    events: list[dict[str, object]] = []

    def fail(**_kwargs: object) -> object:
        raise error

    monkeypatch.setattr(workflow_module, stage_function, fail)
    plan = SemanticPlan(
        summary="report-only plan",
        report_task=ReportTask(goal="Set the report title.", capability_ids=("report.standard",)),
    )

    with pytest.raises(type(error)) as caught:
        asyncio.run(_graph(plan, _Workers(), trace_callback=events.append).ainvoke(_state(plan)))

    assert caught.value is error
    event = next(item for item in events if item["event"] == stage_event)
    assert event["exception_type"] == type(error).__name__
    assert event["code"] == error.code
    assert event["safe_message"] == error.safe_message


def test_enrichment_failure_emits_stage_trace_and_propagates() -> None:
    """The pre-dispatch enrichment boundary records its typed failure only."""

    class FailingEnricher:
        def enrich(self, **_kwargs: object) -> EnrichedSemanticContext:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_MISSING,
                "bounded missing source",
                task_index=0,
            )

    plan = SemanticPlan(
        summary="one section",
        section_tasks=(SectionTask(goal="Plot GR", capability_ids=("section.log_plot",)),),
    )
    events: list[dict[str, object]] = []

    with pytest.raises(SemanticEnrichmentError):
        asyncio.run(
            _graph(
                plan,
                _Workers(),
                trace_callback=events.append,
                enricher=FailingEnricher(),
            ).ainvoke(_state(plan))
        )

    failure = next(event for event in events if event["event"] == "ENRICHMENT_FAIL")
    assert failure["code"] == EnrichmentErrorCode.SOURCE_MISSING
    assert failure["exception_type"] == "SemanticEnrichmentError"


def test_dispatch_failure_records_context_order_error() -> None:
    """A pre-dispatch order mismatch is captured before any worker is sent."""

    class MismatchedEnricher:
        def enrich(self, *, plan: SemanticPlan, **_kwargs: object) -> EnrichedSemanticContext:
            return EnrichedSemanticContext(
                plan=plan,
                sections=(ResolvedSectionContext(task_index=9),),
                report=ReportContext(),
            )

    plan = SemanticPlan(
        summary="one section",
        section_tasks=(SectionTask(goal="Plot GR", capability_ids=("section.log_plot",)),),
    )
    events: list[dict[str, object]] = []

    with pytest.raises(ValueError, match="context order"):
        asyncio.run(
            _graph(
                plan,
                _Workers(),
                trace_callback=events.append,
                enricher=MismatchedEnricher(),
            ).ainvoke(_state(plan))
        )

    failure = next(event for event in events if event["event"] == "DISPATCH_FAIL")
    assert failure["code"] == "dispatch_section_context_order_mismatch"


def test_compile_facade_observes_zero_worker_top_level_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unchanged safe compile result is observable before session projection."""
    error = workflow_module.CapabilitySafetyFailure(
        "synthetic_capability_failure", "bounded capability failure"
    )

    def fail(**_kwargs: object) -> object:
        raise error

    monkeypatch.setattr(workflow_module, "enforce_capability_safety", fail)
    plan = SemanticPlan(
        summary="report-only plan",
        report_task=ReportTask(goal="Set the report title.", capability_ids=("report.standard",)),
    )
    observed: list[object] = []
    facade = CodeModeCompileFacade(
        dependencies=workflow_module.CodeModeGraphDependencies(
            planner=_Planner(plan),  # type: ignore[arg-type]
            enricher=_Enricher(),  # type: ignore[arg-type]
            report_compiler=_ReportAdapter(_Workers()),
            section_compiler=_SectionAdapter(_Workers()),
        ),
        result_callback=observed.append,
    )

    result = asyncio.run(
        facade.compile(
            request="Set the report title.",
            mode="reconstruct",
            document=_document(),
            source_candidates=(),
            timeout_seconds=5.0,
        )
    )

    assert result.success is False
    assert result.workers == ()
    assert result.diagnostics[0].code == "capability_safety.synthetic_capability_failure"
    assert observed == [result]


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


def test_graph_propagates_cancellation_without_worker_exception_diagnostic() -> None:
    """Sibling cancellation remains transport-level termination evidence."""
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
    with pytest.raises(NodeCancelledError) as error:
        asyncio.run(
            _graph(
                plan,
                _Workers(),
                diagnostic_callback=events.append,
                section_compiler=_CancellingSectionAdapter(),
            ).ainvoke(_state(plan))
        )
    assert isinstance(error.value.__cause__, asyncio.CancelledError)
    assert events == []


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


def test_invalid_section_work_contract_fails_before_worker_invocation() -> None:
    """A deterministic dispatch-contract failure becomes bounded worker evidence."""
    task = SectionTask(
        goal="first section",
        capability_ids=("section.log_plot",),
        existing_section_hint=None,
        obligations=tuple(
            obligation.model_copy(update={"state": ObligationState.UNRESOLVED, "value": None})
            for obligation in compile_request_contract(
                _SECTION_WORK_REQUEST
            ).requirements.requirements
        ),
    )
    plan = SemanticPlan(summary="contract failure", section_tasks=(task,))
    workers = _Workers()

    result = _invoke(plan, workers)

    assert workers.completion_order == []
    outcome = json.loads(result["worker_outcomes"][0])
    assert outcome["success"] is False
    assert outcome["diagnostics"][0]["stage"] == "worker_obligation"
    assert outcome["diagnostics"][0]["code"] == "section_work_contract_unresolved"


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
