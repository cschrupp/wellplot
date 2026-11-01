"""JSON-safe state contracts for the Code Mode v2 compile graph."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...model.intent import AuthoringDocumentIntent
from ..semantic_runtime import SemanticDiagnostic, SemanticMetrics, SemanticStageEvidence
from .planner import CompilationMode


def replace_merged_intent(
    _current: dict[str, Any],
    update: dict[str, Any],
) -> dict[str, Any]:
    """Replace the one graph-level merged intent after all workers finish."""
    return update


class ConditionalOmissionEvidence(BaseModel):
    """One verified request-local operation omitted by an evaluated condition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_ref: str = Field(min_length=1)
    predicate: Literal["source_channel_available", "source_channel_absent"]
    evidence_source_handle: str = Field(min_length=1)
    channel_clue: str = Field(min_length=1)
    requirement_ids: tuple[str, ...] = Field(min_length=1)


class WorkerOutcome(BaseModel):
    """Compact result from one isolated report or section worker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["report", "section"]
    plan_order: int = Field(ge=0)
    success: bool
    intent_fragment: AuthoringDocumentIntent | None = None
    diagnostics: tuple[SemanticDiagnostic, ...] = ()
    metrics: SemanticMetrics = Field(default_factory=SemanticMetrics)
    stage_evidence: SemanticStageEvidence = Field(default_factory=SemanticStageEvidence)
    conditional_omissions: tuple[ConditionalOmissionEvidence, ...] = ()

    @model_validator(mode="after")
    def validate_evidence(self) -> WorkerOutcome:
        """Keep graph evidence explicit without retaining generated source text."""
        if self.success and self.intent_fragment is None:
            raise ValueError("Successful worker outcomes require an intent fragment.")
        if not self.success:
            if self.intent_fragment is not None:
                raise ValueError("Failed worker outcomes cannot contain an intent fragment.")
            if not self.diagnostics:
                raise ValueError("Failed worker outcomes require diagnostics.")
        return self


class CodeModeGraphState(TypedDict, total=False):
    """JSON-safe state shared by v2 planning, enrichment, and merge nodes."""

    request: str
    mode: CompilationMode
    document: dict[str, Any]
    source_candidates: list[dict[str, Any]]
    timeout_seconds: float
    planner_temperature: float | None
    temperature: float | None
    max_output_tokens: int | None
    plan: dict[str, Any]
    planned_document_revision: str
    capability_safety: dict[str, Any]
    report_boundary_safety: dict[str, Any]
    section_leaf_safety: dict[str, Any]
    enriched_context: dict[str, Any]
    worker_outcomes: Annotated[list[str], operator.add]
    diagnostics: Annotated[list[str], operator.add]
    merged_intent: Annotated[dict[str, Any], replace_merged_intent]


class CodeModeWorkerState(TypedDict, total=False):
    """Isolated JSON-safe payload sent to one dynamic worker invocation."""

    kind: Literal["report", "section"]
    plan_order: int
    authoritative_request: str
    report_task: NotRequired[dict[str, Any]]
    report_context: NotRequired[dict[str, Any]]
    report_operation_contract: NotRequired[dict[str, Any]]
    report_operation_contract_error: NotRequired[str]
    section_task: NotRequired[dict[str, Any]]
    section_context: NotRequired[dict[str, Any]]
    section_work_contract: NotRequired[dict[str, Any]]
    section_operation_contract: NotRequired[dict[str, Any]]
    conditional_omissions: NotRequired[list[dict[str, Any]]]
    conditional_noop: NotRequired[bool]
    section_work_contract_error: NotRequired[str]
    document: dict[str, Any]
    timeout_seconds: float
    temperature: float | None
    max_output_tokens: int | None


__all__ = [
    "CodeModeGraphState",
    "CodeModeWorkerState",
    "WorkerOutcome",
    "replace_merged_intent",
]
