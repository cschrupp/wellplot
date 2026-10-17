"""Harness-local recursively closed ScopeNormalizedProgram models (extra=forbid)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nlp_gate_modernbert.mb02.contracts import RequestedOperation


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClosedScaleBounds(ClosedModel):
    kind: Literal["linear", "log"] | None = None
    minimum: float | None = None
    maximum: float | None = None


class ClosedIntervalBounds(ClosedModel):
    top: float | None = None
    base: float | None = None
    unit: str | None = None


class ClosedFillPredicate(ClosedModel):
    kind: Literal[
        "ABOVE_THRESHOLD",
        "BELOW_THRESHOLD",
        "BETWEEN_CURVES",
        "TO_LIMIT",
        "BASELINE_SPLIT",
    ]
    value: float | None = None
    secondary_query: str | None = None
    limit: Literal["lower", "upper"] | None = None


class ClosedFillSpec(ClosedModel):
    mode: Literal[
        "CONDITIONAL",
        "BETWEEN",
        "BETWEEN_INSTANCES",
        "TO_LIMIT",
        "BASELINE_SPLIT",
        "SOLID",
    ] | None = None
    predicate: ClosedFillPredicate | None = None
    primary_query: str | None = None
    baseline_value: float | None = None
    asserts_cross_track: bool = False
    asserts_scale_mismatch: bool = False


class ClosedSemanticQuery(ClosedModel):
    kind: Literal["curve", "track", "fill", "deictic"]
    text: str | None = None
    local_ref: str | None = None

    @model_validator(mode="after")
    def _xor(self) -> ClosedSemanticQuery:
        has_text = self.text is not None and str(self.text).strip() != ""
        has_ref = self.local_ref is not None and str(self.local_ref).strip() != ""
        if has_text and has_ref:
            raise ValueError("local_ref_and_text_both_set")
        if not has_text and not has_ref:
            raise ValueError("local_ref_and_text_both_absent")
        if has_text:
            object.__setattr__(self, "local_ref", None)
        else:
            object.__setattr__(self, "text", None)
        return self


class ClosedNormalizedRequest(ClosedModel):
    requested_operation: RequestedOperation
    query: ClosedSemanticQuery | None = None
    secondary_query: ClosedSemanticQuery | None = None
    target: ClosedSemanticQuery | None = None
    deictic_reference: bool = False
    scale_direction_claims: list[Literal["increasing", "decreasing"]] = Field(
        default_factory=list
    )
    target_claims: list[str] = Field(default_factory=list)
    scale_bounds: ClosedScaleBounds | None = None
    interval_bounds: ClosedIntervalBounds | None = None
    alpha: float | None = None
    line_width: float | None = None
    requested_unit: str | None = None
    fill: ClosedFillSpec | None = None
    source_qualifier: str | None = None
    section_qualifier: str | None = None
    report_title: str | None = None
    track_title: str | None = None
    track_width_mm: float | None = None


class ClosedNormalizedTask(ClosedModel):
    task_id: str
    request: ClosedNormalizedRequest
    depends_on: list[str] = Field(default_factory=list)
    produces_binds: dict[str, Literal["track"]] = Field(default_factory=dict)


class ClosedNormalizedProgram(ClosedModel):
    version: str | None = None
    tasks: list[ClosedNormalizedTask]
