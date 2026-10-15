"""MB-02 typed contracts (allowlisted request / workspace / derived / oracle)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RequestedOperation = Literal[
    "PLACE_CURVE",
    "MOVE_CURVE",
    "REMOVE_CURVE",
    "CONFIGURE_CURVE_DISPLAY",
    "SET_INTERVAL",
    "CREATE_TRACK",
    "DEFINE_FILL",
    "REMOVE_FILL",
    "RENAME_REPORT",
    "SET_PAGE_ORIENTATION",
    "ADD_ANNOTATION",
    "INSTANTIATE_TEMPLATE",
    "SELECT_SOURCE",
    "COMPARE_WELLS",
    "MULTI_SECTION_LAYOUT",
    "RASTER_WAVEFORM",
    "SECTION_TARGETED_SCALE",
    "UNKNOWN",
]


class SemanticQuery(BaseModel):
    kind: Literal["curve", "track", "fill", "deictic"]
    text: str | None = None


class FillPredicate(BaseModel):
    kind: Literal["ABOVE_THRESHOLD", "BELOW_THRESHOLD", "BETWEEN_CURVES", "TO_LIMIT"]
    value: float | None = None
    secondary_query: str | None = None
    limit: Literal["lower", "upper"] | None = None


class FillSpec(BaseModel):
    mode: Literal["CONDITIONAL", "BETWEEN", "TO_LIMIT", "SOLID"] | None = None
    predicate: FillPredicate | None = None
    primary_query: str | None = None
    # Explicit request language asserting cross-track / incompatible setup
    asserts_cross_track: bool = False
    asserts_scale_mismatch: bool = False


class ScaleBounds(BaseModel):
    kind: Literal["linear", "log"] | None = None
    minimum: float | None = None
    maximum: float | None = None


class IntervalBounds(BaseModel):
    top: float | None = None
    base: float | None = None
    unit: str | None = None


class NormalizedRequest(BaseModel):
    """Allowlisted interpreted-request fields only (no decision labels)."""

    requested_operation: RequestedOperation
    query: SemanticQuery | None = None
    secondary_query: SemanticQuery | None = None
    target: SemanticQuery | None = None
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


class CurveFact(BaseModel):
    id: str
    channel: str | None = None
    handle: str | None = None
    label: str | None = None
    aliases: list[str] = Field(default_factory=list)
    track_ref: int | None = None
    scale_kind: str | None = None
    scale_min: float | None = None
    scale_max: float | None = None
    scale_reverse: bool | None = None


class TrackFact(BaseModel):
    ref: int
    id: str | None = None
    title: str | None = None
    curves: list[str] = Field(default_factory=list)


class FillFact(BaseModel):
    ref: str
    curve: str | None = None
    mode: str | None = None


class ProjectedWorkspace(BaseModel):
    fixture_id: str
    curves: list[CurveFact] = Field(default_factory=list)
    tracks: list[TrackFact] = Field(default_factory=list)
    fills: list[FillFact] = Field(default_factory=list)
    focus_curve_handle: str | None = None
    focus_track_ref: int | None = None
    depth_unit: str | None = None
    supported_depth_units: list[str] = Field(default_factory=lambda: ["m", "ft"])


class ReferenceMatch(BaseModel):
    field: str
    query: str
    candidate_ids: list[str]
    candidate_count: int


Authority = Literal[
    "DETERMINISTIC_SCHEMA_DOMAIN",
    "STATIC_CAPABILITY_BOUNDARY",
    "DETERMINISTIC_NOT_FOUND",
    "DETERMINISTIC_CARDINALITY",
    "DETERMINISTIC_PRECONDITION",
    "OK",
]

PreconditionSubtype = Literal[
    "MISSING_DEICTIC_FOCUS",
    "FILL_CROSS_TRACK",
    "FILL_SCALE_INCOMPATIBLE",
    "OTHER_EXECUTION_PRECONDITION",
]


class DerivedFacts(BaseModel):
    schema_invalid: bool = False
    schema_reason: str | None = None
    capability_supported: bool = True
    capability_reason: str | None = None
    capability_detail: str | None = None
    reference_matches: list[ReferenceMatch] = Field(default_factory=list)
    not_found_fields: list[str] = Field(default_factory=list)
    ambiguous_fields: list[str] = Field(default_factory=list)
    precondition_failures: list[PreconditionSubtype] = Field(default_factory=list)
    precondition_details: dict[str, str] = Field(default_factory=dict)


class PublicEnvelope(BaseModel):
    status: Literal["ok", "ambiguous", "unsupported", "invalid"]
    reason: str | None = None
    detail: str | None = None
    ambiguities: list[dict[str, Any]] = Field(default_factory=list)


class ResolverDecision(BaseModel):
    authority: Authority
    subtype: str | None = None
    outcome: str
    reason: str | None = None
    facts: DerivedFacts
    suppressed_terminal_facts: list[str] = Field(default_factory=list)
    public_envelope: PublicEnvelope
    rule_provenance: list[str] = Field(default_factory=list)
