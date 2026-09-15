"""Tests for the internal async Code Mode v2 host facade."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field

import pytest

pytest.importorskip("langgraph")

from wellplot.agent.code_mode.enrichment import (
    EnrichedSemanticContext,
    EnrichmentErrorCode,
    ReportContext,
    ResolvedSectionContext,
    SemanticEnrichmentError,
)
from wellplot.agent.code_mode.facade import (
    CodeModeCompileFacade,
    CodeModeCompileResult,
)
from wellplot.agent.code_mode.planner import (
    CompilationMode,
    ReportTask,
    SectionTask,
    SemanticPlan,
)
from wellplot.agent.code_mode.workflow import CodeModeGraphDependencies
from wellplot.agent.graph import (
    ReconstructionGraphDependencies,
    ReconstructionPlanner,
    ReportCompiler,
    SectionCompiler,
    compile_document_revision,
)
from wellplot.agent.graph import (
    build_compile_graph as build_legacy_graph,
)
from wellplot.agent.graph.models import CompiledArtifact, ReconstructionPlan, SectionPlan
from wellplot.agent.providers.base import (
    ProviderFailureCategory,
    ProviderRequestError,
)
from wellplot.authoring_program.models import (
    AuthoringProgram,
    ProgramArtifact,
    ProgramDiagnostic,
    ProgramExecutionResult,
    ProgramMetrics,
    ProgramSource,
)
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.model.intent import AuthoringDocumentIntent


def _document() -> AuthoringDocumentSpec:
    """Build the smallest canonical document accepted by the facade."""
    return AuthoringDocumentSpec(
        name="cm-46",
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


def _success_result(
    fragment: AuthoringDocumentIntent,
    *,
    chars: int = 10,
) -> ProgramExecutionResult:
    """Build successful deterministic worker evidence."""
    program = AuthoringProgram(
        source=ProgramSource(text="report = wp.report(title='test')", logical_name="test.wpa")
    )
    return ProgramExecutionResult(
        program=program,
        success=True,
        artifact=ProgramArtifact(intent_fragment=fragment),
        metrics=ProgramMetrics(
            program_chars=chars,
            program_ast_nodes=2,
            program_statements=1,
            program_calls=1,
            program_repairs=1,
            program_loop_iterations=3,
            program_nesting_depth=2,
            created_objects=4,
        ),
    )


def _failed_result() -> ProgramExecutionResult:
    """Build a deterministic worker failure without provider payloads."""
    return ProgramExecutionResult(
        program=AuthoringProgram(source=ProgramSource(text="failed")),
        success=False,
        diagnostics=(
            ProgramDiagnostic(
                stage="program",
                code="program.dry_run_error",
                message="worker program failed",
            ),
        ),
    )


@dataclass
class _Planner:
    plan_value: SemanticPlan | None = None
    failure: ProviderRequestError | None = None

    async def plan(self, **_kwargs: object) -> SemanticPlan:
        """Return the fixture plan or its configured provider failure."""
        if self.failure is not None:
            raise self.failure
        assert self.plan_value is not None
        return self.plan_value


@dataclass
class _Enricher:
    failure: SemanticEnrichmentError | None = None

    def enrich(self, *, plan: SemanticPlan, **_kwargs: object) -> EnrichedSemanticContext:
        """Return one bounded context per planned section."""
        if self.failure is not None:
            raise self.failure
        return EnrichedSemanticContext(
            plan=plan,
            sections=tuple(
                ResolvedSectionContext(
                    task_index=index,
                    section_id=("existing" if task.existing_section_hint else None),
                )
                for index, task in enumerate(plan.section_tasks)
            ),
            report=ReportContext(),
        )


@dataclass
class _Workers:
    fail_kind: str | None = None
    provider_kind: str | None = None
    completion_order: list[str] = field(default_factory=list)

    async def compile_report(
        self,
        *,
        task: ReportTask,
        **_kwargs: object,
    ) -> ProgramExecutionResult:
        """Return the report fixture or a configured failure."""
        await asyncio.sleep(0.01)
        self.completion_order.append("report")
        if self.provider_kind == "report":
            raise ProviderRequestError(
                ProviderFailureCategory.TIMEOUT,
                "Report provider timed out.",
            )
        if self.fail_kind == "report":
            return _failed_result()
        return _success_result(AuthoringDocumentIntent(title=task.goal))

    async def compile_section(
        self,
        *,
        context: EnrichedSemanticContext,
        **_kwargs: object,
    ) -> ProgramExecutionResult:
        """Return one section fixture or a configured failure."""
        index = 0 if "first" in context.plan.summary else 1
        await asyncio.sleep(0.03 if index == 0 else 0.0)
        self.completion_order.append(f"section-{index}")
        if self.provider_kind == "section":
            raise ProviderRequestError(
                ProviderFailureCategory.CONFIGURATION,
                "Section provider configuration is invalid.",
            )
        if self.fail_kind == "section":
            return _failed_result()
        task = context.plan.section_tasks[0]
        target_id = context.sections[0].section_id
        return _success_result(
            AuthoringDocumentIntent(
                sections=[
                    {
                        "section_id": target_id or f"section-{index}",
                        "title": task.goal if target_id else f"Section {index}",
                    }
                ]
            ),
            chars=20,
        )


class _ReportAdapter:
    """Adapt deterministic test workers to the report compiler boundary."""

    def __init__(self, workers: _Workers) -> None:
        self.workers = workers

    async def compile(self, **kwargs: object) -> ProgramExecutionResult:
        """Delegate to the configured report fake."""
        return await self.workers.compile_report(**kwargs)


class _SectionAdapter:
    """Adapt deterministic test workers to the section compiler boundary."""

    def __init__(self, workers: _Workers) -> None:
        self.workers = workers

    async def compile(self, **kwargs: object) -> ProgramExecutionResult:
        """Delegate to the configured section fake."""
        return await self.workers.compile_section(**kwargs)


def _facade(plan: SemanticPlan, workers: _Workers) -> CodeModeCompileFacade:
    """Build the v2 facade with deterministic host-owned dependencies."""
    dependencies = CodeModeGraphDependencies(
        planner=_Planner(plan_value=plan),  # type: ignore[arg-type]
        enricher=_Enricher(),  # type: ignore[arg-type]
        report_compiler=_ReportAdapter(workers),  # type: ignore[arg-type]
        section_compiler=_SectionAdapter(workers),  # type: ignore[arg-type]
    )
    return CodeModeCompileFacade(dependencies)


async def _compile(
    facade: CodeModeCompileFacade,
    *,
    request: str = "compile the fixture",
    mode: CompilationMode = "reconstruct",
    document: AuthoringDocumentSpec | None = None,
) -> CodeModeCompileResult:
    """Invoke the facade with its stable host inputs."""
    return await facade.compile(
        request=request,
        mode=mode,
        document=document or _document(),
        source_candidates=(),
        timeout_seconds=5.0,
    )


def _plan(*, report: bool, sections: int) -> SemanticPlan:
    """Build one of the frozen parity plan shapes."""
    return SemanticPlan(
        summary="first section fixture" if sections else "report fixture",
        report_task=ReportTask(goal="Report title") if report else None,
        section_tasks=tuple(
            SectionTask(
                goal="first section" if index == 0 else "second section",
                capability_ids=("section.log_plot",),
            )
            for index in range(sections)
        ),
    )


def _revision_plan(*, report: bool, sections: int) -> SemanticPlan:
    """Build deterministic report, existing-section, and mixed revision plans."""
    return SemanticPlan(
        summary="revision fixture",
        report_task=ReportTask(goal="Updated report") if report else None,
        section_tasks=tuple(
            SectionTask(
                goal="Existing section revised",
                capability_ids=("section.log_plot",),
                existing_section_hint="Existing section",
            )
            for _index in range(sections)
        ),
    )


def test_facade_compiles_inside_an_already_running_event_loop() -> None:
    """The host boundary uses native graph.ainvoke without nested asyncio.run."""

    async def scenario() -> None:
        plan = _plan(report=True, sections=2)
        workers = _Workers()
        result = await _compile(_facade(plan, workers))

        assert result.success is True
        assert [worker.plan_order for worker in result.workers] == [0, 1, 2]
        assert workers.completion_order == ["section-1", "report", "section-0"]
        assert result.metrics.worker_count == 3
        assert result.metrics.successful_workers == 3
        assert result.metrics.failed_workers == 0
        assert result.metrics.total_program_chars == 50
        assert result.metrics.max_nesting_depth == 2
        outward = result.model_dump(mode="json")
        assert "plan" not in outward
        assert "intent_fragment" not in str(outward)
        assert "report = wp.report" not in str(outward)

    asyncio.run(scenario())


def test_workflow_contains_no_nested_event_loop_bridge() -> None:
    """The CM-46 graph path must not reintroduce asyncio.run."""
    from wellplot.agent.code_mode import workflow

    assert "asyncio.run(" not in inspect.getsource(workflow)


@pytest.mark.parametrize(
    ("report", "sections", "expected"),
    [
        (True, 0, AuthoringDocumentIntent(title="Report title")),
        (
            False,
            1,
            AuthoringDocumentIntent(sections=[{"section_id": "section-0", "title": "Section 0"}]),
        ),
        (
            True,
            2,
            AuthoringDocumentIntent(
                title="Report title",
                sections=[
                    {"section_id": "section-0", "title": "Section 0"},
                    {"section_id": "section-1", "title": "Section 1"},
                ],
            ),
        ),
    ],
)
def test_v2_matches_frozen_canonical_parity_fixture(
    report: bool,
    sections: int,
    expected: AuthoringDocumentIntent,
) -> None:
    """Frozen report/section shapes produce exact canonical intent fixtures."""
    result = asyncio.run(_compile(_facade(_plan(report=report, sections=sections), _Workers())))

    assert result.success is True
    assert result.merged_intent is not None
    assert result.merged_intent.model_dump(exclude_unset=True) == expected.model_dump(
        exclude_unset=True
    )


def test_v2_parity_matches_deterministic_legacy_graph_for_sections() -> None:
    """Legacy graph fakes and v2 fakes agree on exact section fixtures."""
    registry = create_builtin_registry()

    class LegacyPlanner:
        async def plan(self, **_kwargs: object) -> ReconstructionPlan:
            return ReconstructionPlan(
                summary="legacy fixture",
                sections=[
                    SectionPlan(
                        section_id="section-0",
                        capability_id="section.log_plot",
                        goal="first section",
                    ),
                    SectionPlan(
                        section_id="section-1",
                        capability_id="section.log_plot",
                        goal="second section",
                    ),
                ],
            )

    class LegacyReport:
        async def compile(self, **_kwargs: object) -> CompiledArtifact:
            return CompiledArtifact(
                worker_id="report",
                capability_id="report.standard",
                target_id="report",
                payload={"intent": {"title": "Report title"}},
            )

    class LegacySections:
        async def compile(
            self,
            *,
            plan: SectionPlan,
            **_kwargs: object,
        ) -> CompiledArtifact:
            return CompiledArtifact(
                worker_id=plan.section_id,
                capability_id="section.log_plot",
                target_id=plan.section_id,
                payload={
                    "section": {
                        "section_id": plan.section_id,
                        "title": plan.section_id.replace("-", " ").title(),
                    }
                },
            )

    legacy = build_legacy_graph(
        ReconstructionGraphDependencies(
            planner=LegacyPlanner(),  # type: ignore[arg-type]
            report_compiler=LegacyReport(),  # type: ignore[arg-type]
            section_compiler=LegacySections(),  # type: ignore[arg-type]
            registry=registry,
        )
    )
    legacy_result = asyncio.run(
        legacy.ainvoke(
            {
                "request": "compile the fixture",
                "mode": "reconstruct",
                "current_document": _document().model_dump(mode="json"),
                "source_manifest": {},
                "compiled_artifacts": [],
                "diagnostics": [],
            }
        )
    )
    v2_plan = _plan(report=True, sections=2)
    v2_result = asyncio.run(_compile(_facade(v2_plan, _Workers())))

    assert v2_result.merged_intent is not None
    assert legacy_result["merged_intent"] == v2_result.merged_intent.model_dump(
        mode="json", exclude_unset=True
    )


@dataclass
class _LegacyRevisionModel:
    """Deterministic structured model for legacy revision parity fixtures."""

    include_report: bool

    async def generate(
        self,
        *,
        response_model: type[object],
        tool_name: str,
        **_kwargs: object,
    ) -> object:
        """Return one fixed report-plus-existing-section revision shape."""
        if tool_name == "submit_reconstruction_plan":
            return response_model.model_validate(
                {
                    "summary": "Revision fixture",
                    "sections": [
                        {
                            "section_id": "existing",
                            "capability_id": "section.log_plot",
                            "goal": "Existing section revised",
                        }
                    ],
                }
            )
        if tool_name == "submit_report_artifact":
            intent = {"title": "Updated report"} if self.include_report else {}
            return response_model.model_validate({"intent": intent})
        if tool_name == "submit_section_artifact":
            return response_model.model_validate(
                {
                    "section": {
                        "section_id": "existing",
                        "title": "Existing section revised",
                    }
                }
            )
        raise AssertionError(f"Unexpected legacy revision tool: {tool_name}")


class _LegacyReportBoundary:
    """Represent the unchanged legacy report-worker boundary for parity."""

    async def compile(self, **_kwargs: object) -> CompiledArtifact:
        """Return the exact report intent used by the revision fixture."""
        return CompiledArtifact(
            worker_id="report",
            capability_id="report.standard",
            target_id="report",
            payload={"intent": {"title": "Updated report"}},
        )


def _legacy_revision_intent(*, include_report: bool) -> AuthoringDocumentIntent:
    """Compile one comparable existing-section revision through the legacy graph."""
    registry = create_builtin_registry()
    model = _LegacyRevisionModel(include_report=include_report)
    graph = build_legacy_graph(
        ReconstructionGraphDependencies(
            planner=ReconstructionPlanner(model=model, registry=registry),
            report_compiler=ReportCompiler(model=model, registry=registry),
            section_compiler=SectionCompiler(model=model, registry=registry),
            registry=registry,
        )
    )
    result = asyncio.run(
        compile_document_revision(
            graph,
            request="Revise the existing section fixture.",
            current_document=_document(),
        )
    )
    return result.intent


def test_v2_report_only_revision_matches_legacy_report_boundary() -> None:
    """Report-only revision compares exactly at the legacy report-worker boundary."""
    document = _document()
    before = document.model_dump(mode="json")
    result = asyncio.run(
        _compile(
            _facade(_revision_plan(report=True, sections=0), _Workers()),
            mode="revise",
            document=document,
        )
    )
    legacy_artifact = asyncio.run(_LegacyReportBoundary().compile())
    legacy_intent = AuthoringDocumentIntent.model_validate(legacy_artifact.payload["intent"])

    assert result.success is True
    assert result.merged_intent is not None
    assert result.merged_intent.model_dump(exclude_unset=True) == legacy_intent.model_dump(
        exclude_unset=True
    )
    assert document.model_dump(mode="json") == before
    assert result.merged_intent.sections is None


@pytest.mark.parametrize("include_report", [False, True])
def test_v2_revision_matches_legacy_graph_for_existing_and_mixed_shapes(
    include_report: bool,
) -> None:
    """Existing-section and mixed revision shapes have exact canonical parity."""
    document = _document()
    before = document.model_dump(mode="json")
    result = asyncio.run(
        _compile(
            _facade(_revision_plan(report=include_report, sections=1), _Workers()),
            mode="revise",
            document=document,
        )
    )
    legacy_intent = _legacy_revision_intent(include_report=include_report)

    assert result.success is True
    assert result.merged_intent is not None
    assert result.merged_intent.model_dump(exclude_unset=True) == legacy_intent.model_dump(
        exclude_unset=True
    )
    assert document.model_dump(mode="json") == before
    section = result.merged_intent.sections[0]
    assert section.subtitle is None
    assert section.tracks is None


def test_mixed_revision_failure_is_atomic_without_partial_intent() -> None:
    """A failed existing-section worker cannot publish a successful report fragment."""
    document = _document()
    before = document.model_dump(mode="json")
    result = asyncio.run(
        _compile(
            _facade(
                _revision_plan(report=True, sections=1),
                _Workers(fail_kind="section"),
            ),
            mode="revise",
            document=document,
        )
    )

    assert result.success is False
    assert result.merged_intent is None
    assert document.model_dump(mode="json") == before


def test_worker_failure_is_normalized_without_partial_intent() -> None:
    """A normal worker failure returns ordered bounded evidence and no intent."""
    plan = _plan(report=True, sections=1)
    result = asyncio.run(_compile(_facade(plan, _Workers(fail_kind="section"))))

    assert result.success is False
    assert result.merged_intent is None
    assert [worker.plan_order for worker in result.workers] == [0, 1]
    assert result.diagnostics[0].plan_order == 1
    assert result.metrics.failed_workers == 1


def test_worker_provider_failure_is_normalized() -> None:
    """Provider failures emitted by a worker become safe compile diagnostics."""
    result = asyncio.run(
        _compile(_facade(_plan(report=False, sections=1), _Workers(provider_kind="section")))
    )

    assert result.success is False
    assert result.merged_intent is None
    assert result.diagnostics[0].code == "provider.configuration"
    assert result.diagnostics[0].retryable is False


def test_planner_provider_failure_has_no_worker_evidence() -> None:
    """Planner provider failure is bounded before enrichment or workers run."""
    dependencies = CodeModeGraphDependencies(
        planner=_Planner(
            failure=ProviderRequestError(
                ProviderFailureCategory.RATE_LIMIT,
                "Planner rate limit.",
            )
        ),  # type: ignore[arg-type]
        enricher=_Enricher(),  # type: ignore[arg-type]
        report_compiler=_ReportAdapter(_Workers()),  # type: ignore[arg-type]
        section_compiler=_SectionAdapter(_Workers()),  # type: ignore[arg-type]
    )
    result = asyncio.run(_compile(CodeModeCompileFacade(dependencies)))

    assert result.success is False
    assert result.workers == ()
    assert result.diagnostics[0].stage == "planner"
    assert result.diagnostics[0].retryable is True


def test_enrichment_failure_has_no_worker_evidence() -> None:
    """Known enrichment failure is normalized before fan-out."""
    dependencies = CodeModeGraphDependencies(
        planner=_Planner(plan_value=_plan(report=False, sections=1)),  # type: ignore[arg-type]
        enricher=_Enricher(
            failure=SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_MISSING,
                "The selected source is missing.",
            )
        ),  # type: ignore[arg-type]
        report_compiler=_ReportAdapter(_Workers()),  # type: ignore[arg-type]
        section_compiler=_SectionAdapter(_Workers()),  # type: ignore[arg-type]
    )
    result = asyncio.run(_compile(CodeModeCompileFacade(dependencies)))

    assert result.success is False
    assert result.workers == ()
    assert result.diagnostics[0].code == "enrichment.source_missing"


def test_unexpected_graph_invariant_still_raises() -> None:
    """Facade normalization does not hide impossible graph state."""

    class BrokenEnricher(_Enricher):
        def enrich(self, *, plan: SemanticPlan, **_kwargs: object) -> EnrichedSemanticContext:
            return EnrichedSemanticContext(plan=plan, sections=(), report=ReportContext())

    dependencies = CodeModeGraphDependencies(
        planner=_Planner(plan_value=_plan(report=False, sections=1)),  # type: ignore[arg-type]
        enricher=BrokenEnricher(),  # type: ignore[arg-type]
        report_compiler=_ReportAdapter(_Workers()),  # type: ignore[arg-type]
        section_compiler=_SectionAdapter(_Workers()),  # type: ignore[arg-type]
    )
    with pytest.raises(IndexError):
        asyncio.run(_compile(CodeModeCompileFacade(dependencies)))
