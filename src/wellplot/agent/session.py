"""Direct Python boundary for the Code Mode v2 compile service."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..model.authoring import AuthoringDocumentSpec
from ..model.intent import AuthoringDocumentIntent
from .code_mode.enrichment import SourceCandidate

CompilationMode = Literal["reconstruct", "revise"]


class _SessionModel(BaseModel):
    """Shared strict immutable configuration for the public session boundary."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class AgentSessionConfig(_SessionModel):
    """Provider-neutral execution limits for one direct Python session."""

    timeout_seconds: float = Field(default=120.0, gt=0)
    temperature: float | None = Field(default=None, ge=0)
    max_output_tokens: int | None = Field(default=None, gt=0)

    @field_validator("timeout_seconds", "temperature", mode="before")
    @classmethod
    def validate_finite_numbers(cls, value: object) -> object:
        """Match provider validation for finite numeric execution settings."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Execution settings must use numeric values.")
        if not math.isfinite(value):
            raise ValueError("Execution settings must be finite numbers.")
        return value

    @field_validator("max_output_tokens", mode="before")
    @classmethod
    def validate_integer_token_limit(cls, value: object) -> object:
        """Match provider validation for a real positive integer token limit."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("max_output_tokens must be an integer.")
        return value


class AgentSourceConfig(_SessionModel):
    """One host-approved source reference passed to the v2 compiler."""

    candidate_id: str = Field(min_length=1)
    root_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    labels: tuple[str, ...] = ()
    trusted_format: Literal["las", "dlis"] | None = None

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject blank source labels before crossing into the internal model."""
        if any(not value.strip() for value in values):
            raise ValueError("Source labels cannot contain blank items.")
        return values

    def _internal(self) -> SourceCandidate:
        """Convert the public source reference to the internal enrichment contract."""
        return SourceCandidate(
            candidate_id=self.candidate_id,
            root_id=self.root_id,
            path=self.path,
            labels=self.labels,
            trusted_format=self.trusted_format,
        )


class AgentDiagnosticSeverity(StrEnum):
    """Severity values exposed by the direct session result."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class AgentDiagnostic(_SessionModel):
    """Safe graph or worker diagnostic projected for public callers."""

    stage: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: AgentDiagnosticSeverity = AgentDiagnosticSeverity.ERROR
    retryable: bool | None = None
    worker_kind: Literal["report", "section"] | None = None
    plan_order: int | None = Field(default=None, ge=0)


class AgentMetrics(_SessionModel):
    """Aggregate measured work from one direct v2 session call."""

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
    def validate_worker_counts(self) -> AgentMetrics:
        """Keep aggregate success and failure counts consistent."""
        if self.successful_workers + self.failed_workers != self.worker_count:
            raise ValueError("Agent worker counts must add up to worker_count.")
        return self


class AgentWorkerMetrics(_SessionModel):
    """Per-worker program measurements without generated source material."""

    program_chars: int = Field(default=0, ge=0)
    program_ast_nodes: int = Field(default=0, ge=0)
    program_statements: int = Field(default=0, ge=0)
    program_calls: int = Field(default=0, ge=0)
    program_repairs: int = Field(default=0, ge=0)
    program_loop_iterations: int = Field(default=0, ge=0)
    program_nesting_depth: int = Field(default=0, ge=0)
    created_objects: int = Field(default=0, ge=0)


class AgentWorkerEvidence(_SessionModel):
    """Bounded evidence for one report or section worker."""

    kind: Literal["report", "section"]
    plan_order: int = Field(ge=0)
    success: bool
    diagnostics: tuple[AgentDiagnostic, ...] = ()
    metrics: AgentWorkerMetrics = Field(default_factory=AgentWorkerMetrics)


class AgentSessionResult(_SessionModel):
    """Stable public result for one direct v2 compilation."""

    mode: CompilationMode
    success: bool
    intent: AuthoringDocumentIntent | None = None
    diagnostics: tuple[AgentDiagnostic, ...] = ()
    workers: tuple[AgentWorkerEvidence, ...] = ()
    metrics: AgentMetrics

    @model_validator(mode="after")
    def validate_result_evidence(self) -> AgentSessionResult:
        """Preserve the facade invariant that failure never exposes intent."""
        if self.success:
            if self.intent is None:
                raise ValueError("Successful session results require an intent.")
            if not self.workers or any(not worker.success for worker in self.workers):
                raise ValueError("Successful session results require all workers to succeed.")
        elif self.intent is not None:
            raise ValueError("Failed session results cannot expose an intent.")
        return self

    def inspection(self) -> dict[str, object]:
        """Return bounded JSON-safe evidence without intent or provider material."""
        return {
            "mode": self.mode,
            "success": self.success,
            "diagnostics": [item.model_dump(mode="json") for item in self.diagnostics],
            "workers": [item.model_dump(mode="json") for item in self.workers],
            "metrics": self.metrics.model_dump(mode="json"),
            "intent_present": self.intent is not None,
        }


class _DiagnosticLike(Protocol):
    """Internal diagnostic shape accepted from the compile facade."""

    stage: str
    code: str
    message: str
    severity: object
    retryable: bool | None
    worker_kind: Literal["report", "section"] | None
    plan_order: int | None


class _AggregateMetricsLike(Protocol):
    """Internal aggregate metrics shape accepted from the compile facade."""

    worker_count: int
    successful_workers: int
    failed_workers: int
    total_program_chars: int
    total_ast_nodes: int
    total_statements: int
    total_calls: int
    total_repairs: int
    total_loop_iterations: int
    total_created_objects: int
    max_nesting_depth: int


class _WorkerMetricsLike(Protocol):
    """Internal per-worker metrics shape accepted from the compile facade."""

    program_chars: int
    program_ast_nodes: int
    program_statements: int
    program_calls: int
    program_repairs: int
    program_loop_iterations: int
    program_nesting_depth: int
    created_objects: int


class _WorkerLike(Protocol):
    """Internal worker evidence shape accepted from the compile facade."""

    kind: Literal["report", "section"]
    plan_order: int
    success: bool
    diagnostics: Sequence[_DiagnosticLike]
    metrics: _WorkerMetricsLike


class _CompileResultLike(Protocol):
    """Internal result shape accepted from the compile facade."""

    success: bool
    merged_intent: AuthoringDocumentIntent | None
    diagnostics: Sequence[_DiagnosticLike]
    workers: Sequence[_WorkerLike]
    metrics: _AggregateMetricsLike


class _CompileFacadeProtocol(Protocol):
    """Private structural contract accepted by AgentSession."""

    async def compile(
        self,
        *,
        request: str,
        mode: CompilationMode,
        document: AuthoringDocumentSpec,
        source_candidates: Sequence[SourceCandidate],
        timeout_seconds: float,
        temperature: float | None,
        max_output_tokens: int | None,
    ) -> _CompileResultLike:
        """Compile one host-owned document through the v2 graph."""


@dataclass(frozen=True, slots=True)
class AgentSession:
    """Direct async Python session over an injected Code Mode compiler."""

    compiler: _CompileFacadeProtocol
    config: AgentSessionConfig = AgentSessionConfig()

    async def build(
        self,
        *,
        request: str,
        document: AuthoringDocumentSpec,
        sources: Sequence[AgentSourceConfig] = (),
    ) -> AgentSessionResult:
        """Compile a reconstruction without applying or retaining its intent."""
        return await self._compile(
            request=request,
            mode="reconstruct",
            document=document,
            sources=sources,
        )

    async def revise(
        self,
        *,
        request: str,
        document: AuthoringDocumentSpec,
        sources: Sequence[AgentSourceConfig] = (),
    ) -> AgentSessionResult:
        """Compile a sparse revision without applying or retaining its intent."""
        return await self._compile(
            request=request,
            mode="revise",
            document=document,
            sources=sources,
        )

    async def _compile(
        self,
        *,
        request: str,
        mode: CompilationMode,
        document: AuthoringDocumentSpec,
        sources: Sequence[AgentSourceConfig],
    ) -> AgentSessionResult:
        """Project one compiler call into the public result boundary."""
        normalized_request = request.strip()
        if not normalized_request:
            raise ValueError("request must be a non-empty string.")
        internal_sources = tuple(source._internal() for source in sources)
        result = await self.compiler.compile(
            request=normalized_request,
            mode=mode,
            document=document,
            source_candidates=internal_sources,
            timeout_seconds=self.config.timeout_seconds,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
        )
        return _project_result(result, mode=mode)


def _project_result(result: _CompileResultLike, *, mode: CompilationMode) -> AgentSessionResult:
    """Project the internal facade result without exposing its model types."""
    workers = tuple(_project_worker(worker) for worker in result.workers)
    return AgentSessionResult(
        mode=mode,
        success=result.success,
        intent=result.merged_intent,
        diagnostics=tuple(_project_diagnostic(item) for item in result.diagnostics),
        workers=workers,
        metrics=_project_metrics(result.metrics),
    )


def _project_diagnostic(diagnostic: _DiagnosticLike) -> AgentDiagnostic:
    """Copy only safe diagnostic fields from the internal facade result."""
    severity = getattr(diagnostic.severity, "value", diagnostic.severity)
    return AgentDiagnostic(
        stage=diagnostic.stage,
        code=diagnostic.code,
        message=diagnostic.message,
        severity=severity,
        retryable=diagnostic.retryable,
        worker_kind=diagnostic.worker_kind,
        plan_order=diagnostic.plan_order,
    )


def _project_metrics(metrics: _AggregateMetricsLike) -> AgentMetrics:
    """Copy the measured aggregate into the public metrics model."""
    fields = {
        field_name: getattr(metrics, field_name)
        for field_name in (
            "worker_count",
            "successful_workers",
            "failed_workers",
            "total_program_chars",
            "total_ast_nodes",
            "total_statements",
            "total_calls",
            "total_repairs",
            "total_loop_iterations",
            "total_created_objects",
            "max_nesting_depth",
        )
    }
    return AgentMetrics(**fields)


def _project_worker(worker: _WorkerLike) -> AgentWorkerEvidence:
    """Project one worker without exposing its intent fragment or program."""
    return AgentWorkerEvidence(
        kind=worker.kind,
        plan_order=worker.plan_order,
        success=worker.success,
        diagnostics=tuple(_project_diagnostic(item) for item in worker.diagnostics),
        metrics=_project_worker_metrics(worker.metrics),
    )


def _project_worker_metrics(metrics: _WorkerMetricsLike) -> AgentWorkerMetrics:
    """Copy per-worker program measurements into the public model."""
    fields = {
        field_name: getattr(metrics, field_name)
        for field_name in (
            "program_chars",
            "program_ast_nodes",
            "program_statements",
            "program_calls",
            "program_repairs",
            "program_loop_iterations",
            "program_nesting_depth",
            "created_objects",
        )
    }
    return AgentWorkerMetrics(**fields)


def _empty_metrics() -> AgentMetrics:
    """Return measured-zero worker metrics for a worker with no evidence."""
    return AgentMetrics(
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


__all__ = [
    "AgentDiagnostic",
    "AgentDiagnosticSeverity",
    "AgentMetrics",
    "AgentSession",
    "AgentSessionConfig",
    "AgentSessionResult",
    "AgentSourceConfig",
    "AgentWorkerMetrics",
    "AgentWorkerEvidence",
]
