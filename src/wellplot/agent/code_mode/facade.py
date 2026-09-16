"""Internal async host facade for the Code Mode v2 compile graph."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...authoring_program.models import (
    ProgramDiagnostic,
    ProgramMetrics,
)
from ...model.authoring import AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent
from ..providers.base import ProviderRequestError
from .enrichment import (
    EnrichedSemanticContext,
    EnrichmentWarning,
    SemanticEnrichmentError,
    SourceCandidate,
)
from .planner import CompilationMode, PlannerSemanticFailure, SemanticPlan
from .state import CodeModeGraphState, WorkerOutcome
from .workflow import CodeModeGraphDependencies, build_compile_graph


class _CompileModel(BaseModel):
    """Strict immutable configuration for the internal compile result."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CompileDiagnosticSeverity(StrEnum):
    """Severity for graph-level compile diagnostics."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class CompileDiagnostic(_CompileModel):
    """Safe graph-level diagnostic independent of program-kernel semantics."""

    stage: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: CompileDiagnosticSeverity = CompileDiagnosticSeverity.ERROR
    retryable: bool | None = None
    worker_kind: Literal["report", "section"] | None = None
    plan_order: int | None = Field(default=None, ge=0)


class CompileWorkerEvidence(_CompileModel):
    """Stable outward evidence for one dispatched worker."""

    kind: Literal["report", "section"]
    plan_order: int = Field(ge=0)
    success: bool
    diagnostics: tuple[CompileDiagnostic, ...] = ()
    metrics: ProgramMetrics = Field(default_factory=ProgramMetrics)


class CompileMetrics(_CompileModel):
    """Aggregate measured work from completed Code Mode workers."""

    worker_count: int = Field(ge=0)
    successful_workers: int = Field(ge=0)
    failed_workers: int = Field(ge=0)
    total_program_chars: int = Field(ge=0)
    total_ast_nodes: int = Field(ge=0)
    total_statements: int = Field(ge=0)
    total_calls: int = Field(ge=0)
    total_repairs: int = Field(ge=0)
    total_loop_iterations: int = Field(ge=0)
    total_created_objects: int = Field(ge=0)
    max_nesting_depth: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_worker_counts(self) -> CompileMetrics:
        """Keep aggregate success and failure counts consistent."""
        if self.successful_workers + self.failed_workers != self.worker_count:
            raise ValueError("Compile worker counts must add up to worker_count.")
        return self


class CodeModeCompileResult(_CompileModel):
    """Stable host result for one internal v2 graph compilation."""

    success: bool
    merged_intent: AuthoringDocumentIntent | None = None
    diagnostics: tuple[CompileDiagnostic, ...] = ()
    workers: tuple[CompileWorkerEvidence, ...] = ()
    metrics: CompileMetrics

    @model_validator(mode="after")
    def validate_result_evidence(self) -> CodeModeCompileResult:
        """Prevent success or partial intent from being inferred by callers."""
        if self.success:
            if self.merged_intent is None:
                raise ValueError("Successful compilation requires a merged intent.")
            if not self.workers or any(not worker.success for worker in self.workers):
                raise ValueError("Successful compilation requires all workers to succeed.")
        elif self.merged_intent is not None:
            raise ValueError("Failed compilation cannot expose a merged intent.")
        return self


@dataclass(frozen=True, slots=True)
class CodeModeCompileFacade:
    """Own graph construction, invocation, and stable result projection."""

    dependencies: CodeModeGraphDependencies
    _graph: CompiledStateGraph = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Build one private graph owned by this internal facade."""
        object.__setattr__(self, "_graph", build_compile_graph(self.dependencies))

    async def compile(
        self,
        *,
        request: str,
        mode: CompilationMode,
        document: AuthoringDocumentSpec,
        source_candidates: Sequence[SourceCandidate],
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> CodeModeCompileResult:
        """Invoke the v2 graph natively from an async host."""
        state: CodeModeGraphState = {
            "request": request,
            "mode": mode,
            "document": document.model_dump(mode="json"),
            "source_candidates": [
                candidate.model_dump(mode="json") for candidate in source_candidates
            ],
            "timeout_seconds": timeout_seconds,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "worker_outcomes": [],
            "diagnostics": [],
            "merged_intent": {},
        }
        try:
            result = await self._graph.ainvoke(state)
        except ProviderRequestError as error:
            return _failure_result((_provider_diagnostic(error),))
        except PlannerSemanticFailure as error:
            return _failure_result((_planner_diagnostic(error),))
        except SemanticEnrichmentError as error:
            return _failure_result((_enrichment_diagnostic(error),))
        return _project_graph_result(result)


def _project_graph_result(state: dict[str, object]) -> CodeModeCompileResult:
    """Project validated graph state into the stable host-facing result."""
    plan = SemanticPlan.model_validate(state["plan"])
    enriched_context = EnrichedSemanticContext.model_validate(state["enriched_context"])
    outcomes = tuple(
        WorkerOutcome.model_validate(json.loads(payload))
        for payload in state.get("worker_outcomes", [])
    )
    _validate_projected_work_units(outcomes, plan)
    workers = tuple(
        _worker_evidence(outcome) for outcome in sorted(outcomes, key=lambda item: item.plan_order)
    )
    metrics = _aggregate_metrics(workers)
    diagnostics = tuple(
        _enrichment_warning_diagnostic(warning) for warning in enriched_context.warnings
    )
    diagnostics += tuple(diagnostic for worker in workers for diagnostic in worker.diagnostics)
    if any(not worker.success for worker in workers):
        return CodeModeCompileResult(
            success=False,
            diagnostics=diagnostics,
            workers=workers,
            metrics=metrics,
        )

    merged_payload = state.get("merged_intent")
    if not isinstance(merged_payload, dict) or not merged_payload:
        raise ValueError("Successful Code Mode graph completed without merged intent.")
    merged_intent = AuthoringDocumentIntent.model_validate(merged_payload)
    return CodeModeCompileResult(
        success=True,
        merged_intent=merged_intent,
        diagnostics=diagnostics,
        workers=workers,
        metrics=metrics,
    )


def _worker_evidence(outcome: WorkerOutcome) -> CompileWorkerEvidence:
    """Project one internal outcome without exposing its intent fragment."""
    return CompileWorkerEvidence(
        kind=outcome.kind,
        plan_order=outcome.plan_order,
        success=outcome.success,
        diagnostics=tuple(
            _program_diagnostic(
                diagnostic,
                worker_kind=outcome.kind,
                plan_order=outcome.plan_order,
            )
            for diagnostic in outcome.diagnostics
        ),
        metrics=outcome.metrics,
    )


def _program_diagnostic(
    diagnostic: ProgramDiagnostic,
    *,
    worker_kind: Literal["report", "section"],
    plan_order: int,
) -> CompileDiagnostic:
    """Project a worker program diagnostic into the generic host contract."""
    retryable = None
    if diagnostic.code is not None and diagnostic.code.startswith("provider."):
        retryable = diagnostic.code.removeprefix("provider.") in {
            "timeout",
            "rate_limit",
            "transport",
        }
    return CompileDiagnostic(
        stage=diagnostic.stage,
        code=diagnostic.code or "program.unknown",
        message=diagnostic.message,
        severity=CompileDiagnosticSeverity(diagnostic.severity.value),
        retryable=retryable,
        worker_kind=worker_kind,
        plan_order=plan_order,
    )


def _provider_diagnostic(error: ProviderRequestError) -> CompileDiagnostic:
    """Project only explicitly safe provider failure fields."""
    return CompileDiagnostic(
        stage="planner",
        code=f"provider.{error.category.value}",
        message=error.safe_message,
        retryable=error.retryable,
    )


def _enrichment_diagnostic(error: SemanticEnrichmentError) -> CompileDiagnostic:
    """Project the stable enrichment category without raw exception details."""
    return CompileDiagnostic(
        stage="enrichment",
        code=f"enrichment.{error.code.value}",
        message=str(error),
    )


def _enrichment_warning_diagnostic(warning: EnrichmentWarning) -> CompileDiagnostic:
    """Project safe non-fatal enrichment evidence into the compile result."""
    return CompileDiagnostic(
        stage="enrichment",
        code=f"enrichment.{warning.code}",
        message=warning.message,
        severity=CompileDiagnosticSeverity.WARNING,
        retryable=False,
    )


def _planner_diagnostic(error: PlannerSemanticFailure) -> CompileDiagnostic:
    """Project the bounded final semantic planner failure."""
    return CompileDiagnostic(
        stage="planner",
        code=f"planner.{error.code}",
        message=error.safe_message,
        retryable=False,
    )


def _failure_result(diagnostics: tuple[CompileDiagnostic, ...]) -> CodeModeCompileResult:
    """Build a bounded failure result before any worker has run."""
    return CodeModeCompileResult(
        success=False,
        diagnostics=diagnostics,
        metrics=_empty_metrics(),
    )


def _empty_metrics() -> CompileMetrics:
    """Return the measured-zero aggregate for a graph with no workers."""
    return CompileMetrics(
        worker_count=0,
        successful_workers=0,
        failed_workers=0,
        total_program_chars=0,
        total_ast_nodes=0,
        total_statements=0,
        total_calls=0,
        total_repairs=0,
        total_loop_iterations=0,
        total_created_objects=0,
        max_nesting_depth=0,
    )


def _aggregate_metrics(workers: Sequence[CompileWorkerEvidence]) -> CompileMetrics:
    """Aggregate measured worker metrics without inventing provider metrics."""
    metrics = [worker.metrics for worker in workers]
    return CompileMetrics(
        worker_count=len(workers),
        successful_workers=sum(worker.success for worker in workers),
        failed_workers=sum(not worker.success for worker in workers),
        total_program_chars=sum(item.program_chars for item in metrics),
        total_ast_nodes=sum(item.program_ast_nodes for item in metrics),
        total_statements=sum(item.program_statements for item in metrics),
        total_calls=sum(item.program_calls for item in metrics),
        total_repairs=sum(item.program_repairs for item in metrics),
        total_loop_iterations=sum(item.program_loop_iterations for item in metrics),
        total_created_objects=sum(item.created_objects for item in metrics),
        max_nesting_depth=max((item.program_nesting_depth for item in metrics), default=0),
    )


def _validate_projected_work_units(
    outcomes: Sequence[WorkerOutcome],
    plan: SemanticPlan,
) -> None:
    """Keep the facade's worker projection aligned with graph dispatch."""
    expected = {("report", 0)} if plan.report_task is not None else set()
    expected.update(("section", index + 1) for index in range(len(plan.section_tasks)))
    actual = {(outcome.kind, outcome.plan_order) for outcome in outcomes}
    if actual != expected or len(actual) != len(outcomes):
        raise ValueError("Code Mode worker outcomes do not exactly match graph dispatch.")


__all__ = [
    "CodeModeCompileFacade",
    "CodeModeCompileResult",
    "CompileDiagnostic",
    "CompileDiagnosticSeverity",
    "CompileMetrics",
    "CompileWorkerEvidence",
]
