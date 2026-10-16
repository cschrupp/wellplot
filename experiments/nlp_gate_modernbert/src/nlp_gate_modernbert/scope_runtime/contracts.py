"""Successor program contracts (scope-runtime side). MB-02R request classes untouched."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from nlp_gate_modernbert.mb02.contracts import (
    FillSpec,
    IntervalBounds,
    PublicEnvelope,
    RequestedOperation,
    ScaleBounds,
)


class ScopeSemanticQuery(BaseModel):
    """Exactly one of text | local_ref for a reference-bearing query."""

    kind: Literal["curve", "track", "fill", "deictic"]
    text: str | None = None
    local_ref: str | None = None

    @model_validator(mode="after")
    def _xor_text_local_ref(self) -> ScopeSemanticQuery:
        """Q4: exactly one of text | local_ref (both-set and neither-set are invalid)."""
        has_text = self.text is not None and str(self.text).strip() != ""
        has_ref = self.local_ref is not None and str(self.local_ref).strip() != ""
        if has_text and has_ref:
            raise ValueError("local_ref_and_text_both_set")
        if not has_text and not has_ref:
            raise ValueError("local_ref_and_text_both_absent")
        # Normalize empty string counterpart to None for the unused side
        if has_text:
            object.__setattr__(self, "local_ref", None)
        else:
            object.__setattr__(self, "text", None)
        return self


class ScopeNormalizedRequest(BaseModel):
    """MB-02R-compatible operands + frozen Q1A / Q4 extensions only."""

    requested_operation: RequestedOperation
    query: ScopeSemanticQuery | None = None
    secondary_query: ScopeSemanticQuery | None = None
    target: ScopeSemanticQuery | None = None
    deictic_reference: bool = False
    scale_direction_claims: list[Literal["increasing", "decreasing"]] = Field(
        default_factory=list
    )
    target_claims: list[str] = Field(default_factory=list)
    scale_bounds: ScaleBounds | None = None
    interval_bounds: IntervalBounds | None = None
    alpha: float | None = None
    line_width: float | None = None
    requested_unit: str | None = None
    fill: FillSpec | None = None
    source_qualifier: str | None = None
    section_qualifier: str | None = None
    report_title: str | None = None
    # Q1A — CREATE_TRACK only
    track_title: str | None = None
    track_width_mm: float | None = None


class ScopeNormalizedTask(BaseModel):
    task_id: str
    request: ScopeNormalizedRequest
    depends_on: list[str] = Field(default_factory=list)
    produces_binds: dict[str, Literal["track"]] = Field(default_factory=dict)


class ScopeNormalizedProgram(BaseModel):
    version: str | None = None
    tasks: list[ScopeNormalizedTask]


class LocalBindingTable(BaseModel):
    """Ephemeral execution state (not part of declarative program)."""

    binds: dict[str, int] = Field(default_factory=dict)  # local_ref → projected track_ref

    def get(self, local_ref: str) -> int | None:
        return self.binds.get(local_ref)

    def publish(self, local_ref: str, projected_track_ref: int) -> None:
        self.binds[local_ref] = projected_track_ref


class TaskTraceRecord(BaseModel):
    task_id: str
    workspace_before: dict[str, Any]
    scope_request: dict[str, Any]
    source_local_ref: str | None = None
    resolved_projected_ref: int | None = None
    mb02_adjudication_query: str | None = None
    mb02_authority: str
    public_envelope: dict[str, Any]
    effect_applied: str | None = None
    binds_produced: dict[str, int] = Field(default_factory=dict)
    workspace_after: dict[str, Any]
    adjudicated: bool = True


class ProgramExecutionResult(BaseModel):
    case_id: str | None = None
    structural_valid: bool
    structural_reason: str | None = None
    task_trace: list[TaskTraceRecord] = Field(default_factory=list)
    program_terminal: dict[str, Any]
    gold_used_as_runtime_decision_input: bool = False
    frontier_calls: int = 0
    all_task_effects_post_ok_only: bool = True
    all_local_ref_adapters_resolved_from_binding_table: bool = True
