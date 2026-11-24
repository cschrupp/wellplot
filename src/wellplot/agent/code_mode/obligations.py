"""Bounded request-owned obligations for the canonical semantic engine."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from ...authoring_executor import _omit_undefined, _order_plan_operations, _resolve_clears
from ...authoring_reconciler import AuthoringOperation, AuthoringReconciliationPlan
from ...model.authoring import (
    AnnotationSpec,
    AuthoringRemarkSpec,
    AuthoringSectionSpec,
    CurveBindingSpec,
    CurveFillSpec,
    RasterBindingSpec,
    TrackSpec,
)
from ...semantic_catalog import (
    ExpectedSemanticBinding,
    SemanticCatalogTrustError,
    SemanticPublicationContract,
    SemanticRequestClassification,
    SemanticResolutionEvidence,
    TrustedCatalogRelease,
    load_deployed_catalog_release,
    normalize_request_term,
    revalidate_deployed_catalog_release,
    verify_semantic_publication,
)

if TYPE_CHECKING:
    from ...model.intent import AuthoringDocumentIntent
    from .enrichment import ReportContext, ResolvedSectionContext
    from .semantic_actions import SectionSemanticAction


class ObligationKind(StrEnum):
    """Supported semantic obligation families."""

    EXPLICIT_FIELD = "explicit_field"
    TARGET_REFERENCE = "target_reference"
    PRESERVATION = "preservation"


class ObligationState(StrEnum):
    """State of an explicit request fact."""

    SET = "SET"
    CLEAR = "CLEAR"
    FORBIDDEN = "FORBIDDEN"
    CONFLICTING = "CONFLICTING"
    UNRESOLVED = "UNRESOLVED"


class OwnerKind(StrEnum):
    """Canonical object owner categories."""

    REPORT = "report"
    SECTION = "section"
    TRACK = "track"
    BINDING = "binding"
    SOURCE = "source"
    FILL = "fill"
    ARRAY_TRACK = "array_track"


class RequestCompilationStatus(StrEnum):
    """Bounded result of compiling one authoritative request."""

    EXTRACTION_COMPLETE = "EXTRACTION_COMPLETE"
    CONFLICTING = "CONFLICTING"
    UNRESOLVED_SUPPORTED = "UNRESOLVED_SUPPORTED"
    COVERAGE_FAILURE = "COVERAGE_FAILURE"
    NO_SUPPORTED_SEMANTICS = "NO_SUPPORTED_SEMANTICS"


class ScopeBindingStatus(StrEnum):
    """Result of reconciling requested scopes with planner tasks."""

    BINDING_COMPLETE = "BINDING_COMPLETE"
    MISSING_REQUESTED_SCOPE = "MISSING_REQUESTED_SCOPE"
    DUPLICATE_SCOPE_ASSIGNMENT = "DUPLICATE_SCOPE_ASSIGNMENT"
    UNEXPECTED_SCOPE_ASSIGNMENT = "UNEXPECTED_SCOPE_ASSIGNMENT"
    AMBIGUOUS_SCOPE_RESOLUTION = "AMBIGUOUS_SCOPE_RESOLUTION"
    UNRESOLVED_EXISTING_OBJECT = "UNRESOLVED_EXISTING_OBJECT"


class CollectionSemantics(StrEnum):
    """Merge behavior declared for an ordered semantic collection."""

    ORDERED_ASSOCIATIVE = "ORDERED_ASSOCIATIVE"
    ORDERED_ATOMIC = "ORDERED_ATOMIC"
    SET = "SET"


FieldName = Literal[
    "title",
    "subtitle",
    "target",
    "kind",
    "width_mm",
    "scale_kind",
    "scale_minimum",
    "scale_maximum",
    "channel",
    "label",
    "source",
    "color",
    "alpha",
    "line_width",
    "line_style",
    "scale_reverse",
    "track_scale_kind",
    "track_scale_minimum",
    "track_scale_maximum",
    "track_scale_unit",
    "vertical_main_visible",
    "vertical_secondary_visible",
    "raster_profile",
    "raster_colormap",
    "colorbar_enabled",
    "colorbar_label",
    "colorbar_position",
    "sample_axis_enabled",
    "sample_axis_unit",
    "sample_axis_minimum",
    "sample_axis_maximum",
    "sample_axis_tick_count",
    "sample_axis_source_origin",
    "sample_axis_source_step",
    "service_title",
    "metadata",
    "remark",
    "tail_enabled",
    "page_presentation_allowed",
    "depth_presentation_allowed",
    "forbidden",
    "preservation",
]
RequestFieldName = FieldName | Literal["baseline"]


class RequirementProvenance(BaseModel):
    """One validated span supporting a canonical request requirement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_byte: int = Field(ge=0)
    end_byte: int = Field(gt=0)
    span_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    derivation: Literal[
        "DIRECT",
        "SHARED_CLAUSE",
        "ORDINAL_CLAUSE",
        "PRESERVATION",
        "FORBIDDEN",
    ] = "DIRECT"

    @model_validator(mode="after")
    def validate_span(self) -> RequirementProvenance:
        """Reject empty or reversed request spans."""
        if self.end_byte <= self.start_byte:
            raise ValueError("Requirement provenance span must be non-empty.")
        return self


class ScopeDeclaration(BaseModel):
    """Request-owned symbolic section scope, not a planner assignment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    declaration_id: str = Field(min_length=1)
    kind: Literal["EXISTING_SECTION", "NEW_SECTION"]
    selector_text: str | None = None
    provenance: tuple[RequirementProvenance, ...] = ()
    origin: Literal["REQUEST", "HOST_CONTEXT"] = "REQUEST"


class ScopeDeclarationSet(BaseModel):
    """Ordered request-declared section scopes and their identities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scopes: tuple[ScopeDeclaration, ...] = ()
    collection_semantics: CollectionSemantics = CollectionSemantics.ORDERED_ASSOCIATIVE


class SharedScopeRule(BaseModel):
    """Requirement template applied to declared scopes after binding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selector: Literal["ALL_DECLARED_PASSES", "ALL_DECLARED_SECTIONS"]
    requirement_ids: tuple[str, ...]


class ScopeBindingResult(BaseModel):
    """Bijection between request-declared scopes and canonical tasks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ScopeBindingStatus
    expected_scope_ids: tuple[str, ...] = ()
    assigned_scope_ids: tuple[str, ...] = ()
    task_scope_ids: tuple[str, ...] = ()
    diagnostic_code: str | None = None


class RequestObligation(BaseModel):
    """One typed fact grounded in exact UTF-8 request bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ObligationKind
    owner_kind: OwnerKind
    owner_ref: str = Field(min_length=1)
    field: RequestFieldName
    scope: Literal["task", "global"] = "task"
    value: str | float | int | bool | None = None
    state: ObligationState = ObligationState.SET
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_byte: int = Field(ge=0)
    end_byte: int = Field(gt=0)
    span_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    requirement_id: str = ""
    provenance: tuple[RequirementProvenance, ...] = ()
    scope_key: str | None = None
    slot_key: str | None = None

    @model_validator(mode="after")
    def validate_span(self) -> RequestObligation:
        """Require an ordered span and value/state consistency."""
        if self.end_byte <= self.start_byte:
            raise ValueError("Obligation span must be non-empty.")
        if self.state is ObligationState.UNRESOLVED and self.value is not None:
            raise ValueError("Unresolved obligations cannot assert a value.")
        if not self.provenance:
            object.__setattr__(
                self,
                "provenance",
                (
                    RequirementProvenance(
                        request_sha256=self.request_sha256,
                        start_byte=self.start_byte,
                        end_byte=self.end_byte,
                        span_sha256=self.span_sha256,
                        derivation=(
                            "PRESERVATION"
                            if self.kind is ObligationKind.PRESERVATION
                            else "FORBIDDEN"
                            if self.state is ObligationState.FORBIDDEN
                            else "DIRECT"
                        ),
                    ),
                ),
            )
        if not self.requirement_id:
            object.__setattr__(self, "requirement_id", _requirement_identity(self))
        return self


def _requirement_identity(item: RequestObligation) -> str:
    identity = f"{item.owner_kind}:{item.owner_ref}:{item.field}:{item.start_byte}"
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


class SupportedAnchor(BaseModel):
    """An independent request anchor before obligation construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1)
    start_byte: int = Field(ge=0)
    end_byte: int = Field(gt=0)
    kind: Literal["explicit", "target", "preservation", "presentation", "scope"]
    field: RequestFieldName
    family: str | None = None
    required_fields: tuple[FieldName, ...] = ()


class ReportMetadataBinding(BaseModel):
    """Host-owned resolution of one request-bound metadata fact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact: RequestObligation
    semantic_field: str
    snapshot_id: str | None
    slot_id: str | None = None
    group: Literal["general", "detail"] | None = None
    status: Literal[
        "resolved", "absent", "ambiguous", "conflict", "unsupported", "stale", "uninspected"
    ]
    diagnostic: str


class RequestDependency(BaseModel):
    """Request-grounded relation between an explicit fill target and curve."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predecessor_requirement_id: str = Field(min_length=1)
    dependent_requirement_id: str = Field(min_length=1)
    relation: Literal["FILL_TARGET_SATISFIED_BY"]
    provenance: tuple[RequirementProvenance, ...] = Field(min_length=2, max_length=2)


class CanonicalRequirementSet(BaseModel):
    """Single value-bearing, versioned compilation of request semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    language_version: str = Field(min_length=1)
    requirements: tuple[RequestObligation, ...] = ()
    dependencies: tuple[RequestDependency, ...] = ()
    scopes: ScopeDeclarationSet = ScopeDeclarationSet()
    shared_scope_rules: tuple[SharedScopeRule, ...] = ()
    track_collection: CollectionSemantics = CollectionSemantics.ORDERED_ASSOCIATIVE
    binding_collection: CollectionSemantics = CollectionSemantics.ORDERED_ASSOCIATIVE


class RequestCompilationResult(BaseModel):
    """Compilation output plus independent coverage and bounded status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirements: CanonicalRequirementSet
    anchors: tuple[SupportedAnchor, ...] = ()
    status: RequestCompilationStatus
    diagnostic_codes: tuple[str, ...] = ()


class ValidationIssue(BaseModel):
    """One bounded validation gap tied to a canonical requirement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: str = Field(min_length=1)
    owner_kind: OwnerKind
    owner_ref: str = Field(min_length=1)
    field: RequestFieldName
    slot_key: str | None = None
    code: str = Field(min_length=1)
    expected_value: str | float | int | bool | None = None


class ValidationIssueSet(BaseModel):
    """Stable, ordered collection of unsatisfied canonical requirements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issues: tuple[ValidationIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class SectionObjectBindings:
    """Host-owned proposal indices shared by one section-worker pass."""

    track_indices: tuple[tuple[str, int], ...] = ()
    binding_indices: tuple[tuple[str, str, int | None], ...] = ()

    def track_index(self, owner_ref: str) -> int | None:
        """Return the one proposal track bound to a request owner."""
        return next((index for owner, index in self.track_indices if owner == owner_ref), None)

    def binding_index(self, owner_ref: str, slot_key: str) -> int | None:
        """Return the proposal binding bound to an owner slot, if it exists."""
        return next(
            (
                index
                for owner, slot, index in self.binding_indices
                if owner == owner_ref and slot == slot_key
            ),
            None,
        )


class RepairOperation(BaseModel):
    """One narrowly permitted semantic correction operation.

    This tranche supports only ADD and REPLACE. REMOVE and MOVE remain
    unsupported and are rejected by schema validation, so they cannot
    authorize deletion or reordering.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: str = Field(min_length=1)
    requirement_refs: tuple[str, ...] = ()
    path_prefix: str = Field(min_length=1)
    operation: Literal["ADD", "REPLACE"]
    owner_kind: OwnerKind
    owner_ref: str = Field(min_length=1)
    field: FieldName | None = None
    slot_key: str | None = None
    expected_value: str | float | int | bool | None = None
    permitted_fields: tuple[FieldName, ...] = ()
    order_precondition: tuple[str, ...] = ()
    order_postcondition: tuple[str, ...] = ()


class RepairContract(BaseModel):
    """Immutable correction authority derived from outstanding issues."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    operations: tuple[RepairOperation, ...] = ()
    postconditions: tuple[ValidationIssue, ...] = ()


_REPORT_TITLE_RE = re.compile(
    r"\b(?:rename|set|change)\s+(?:this|the)?\s*report\s+['\"](?P<value>[^'\"]+)['\"]",
    re.IGNORECASE,
)
_REPORT_SUBTITLE_RE = re.compile(
    r"\bset\s+the\s+report\s+subtitle\s+to\s+['\"](?P<value>[^'\"]+)['\"]",
    re.IGNORECASE,
)
_REPORT_METADATA_BLOCK_RE = re.compile(
    r"\bSet\s+the\s+report\s+metadata\s+to\s*:\s*"
    r"(?P<body>.*?)(?=\n\s*\n|\n\s*(?:Include|For each|On)\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_REPORT_SERVICE_TITLES_RE = re.compile(
    r"\bUse\s+these\s+service\s+titles\s*,?\s*in\s+order\s*:\s*"
    r"(?P<body>.*?)(?=\n\s*\n|\n\s*(?:Set|Include|For each|On)\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_REPORT_REMARKS_RE = re.compile(
    r"\bInclude\s+(?:three|the)\s+remarks?\s*:\s*"
    r"(?P<body>.*?)(?=\n\s*\n|\n\s*(?:For each|On)\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_REPORT_TAIL_RE = re.compile(
    r"\b(?:limit\s+the\s+report\s+to|include|retain|keep|preserve)\b"
    r"[^.]*\btail\b",
    re.IGNORECASE,
)
_REPORT_METADATA_LABELS = (
    "drilling and log datum",
    "maximum temperature",
    "bottom temperature",
    "top log interval",
    "bottom log interval",
    "driller depth",
    "logged depth",
    "logged by",
    "witnessed by",
    "fluid density",
    "measured from",
    "logging date",
    "township",
    "latitude",
    "longitude",
    "footage",
    "company",
    "county",
    "country",
    "section",
    "range",
    "field",
    "state",
    "well",
    "fluid",
    "density",
    "run",
    "top interval",
    "bottom interval",
    "kb",
    "gl",
    "df",
)
_REPORT_METADATA_ITEM_RE = re.compile(
    r"(?P<label>"
    + "|".join(
        r"\s+".join(re.escape(part) for part in item.split()) for item in _REPORT_METADATA_LABELS
    )
    + r")"
    r"\s*:?\s+(?P<value>[^;]+)",
    re.IGNORECASE,
)
_ADD_TRACK_RE = re.compile(
    r"\b(?:add|append)\s+(?:a|an)(?:\s+new)?\s+"
    r"(?:(?P<width_prefix>[0-9]+(?:\.[0-9]+)?)\s*mm\s+)?"
    r"(?P<kind>normal|reference|array)\s+track\s+"
    r"(?:titled|named)\s+['\"](?P<title>[^'\"]+)['\"](?P<body>[^.;\n]*)",
    re.IGNORECASE,
)
_SCALAR_TRACK_SHORTHAND_RE = re.compile(
    r"\s*(?i:add|append)\s+(?i:a|an)\s+(?:(?i:exact)\s+)?(?:(?i:physical)\s+)?"
    r"(?P<channel>[A-Z][A-Z0-9_]{1,11})\s+(?i:track)"
    r"(?:\s+(?i:and set its scale to)\s+(?P<kind>(?i:linear|log))\s+"
    r"(?P<minimum>-?[0-9]+(?:\.[0-9]+)?)\s*(?:to|\.\.|[-\u2013\u2014])\s*"
    r"(?P<maximum>-?[0-9]+(?:\.[0-9]+)?)(?:\s+(?P<unit>[A-Za-z][A-Za-z0-9/]*))?)?"
    r"\s*\.?\s*"
)
_EXPLICIT_PHYSICAL_PLOT_RE = re.compile(
    r"\s*(?i:plot|show)\s+(?:(?i:the)\s+)?(?i:physical)\s+"
    r"(?P<channel>[A-Z][A-Z0-9_]{1,11})(?:\s+(?i:channel|curve))?\s*\.?\s*"
)
_CREATE_PHYSICAL_CURVE = (
    r"\s*(?i:create|add)\s+(?:(?i:a|the)\s+)?(?P<channel>[A-Z][A-Z0-9_]{1,11})"
    r"\s+(?i:curve)\b"
)
_CREATE_PHYSICAL_CURVE_RE = re.compile(_CREATE_PHYSICAL_CURVE + r"\s*\.?\s*")
_CURVE_CREATION_START_RE = re.compile(
    r"\s*(?:create|add)\s+(?:a\s+|the\s+)?"
    r"(?:(?!report\b|section\b|track\b)[A-Za-z0-9_]+\s+){0,3}curve\b",
    re.I,
)
_EXPLICIT_BASELINE_SPLIT_RE = re.compile(
    r"\s*(?P<geometry>(?i:split the)\s+(?P<channel>[A-Z][A-Z0-9_]{1,11})"
    r"\s+(?i:curve))\s+(?i:fill at baseline)\s+(?P<baseline>[+-]?\d{1,12}(?:\.\d{1,12})?)\s*\.?\s*"
)
_BASELINE_FILL_REQUEST_RE = re.compile(
    r"(?:\A|[.!?;,\n]|\b(?:and|then)\b)\s*(?:(?:please|also)\s+)*"
    r"(?:fill\b[^.!?;\n]*\bbaseline\b|"
    r"(?:add|apply|create|set|split|plot|show|use|change|replace|update)\b"
    r"[^.!?;:\n]*?(?:\bfill\b[^.!?;\n]*\bbaseline\b|\bbaseline\s+(?:split\s+)?fill\b))",
    re.I,
)
_QUOTED_REQUEST_LITERAL_RE = re.compile(
    r"""(?<!\w)(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'(?!\w)|"""
    r"\u201c[^\u201d]*\u201d|\u2018[^\u2019]*\u2019)",
    re.DOTALL,
)
_TRACK_LINE_RE = re.compile(
    r"\btrack\s+(?P<owner>[A-Za-z0-9_. -]+?)\s*:\s*"
    r"(?P<kind>normal|reference|array)\b[^\n;]*?"
    r"\bwidth\s+(?P<width>[0-9]+(?:\.[0-9]+)?)\s*mm\b",
    re.IGNORECASE,
)
_SECTION_TARGET_RE = re.compile(
    r"\b(?i:in|within)\s+(?i:the\s+)?"
    r"(?P<target>[A-Z][A-Za-z0-9 _-]{1,48}?)\s+section\b",
)
_SECTION_IN_COMMA_TARGET_RE = re.compile(
    r"\b(?i:in|within)\s+(?i:the\s+)?"
    r"(?P<target>[A-Z][A-Za-z0-9 _-]{1,48}?)(?i:(?<!section))\s*,",
)
_SECTION_TO_TARGET_RE = re.compile(
    r"\b(?i:to)\s+(?:(?i:the)\s+)?"
    r"(?P<target>[A-Z][A-Za-z0-9 _\-\u2012\u2013\u2014]{1,48}?)"
    r"(?=\s*(?:[.,;]|$|\b(?:plot|bind|select|use|and)\b))",
)
_SECTION_POSSESSIVE_TRACK_TARGET_RE = re.compile(
    r"\b(?i:on)\s+(?P<target>[A-Z][A-Za-z0-9 _-]{1,48}?)['’]s\s+"
    r"(?:the\s+)?[A-Za-z0-9_-]+\s+track\b",
    re.IGNORECASE,
)
_TRACK_TARGET_RE = re.compile(
    r"\bon\s+(?:the\s+)?(?P<target>[A-Za-z][A-Za-z0-9 _-]{1,48}?)\s+track\b",
    re.IGNORECASE,
)
_CHANNEL_RE = re.compile(
    r"\b(?i:plot|bind|select|use(?:\s+exact)?|channel)\s+"
    r"(?i:the\s+)?(?i:channel\s+)?(?P<channel>[A-Z][A-Z0-9_]{1,11})\b"
    r"(?:\s+curve|\s+binding)?",
)
_SEMANTIC_CHANNEL_AUTHORING_RE = re.compile(
    r"\b(?:plot|bind|select|use(?:\s+exact)?|channel)\s+"
    r"(?:the\s+)?(?P<term>[^.;,\n]+?)\s*(?=[.;,\n]|$)",
    re.IGNORECASE,
)
_TARGET_CHANNEL_RE = re.compile(
    r"\b(?i:on)\s+(?i:the\s+)?(?P<target>[A-Za-z][A-Za-z0-9_ -]{0,32}?)\s*[:,]\s*"
    r"(?i:plot|bind|select|use(?:\s+exact)?)\s+(?i:the\s+)?"
    r"(?P<channel>[A-Z][A-Z0-9_]{1,11})\b",
)
_CHANNEL_LIST_RE = re.compile(
    r"\bchannels?\s+(?P<channels>[A-Z][A-Z0-9_]{1,11}(?:\s*(?:,|and)\s*[A-Z][A-Z0-9_]{1,11})+)"
)
_QUOTED_CHANNEL_RE = re.compile(
    r"\b(?:channel|curve)\s+['\"](?P<channel>[A-Z][A-Z0-9_]{1,11})['\"]"
)
_SOURCE_RE = re.compile(
    r"\b(?:from|source(?:\s+file)?)\s+['\"]?"
    r"(?P<source>[A-Za-z0-9_./ -]+\.(?:las|dlis))['\"]?\b",
    re.IGNORECASE,
)
_SCALE_RE = re.compile(
    r"\b(?:change|set)\s+(?:the\s+)?(?P<owner>[A-Za-z][A-Za-z0-9 _-]*?)\s+"
    r"(?:curve\s+)?scale\s+to\s+(?P<kind>linear|log)[^0-9-]*"
    r"(?P<minimum>-?[0-9]+(?:\.[0-9]+)?)\s*(?:to|\.\.)\s*"
    r"(?P<maximum>-?[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_SCALE_CLAUSE_RE = re.compile(
    r"\b(?:with|using|to)\s+(?:a\s+)?(?P<kind>linear|log)\s+scale\s+from\s+"
    r"(?P<minimum>-?[0-9]+(?:\.[0-9]+)?)\s*(?:to|\.\.)\s*"
    r"(?P<maximum>-?[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_SCALE_TARGET_RE = re.compile(
    r"\b(?:change|set)\s+(?:the\s+)?"
    r"(?P<target>[A-Za-z][A-Za-z0-9 _-]*?)\s+(?:curve|binding)\s+"
    r"(?:scale\s+)?(?:to|with)\s+(?:a\s+)?(?:linear|log(?:arithmic)?)\b",
    re.IGNORECASE,
)
_SCALE_PREFIX_RANGE_RE = re.compile(
    r"\b(?:with|using|to)\s+(?:a\s+)?(?P<kind>linear|log(?:arithmic)?)\s+"
    r"(?P<minimum>-?[0-9]+(?:\.[0-9]+)?)\s*"
    r"(?:to|\.\.|[\u2012\u2013\u2014-])\s*"
    r"(?P<maximum>-?[0-9]+(?:\.[0-9]+)?)\s+scale\b",
    re.IGNORECASE,
)
_FILL_COLOR_RE = re.compile(r"\busing\s+(?P<color>#[0-9a-f]{6})\b", re.IGNORECASE)
_FILL_ALPHA_RE = re.compile(r"\bat\s+(?P<alpha>[0-9]+(?:\.[0-9]+)?)%\s+opacity\b", re.IGNORECASE)
_REQUEST_TRACK_BLOCK_RE = re.compile(
    r"^\s*On\s+(?P<track>[^:,\n]+?)\s*(?::|,)\s*",
    re.IGNORECASE | re.MULTILINE,
)
_CURVE_PRESENTATION_RE = re.compile(
    r"(?P<channel>[A-Z][A-Z0-9_]*)\s*(?:→|->)\s*"
    r"(?:\"(?P<label_quoted>[^\"]+)\"|(?P<label_plain>.*?))\s*,\s*"
    r"(?P<kind>linear|log)\s+(?P<minimum>-?[0-9]+(?:\.[0-9]+)?)\.\."
    r"(?P<maximum>-?[0-9]+(?:\.[0-9]+)?)(?P<reverse>\s+reversed)?\s*,\s*"
    r"(?P<color>#[0-9A-Fa-f]{6})(?:\s+(?P<line_style>dashed|dotted))?\s*,\s*"
    r"width\s+(?P<line_width>[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_ORDINAL_PRESENTATION_RE = re.compile(
    r"The\s+(?P<ordinal>first|second|third|fourth)\s+is\s+"
    r"(?P<kind>linear|log)\s+(?P<minimum>-?[0-9]+(?:\.[0-9]+)?)\.\."
    r"(?P<maximum>-?[0-9]+(?:\.[0-9]+)?)(?P<reverse>\s+reversed)?\s*,\s*"
    r"(?P<color>#[0-9A-Fa-f]{6})(?:\s+(?P<line_style>dashed|dotted))?\s*,\s*"
    r"width\s+(?P<line_width>[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_SHARED_LABEL_RE = re.compile(
    r"\b(?:both|all)\s+labels?\s+are\s+"
    r"(?:\"(?P<quoted>[^\"]+)\"|'(?P<single>[^']+)'|(?P<plain>[^.,\n]+))",
    re.IGNORECASE,
)
_RASTER_LABEL_REQUEST_RE = re.compile(
    r"\braster\s+label(?:led|ed)\s+"
    r"(?:\"(?P<quoted>[^\"]+)\"|'(?P<single>[^']+)'|(?P<plain>[^.,\n]+))",
    re.IGNORECASE,
)
_SAMPLE_AXIS_RE = re.compile(
    r"sample\s+axis\s+enabled\s+in\s+(?P<unit>[A-Za-z]+)\s+from\s+"
    r"(?P<minimum>-?[0-9]+(?:\.[0-9]+)?)\s+to\s+"
    r"(?P<maximum>-?[0-9]+(?:\.[0-9]+)?)\s+with\s+(?P<ticks>[0-9]+)\s+ticks,\s+"
    r"source\s+origin\s+(?P<origin>-?[0-9]+(?:\.[0-9]+)?)\s+and\s+step\s+"
    r"(?P<step>-?[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_ARRAY_SCALE_RE = re.compile(
    r"linear\s+track\s+scale\s+(?P<minimum>-?[0-9]+(?:\.[0-9]+)?)\.\."
    r"(?P<maximum>-?[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_SCOPE_NAME_RE = re.compile(
    r"\b(?P<name>Main\s+Pass|Repeat\s+Pass)\b",
    re.IGNORECASE,
)
_NAMED_TRACK_LAYOUT_RE = re.compile(
    r"(?P<track>[A-Za-z][A-Za-z0-9_-]*)\s*=\s*"
    r"(?P<kind>normal|reference|array)\s+"
    r"(?P<width>[0-9]+(?:\.[0-9]+)?)\s*mm\b",
    re.IGNORECASE,
)
_PROFILE_RE = re.compile(r"\bprofile\s+(?P<value>[a-z_]+)", re.IGNORECASE)
_COLORMAP_RE = re.compile(r"\b(?P<value>gray_r)\b", re.IGNORECASE)
_COLORBAR_RE = re.compile(
    r"colorbar\s+(?P<enabled>enabled|disabled)\s+with\s+label\s+"
    r"(?P<label>[A-Za-z][A-Za-z ]*?)\s+in\s+the\s+(?P<position>header|right)",
    re.IGNORECASE,
)
_GRID_HIDE_RE = re.compile(
    r"hide\s+both\s+vertical\s+main\s+and\s+secondary\s+grid(?:\s+lines)?",
    re.IGNORECASE,
)
_PRESENTATION_ANCHOR_PATTERNS = (
    (
        "curve_presentation",
        re.compile(
            r"\b[A-Z][A-Z0-9_]*\s*(?:→|->)\s*.+?,\s*"
            r"(?:linear|log)\s+-?[0-9]+(?:\.[0-9]+)?\.\."
            r"-?[0-9]+(?:\.[0-9]+)?.*?#(?:[0-9a-f]{6}).*?"
            r"\bwidth\s+[0-9]+(?:\.[0-9]+)?",
            re.I,
        ),
    ),
    (
        "shared_binding_label",
        re.compile(r"\b(?:both|all)\s+labels?\s+are\s+(?:\"[^\"]+\"|'[^']+'|[^.,\n]+)", re.I),
    ),
    (
        "raster_label",
        re.compile(r"\braster\s+label(?:led|ed)\s+(?:\"[^\"]+\"|'[^']+'|[^.,\n]+)", re.I),
    ),
    (
        "sample_axis",
        re.compile(
            r"\bsample\s+axis\s+enabled\b.*?\bsource\s+origin\s+"
            r"-?[0-9]+(?:\.[0-9]+)?\s+and\s+step\s+-?[0-9]+(?:\.[0-9]+)?",
            re.I,
        ),
    ),
    (
        "array_scale",
        re.compile(r"\blinear\s+track\s+scale\s+-?[0-9.]+\.\.-?[0-9.]+", re.I),
    ),
    (
        "colorbar",
        re.compile(
            r"\bcolorbar\s+(?:enabled|disabled)\s+with\s+label\b.*?\b(header|right)\b", re.I
        ),
    ),
    (
        "grid",
        re.compile(r"\bhide\s+both\s+vertical\s+main\s+and\s+secondary\s+grid", re.I),
    ),
)

# Keep coverage broader and structurally independent from the semantic
# extraction templates.  An explicit request fact must not disappear merely
# because the semantic parser does not recognize its sentence form.
_INDEPENDENT_ANCHOR_PATTERNS = (
    ("explicit", "subtitle", _REPORT_SUBTITLE_RE),
    (
        "explicit",
        "title",
        re.compile(r"\b(?:rename|set|change)\s+(?:this|the)?\s*report\s+['\"][^'\"]+['\"]", re.I),
    ),
    (
        "explicit",
        "kind",
        re.compile(r"\b(?:add|append)\b[^.;\n]*?\b(?:normal|reference|array)\s+track\b", re.I),
    ),
    (
        "explicit",
        "title",
        re.compile(
            r"\b(?:add|append)\b[^.;\n]*?\b(?:named|titled)\s+['\"][^'\"]+['\"]",
            re.I,
        ),
    ),
    ("target", "target", _SCALE_RE),
    ("target", "target", _SCALE_TARGET_RE),
    (
        "explicit",
        "title",
        re.compile(
            r"\bTrack\s+[A-Za-z0-9_. -]+?\s*:\s*"
            r"(?:normal|reference|array)\b[^\n;]*?"
            r"\bwidth\s+[0-9]+(?:\.[0-9]+)?\s*mm\b",
            re.I,
        ),
    ),
    (
        "explicit",
        "width_mm",
        re.compile(
            r"\b(?:add|append)\s+(?:a|an)(?:\s+new)?\s+"
            r"[0-9]+(?:\.[0-9]+)?\s*mm\b",
            re.I,
        ),
    ),
    (
        "explicit",
        "width_mm",
        re.compile(r"\bwidth\s+[0-9]+(?:\.[0-9]+)?\s*mm\b", re.I),
    ),
    (
        "explicit",
        "width_mm",
        re.compile(
            r"\b[A-Za-z][A-Za-z0-9_-]*\s*=\s*"
            r"(?:normal|reference|array)\s+[0-9]+(?:\.[0-9]+)?\s*mm\b",
            re.I,
        ),
    ),
    (
        "target",
        "target",
        re.compile(
            r"\b(?i:in|within)\s+(?:(?i:the)\s+)?"
            r"[A-Z][A-Za-z0-9 _-]{1,48}\s+section\b"
            r"|\b(?i:to)\s+(?:(?i:the)\s+)?"
            r"[A-Z][A-Za-z0-9 _-]{1,48}"
            r"(?=\s*(?:[.,;]|$|\b(?:plot|bind|select|use|and)\b))",
        ),
    ),
    (
        "explicit",
        "channel",
        re.compile(
            r"\b(?i:plot|bind|select|use(?:\s+exact)?)\s+"
            r"(?:(?i:the)\s+)?(?:(?i:channel)\s+)?[A-Z][A-Z0-9_]{1,11}\b",
        ),
    ),
    (
        "explicit",
        "scale_kind",
        re.compile(
            r"\b(?:linear|log(?:arithmic)?)\s+(?:[0-9]+(?:\.[0-9]+)?\s*(?:to|\.\.|[\u2012\u2013\u2014-])\s*[0-9]+(?:\.[0-9]+)?\s+scale|scale\s+from\s+-?[0-9]+(?:\.[0-9]+)?\s+to\s+-?[0-9]+(?:\.[0-9]+)?)\b",
            re.I,
        ),
    ),
    (
        "explicit",
        "scale_minimum",
        re.compile(
            r"\b(?:linear|log(?:arithmic)?)\s+-?[0-9]+(?:\.[0-9]+)?\s*(?:to|\.\.|[\u2012\u2013\u2014-])\s*[0-9]+(?:\.[0-9]+)?\s+scale\b",
            re.I,
        ),
    ),
    (
        "explicit",
        "scale_maximum",
        re.compile(
            r"\b(?:linear|log(?:arithmic)?)\s+[0-9]+(?:\.[0-9]+)?\s*(?:to|\.\.|[\u2012\u2013\u2014-])\s*-?[0-9]+(?:\.[0-9]+)?\s+scale\b",
            re.I,
        ),
    ),
    ("explicit", "source", _SOURCE_RE),
    ("explicit", "color", _FILL_COLOR_RE),
    ("explicit", "alpha", _FILL_ALPHA_RE),
)


def _request_identity(request: str) -> tuple[bytes, str]:
    """Return exact request bytes and their identity."""
    data = request.encode("utf-8")
    return data, hashlib.sha256(data).hexdigest()


def _byte_offset(request: str, character_offset: int) -> int:
    """Convert a character offset to a UTF-8 byte offset."""
    return len(request[:character_offset].encode("utf-8"))


def _state_for(request: str, character_start: int) -> ObligationState:
    """Recognize only local explicit negation."""
    prefix = request[max(0, character_start - 32) : character_start].casefold()
    if re.search(r"(?:\bnot|\bwithout|\bforbid|\bdo not|\bdon't)\s*$", prefix):
        return ObligationState.FORBIDDEN
    return ObligationState.SET


def _make_obligation(
    *,
    request: str,
    request_sha256: str,
    match: re.Match[str],
    kind: ObligationKind,
    owner_kind: OwnerKind,
    owner_ref: str,
    field: RequestFieldName,
    value: str | float | None,
    scope: Literal["task", "global"] = "task",
) -> RequestObligation:
    """Build an obligation with real UTF-8 byte offsets."""
    char_start, char_end = match.span()
    start = _byte_offset(request, char_start)
    end = _byte_offset(request, char_end)
    data = request.encode("utf-8")[start:end]
    return RequestObligation(
        kind=kind,
        owner_kind=owner_kind,
        owner_ref=owner_ref.strip(),
        field=field,
        scope=scope,
        value=value.strip() if isinstance(value, str) else value,
        state=_state_for(request, char_start),
        request_sha256=request_sha256,
        start_byte=start,
        end_byte=end,
        span_sha256=hashlib.sha256(data).hexdigest(),
    )


def _append_conflicts(obligations: list[RequestObligation]) -> tuple[RequestObligation, ...]:
    """Mark contradictory values instead of choosing one."""
    grouped: dict[tuple[OwnerKind, str, str, str | None], set[object]] = {}
    forbidden: set[tuple[OwnerKind, str, str, str | None]] = set()
    for item in obligations:
        key = (item.owner_kind, item.owner_ref, item.field, item.slot_key)
        if item.state is ObligationState.SET:
            grouped.setdefault(key, set()).add(item.value)
        elif item.state is ObligationState.FORBIDDEN:
            forbidden.add(key)
    conflicts = {key for key, values in grouped.items() if len(values) > 1 or key in forbidden}
    return tuple(
        item.model_copy(update={"state": ObligationState.CONFLICTING})
        if (item.owner_kind, item.owner_ref, item.field, item.slot_key) in conflicts
        else item
        for item in obligations
    )


def _patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    """Return the semantic extraction patterns."""
    return (
        ("explicit", _REPORT_TITLE_RE),
        ("explicit", _ADD_TRACK_RE),
        ("explicit", _TRACK_LINE_RE),
        ("target", _SECTION_TARGET_RE),
        ("target", _SECTION_IN_COMMA_TARGET_RE),
        ("target", _SECTION_TO_TARGET_RE),
        ("target", _SECTION_POSSESSIVE_TRACK_TARGET_RE),
        ("target", _TRACK_TARGET_RE),
        ("explicit", _TARGET_CHANNEL_RE),
        ("explicit", _CHANNEL_RE),
        ("explicit", _CHANNEL_LIST_RE),
        ("explicit", _QUOTED_CHANNEL_RE),
        ("explicit", _SOURCE_RE),
        ("explicit", _SCALE_RE),
        ("explicit", _SCALE_CLAUSE_RE),
        ("target", _SCALE_TARGET_RE),
        ("explicit", _SCALE_PREFIX_RANGE_RE),
        ("explicit", _FILL_COLOR_RE),
        ("explicit", _FILL_ALPHA_RE),
    )


def extract_supported_anchors(request: str) -> tuple[SupportedAnchor, ...]:
    """Return the independent, bounded anchor inventory used for coverage."""
    data = request.encode("utf-8")
    anchors: list[SupportedAnchor] = []
    joint = _C2_REQUEST_RE.fullmatch(request)
    if joint is not None:
        plot_start = joint.end("section_prefix") if joint["section_prefix"] else 0
        plot = _EXPLICIT_PHYSICAL_PLOT_RE.fullmatch(request[plot_start : joint.start("sequence")])
        fill_start = joint.start("geometry")
        fill = _EXPLICIT_BASELINE_SPLIT_RE.fullmatch(request[fill_start:])
        if plot is None or fill is None:
            raise ValueError("C2 lacks independent plot and fill anchors.")
        spans = [
            ("channel", "explicit", None, *(plot_start + i for i in plot.span("channel"))),
            ("target", "explicit", None, *(fill_start + i for i in fill.span("channel"))),
            ("kind", "explicit", None, *(fill_start + i for i in fill.span("geometry"))),
            ("baseline", "explicit", None, *(fill_start + i for i in fill.span("baseline"))),
        ]
        if joint["selector"] is not None:
            clause = _SECTION_TARGET_RE.search(request)
            scope = _SCOPE_NAME_RE.search(request)
            if clause is None or scope is None:
                raise ValueError("C2 lacks independent named scope anchors.")
            spans.extend(
                [
                    ("target", "target", "section_scope_target", *clause.span()),
                    ("target", "scope", "section_scope", *scope.span()),
                ]
            )
        return tuple(
            SupportedAnchor(
                text=request[start:end],
                start_byte=_byte_offset(request, start),
                end_byte=_byte_offset(request, end),
                field=field,
                kind=kind,
                family=family,
            )
            for field, kind, family, start, end in spans
        )
    split = _EXPLICIT_BASELINE_SPLIT_RE.fullmatch(request)
    create_curve = _CREATE_PHYSICAL_CURVE_RE.fullmatch(request)
    if split or create_curve:
        fields: tuple[tuple[str | int, RequestFieldName], ...] = (
            (("channel", "target"), (0, "kind"), ("baseline", "baseline"))
            if split
            else (("channel", "channel"),)
        )
        match = split or create_curve
        assert match is not None
        for group, field in fields:
            start, end = match.span(group)
            anchors.append(
                SupportedAnchor(
                    text=request[start:end],
                    start_byte=_byte_offset(request, start),
                    end_byte=_byte_offset(request, end),
                    kind="explicit",
                    field=field,
                )
            )
        return tuple(anchors)
    for kind, field, pattern in _INDEPENDENT_ANCHOR_PATTERNS:
        for match in pattern.finditer(request):
            start = _byte_offset(request, match.start())
            end = _byte_offset(request, match.end())
            anchors.append(
                SupportedAnchor(
                    text=data[start:end].decode("utf-8"),
                    start_byte=start,
                    end_byte=end,
                    kind=kind,  # type: ignore[arg-type]
                    field=field,  # type: ignore[arg-type]
                )
            )
    family_fields: dict[str, tuple[FieldName, ...]] = {
        "curve_presentation": (
            "channel",
            "label",
            "scale_kind",
            "scale_minimum",
            "scale_maximum",
            "scale_reverse",
            "color",
            "line_width",
            "line_style",
        ),
        "shared_binding_label": ("label",),
        "raster_label": ("label",),
        "sample_axis": (
            "sample_axis_enabled",
            "sample_axis_unit",
            "sample_axis_minimum",
            "sample_axis_maximum",
            "sample_axis_tick_count",
            "sample_axis_source_origin",
            "sample_axis_source_step",
        ),
        "array_scale": (
            "track_scale_kind",
            "track_scale_minimum",
            "track_scale_maximum",
        ),
        "colorbar": ("colorbar_enabled", "colorbar_label", "colorbar_position"),
        "grid": ("vertical_main_visible", "vertical_secondary_visible"),
    }
    for family, pattern in _PRESENTATION_ANCHOR_PATTERNS:
        for match in pattern.finditer(request):
            start = _byte_offset(request, match.start())
            end = _byte_offset(request, match.end())
            text = data[start:end].decode("utf-8")
            for field in family_fields[family]:
                anchors.append(
                    SupportedAnchor(
                        text=text,
                        start_byte=start,
                        end_byte=end,
                        kind="presentation",
                        field=field,
                        family=family,
                        required_fields=family_fields[family],
                    )
                )
    for match in _SCOPE_NAME_RE.finditer(request):
        start = _byte_offset(request, match.start())
        end = _byte_offset(request, match.end())
        anchors.append(
            SupportedAnchor(
                text=data[start:end].decode("utf-8"),
                start_byte=start,
                end_byte=end,
                kind="scope",
                field="target",
                family="section_scope",
            )
        )
    for block in _REPORT_METADATA_BLOCK_RE.finditer(request):
        body_start = block.start("body")
        for match in _REPORT_METADATA_ITEM_RE.finditer(block.group("body")):
            span = _re_span_match(
                request,
                body_start + match.start(),
                body_start + match.end(),
            )
            start, end = span.span()
            anchors.append(
                SupportedAnchor(
                    text=request[start:end],
                    start_byte=_byte_offset(request, start),
                    end_byte=_byte_offset(request, end),
                    kind="explicit",
                    field="metadata",
                    family="report_metadata",
                )
            )
    for block in _REPORT_SERVICE_TITLES_RE.finditer(request):
        body_start = block.start("body")
        for match in re.finditer(r'"(?P<value>[^"]+)"', block.group("body")):
            span = _re_span_match(
                request,
                body_start + match.start("value"),
                body_start + match.end("value"),
            )
            start, end = span.span()
            anchors.append(
                SupportedAnchor(
                    text=request[start:end],
                    start_byte=_byte_offset(request, start),
                    end_byte=_byte_offset(request, end),
                    kind="explicit",
                    field="service_title",
                    family="report_service_title",
                )
            )
    for block in _REPORT_REMARKS_RE.finditer(request):
        body_start = block.start("body")
        for match in re.finditer(
            r"(?:^|\s)\d+\.\s*(?P<title>[^—\n]+?)\s+—\s*(?P<text>.*?)(?=\s+\d+\.\s|\Z)",
            block.group("body"),
            re.DOTALL,
        ):
            span = _re_span_match(
                request,
                body_start + match.start(),
                body_start + match.end(),
            )
            start, end = span.span()
            anchors.append(
                SupportedAnchor(
                    text=request[start:end],
                    start_byte=_byte_offset(request, start),
                    end_byte=_byte_offset(request, end),
                    kind="explicit",
                    field="remark",
                    family="report_remark",
                )
            )
    for match in _REPORT_TAIL_RE.finditer(request):
        start, end = match.span()
        anchors.append(
            SupportedAnchor(
                text=request[start:end],
                start_byte=_byte_offset(request, start),
                end_byte=_byte_offset(request, end),
                kind="explicit",
                field="tail_enabled",
                family="report_tail",
            )
        )
    return tuple(sorted(anchors, key=lambda item: (item.start_byte, item.end_byte, item.kind)))


def extract_supported_obligations(request: str) -> tuple[RequestObligation, ...]:
    """Extract bounded explicit facts without promoting ordinary prose."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Authoritative request must be non-empty.")
    _, request_sha256 = _request_identity(request)
    # These complete clauses cannot authorize a subset of a more complex request.
    shorthand = _SCALAR_TRACK_SHORTHAND_RE.fullmatch(request)
    if shorthand is not None:
        return _scalar_track_shorthand_obligations(request, request_sha256, shorthand)
    physical = _EXPLICIT_PHYSICAL_PLOT_RE.fullmatch(request) or _CREATE_PHYSICAL_CURVE_RE.fullmatch(
        request
    )
    if physical is not None:
        return (
            _make_obligation(
                request=request,
                request_sha256=request_sha256,
                match=physical,
                kind=ObligationKind.EXPLICIT_FIELD,
                owner_kind=OwnerKind.BINDING,
                owner_ref="request",
                field="channel",
                value=physical.group("channel"),
            ),
        )
    split = _EXPLICIT_BASELINE_SPLIT_RE.fullmatch(request)
    if split is not None:
        facts: tuple[tuple[str | int, RequestFieldName, str | float], ...] = (
            ("channel", "target", split["channel"]),
            (0, "kind", "baseline_split"),
            ("baseline", "baseline", float(split["baseline"])),
        )
        return tuple(
            _make_obligation(
                request=request,
                request_sha256=request_sha256,
                match=_re_span_match(request, *split.span(group)),
                kind=ObligationKind.TARGET_REFERENCE
                if field == "target"
                else ObligationKind.EXPLICIT_FIELD,
                owner_kind=OwnerKind.FILL,
                owner_ref=split["channel"],
                field=field,
                value=value,
            )
            for group, field, value in facts
        )
    obligations: list[RequestObligation] = []
    for report_field, pattern in (("title", _REPORT_TITLE_RE), ("subtitle", _REPORT_SUBTITLE_RE)):
        for match in pattern.finditer(request):
            obligations.append(
                _make_obligation(
                    request=request,
                    request_sha256=request_sha256,
                    match=match,
                    kind=ObligationKind.EXPLICIT_FIELD,
                    owner_kind=OwnerKind.REPORT,
                    owner_ref="report",
                    field=report_field,
                    value=match.group("value"),
                )
            )
    for pattern in (_ADD_TRACK_RE, _TRACK_LINE_RE):
        for match in pattern.finditer(request):
            owner_text = match.groupdict().get("title") or match.group("owner")
            owner = (
                _normalize_requirement_key(owner_text) if pattern is _TRACK_LINE_RE else owner_text
            )
            declared_title = match.groupdict().get("title")
            if declared_title is None and pattern is _TRACK_LINE_RE:
                declared_title = owner_text
            if declared_title:
                obligations.append(
                    _make_obligation(
                        request=request,
                        request_sha256=request_sha256,
                        match=match,
                        kind=ObligationKind.EXPLICIT_FIELD,
                        owner_kind=OwnerKind.TRACK,
                        owner_ref=owner,
                        field="title",
                        value=declared_title,
                    )
                )
            obligations.append(
                _make_obligation(
                    request=request,
                    request_sha256=request_sha256,
                    match=match,
                    kind=ObligationKind.EXPLICIT_FIELD,
                    owner_kind=OwnerKind.TRACK,
                    owner_ref=owner,
                    field="kind",
                    value=match.group("kind").lower(),
                )
            )
            width = re.search(r"\b(?P<width>[0-9]+(?:\.[0-9]+)?)\s*mm\b", match.group(0), re.I)
            if width:
                obligations.append(
                    _make_obligation(
                        request=request,
                        request_sha256=request_sha256,
                        match=match,
                        kind=ObligationKind.EXPLICIT_FIELD,
                        owner_kind=OwnerKind.TRACK,
                        owner_ref=owner,
                        field="width_mm",
                        value=float(width.group("width")),
                    )
                )
    for match in _NAMED_TRACK_LAYOUT_RE.finditer(request):
        owner = _normalize_requirement_key(match.group("track"))
        for field, value in (
            ("kind", match.group("kind").casefold()),
            ("width_mm", float(match.group("width"))),
        ):
            obligations.append(
                _make_obligation(
                    request=request,
                    request_sha256=request_sha256,
                    match=match,
                    kind=ObligationKind.EXPLICIT_FIELD,
                    owner_kind=OwnerKind.TRACK,
                    owner_ref=owner,
                    field=field,
                    value=value,
                )
            )
    for pattern in (
        _SECTION_TARGET_RE,
        _SECTION_IN_COMMA_TARGET_RE,
        _SECTION_TO_TARGET_RE,
        _SECTION_POSSESSIVE_TRACK_TARGET_RE,
        _TRACK_TARGET_RE,
    ):
        for match in pattern.finditer(request):
            target = match.group("target").strip()
            obligations.append(
                _make_obligation(
                    request=request,
                    request_sha256=request_sha256,
                    match=match,
                    kind=ObligationKind.TARGET_REFERENCE,
                    owner_kind=(
                        OwnerKind.TRACK if pattern is _TRACK_TARGET_RE else OwnerKind.SECTION
                    ),
                    owner_ref=target,
                    field="target",
                    value=target,
                )
            )
    for pattern in (_SCALE_RE, _SCALE_TARGET_RE):
        for match in pattern.finditer(request):
            target = match.groupdict().get("target") or match.groupdict().get("owner")
            if not target or target.strip().casefold() == "request":
                continue
            obligations.append(
                _make_obligation(
                    request=request,
                    request_sha256=request_sha256,
                    match=match,
                    kind=ObligationKind.TARGET_REFERENCE,
                    owner_kind=OwnerKind.BINDING,
                    owner_ref=target.strip(),
                    field="target",
                    value=target.strip(),
                )
            )
    targeted_channel_spans: set[tuple[int, int]] = set()
    for match in _TARGET_CHANNEL_RE.finditer(request):
        targeted_channel_spans.add(match.span())
        obligations.append(
            _make_obligation(
                request=request,
                request_sha256=request_sha256,
                match=match,
                kind=ObligationKind.EXPLICIT_FIELD,
                owner_kind=OwnerKind.BINDING,
                owner_ref=match.group("target").strip(),
                field="channel",
                value=match.group("channel").upper(),
            )
        )
    for pattern in (_CHANNEL_RE, _QUOTED_CHANNEL_RE):
        for match in pattern.finditer(request):
            if any(start <= match.start() < end for start, end in targeted_channel_spans):
                continue
            obligations.append(
                _make_obligation(
                    request=request,
                    request_sha256=request_sha256,
                    match=match,
                    kind=ObligationKind.EXPLICIT_FIELD,
                    owner_kind=OwnerKind.BINDING,
                    owner_ref="request",
                    field="channel",
                    value=match.group("channel").upper(),
                )
            )
    for match in _CHANNEL_LIST_RE.finditer(request):
        for channel in re.findall(r"[A-Z][A-Z0-9_]{1,11}", match.group("channels")):
            obligations.append(
                _make_obligation(
                    request=request,
                    request_sha256=request_sha256,
                    match=match,
                    kind=ObligationKind.EXPLICIT_FIELD,
                    owner_kind=OwnerKind.BINDING,
                    owner_ref="request",
                    field="channel",
                    value=channel,
                    scope="global",
                )
            )
    for match in _SOURCE_RE.finditer(request):
        obligations.append(
            _make_obligation(
                request=request,
                request_sha256=request_sha256,
                match=match,
                kind=ObligationKind.EXPLICIT_FIELD,
                owner_kind=OwnerKind.SOURCE,
                owner_ref="request",
                field="source",
                value=match.group("source"),
            )
        )
    for pattern in (_SCALE_RE, _SCALE_CLAUSE_RE, _SCALE_PREFIX_RANGE_RE):
        for match in pattern.finditer(request):
            owner = match.groupdict().get("owner") or "request"
            scale_kind = match.group("kind").lower()
            if scale_kind == "logarithmic":
                scale_kind = "log"
            for field, value in (
                ("scale_kind", scale_kind),
                ("scale_minimum", float(match.group("minimum"))),
                ("scale_maximum", float(match.group("maximum"))),
            ):
                obligations.append(
                    _make_obligation(
                        request=request,
                        request_sha256=request_sha256,
                        match=match,
                        kind=ObligationKind.EXPLICIT_FIELD,
                        owner_kind=OwnerKind.BINDING,
                        owner_ref=owner.strip(),
                        field=field,
                        value=value,  # type: ignore[arg-type]
                    )
                )
    for pattern, field in ((_FILL_COLOR_RE, "color"), (_FILL_ALPHA_RE, "alpha")):
        for match in pattern.finditer(request):
            value: str | float = match.group(field).lower()
            if field == "alpha":
                value = float(value) / 100
            obligations.append(
                _make_obligation(
                    request=request,
                    request_sha256=request_sha256,
                    match=match,
                    kind=ObligationKind.EXPLICIT_FIELD,
                    owner_kind=OwnerKind.FILL,
                    owner_ref="request",
                    field=field,
                    value=value,  # type: ignore[arg-type]
                )
            )
    obligations.extend(_extract_presentation_obligations(request, request_sha256))
    obligations.extend(_extract_report_obligations(request, request_sha256))
    obligations.extend(
        _extract_reviewed_semantic_channel_obligation(request, request_sha256, obligations)
    )
    return _append_conflicts(obligations)


def _scalar_track_shorthand_obligations(
    request: str, request_sha256: str, match: re.Match[str]
) -> tuple[RequestObligation, ...]:
    """Bind one literal curve slot and its explicitly requested track scale."""
    channel = match.group("channel")
    fields: list[tuple[OwnerKind, FieldName, str | float]] = [
        (OwnerKind.TRACK, "title", channel),
        (OwnerKind.TRACK, "kind", "normal"),
        (OwnerKind.BINDING, "channel", channel),
    ]
    if match.group("kind") is not None:
        fields.extend(
            (
                (OwnerKind.TRACK, "track_scale_kind", match.group("kind").casefold()),
                (OwnerKind.TRACK, "track_scale_minimum", float(match.group("minimum"))),
                (OwnerKind.TRACK, "track_scale_maximum", float(match.group("maximum"))),
            )
        )
        if match.group("unit") is not None:
            fields.append((OwnerKind.TRACK, "track_scale_unit", match.group("unit")))
    return tuple(
        _make_obligation(
            request=request,
            request_sha256=request_sha256,
            match=match,
            kind=ObligationKind.EXPLICIT_FIELD,
            owner_kind=owner_kind,
            owner_ref=channel,
            field=field,
            value=value,
        )
        for owner_kind, field, value in fields
    )


def _extract_reviewed_semantic_channel_obligation(
    request: str,
    request_sha256: str,
    existing: Sequence[RequestObligation],
) -> list[RequestObligation]:
    """Compile one reviewed scientist term without resolving its physical channel."""
    scale_only_fields = {
        "scale_kind",
        "scale_minimum",
        "scale_maximum",
        "scale_reverse",
    }
    if existing and all(
        (item.owner_kind is OwnerKind.BINDING and item.field in scale_only_fields)
        or (item.owner_kind is OwnerKind.BINDING and item.field == "target")
        or (item.owner_kind is OwnerKind.SECTION and item.field == "target")
        or item.owner_kind is OwnerKind.FILL
        for item in existing
    ):
        return []
    if any(item.owner_kind is OwnerKind.BINDING and item.field == "channel" for item in existing):
        return []
    try:
        release = load_deployed_catalog_release()
    except SemanticCatalogTrustError:
        return []
    matches: list[tuple[re.Match[str], str]] = []
    for rule in release.catalog.request_term_rules:
        if rule.status != "reviewed":
            continue
        for term in rule.terms:
            for match in _SEMANTIC_CHANNEL_AUTHORING_RE.finditer(request):
                requested_term = match.group("term")
                if normalize_request_term(requested_term) == normalize_request_term(term):
                    matches.append((match, requested_term.strip()))
    if len(matches) != 1:
        return []
    match, term = matches[0]
    start = _byte_offset(request, match.start("term"))
    end = _byte_offset(request, match.end("term"))
    request_bytes = request.encode("utf-8")
    span = request_bytes[start:end]
    return [
        RequestObligation(
            kind=ObligationKind.EXPLICIT_FIELD,
            owner_kind=OwnerKind.BINDING,
            owner_ref="request",
            field="channel",
            value=term,
            request_sha256=request_sha256,
            start_byte=start,
            end_byte=end,
            span_sha256=hashlib.sha256(span).hexdigest(),
            slot_key="request.binding.1",
        )
    ]


def _extract_report_obligations(
    request: str,
    request_sha256: str,
) -> list[RequestObligation]:
    """Compile report metadata, ordered services, remarks, and preservation flags."""
    result: list[RequestObligation] = []
    metadata_matches: list[re.Match[str]] = []
    block_spans: list[tuple[int, int]] = []
    for block in _REPORT_METADATA_BLOCK_RE.finditer(request):
        body_start = block.start("body")
        block_spans.append(block.span("body"))
        metadata_matches.extend(
            _re_span_match(
                request,
                body_start + match.start(),
                body_start + match.end(),
            )
            for match in _REPORT_METADATA_ITEM_RE.finditer(block.group("body"))
        )
    for line in re.finditer(r"^\s*[^\n]+", request, re.MULTILINE):
        if any(start <= line.start() < end for start, end in block_spans):
            continue
        fragment = line.group(0)
        label_match = _REPORT_METADATA_ITEM_RE.match(fragment.strip())
        if label_match is not None and ":" in label_match.group(0):
            start = line.start() + len(line.group(0)) - len(line.group(0).lstrip())
            metadata_matches.append(_re_span_match(request, start, start + label_match.end()))
    for match in metadata_matches:
        match_start, match_end = match.span()
        match_text = request[match_start:match_end]
        parsed = _REPORT_METADATA_ITEM_RE.match(match_text)
        if parsed is None:
            continue
        result.append(
            _make_obligation(
                request=request,
                request_sha256=request_sha256,
                match=match,
                kind=ObligationKind.EXPLICIT_FIELD,
                owner_kind=OwnerKind.REPORT,
                owner_ref=_normalize_requirement_key(parsed.group("label")),
                field="metadata",
                value=parsed.group("value").strip().rstrip("."),
            )
        )

    for block in _REPORT_SERVICE_TITLES_RE.finditer(request):
        body_start = block.start("body")
        title_matches = list(re.finditer(r'"(?P<value>[^"]+)"', block.group("body")))
        if not title_matches:
            title_matches = list(re.finditer(r"(?P<value>[^,\n]+)", block.group("body")))
        for index, title in enumerate(title_matches, start=1):
            value = title.group("value").strip().rstrip(".")
            if not value or value.casefold() == "and":
                continue
            match = _re_span_match(
                request,
                body_start + title.start("value"),
                body_start + title.end("value"),
            )
            result.append(
                _make_obligation(
                    request=request,
                    request_sha256=request_sha256,
                    match=match,
                    kind=ObligationKind.EXPLICIT_FIELD,
                    owner_kind=OwnerKind.REPORT,
                    owner_ref=f"service_title_{index}",
                    field="service_title",
                    value=value,
                ).model_copy(update={"slot_key": f"service_title.{index}"})
            )

    remark_pattern = re.compile(
        r"(?:^|\s)\d+\.\s*(?P<title>[^—\n]+?)\s+—\s*(?P<text>.*?)(?=\s+\d+\.\s|\Z)",
        re.DOTALL,
    )
    for block in _REPORT_REMARKS_RE.finditer(request):
        body_start = block.start("body")
        for index, remark in enumerate(remark_pattern.finditer(block.group("body")), start=1):
            title = " ".join(remark.group("title").split())
            text = remark.group("text").strip()
            value = json.dumps({"title": title, "text": text}, sort_keys=True)
            match = _re_span_match(
                request,
                body_start + remark.start(),
                body_start + remark.end(),
            )
            result.append(
                _make_obligation(
                    request=request,
                    request_sha256=request_sha256,
                    match=match,
                    kind=ObligationKind.EXPLICIT_FIELD,
                    owner_kind=OwnerKind.REPORT,
                    owner_ref=f"remark_{index}",
                    field="remark",
                    value=value,
                ).model_copy(update={"slot_key": f"remark.{index}"})
            )

    for match in _REPORT_TAIL_RE.finditer(request):
        result.append(
            _make_obligation(
                request=request,
                request_sha256=request_sha256,
                match=match,
                kind=ObligationKind.EXPLICIT_FIELD,
                owner_kind=OwnerKind.REPORT,
                owner_ref="tail",
                field="tail_enabled",
                value=True,
            )
        )
    for field, pattern in (
        (
            "depth_presentation_allowed",
            r"\bdepth\s+(?:axis|scale|unit)\b|\bscale\s+ratio\b",
        ),
        (
            "page_presentation_allowed",
            r"\b(?:page|paper)\s+(?:size|orientation)\b|\b(?:a4|portrait|landscape)\b",
        ),
    ):
        match = re.search(pattern, request, re.IGNORECASE)
        if match is not None:
            span = _re_span_match(request, *match.span())
            result.append(
                _make_obligation(
                    request=request,
                    request_sha256=request_sha256,
                    match=span,
                    kind=ObligationKind.PRESERVATION,
                    owner_kind=OwnerKind.REPORT,
                    owner_ref="report",
                    field=field,  # type: ignore[arg-type]
                    value=True,
                )
            )
    return result


def _extract_presentation_obligations(
    request: str,
    request_sha256: str,
) -> list[RequestObligation]:
    """Compile presentation clauses into the existing typed obligation model."""
    result: list[RequestObligation] = []

    def add(
        match: re.Match[str],
        *,
        owner_kind: OwnerKind,
        owner_ref: str,
        field: FieldName,
        value: str | float | int | bool,
        slot_key: str | None = None,
        derivation: Literal["DIRECT", "SHARED_CLAUSE", "ORDINAL_CLAUSE"] = "DIRECT",
    ) -> None:
        item = _make_obligation(
            request=request,
            request_sha256=request_sha256,
            match=match,
            kind=ObligationKind.EXPLICIT_FIELD,
            owner_kind=owner_kind,
            owner_ref=owner_ref,
            field=field,
            value=value,
        )
        if derivation != "DIRECT":
            provenance = tuple(
                evidence.model_copy(update={"derivation": derivation})
                for evidence in item.provenance
            )
            item = item.model_copy(update={"provenance": provenance})
        stable_id = hashlib.sha256(
            f"{owner_kind}:{owner_ref}:{field}:{slot_key}:{item.start_byte}".encode()
        ).hexdigest()[:24]
        result.append(item.model_copy(update={"slot_key": slot_key, "requirement_id": stable_id}))

    block_matches = list(_REQUEST_TRACK_BLOCK_RE.finditer(request))
    blocks: list[tuple[str, str, int, int]] = []
    for index, header in enumerate(block_matches):
        end = block_matches[index + 1].start() if index + 1 < len(block_matches) else len(request)
        body_end = re.search(r"^\s*Use only channels\b", request[header.end() : end], re.I | re.M)
        if body_end:
            end = header.end() + body_end.start()
        blocks.append(
            (header.group("track").strip(), request[header.end() : end], header.start(), end)
        )

    for track, body, block_start, block_end in blocks:
        track_key = _normalize_requirement_key(track)
        block_text = request[block_start:block_end]
        block_match = re.match(r"(?s).+", block_text)
        if block_match is None:
            continue
        for match in _CURVE_PRESENTATION_RE.finditer(body):
            channel = match.group("channel").upper()
            slot = _binding_slot(body, channel, match.start(), track_key)
            label = _match_text_group(match, "label")
            values: tuple[tuple[FieldName, str | float | int | bool], ...] = (
                ("channel", channel),
                ("scale_kind", match.group("kind").casefold()),
                ("scale_minimum", float(match.group("minimum"))),
                ("scale_maximum", float(match.group("maximum"))),
                ("scale_reverse", match.group("reverse") is not None),
                ("color", match.group("color").casefold()),
                ("line_width", float(match.group("line_width"))),
                ("line_style", (match.group("line_style") or "solid").casefold()),
            )
            for field, value in values:
                add(
                    _re_span_match(request, block_start, block_end),
                    owner_kind=OwnerKind.BINDING,
                    owner_ref=track_key,
                    field=field,
                    value=value,
                    slot_key=slot,
                )
            if label:
                add(
                    _re_span_match(request, block_start, block_end),
                    owner_kind=OwnerKind.BINDING,
                    owner_ref=track_key,
                    field="label",
                    value=label,
                    slot_key=slot,
                )

        ordinal_matches = list(_ORDINAL_PRESENTATION_RE.finditer(body))
        for match in ordinal_matches:
            ordinal = {"first": 1, "second": 2, "third": 3, "fourth": 4}[
                match.group("ordinal").casefold()
            ]
            slot = f"{track_key}.binding.{ordinal}"
            for field, value in (
                ("scale_kind", match.group("kind").casefold()),
                ("scale_minimum", float(match.group("minimum"))),
                ("scale_maximum", float(match.group("maximum"))),
                ("scale_reverse", match.group("reverse") is not None),
                ("color", match.group("color").casefold()),
                ("line_width", float(match.group("line_width"))),
                ("line_style", (match.group("line_style") or "solid").casefold()),
            ):
                add(
                    _re_span_match(request, block_start, block_end),
                    owner_kind=OwnerKind.BINDING,
                    owner_ref=track_key,
                    field=field,
                    value=value,
                    slot_key=slot,
                    derivation="ORDINAL_CLAUSE",
                )

        shared_label = _SHARED_LABEL_RE.search(body)
        if shared_label:
            label = _match_text_group(shared_label, "label")
            if label:
                channel_counts: dict[str, int] = {}
                for curve in _CURVE_PRESENTATION_RE.finditer(body):
                    channel = curve.group("channel").upper()
                    channel_counts[channel] = channel_counts.get(channel, 0) + 1
                if not channel_counts:
                    channels = [
                        match.group("channel").upper() for match in _CHANNEL_RE.finditer(body)
                    ]
                    if channels and ordinal_matches:
                        channel_counts[channels[0]] = len(ordinal_matches)
                for _channel, count in channel_counts.items():
                    if count > 1:
                        for slot_index in range(1, count + 1):
                            add(
                                _re_span_match(request, block_start, block_end),
                                owner_kind=OwnerKind.BINDING,
                                owner_ref=track_key,
                                field="label",
                                value=label,
                                slot_key=f"{track_key}.binding.{slot_index}",
                                derivation="SHARED_CLAUSE",
                            )

        array_scale = _ARRAY_SCALE_RE.search(body)
        if array_scale:
            for field, value in (
                ("track_scale_kind", "linear"),
                ("track_scale_minimum", float(array_scale.group("minimum"))),
                ("track_scale_maximum", float(array_scale.group("maximum"))),
            ):
                add(
                    _re_span_match(request, block_start, block_end),
                    owner_kind=OwnerKind.TRACK,
                    owner_ref=track_key,
                    field=field,
                    value=value,
                )

        if _GRID_HIDE_RE.search(body):
            for field in ("vertical_main_visible", "vertical_secondary_visible"):
                add(
                    _re_span_match(request, block_start, block_end),
                    owner_kind=OwnerKind.TRACK,
                    owner_ref=track_key,
                    field=field,
                    value=False,
                )

        raster_label = _RASTER_LABEL_REQUEST_RE.search(body)
        if raster_label:
            label = _match_text_group(raster_label, "label")
            if label:
                add(
                    _re_span_match(request, block_start, block_end),
                    owner_kind=OwnerKind.BINDING,
                    owner_ref=track_key,
                    field="label",
                    value=label,
                    slot_key=f"{track_key}.binding.raster",
                )
        profile = _PROFILE_RE.search(body)
        if profile:
            add(
                _re_span_match(request, block_start, block_end),
                owner_kind=OwnerKind.BINDING,
                owner_ref=track_key,
                field="raster_profile",
                value=profile.group("value").casefold(),
                slot_key=f"{track_key}.binding.raster",
            )
        colormap = _COLORMAP_RE.search(body)
        if colormap:
            add(
                _re_span_match(request, block_start, block_end),
                owner_kind=OwnerKind.BINDING,
                owner_ref=track_key,
                field="raster_colormap",
                value=colormap.group("value").casefold(),
                slot_key=f"{track_key}.binding.raster",
            )
        colorbar = _COLORBAR_RE.search(body)
        if colorbar:
            for field, value in (
                ("colorbar_enabled", colorbar.group("enabled").casefold() == "enabled"),
                ("colorbar_label", colorbar.group("label").strip()),
                ("colorbar_position", colorbar.group("position").casefold()),
            ):
                add(
                    _re_span_match(request, block_start, block_end),
                    owner_kind=OwnerKind.BINDING,
                    owner_ref=track_key,
                    field=field,
                    value=value,
                    slot_key=f"{track_key}.binding.raster",
                )
        sample_axis = _SAMPLE_AXIS_RE.search(body)
        if sample_axis:
            for field, value in (
                ("sample_axis_enabled", True),
                ("sample_axis_unit", sample_axis.group("unit").casefold()),
                ("sample_axis_minimum", float(sample_axis.group("minimum"))),
                ("sample_axis_maximum", float(sample_axis.group("maximum"))),
                ("sample_axis_tick_count", int(sample_axis.group("ticks"))),
                ("sample_axis_source_origin", float(sample_axis.group("origin"))),
                ("sample_axis_source_step", float(sample_axis.group("step"))),
            ):
                add(
                    _re_span_match(request, block_start, block_end),
                    owner_kind=OwnerKind.BINDING,
                    owner_ref=track_key,
                    field=field,
                    value=value,
                    slot_key=f"{track_key}.binding.raster",
                )
    return result


def _request_scope_declarations(
    request: str,
    request_sha256: str,
) -> ScopeDeclarationSet:
    """Extract independently named request scopes before planner output exists."""
    if _CURVE_CREATION_START_RE.match(request) or _EXPLICIT_BASELINE_SPLIT_RE.fullmatch(request):
        return ScopeDeclarationSet()
    scopes: list[ScopeDeclaration] = []
    seen: set[str] = set()
    creates_sections = bool(
        re.search(r"\b(?:create|construct|rebuild|build)\b", request, re.I)
        and re.search(r"\bsection", request, re.I)
        and not any(
            pattern.search(request)
            for pattern in (
                _SECTION_TARGET_RE,
                _SECTION_IN_COMMA_TARGET_RE,
                _SECTION_POSSESSIVE_TRACK_TARGET_RE,
            )
        )
    )
    for match in _SCOPE_NAME_RE.finditer(request):
        name = match.group("name").strip()
        key = _normalize_requirement_key(name)
        if key in seen:
            continue
        seen.add(key)
        start = _byte_offset(request, match.start())
        end = _byte_offset(request, match.end())
        span = request.encode("utf-8")[start:end]
        scopes.append(
            ScopeDeclaration(
                declaration_id=f"scope.{key}",
                kind="NEW_SECTION" if creates_sections else "EXISTING_SECTION",
                selector_text=name,
                provenance=(
                    RequirementProvenance(
                        request_sha256=request_sha256,
                        start_byte=start,
                        end_byte=end,
                        span_sha256=hashlib.sha256(span).hexdigest(),
                    ),
                ),
            )
        )
    if scopes:
        return ScopeDeclarationSet(scopes=tuple(scopes))

    targets = (
        list(_SECTION_TARGET_RE.finditer(request))
        + list(_SECTION_IN_COMMA_TARGET_RE.finditer(request))
        + list(_SECTION_TO_TARGET_RE.finditer(request))
        + list(_SECTION_POSSESSIVE_TRACK_TARGET_RE.finditer(request))
    )
    if targets:
        for match in targets:
            name = match.group("target").strip()
            key = _normalize_requirement_key(name)
            if key in seen:
                continue
            seen.add(key)
            start = _byte_offset(request, match.start("target"))
            end = _byte_offset(request, match.end("target"))
            span = request.encode("utf-8")[start:end]
            scopes.append(
                ScopeDeclaration(
                    declaration_id=f"scope.{key}",
                    kind="EXISTING_SECTION",
                    selector_text=name,
                    provenance=(
                        RequirementProvenance(
                            request_sha256=request_sha256,
                            start_byte=start,
                            end_byte=end,
                            span_sha256=hashlib.sha256(span).hexdigest(),
                        ),
                    ),
                )
            )
    elif re.search(r"\b(?:create|construct|rebuild|build)\b", request, re.I) or any(
        pattern.search(request) for pattern in (_ADD_TRACK_RE, _TRACK_LINE_RE)
    ):
        start = _byte_offset(request, 0)
        end = _byte_offset(request, len(request))
        span = request.encode("utf-8")[start:end]
        scopes.append(
            ScopeDeclaration(
                declaration_id="scope.new.request.1",
                kind="NEW_SECTION",
                selector_text=None,
                provenance=(
                    RequirementProvenance(
                        request_sha256=request_sha256,
                        start_byte=start,
                        end_byte=end,
                        span_sha256=hashlib.sha256(span).hexdigest(),
                    ),
                ),
            )
        )
    return ScopeDeclarationSet(scopes=tuple(scopes))


def compile_request_contract(request: str) -> RequestCompilationResult:
    """Compile request facts once and independently verify supported coverage."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Authoritative request must be non-empty.")
    _, request_sha256 = _request_identity(request)
    joint = _C2_REQUEST_RE.fullmatch(request)
    if joint is not None or is_c2_request(request):
        if joint is not None and joint["channel"] == joint["fill_channel"]:
            try:
                return _compile_c2_request(request, joint, request_sha256)
            except ValueError:
                pass
        return RequestCompilationResult(
            requirements=CanonicalRequirementSet(
                request_sha256=request_sha256, language_version="wellplot-request-v1"
            ),
            status=RequestCompilationStatus.COVERAGE_FAILURE,
            diagnostic_codes=("supported_request_coverage_failure",),
        )
    if _has_unsupported_curve_creation_or_baseline_fill(request):
        return RequestCompilationResult(
            requirements=CanonicalRequirementSet(
                request_sha256=request_sha256, language_version="wellplot-request-v1"
            ),
            status=RequestCompilationStatus.COVERAGE_FAILURE,
            diagnostic_codes=("unsupported_curve_creation_or_baseline_fill",),
        )
    obligations = list(extract_supported_obligations(request))
    anchors = extract_supported_anchors(request)
    scopes = _request_scope_declarations(request, request_sha256)
    if (
        _EXPLICIT_PHYSICAL_PLOT_RE.fullmatch(request) is not None
        or _CREATE_PHYSICAL_CURVE_RE.fullmatch(request) is not None
        or _EXPLICIT_BASELINE_SPLIT_RE.fullmatch(request) is not None
        or _SCALAR_TRACK_SHORTHAND_RE.fullmatch(request) is not None
        or any(
            item.owner_kind is OwnerKind.BINDING
            and item.field == "channel"
            and item.owner_ref == "request"
            and item.value is not None
            and not str(item.value).isupper()
            for item in obligations
        )
    ) and not scopes.scopes:
        scopes = ScopeDeclarationSet(
            scopes=(
                ScopeDeclaration(
                    declaration_id="scope.existing.request.1",
                    kind="EXISTING_SECTION",
                    selector_text=None,
                    origin="HOST_CONTEXT",
                ),
            )
        )
    for declaration in scopes.scopes:
        if declaration.kind != "NEW_SECTION" or declaration.selector_text is None:
            continue
        evidence = declaration.provenance[0]
        obligations.append(
            RequestObligation(
                kind=ObligationKind.TARGET_REFERENCE,
                owner_kind=OwnerKind.SECTION,
                owner_ref=declaration.selector_text,
                field="target",
                value=declaration.selector_text,
                request_sha256=request_sha256,
                start_byte=evidence.start_byte,
                end_byte=evidence.end_byte,
                span_sha256=evidence.span_sha256,
                provenance=evidence and (evidence,),
                scope_key=declaration.declaration_id,
            )
        )
    diagnostics: list[str] = []
    status = RequestCompilationStatus.EXTRACTION_COMPLETE
    try:
        verify_obligation_spans(request, obligations)
        verify_anchor_coverage(request, obligations, anchors=anchors)
        for anchor in anchors:
            if anchor.kind == "scope" and not any(
                declaration.provenance
                and declaration.provenance[0].start_byte <= anchor.start_byte
                and declaration.provenance[0].end_byte >= anchor.end_byte
                for declaration in scopes.scopes
            ):
                raise ValueError("Supported request scope was not compiled.")
    except ValueError:
        status = RequestCompilationStatus.COVERAGE_FAILURE
        diagnostics.append("supported_request_coverage_failure")

    if any(item.state is ObligationState.CONFLICTING for item in obligations):
        status = RequestCompilationStatus.CONFLICTING
        diagnostics.append("conflicting_request_values")
    elif not obligations and not scopes.scopes and not anchors:
        status = RequestCompilationStatus.NO_SUPPORTED_SEMANTICS

    requirement_set = CanonicalRequirementSet(
        request_sha256=request_sha256,
        language_version="wellplot-request-v1",
        requirements=obligations,
        scopes=scopes,
        shared_scope_rules=(
            (
                SharedScopeRule(
                    selector="ALL_DECLARED_PASSES",
                    requirement_ids=tuple(item.requirement_id for item in obligations),
                ),
            )
            if re.search(r"\bfor\s+each\s+pass\b", request, re.I)
            else ()
        ),
    )
    return RequestCompilationResult(
        requirements=requirement_set,
        anchors=anchors,
        status=status,
        diagnostic_codes=tuple(dict.fromkeys(diagnostics)),
    )


def _has_unsupported_curve_creation_or_baseline_fill(request: str) -> bool:
    """Do not turn a partial match into authority for either bounded request family."""
    if _EXPLICIT_BASELINE_SPLIT_RE.fullmatch(request) or _CREATE_PHYSICAL_CURVE_RE.fullmatch(
        request
    ):
        return False
    # Keep literal text out of this guard without changing request provenance.
    instruction_text = _QUOTED_REQUEST_LITERAL_RE.sub(" ", request)
    return bool(
        _CURVE_CREATION_START_RE.match(request)
        or _BASELINE_FILL_REQUEST_RE.search(instruction_text)
    )


def _normalize_requirement_key(value: str) -> str:
    """Normalize a request-local display identity for deterministic matching."""
    return "_".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _binding_slot(body: str, channel: str, start: int, track_key: str) -> str:
    """Assign repeated channel clauses stable occurrence-based slot keys."""
    del channel
    preceding = sum(1 for match in _CURVE_PRESENTATION_RE.finditer(body) if match.start() < start)
    return f"{track_key}.binding.{preceding + 1}"


def _match_text_group(match: re.Match[str], prefix: str) -> str | None:
    """Return a present quoted or plain text value from a clause."""
    group_names = match.groupdict()
    for name in (
        f"{prefix}_quoted",
        f"{prefix}_single",
        f"{prefix}_plain",
        "quoted",
        "single",
        "plain",
    ):
        value = group_names.get(name)
        if value and value.strip():
            return value.strip()
    return None


def _re_span_match(request: str, start: int, end: int) -> re.Match[str]:
    """Create a match-like span for provenance over a larger semantic block."""
    del request

    class _AbsoluteSpan:
        def span(self) -> tuple[int, int]:
            return start, end

    return _AbsoluteSpan()  # type: ignore[return-value]


def verify_obligation_spans(request: str, obligations: tuple[RequestObligation, ...]) -> None:
    """Re-slice and verify every obligation using UTF-8 byte offsets."""
    data, request_sha256 = _request_identity(request)
    for obligation in obligations:
        if obligation.request_sha256 != request_sha256:
            raise ValueError("Obligation request identity mismatch.")
        span = data[obligation.start_byte : obligation.end_byte]
        if hashlib.sha256(span).hexdigest() != obligation.span_sha256:
            raise ValueError("Obligation span digest mismatch.")
        if obligation.state is ObligationState.SET and obligation.value is not None:
            literal = str(obligation.value).casefold()
            if isinstance(obligation.value, float):
                literal = literal.rstrip("0").rstrip(".")
            span_text = span.decode("utf-8").casefold()
            if obligation.owner_kind is OwnerKind.FILL and obligation.field == "kind":
                if obligation.value == "baseline_split" and _EXPLICIT_BASELINE_SPLIT_RE.fullmatch(
                    span.decode("utf-8")
                ):
                    continue
                raise ValueError("Fill geometry is not present in its request span.")
            if obligation.owner_kind is OwnerKind.FILL and obligation.field == "baseline":
                if (
                    isinstance(obligation.value, (int, float))
                    and re.fullmatch(r"[+-]?\d{1,12}(?:\.\d{1,12})?", span_text)
                    and float(span_text) == obligation.value
                ):
                    continue
                raise ValueError("Fill baseline is not present in its request span.")
            if (
                obligation.owner_kind is OwnerKind.TRACK
                and obligation.field == "kind"
                and obligation.value == "normal"
                and _SCALAR_TRACK_SHORTHAND_RE.fullmatch(span.decode("utf-8")) is not None
            ):
                continue
            if (
                obligation.field == "alpha"
                and isinstance(obligation.value, (float, int))
                and f"{float(obligation.value) * 100:g}%" in span_text
            ):
                continue
            if obligation.field == "scale_reverse" and obligation.value is False:
                continue
            if (
                obligation.field == "scale_reverse"
                and obligation.value is True
                and "reversed" in span_text
            ):
                continue
            if (
                obligation.field == "sample_axis_enabled"
                and obligation.value is True
                and "sample axis enabled" in span_text
            ):
                continue
            if (
                obligation.field == "colorbar_enabled"
                and isinstance(obligation.value, bool)
                and ("colorbar enabled" in span_text or "colorbar disabled" in span_text)
            ):
                continue
            if (
                obligation.field in {"vertical_main_visible", "vertical_secondary_visible"}
                and obligation.value is False
                and "hide" in span_text
            ):
                continue
            if obligation.field == "line_style" and obligation.value == "solid":
                continue
            if obligation.field == "remark" and isinstance(obligation.value, str):
                remark = json.loads(obligation.value)
                normalized_span = " ".join(span_text.split())
                if all(
                    " ".join(str(value).casefold().split()) in normalized_span
                    for value in remark.values()
                ):
                    continue
            if (
                obligation.field == "tail_enabled"
                and obligation.value is True
                and "tail" in span_text
                and not re.search(r"\b(?:without|omit|exclude|disable)\b", span_text)
            ):
                continue
            if obligation.field in {"page_presentation_allowed", "depth_presentation_allowed"}:
                continue
            if literal not in span_text:
                raise ValueError(
                    f"Obligation field {obligation.field} is not present in its request span."
                )


def verify_anchor_coverage(
    request: str,
    obligations: tuple[RequestObligation, ...] | CanonicalRequirementSet,
    *,
    anchors: tuple[SupportedAnchor, ...] | None = None,
) -> None:
    """Require every independently recognized anchor to have an obligation."""
    has_dependencies = isinstance(obligations, CanonicalRequirementSet) and bool(
        obligations.dependencies
    )
    if not has_dependencies and _has_unsupported_curve_creation_or_baseline_fill(request):
        raise ValueError("Canonical requirement set lacks supported request coverage.")
    if isinstance(obligations, CanonicalRequirementSet):
        if not obligations.dependencies and is_c2_request(request):
            raise ValueError("C2 dependency custody is missing.")
        if obligations.request_sha256 != _request_identity(request)[1]:
            raise ValueError("Canonical requirement set request identity mismatch.")
        if obligations.dependencies:
            _verify_request_dependencies(request, obligations)
            fresh = extract_supported_anchors(request)
            if anchors is not None and anchors != fresh:
                raise ValueError("C2 anchor custody differs from the original request.")
            anchors = fresh
        obligations = obligations.requirements
    anchors = anchors if anchors is not None else extract_supported_anchors(request)
    for anchor in anchors:
        if anchor.kind == "scope" or (has_dependencies and anchor.family == "section_scope_target"):
            continue
        if not any(
            item.field == anchor.field
            and item.start_byte <= anchor.start_byte
            and item.end_byte >= anchor.end_byte
            for item in obligations
        ):
            raise ValueError("Supported request anchor was not converted to an obligation.")


_C2_REQUEST_RE = re.compile(
    r"\s*(?P<section_prefix>(?P<section_clause>(?i:in the)\s+"
    r"(?P<selector>(?i:Main\s+Pass|Repeat\s+Pass))\s+(?i:section)),\s*)?"
    r"(?i:plot physical)\s+(?P<channel>[A-Z][A-Z0-9_]{1,11})\."
    r"\s*(?P<sequence>(?i:then))\s+(?P<geometry>(?i:split)\s+"
    r"(?P<target>(?i:the)\s+(?P<fill_channel>[A-Z][A-Z0-9_]{1,11})\s+(?i:curve))"
    r"\s+(?i:fill at baseline)\s+(?P<baseline>[+-]?\d{1,12}(?:\.\d{1,12})?)\.)\s*"
)


def is_c2_request(request: str) -> bool:
    """Recognize only the bounded compound family, including rejected forms."""
    if _C2_REQUEST_RE.fullmatch(request):
        return True
    text = _QUOTED_REQUEST_LITERAL_RE.sub(lambda match: " " * len(match[0]), request)
    boundaries = list(re.finditer(r"[.!?;,\n]|\b(?:and|then)\b", text, re.I))
    starts = [0, *(match.end() for match in boundaries)]
    ends = [*(match.start() for match in boundaries), len(text)]
    for start, end in zip(starts, ends, strict=True):
        plot = _EXPLICIT_PHYSICAL_PLOT_RE.fullmatch(text, start, end)
        if plot is not None:
            without_plot = text[:start] + " " * (end - start) + text[end:]
            if _BASELINE_FILL_REQUEST_RE.search(without_plot):
                return True
    return False


def _c2_scope(request: str, match: re.Match[str], digest: str) -> ScopeDeclaration:
    if match["selector"] is None:
        return ScopeDeclaration(
            declaration_id="scope.existing.request.1",
            kind="EXISTING_SECTION",
            origin="HOST_CONTEXT",
        )
    declarations = _request_scope_declarations(request, digest).scopes
    clause = _SECTION_TARGET_RE.search(request)
    selector = _SCOPE_NAME_RE.search(request)
    if (
        len(declarations) != 1
        or clause is None
        or selector is None
        or clause.span() != match.span("section_clause")
        or clause.span("target") != match.span("selector")
        or selector.span() != match.span("selector")
        or declarations[0].origin != "REQUEST"
        or declarations[0].kind != "EXISTING_SECTION"
    ):
        raise ValueError("Invalid C2 named scope.")
    return declarations[0]


def _compile_c2_request(
    request: str, match: re.Match[str], digest: str
) -> RequestCompilationResult:
    scope = _c2_scope(request, match, digest)
    channel = match["channel"]
    facts = tuple(
        _make_obligation(
            request=request,
            request_sha256=digest,
            match=_re_span_match(request, *match.span(group)),
            kind=kind,
            owner_kind=owner_kind,
            owner_ref=owner,
            field=field,
            value=value,
        ).model_copy(update={"scope_key": scope.declaration_id})
        for group, kind, owner_kind, owner, field, value in (
            (
                "channel",
                ObligationKind.EXPLICIT_FIELD,
                OwnerKind.BINDING,
                "request",
                "channel",
                channel,
            ),
            (
                "fill_channel",
                ObligationKind.TARGET_REFERENCE,
                OwnerKind.FILL,
                channel,
                "target",
                channel,
            ),
            (
                "geometry",
                ObligationKind.EXPLICIT_FIELD,
                OwnerKind.FILL,
                channel,
                "kind",
                "baseline_split",
            ),
            (
                "baseline",
                ObligationKind.EXPLICIT_FIELD,
                OwnerKind.FILL,
                channel,
                "baseline",
                float(match["baseline"]),
            ),
        )
    )
    data = request.encode("utf-8")
    provenance = tuple(
        RequirementProvenance(
            request_sha256=digest,
            start_byte=start,
            end_byte=end,
            span_sha256=hashlib.sha256(data[start:end]).hexdigest(),
        )
        for group in ("sequence", "target")
        for start, end in [tuple(_byte_offset(request, offset) for offset in match.span(group))]
    )
    requirements = CanonicalRequirementSet(
        request_sha256=digest,
        language_version="wellplot-request-v1",
        requirements=facts,
        scopes=ScopeDeclarationSet(scopes=(scope,)),
        dependencies=(
            RequestDependency(
                request_sha256=digest,
                relation="FILL_TARGET_SATISFIED_BY",
                predecessor_requirement_id=facts[0].requirement_id,
                dependent_requirement_id=facts[1].requirement_id,
                provenance=provenance,
            ),
        ),
    )
    verify_anchor_coverage(request, requirements)
    return RequestCompilationResult(
        requirements=requirements,
        anchors=extract_supported_anchors(request),
        status=RequestCompilationStatus.EXTRACTION_COMPLETE,
    )


def _verify_request_dependencies(
    request: str,
    requirement_set: CanonicalRequirementSet,
) -> None:
    """Validate a finite joint form against original bytes, not repeated names alone."""
    match = _C2_REQUEST_RE.fullmatch(request)
    if match is None:
        raise ValueError("Dependency lacks complete supported request coverage.")
    data, digest = _request_identity(request)
    obligations = requirement_set.requirements
    dependencies = requirement_set.dependencies
    scope = _c2_scope(request, match, digest)
    if (
        requirement_set.language_version != "wellplot-request-v1"
        or requirement_set.scopes != ScopeDeclarationSet(scopes=(scope,))
        or requirement_set.shared_scope_rules
        or any(
            item.scope_key != scope.declaration_id
            or item.scope != "task"
            or item.slot_key is not None
            for item in obligations
        )
    ):
        raise ValueError("Dependency requires the original authoritative scope declaration.")
    if len(obligations) != 4:
        raise ValueError("Dependency requires exactly four explicit facts.")
    for item in obligations:
        if (
            item.requirement_id != _requirement_identity(item)
            or item.state is not ObligationState.SET
            or not 0 <= item.start_byte < item.end_byte <= len(data)
            or item.provenance
            != (
                RequirementProvenance(
                    request_sha256=digest,
                    start_byte=item.start_byte,
                    end_byte=item.end_byte,
                    span_sha256=item.span_sha256,
                ),
            )
        ):
            raise ValueError("Dependency requirement identity or provenance is invalid.")
    verify_obligation_spans(request, obligations)
    by_id = {item.requirement_id: item for item in obligations}
    if len(by_id) != len(obligations) or any(not key for key in by_id):
        raise ValueError("Dependency requirements must have unique identities.")
    if len(dependencies) != 1:
        raise ValueError("Dependency target must have exactly one predecessor.")
    dependency = dependencies[0]
    predecessor = by_id.get(dependency.predecessor_requirement_id)
    dependent = by_id.get(dependency.dependent_requirement_id)
    if predecessor is None or dependent is None or predecessor is dependent:
        raise ValueError("Dependency references invalid requirements.")
    if (
        dependency.request_sha256 != digest
        or dependency.relation != "FILL_TARGET_SATISFIED_BY"
        or len(dependency.provenance) != 2
        or predecessor.request_sha256 != digest
        or dependent.request_sha256 != digest
        or predecessor.state is not ObligationState.SET
        or dependent.state is not ObligationState.SET
        or predecessor.kind is not ObligationKind.EXPLICIT_FIELD
        or predecessor.owner_kind is not OwnerKind.BINDING
        or predecessor.owner_ref != "request"
        or predecessor.field != "channel"
        or dependent.kind is not ObligationKind.TARGET_REFERENCE
        or dependent.owner_kind is not OwnerKind.FILL
        or dependent.field != "target"
        or predecessor.value != match["channel"]
        or dependent.value != match["fill_channel"]
        or predecessor.value != dependent.value
        or predecessor.scope_key != dependent.scope_key
        or not predecessor.scope_key
        or (predecessor.start_byte, predecessor.end_byte)
        != (
            _byte_offset(request, match.start("channel")),
            _byte_offset(request, match.end("channel")),
        )
        or (dependent.start_byte, dependent.end_byte)
        != (
            _byte_offset(request, match.start("fill_channel")),
            _byte_offset(request, match.end("fill_channel")),
        )
    ):
        raise ValueError("Dependency requirements do not identify the same scoped curve outcome.")
    fill_facts = [
        item
        for item in obligations
        if item.owner_kind is OwnerKind.FILL and item.owner_ref == dependent.owner_ref
    ]
    if (
        dependent.owner_ref != match["fill_channel"]
        or len(fill_facts) != 3
        or {item.field for item in fill_facts} != {"target", "kind", "baseline"}
        or any(item.scope_key != dependent.scope_key for item in fill_facts)
        or len(
            [
                item
                for item in obligations
                if item.owner_kind is OwnerKind.BINDING and item.field == "channel"
            ]
        )
        != 1
        or not any(item.field == "kind" and item.value == "baseline_split" for item in fill_facts)
        or not any(
            item.field == "baseline" and item.value == float(match["baseline"])
            for item in fill_facts
        )
    ):
        raise ValueError("Dependency lacks complete explicit fill geometry.")
    for item in fill_facts:
        if item.field == "target":
            continue
        group = "geometry" if item.field == "kind" else "baseline"
        if item.kind is not ObligationKind.EXPLICIT_FIELD or (
            item.start_byte,
            item.end_byte,
        ) != tuple(_byte_offset(request, offset) for offset in match.span(group)):
            raise ValueError("Dependency geometry does not match its exact request span.")
    expected_spans = tuple(
        (_byte_offset(request, match.start(group)), _byte_offset(request, match.end(group)))
        for group in ("sequence", "target")
    )
    for provenance, (start, end) in zip(dependency.provenance, expected_spans, strict=True):
        if (
            provenance.request_sha256 != digest
            or provenance.start_byte != start
            or provenance.end_byte != end
            or end > len(data)
            or provenance.derivation != "DIRECT"
            or provenance.span_sha256 != hashlib.sha256(data[start:end]).hexdigest()
        ):
            raise ValueError("Dependency provenance does not match the original request.")


def _plain_json(value: object) -> object:
    """Project model-shaped values into deterministic JSON-compatible data."""
    if isinstance(value, BaseModel):
        return _plain_json(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _identity_matches(value: Mapping[str, Any], object_id: str) -> bool:
    """Match one canonical object without relying on list position."""
    normalized = object_id.casefold()
    return normalized in {
        str(value.get(key, "")).casefold()
        for key in (
            "id",
            "semantic_id",
            "section_id",
            "track_id",
            "binding_id",
            "fill_id",
            "slot_id",
            "key",
            "remark_id",
            "title",
            "channel",
            "label",
        )
    }


def _object_paths(
    value: object,
    *,
    object_kind: str,
    object_id: str,
    path: tuple[str, ...] = (),
) -> list[tuple[str, ...]]:
    """Find canonical object paths in a JSON-shaped document."""
    if not isinstance(value, Mapping):
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            paths: list[tuple[str, ...]] = []
            for index, item in enumerate(value):
                paths.extend(
                    _object_paths(
                        item,
                        object_kind=object_kind,
                        object_id=object_id,
                        path=path + (str(index),),
                    )
                )
            return paths
        return []

    found: list[tuple[str, ...]] = []
    identity = _COLLECTION_OBJECTS.get(object_kind)
    if identity is not None:
        collection, key = identity
        matched = (
            len(path) >= 2
            and path[-2] == collection
            and value.get(key, value.get("id")) == object_id
            and (
                not object_kind.endswith("_binding")
                or value.get("kind", object_kind.removesuffix("_binding"))
                == object_kind.removesuffix("_binding")
            )
        )
    else:
        matched = value.get("slot_id") == object_id if object_kind == "header_slot" else False
    if matched:
        found.append(path)
    for key, child in value.items():
        if key != "extensions" and isinstance(child, (Mapping, list, tuple)):
            found.extend(
                _object_paths(
                    child,
                    object_kind=object_kind,
                    object_id=object_id,
                    path=path + (str(key),),
                )
            )
    return found


_COLLECTION_OBJECTS = {
    "section": ("sections", "id"),
    "track": ("tracks", "id"),
    "curve_binding": ("bindings", "binding_id"),
    "raster_binding": ("bindings", "binding_id"),
    "fill": ("fills", "fill_id"),
    "annotation": ("annotations", "annotation_id"),
    "remark": ("remarks", "remark_id"),
}
_CREATED_OBJECT_MODELS = {
    "section": AuthoringSectionSpec,
    "track": TrackSpec,
    "curve_binding": CurveBindingSpec,
    "raster_binding": RasterBindingSpec,
    "fill": CurveFillSpec,
    "annotation": AnnotationSpec,
    "remark": AuthoringRemarkSpec,
}
_PRESERVATION_ERROR = "Candidate document changed outside the authorized reconciliation envelope."
_MERGED_OPERATION_FIELDS = {
    "curve_binding": {"style", "value_labels", "header_display"},
    "raster_binding": {"style", "colorbar", "sample_axis", "waveform"},
    "header_slot": {"value"},
}


def _scoped_operation_parent(
    document: dict[str, Any], operation: object
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Locate only the canonical parents declared on an operation."""
    parent = document
    path: tuple[str, ...] = ()
    kind = getattr(operation, "object_kind", "")
    for name, scope in (("sections", "section_id"), ("tracks", "track_id")):
        if kind in {"section", "remark"} or (kind == "track" and scope == "track_id"):
            break
        object_id = getattr(operation, scope, None)
        if not object_id:
            continue
        matches = [
            (index, item)
            for index, item in enumerate(parent.get(name, ()))
            if item.get("id") == object_id
        ]
        if len(matches) != 1:
            raise ValueError(_PRESERVATION_ERROR)
        index, parent = matches[0]
        path += (name, str(index))
    return parent, path


def _project_collection_effects(document: dict[str, Any], operations: Sequence[object]) -> None:
    """Project only authorized collection changes; never call the executor or service."""
    for operation in operations:
        action = getattr(operation, "action", "")
        if action not in {"create", "remove", "move"}:
            continue
        kind = getattr(operation, "object_kind", "")
        if kind not in _COLLECTION_OBJECTS:
            raise ValueError(_PRESERVATION_ERROR)
        collection, key = _COLLECTION_OBJECTS[kind]
        parent, _ = _scoped_operation_parent(document, operation)
        items = parent.get(collection)
        if not isinstance(items, list):
            raise ValueError(_PRESERVATION_ERROR)
        object_id = getattr(operation, "object_id", None)
        matches = [index for index, item in enumerate(items) if item.get(key) == object_id]
        payload = operation.payload
        if action == "create":
            if matches or "object" not in payload:
                raise ValueError(_PRESERVATION_ERROR)
            raw = payload["object"]
            if isinstance(operation, AuthoringOperation):
                model = TypeAdapter(_CREATED_OBJECT_MODELS[kind])
                raw = model.validate_python(_omit_undefined(_resolve_clears(raw)))
            created = _plain_json(raw)
            if not isinstance(created, dict) or created.get(key) != object_id:
                raise ValueError(_PRESERVATION_ERROR)
            items.append(created)
            continue
        if len(matches) != 1:
            raise ValueError(_PRESERVATION_ERROR)
        item = items.pop(matches[0])
        if action == "move":
            index = payload.get("new_index")
            if not isinstance(index, int) or not 0 <= index <= len(items):
                raise ValueError(_PRESERVATION_ERROR)
            items.insert(index, item)


def _operation_update_paths(
    document: dict[str, Any], operation: object, kind: str
) -> list[tuple[str, ...]]:
    object_id = getattr(operation, "object_id", "")
    if kind == "report":
        return [()]
    if kind in {"header", "page", "depth", "output", "tail"}:
        return [(kind,)]
    if kind == "header_slot":
        return _object_paths(
            document.get("header"), object_kind=kind, object_id=object_id, path=("header",)
        )
    parent, path = _scoped_operation_parent(document, operation)
    collection = _COLLECTION_OBJECTS.get(kind)
    if collection is None:
        return []
    name, _ = collection
    return _object_paths(
        {name: parent.get(name, [])}, object_kind=kind, object_id=object_id, path=path
    )


def _changed_paths(left: object, right: object, path: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    """Return changed JSON paths, treating collection shape changes atomically."""
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        changed: set[tuple[str, ...]] = set()
        for key in set(left) | set(right):
            child = path + (str(key),)
            if key not in left or key not in right:
                changed.add(child)
            else:
                changed |= _changed_paths(left[key], right[key], child)
        return changed
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return {path}
        changed: set[tuple[str, ...]] = set()
        for index, (old, new) in enumerate(zip(left, right, strict=True)):
            changed |= _changed_paths(old, new, path + (str(index),))
        return changed
    if left != right:
        return {path}
    return set()


def verify_document_preservation(
    before: object,
    after: object,
    operations: Sequence[object],
    *,
    operation_boundary: bool = False,
) -> None:
    """Reject candidate changes outside the canonical reconciliation operations."""
    before_json = _plain_json(before)
    after_json = _plain_json(after)
    if not isinstance(before_json, dict) or not isinstance(after_json, dict):
        raise ValueError(_PRESERVATION_ERROR)
    if operation_boundary:
        # The executor already validates the intact plan and completed dependencies.
        if len(operations) != 1 or not isinstance(operations[0], AuthoringOperation):
            raise ValueError(_PRESERVATION_ERROR)
    elif operations and all(isinstance(op, AuthoringOperation) for op in operations):
        ordered, errors = _order_plan_operations(
            AuthoringReconciliationPlan(ready=True, operations=operations)
        )
        if errors:
            raise ValueError(_PRESERVATION_ERROR)
        operations = tuple(op for group in ordered.values() for op in group)
    _project_collection_effects(before_json, operations)
    changed = _changed_paths(before_json, after_json)
    allowed: set[tuple[str, ...]] = set()
    for operation in operations:
        if getattr(operation, "action", "") != "update":
            continue
        object_kind = str(getattr(operation, "object_kind", "")).casefold()
        payload = getattr(operation, "payload", {})
        prefixes = _operation_update_paths(before_json, operation, object_kind)
        if not prefixes:
            continue
        if object_kind == "annotation" and "object" in payload:
            if len(prefixes) != 1 or prefixes != _operation_update_paths(
                after_json, operation, object_kind
            ):
                raise ValueError(_PRESERVATION_ERROR)
            (prefix,) = prefixes
            actual: Any = after_json
            for key in prefix:
                actual = actual[int(key)] if isinstance(actual, list) else actual[key]
            expected = TypeAdapter(AnnotationSpec).validate_python(
                _resolve_clears(payload["object"])
            )
            if actual != _plain_json(expected):
                raise ValueError(_PRESERVATION_ERROR)
            allowed.add(prefix)
            continue
        if object_kind in _COLLECTION_OBJECTS and (
            len(prefixes) != 1
            or prefixes != _operation_update_paths(after_json, operation, object_kind)
        ):
            raise ValueError(_PRESERVATION_ERROR)
        patch = payload.get("patch") if isinstance(payload, Mapping) else None
        for prefix in prefixes:
            if isinstance(patch, Mapping):
                for key, value in patch.items():
                    path = prefix + (str(key),)
                    if (
                        operation_boundary
                        and key in _MERGED_OPERATION_FIELDS.get(object_kind, ())
                        and isinstance(value, Mapping)
                        and value.get("operation") != "clear"
                    ):
                        allowed.update(path + (str(child),) for child in value)
                    else:
                        allowed.add(path)
            elif object_kind in {"header", "page", "depth", "output", "tail"}:
                allowed.add(prefix)
    if any(not any(path[: len(prefix)] == prefix for prefix in allowed) for path in changed):
        raise ValueError(_PRESERVATION_ERROR)


def validate_report_obligations(
    response: object, obligations: tuple[RequestObligation, ...]
) -> None:
    """Require report-owned obligations to be represented by the worker response."""
    for item in obligations:
        if (
            item.owner_kind is OwnerKind.REPORT
            and item.field in {"title", "subtitle"}
            and (
                item.state is not ObligationState.SET or getattr(response, item.field) != item.value
            )
        ):
            raise ValueError(f"Requested report {item.field} was not satisfied.")


def _validate_sparse_binding_context(
    action: SectionSemanticAction,
    item: RequestObligation,
    *,
    section_context: ResolvedSectionContext | None,
    section_title: str | None,
) -> None:
    """Check context facts on the grounded slot, not on the worker's binding fields."""
    from .worker_contracts import _existing_track_handle, _source_handle

    if section_context is None or section_context.section_id is None:
        raise ValueError("Sparse binding context must be grounded before validation.")
    match (item.owner_kind, item.field):
        case (OwnerKind.SECTION, "target"):
            if section_title and _normalize_requirement_key(
                section_title
            ) == _normalize_requirement_key(str(item.value)):
                return
        case (OwnerKind.TRACK, "target"):
            if _existing_track_handle(str(item.value), section_context) == action.target.handle:
                return
        case (OwnerKind.SOURCE, "source"):
            if (
                len(section_context.sources) == 1
                and _source_handle(item.value, section_context) == section_context.sources[0].handle
            ):
                return
    raise ValueError("Sparse binding context does not satisfy the request obligation.")


def validate_section_obligations(
    action: SectionSemanticAction,
    obligations: tuple[RequestObligation, ...],
    *,
    section_context: ResolvedSectionContext | None = None,
    section_title: str | None = None,
    object_bindings: SectionObjectBindings | None = None,
) -> None:
    """Require every supported section obligation before canonical lowering."""
    if getattr(action, "action", None) == "add_binding":
        binding = action.binding
        for item in obligations:
            if item.state in {ObligationState.CONFLICTING, ObligationState.UNRESOLVED}:
                raise ValueError("Request obligation is unresolved or conflicting.")
            if item.state is ObligationState.FORBIDDEN:
                if item.field == "channel" and binding.channel == item.value:
                    raise ValueError(f"Forbidden channel {item.value} was emitted.")
                continue
            if item.owner_kind is OwnerKind.BINDING and item.field == "channel":
                if binding.kind != "curve" or binding.channel != item.value:
                    raise ValueError(f"Requested channel {item.value} was not satisfied.")
            elif item.owner_kind in {OwnerKind.SECTION, OwnerKind.TRACK, OwnerKind.SOURCE}:
                _validate_sparse_binding_context(
                    action, item, section_context=section_context, section_title=section_title
                )
            else:
                raise ValueError("Sparse binding cannot satisfy a non-binding obligation.")
        return
    if getattr(action, "action", None) == "update_curve_scale":
        if section_context is None:
            raise ValueError("Existing-object obligations require resolved section context.")
        _validate_existing_curve_scale_obligations(
            action,
            obligations,
            section_context=section_context,
            section_title=section_title,
        )
        return

    section = getattr(action, "section", None)
    tracks = list(getattr(section, "tracks", ()) or ())
    tracks.extend(list(getattr(action, "tracks", ()) or ()))
    if hasattr(action, "track") and action.track is not None:
        tracks.append(action.track)
    binding_records = [
        (track, binding) for track in tracks for binding in getattr(track, "bindings", ())
    ]
    bindings = [binding for _, binding in binding_records]
    fill = getattr(action, "fill", None)

    def matching_bindings(item: RequestObligation) -> list[object]:
        if item.slot_key:
            if object_bindings is not None:
                track_index = object_bindings.track_index(item.owner_ref)
                binding_index = object_bindings.binding_index(item.owner_ref, item.slot_key)
                if (
                    track_index is None
                    or binding_index is None
                    or not 0 <= track_index < len(tracks)
                    or not 0 <= binding_index < len(tracks[track_index].bindings)
                ):
                    return []
                return [tracks[track_index].bindings[binding_index]]
            normalized_owner = _normalize_requirement_key(item.owner_ref)
            candidate_tracks = [
                track
                for track in tracks
                if normalized_owner
                in {
                    _normalize_requirement_key(str(getattr(track, "semantic_id", ""))),
                    _normalize_requirement_key(str(getattr(track, "title", ""))),
                }
            ]
            if not candidate_tracks and len(tracks) == 1:
                candidate_tracks = tracks
            if len(candidate_tracks) != 1:
                return []
            slot_match = re.search(r"\.binding\.(\d+)$", item.slot_key)
            slot_tracks = [
                binding
                for binding in getattr(candidate_tracks[0], "bindings", ())
                if item.slot_key.endswith(".binding.raster")
                and any(
                    getattr(binding, field, None) is not None
                    for field in ("profile", "colormap", "sample_axis", "colorbar_enabled")
                )
            ]
            if slot_match:
                index = int(slot_match.group(1)) - 1
                all_bindings = list(getattr(candidate_tracks[0], "bindings", ()))
                return [all_bindings[index]] if 0 <= index < len(all_bindings) else []
            return slot_tracks
        if item.owner_ref.casefold() == "request":
            if item.field == "channel":
                return [
                    binding
                    for binding in bindings
                    if getattr(binding, "channel", None) == item.value
                ]
            return bindings
        if object_bindings is not None:
            track_index = object_bindings.track_index(item.owner_ref)
            if track_index is None or not 0 <= track_index < len(tracks):
                return []
            owner_bindings = list(getattr(tracks[track_index], "bindings", ()))
            if item.field == "channel":
                return [
                    binding
                    for binding in owner_bindings
                    if getattr(binding, "channel", None) == item.value
                ]
            return owner_bindings
        owner = item.owner_ref.casefold()
        owner_key = _normalize_requirement_key(item.owner_ref)
        return [
            binding
            for track, binding in binding_records
            if owner
            in {
                str(getattr(track, "semantic_id", "")).casefold(),
                str(getattr(track, "title", "")).casefold(),
                str(getattr(binding, "semantic_id", "")).casefold(),
                str(getattr(binding, "channel", "")).casefold(),
                str(getattr(binding, "label", "")).casefold(),
            }
            or owner_key
            in {
                _normalize_requirement_key(str(getattr(track, "semantic_id", ""))),
                _normalize_requirement_key(str(getattr(track, "title", ""))),
                _normalize_requirement_key(str(getattr(binding, "semantic_id", ""))),
                _normalize_requirement_key(str(getattr(binding, "channel", ""))),
                _normalize_requirement_key(str(getattr(binding, "label", ""))),
            }
        ]

    for item in obligations:
        if item.state in {ObligationState.CONFLICTING, ObligationState.UNRESOLVED}:
            raise ValueError("Request obligation is unresolved or conflicting.")
        if item.state is ObligationState.FORBIDDEN:
            if (
                item.owner_kind is OwnerKind.BINDING
                and item.field == "channel"
                and any(getattr(binding, "channel", None) == item.value for binding in bindings)
            ):
                raise ValueError(f"Forbidden channel {item.value} was emitted.")
            continue
        if item.owner_kind in {OwnerKind.TRACK, OwnerKind.ARRAY_TRACK}:
            if object_bindings is not None:
                track_index = object_bindings.track_index(item.owner_ref)
                matches = (
                    [tracks[track_index]]
                    if track_index is not None and 0 <= track_index < len(tracks)
                    else []
                )
            else:
                matches = [
                    track
                    for track in tracks
                    if _normalize_requirement_key(str(getattr(track, "semantic_id", "")))
                    == _normalize_requirement_key(item.owner_ref)
                    or _normalize_requirement_key(str(getattr(track, "title", "")))
                    == _normalize_requirement_key(item.owner_ref)
                ]
            if len(matches) != 1:
                raise ValueError("Requested track identity is unresolved or ambiguous.")
            if item.field == "target":
                continue
            actual = getattr(matches[0], item.field, None)
            if item.field == "width_mm" and actual is not None:
                actual = float(actual)
            if item.field.startswith("track_scale_"):
                scale = getattr(matches[0], "x_scale", None)
                actual = getattr(
                    scale,
                    {
                        "track_scale_kind": "kind",
                        "track_scale_minimum": "minimum",
                        "track_scale_maximum": "maximum",
                        "track_scale_unit": "unit",
                    }[item.field],
                    None,
                )
            if item.field in {"vertical_main_visible", "vertical_secondary_visible"}:
                actual = getattr(getattr(matches[0], "grid", None), item.field, None)
            if actual != item.value:
                raise ValueError(f"Requested track {item.field} was not satisfied.")
        if item.owner_kind is OwnerKind.BINDING:
            matches = matching_bindings(item)
            if not matches:
                if item.field == "channel":
                    raise ValueError(f"Requested channel {item.value} was not satisfied.")
                raise ValueError("Requested binding identity is unresolved or ambiguous.")
            if item.field == "channel":
                continue
            if len(matches) != 1:
                raise ValueError("Requested binding identity is unresolved or ambiguous.")
            binding = matches[0]
            if item.field in {"channel", "label", "raster_profile", "raster_colormap"}:
                binding_field = {
                    "raster_profile": "profile",
                    "raster_colormap": "colormap",
                }.get(item.field, item.field)
                actual = getattr(binding, binding_field, None)
            else:
                scale = getattr(binding, "scale", None)
                scale_field = {
                    "scale_kind": "kind",
                    "scale_minimum": "minimum",
                    "scale_maximum": "maximum",
                }.get(item.field)
                actual = getattr(scale, scale_field, None) if scale_field else None
                if item.field == "scale_reverse" and scale is not None:
                    actual = getattr(scale, "reverse", None)
                if item.field in {"color", "line_width", "line_style"}:
                    actual = getattr(getattr(binding, "style", None), item.field, None)
                if item.field.startswith("sample_axis_"):
                    axis_field = {
                        "sample_axis_enabled": "enabled",
                        "sample_axis_unit": "unit",
                        "sample_axis_minimum": "minimum",
                        "sample_axis_maximum": "maximum",
                        "sample_axis_tick_count": "tick_count",
                        "sample_axis_source_origin": "source_origin",
                        "sample_axis_source_step": "source_step",
                    }[item.field]
                    axis = getattr(binding, "sample_axis", None)
                    actual = (
                        (axis is not None)
                        if axis_field == "enabled"
                        else getattr(axis, axis_field, None)
                    )
                if item.field.startswith("colorbar_"):
                    actual = getattr(binding, item.field, None)
            if item.field == "scale_kind" and actual is not None:
                actual = str(actual).casefold()
            if item.field in {"scale_minimum", "scale_maximum"} and actual is not None:
                actual = float(actual)
            if actual != item.value:
                raise ValueError(f"Requested binding {item.field} was not satisfied.")
        if item.owner_kind is OwnerKind.FILL:
            if fill is None:
                raise ValueError("Requested fill semantics were not emitted.")
            if item.field == "target":
                handle = getattr(getattr(action, "target", None), "handle", "")
                curves = section_context.existing_curves if section_context is not None else ()
                if not any(
                    handle == f"curve-{index}"
                    and fill.target_binding == handle
                    and curve.channel == item.value
                    for index, curve in enumerate(curves, 1)
                ):
                    raise ValueError("Requested fill target was not satisfied.")
                continue
            actual = getattr(fill, item.field, None)
            if actual != item.value:
                raise ValueError(f"Requested fill {item.field} was not satisfied.")
        if item.owner_kind is OwnerKind.SOURCE and item.field == "source":
            selected = getattr(getattr(action, "section", None), "source_candidate", None)
            context_sources = section_context.sources if section_context is not None else ()
            requested_basename = str(item.value).casefold().split("/")[-1]
            matching_sources = [
                source
                for source in context_sources
                if requested_basename
                in {
                    label.casefold().split("/")[-1]
                    for label in (*source.labels, source.canonical_path)
                }
            ]
            if selected is not None:
                resolved = [
                    source for source in matching_sources if source.candidate_id == selected
                ]
            elif (
                getattr(action, "action", None) == "add_track"
                and section_context is not None
                and section_context.section_id is not None
            ):
                # Sparse actions against an existing section do not carry the
                # reconstruction-only source_candidate field. Bind the source
                # through the task's inspected context, requiring uniqueness.
                resolved = matching_sources
            else:
                resolved = []
            if len(resolved) != 1:
                raise ValueError("Requested source was not resolved from inspected context.")
        actual_section_title = section_title if section is None else getattr(section, "title", None)
        if (
            item.owner_kind is OwnerKind.SECTION
            and item.field == "target"
            and actual_section_title != item.value
        ):
            raise ValueError("Requested section target was not satisfied.")


def _validate_existing_curve_scale_obligations(
    action: SectionSemanticAction,
    obligations: tuple[RequestObligation, ...],
    *,
    section_context: ResolvedSectionContext,
    section_title: str | None,
) -> None:
    """Validate sparse existing-curve updates against host-owned identity."""
    from .semantic_actions import resolve_existing_curve

    target = resolve_existing_curve(action.target, section_context)
    identities = {
        target.binding_id.casefold(),
        target.channel.casefold(),
        (target.label or "").casefold(),
        target.track_id.casefold(),
        target.track_title.casefold(),
    }
    scale_values = {
        "scale_kind": action.scale.kind.value,
        "scale_minimum": float(action.scale.minimum),
        "scale_maximum": float(action.scale.maximum),
    }
    for item in obligations:
        if item.state in {ObligationState.CONFLICTING, ObligationState.UNRESOLVED}:
            raise ValueError("Request obligation is unresolved or conflicting.")
        if item.state is ObligationState.FORBIDDEN:
            if (
                item.owner_kind is OwnerKind.BINDING
                and item.field == "channel"
                and item.value == target.channel
            ):
                raise ValueError(f"Forbidden channel {item.value} was emitted.")
            continue
        if item.owner_kind is OwnerKind.SECTION and item.field == "target":
            if section_title is None or _normalize_requirement_key(section_title) != (
                _normalize_requirement_key(str(item.value))
            ):
                raise ValueError("Requested existing-curve section target was not satisfied.")
            continue
        if item.owner_kind is not OwnerKind.BINDING:
            raise ValueError("Existing-curve update cannot satisfy this obligation kind.")
        owner = item.owner_ref.casefold()
        if owner != "request" and owner not in identities:
            raise ValueError("Requested binding identity is unresolved or ambiguous.")
        if item.field == "target":
            if str(item.value).casefold() not in identities:
                raise ValueError("Requested binding target was not satisfied.")
            continue
        if item.field in scale_values:
            actual = scale_values[item.field]
        elif item.field == "channel":
            actual = target.channel
        elif item.field == "label":
            actual = target.label
        else:
            raise ValueError(f"Existing-curve update cannot satisfy {item.field}.")
        expected = item.value
        if item.field == "scale_kind" and actual is not None:
            actual = str(actual).casefold()
        if item.field in {"scale_minimum", "scale_maximum"} and actual is not None:
            actual = float(actual)
        if actual != expected:
            raise ValueError(f"Requested binding {item.field} was not satisfied.")


def verify_lowered_existing_curve_obligations(
    action: SectionSemanticAction,
    intent: AuthoringDocumentIntent,
    obligations: tuple[RequestObligation, ...],
    *,
    section_context: ResolvedSectionContext,
) -> None:
    """Verify an existing-curve update remains bound to its resolved identity."""
    if getattr(action, "action", None) != "update_curve_scale":
        return
    from .semantic_actions import resolve_existing_curve

    target = resolve_existing_curve(action.target, section_context)
    matches = [
        binding
        for binding in intent.curve_bindings
        if binding.binding_id == target.binding_id
        and binding.section_id == section_context.section_id
        and binding.track_id == target.track_id
    ]
    if len(matches) != 1:
        raise ValueError("Lowered existing-curve update lost its resolved binding identity.")
    binding = matches[0]
    if binding.scale is None:
        raise ValueError("Lowered existing-curve update omitted its requested scale.")
    actual = {
        "scale_kind": str(binding.scale.kind).casefold(),
        "scale_minimum": float(binding.scale.minimum),
        "scale_maximum": float(binding.scale.maximum),
    }
    for item in obligations:
        if item.owner_kind is OwnerKind.BINDING and item.field in actual:
            expected = item.value
            if item.field == "scale_kind":
                expected = str(expected).casefold()
            if actual[item.field] != expected:
                raise ValueError(f"Post-lowering scale {item.field} obligation failed.")


def verify_worker_correction_scope(
    before: object, after: object, allowed_fields: frozenset[str]
) -> None:
    """Reject correction changes outside fields named by violated obligations."""

    def walk(left: object, right: object, path: str = "") -> None:
        if isinstance(left, dict) and isinstance(right, dict):
            for key in set(left) | set(right):
                walk(left.get(key), right.get(key), f"{path}.{key}")
        elif isinstance(left, list) and isinstance(right, list):
            if len(left) != len(right):
                raise ValueError("Worker correction changed collection cardinality.")
            for index, (old, new) in enumerate(zip(left, right, strict=True)):
                walk(old, new, f"{path}.{index}")
        elif left != right and not any(path.endswith(f".{field}") for field in allowed_fields):
            raise ValueError("Worker correction changed an unauthorized semantic path.")

    walk(before.model_dump(mode="json"), after.model_dump(mode="json"))


def _verify_report_obligations(
    document: object,
    dump: dict[str, Any],
    obligations: tuple[RequestObligation, ...],
    *,
    before: object | None,
    report_context: ReportContext | None,
) -> None:
    report = tuple(item for item in obligations if item.owner_kind is OwnerKind.REPORT)
    metadata: list[RequestObligation] = []
    ordered: dict[str, dict[int, str]] = {"service_title": {}, "remark": {}}
    for item in report:
        if item.state is not ObligationState.SET:
            raise ValueError(f"Unsupported report obligation state: {item.state.value}.")
        if item.field in {"depth_presentation_allowed", "page_presentation_allowed"}:
            if item.kind is not ObligationKind.PRESERVATION or item.value is not True:
                raise ValueError("Invalid report preservation permission.")
        elif item.kind is ObligationKind.PRESERVATION:
            raise ValueError(f"Unhandled report preservation permission: {item.field}.")
        elif item.field in {"title", "subtitle"}:
            if not isinstance(item.value, str) or dump.get(item.field) != item.value:
                raise ValueError(f"Post-lowering report {item.field} obligation failed.")
        elif item.field == "tail_enabled":
            if (
                not isinstance(item.value, bool)
                or (dump.get("tail") or {}).get("enabled") is not item.value
            ):
                raise ValueError("Post-lowering report tail obligation failed.")
        elif item.field == "metadata":
            metadata.append(item)
        elif item.field in ordered:
            match = re.fullmatch(rf"{item.field}\.([1-9][0-9]*)", item.slot_key or "")
            if match is None or not isinstance(item.value, str):
                raise ValueError("Invalid ordered report obligation.")
            index = int(match[1])
            if index in ordered[item.field]:
                raise ValueError("Duplicate ordered report obligation.")
            ordered[item.field][index] = item.value
        else:
            raise ValueError(f"Unhandled executable report obligation: {item.field}.")

    for field, expectations in ordered.items():
        if not expectations:
            continue
        if set(expectations) != set(range(1, len(expectations) + 1)):
            raise ValueError(f"Invalid report {field} ordering.")
        expected = [expectations[index] for index in range(1, len(expectations) + 1)]
        if field == "remark":
            actual = [
                {"title": item["title"], "text": item["text"] if not item["lines"] else None}
                for item in dump["remarks"]
            ]
            matched = actual == [json.loads(value) for value in expected]
        else:
            titles = (dump.get("header") or {}).get("service_titles", [])
            matched = [item["value"]["value"] for item in titles] == expected
            if before is not None:
                original = (_plain_json(before).get("header") or {}).get("service_titles", [])
                matched = matched and [item["slot_id"] for item in titles] == [
                    item["slot_id"] for item in original
                ]
        if not matched:
            raise ValueError(f"Post-lowering report {field} value, order, or cardinality failed.")

    if metadata or (report_context is not None and report_context.metadata_bindings):
        _verify_bound_report_metadata(before, document, tuple(metadata), report_context)


def _verify_bound_report_metadata(
    before: object | None,
    after: object,
    metadata: tuple[RequestObligation, ...],
    context: ReportContext | None,
) -> None:
    from ...authoring_reconciler import _current_header_slot
    from .enrichment import inspect_report_context
    from .worker_contracts import resolve_report_metadata

    if (
        before is None
        or context is None
        or not context.snapshot_id
        or not context.metadata_bindings
    ):
        raise ValueError("Required report metadata binding evidence is missing.")
    inspected = context.model_copy(update={"metadata_bindings": None})
    if (
        inspect_report_context(before, context.snapshot_id) != inspected
        or inspect_report_context(after, context.snapshot_id) != inspected
        or resolve_report_metadata(metadata, context) != context.metadata_bindings
        or any(binding.status != "resolved" for binding in context.metadata_bindings)
    ):
        raise ValueError("Stale or mismatched report metadata bindings.")
    expected = {binding.slot_id: str(binding.fact.value) for binding in context.metadata_bindings}
    for slot_id in (*context.general_slot_ids, *context.detail_slot_ids):
        actual = _plain_json(_current_header_slot(after.header, slot_id))
        if slot_id in expected:
            if actual["value"]["value"] != expected[slot_id]:
                raise ValueError("Post-lowering report metadata value failed at its bound slot.")
        elif actual != _plain_json(_current_header_slot(before.header, slot_id)):
            raise ValueError("Unrequested sibling report metadata slot changed.")


def verify_document_obligations(
    document: object,
    obligations: tuple[RequestObligation, ...],
    *,
    grounded_operations: Sequence[object] = (),
    semantic_requirement_ids: frozenset[str] = frozenset(),
    before: object | None = None,
    report_context: ReportContext | None = None,
) -> None:
    """Verify the reconciled candidate before persistence."""
    dump = document.model_dump(mode="json")
    if not isinstance(dump, dict):
        raise ValueError("Candidate document is not JSON-shaped.")
    sections = dump.get("sections", ())
    if not isinstance(sections, list):
        raise ValueError("Candidate document has no section inventory.")
    _verify_report_obligations(
        document, dump, obligations, before=before, report_context=report_context
    )
    grounded_binding_ids = set()
    for operation in grounded_operations:
        object_kind = str(getattr(operation, "object_kind", "")).casefold()
        object_kind = object_kind.rsplit(".", 1)[-1]
        action = str(getattr(operation, "action", "")).casefold()
        action = action.rsplit(".", 1)[-1]
        if object_kind == "curve_binding" and action in {"add", "create", "update"}:
            grounded_binding_ids.add(str(getattr(operation, "object_id", "")))
    split_fill_targets = {
        (item.scope_key, item.owner_ref): item.value
        for item in obligations
        if item.owner_kind is OwnerKind.FILL and item.field == "target"
    }
    for item in obligations:
        if item.owner_kind is OwnerKind.REPORT:
            continue
        scoped_sections = _document_sections_for_obligation(sections, item)
        if item.state in {ObligationState.CONFLICTING, ObligationState.UNRESOLVED}:
            raise ValueError("Candidate contains unresolved request obligations.")
        if item.state is ObligationState.FORBIDDEN:
            if item.owner_kind is OwnerKind.BINDING and item.field == "channel":
                channels = [
                    binding.get("channel")
                    for section in sections
                    for track in section.get("tracks", ())
                    for binding in track.get("bindings", ())
                ]
                if item.value in channels:
                    raise ValueError(f"Forbidden channel {item.value} was persisted.")
            continue
        if item.owner_kind is OwnerKind.TRACK:
            tracks = [track for section in scoped_sections for track in section.get("tracks", ())]
            matches = [
                track
                for track in tracks
                if item.owner_ref in {track.get("id"), track.get("title"), track.get("semantic_id")}
            ]
            if len(matches) != 1:
                raise ValueError(f"Post-lowering track {item.field} obligation failed.")
            if item.field != "target":
                track = matches[0]
                if item.field.startswith("track_scale_"):
                    scale_field = {
                        "track_scale_kind": "kind",
                        "track_scale_minimum": "minimum",
                        "track_scale_maximum": "maximum",
                        "track_scale_unit": "unit",
                    }[item.field]
                    scale = track.get("x_scale")
                    actual = scale.get(scale_field) if isinstance(scale, dict) else None
                elif item.field in {"vertical_main_visible", "vertical_secondary_visible"}:
                    grid = track.get("grid")
                    actual = grid.get(item.field) if isinstance(grid, dict) else None
                else:
                    actual = track.get(item.field)
                if actual != item.value:
                    raise ValueError(f"Post-lowering track {item.field} obligation failed.")
        if item.owner_kind is OwnerKind.BINDING and item.field == "channel":
            matches = []
            owner = item.owner_ref.casefold()
            for section in scoped_sections:
                for track in section.get("tracks", ()):
                    track_identity = {
                        str(track.get("id", "")).casefold(),
                        str(track.get("title", "")).casefold(),
                        str(track.get("semantic_id", "")).casefold(),
                    }
                    for binding_index, binding in enumerate(track.get("bindings", ())):
                        binding_id = str(binding.get("binding_id", binding.get("id", "")))
                        binding_identity = {
                            binding_id.casefold(),
                            str(binding.get("channel", "")).casefold(),
                            str(binding.get("label", "")).casefold(),
                        }
                        if _binding_matches_compiled_slot(
                            binding,
                            binding_index,
                            item.slot_key,
                        ) and (
                            (
                                owner == "request"
                                and (not grounded_binding_ids or binding_id in grounded_binding_ids)
                                and (
                                    item.requirement_id in semantic_requirement_ids
                                    or binding.get("channel") == item.value
                                )
                            )
                            or owner in track_identity
                            or owner in binding_identity
                        ):
                            matches.append(binding)
                channel_satisfied = (
                    bool(matches)
                    if item.requirement_id in semantic_requirement_ids
                    else any(binding.get("channel") == item.value for binding in matches)
                )
                if not channel_satisfied:
                    raise ValueError("Post-lowering channel obligation failed.")
        if item.owner_kind is OwnerKind.BINDING and item.field in {
            "scale_kind",
            "scale_minimum",
            "scale_maximum",
        }:
            matches = []
            owner = item.owner_ref.casefold()
            for section in scoped_sections:
                for track in section.get("tracks", ()):
                    track_identity = {
                        str(track.get("id", "")).casefold(),
                        str(track.get("title", "")).casefold(),
                        str(track.get("semantic_id", "")).casefold(),
                    }
                    for binding_index, binding in enumerate(track.get("bindings", ())):
                        binding_id = str(binding.get("binding_id", binding.get("id", "")))
                        binding_identity = {
                            binding_id.casefold(),
                            str(binding.get("channel", "")).casefold(),
                            str(binding.get("label", "")).casefold(),
                        }
                        if _binding_matches_compiled_slot(
                            binding,
                            binding_index,
                            item.slot_key,
                        ) and (
                            (
                                owner == "request"
                                and (not grounded_binding_ids or binding_id in grounded_binding_ids)
                            )
                            or owner in track_identity
                            or owner in binding_identity
                        ):
                            matches.append(binding)
            scale = matches[0].get("scale") if len(matches) == 1 else None
            key = {
                "scale_kind": "kind",
                "scale_minimum": "minimum",
                "scale_maximum": "maximum",
            }[item.field]
            actual = scale.get(key) if isinstance(scale, dict) else None
            if item.field == "scale_kind" and actual is not None:
                actual = str(actual).casefold()
            if actual != item.value:
                raise ValueError(f"Post-lowering scale {item.field} obligation failed.")
        if item.owner_kind is OwnerKind.SOURCE and item.field == "source":
            sources = [
                section.get("data_source", {}).get("source_path")
                for section in scoped_sections
                if isinstance(section.get("data_source"), dict)
            ]
            requested_source = str(item.value).casefold()
            if not any(
                str(source).casefold() == requested_source
                or str(source).casefold().endswith(f"/{requested_source}")
                for source in sources
            ):
                raise ValueError("Post-lowering source obligation failed.")
        if (
            item.owner_kind is OwnerKind.SECTION
            and item.field == "target"
            and not any(
                item.value in {section.get("id"), section.get("title")}
                for section in scoped_sections
            )
        ):
            raise ValueError("Post-lowering section target obligation failed.")
        if item.owner_kind is OwnerKind.FILL:
            if (item.scope_key, item.owner_ref) in split_fill_targets:
                _verify_split_fill_obligation(
                    scoped_sections,
                    item,
                    split_fill_targets[(item.scope_key, item.owner_ref)],
                    grounded_operations,
                )
                continue
            fills = [
                fill
                for section in scoped_sections
                for track in section.get("tracks", ())
                for fill in track.get("fills", ())
            ]
            if not any(fill.get(item.field) == item.value for fill in fills):
                raise ValueError(f"Post-lowering fill {item.field} obligation failed.")


def _verify_split_fill_obligation(
    sections: list[dict[str, Any]],
    item: RequestObligation,
    target: object,
    operations: Sequence[object],
) -> None:
    """Verify the same scoped fill and binding, not facts scattered across curves."""
    expected = {
        (op.section_id, op.track_id, op.object_id)
        for op in operations
        if isinstance(op, AuthoringOperation) and op.object_kind == "fill" and op.action == "create"
    }
    matches = [
        (track, fill)
        for section in sections
        for track in section.get("tracks", ())
        for fill in track.get("fills", ())
        if (section.get("id"), track.get("id"), fill.get("fill_id")) in expected
        and any(
            binding.get("kind") == "curve"
            and binding.get("binding_id") == fill.get("binding_id")
            and binding.get("channel") == target
            for binding in track.get("bindings", ())
        )
    ]
    if len(matches) != 1:
        raise ValueError("Post-lowering fill target is not one grounded physical binding.")
    _, fill = matches[0]
    if item.field == "target":
        return
    baseline = fill.get("baseline")
    value = (
        (baseline.get("value") if isinstance(baseline, dict) else None)
        if item.field == "baseline"
        else fill.get(item.field)
    )
    if value != item.value:
        raise ValueError(f"Post-lowering fill {item.field} obligation failed.")


class DocumentPostconditionError(ValueError):
    """Identify which canonical pre-publication postcondition rejected a document."""

    def __init__(
        self,
        check: Literal["obligations", "preservation", "semantic"],
        message: str,
    ) -> None:
        """Retain the original safe failure text and the failed check category."""
        self.check = check
        super().__init__(message)


def compile_semantic_publication_contract(
    obligations: Sequence[RequestObligation],
    classifications: Sequence[SemanticRequestClassification],
    *,
    trusted_release: TrustedCatalogRelease | None = None,
) -> SemanticPublicationContract:
    """Bind host channel classifications to exact request obligations.

    Every compiled channel obligation must be classified as an explicit
    physical selector, a semantic family request with a full expected-binding
    record, or unresolved. Unclassified and unresolved requests fail closed.
    """
    channel_obligations = {
        item.requirement_id: item
        for item in obligations
        if item.owner_kind is OwnerKind.BINDING and item.field == "channel"
    }
    classified: dict[str, SemanticRequestClassification] = {}
    for item in classifications:
        if item.requirement_id in classified:
            raise ValueError("semantic_request_classification_duplicate")
        if item.requirement_id not in channel_obligations:
            raise ValueError("semantic_request_classification_unexpected")
        classified[item.requirement_id] = item
    if set(classified) != set(channel_obligations):
        raise ValueError("semantic_request_classification_incomplete")

    expected: list[ExpectedSemanticBinding] = []
    for requirement_id, obligation in channel_obligations.items():
        classification = classified[requirement_id]
        if classification.request_kind == "UNRESOLVED":
            raise ValueError("semantic_request_unresolved")
        if classification.request_kind == "EXPLICIT_PHYSICAL":
            continue
        binding = classification.expected_binding
        if binding is None:
            raise ValueError("semantic_expected_binding_missing")
        if (
            binding.request_sha256 != obligation.request_sha256
            or binding.requirement_id != obligation.requirement_id
            or binding.requested_term != str(obligation.value)
            or (obligation.scope_key is not None and binding.scope_key != obligation.scope_key)
            or (obligation.slot_key is not None and binding.binding_slot != obligation.slot_key)
            or binding.track_scope != obligation.owner_ref
        ):
            raise ValueError("semantic_expected_binding_request_mismatch")
        expected.append(binding)
    return SemanticPublicationContract(
        expected_bindings=tuple(expected),
        trusted_release=trusted_release,
    )


def verify_document_postconditions(
    before: object,
    after: object,
    obligations: tuple[RequestObligation, ...],
    operations: Sequence[object],
    *,
    semantic_contract: SemanticPublicationContract | None = None,
    semantic_evidence: Sequence[SemanticResolutionEvidence] = (),
    report_context: ReportContext | None = None,
    source_base_dir: Path | None = None,
    source_allowed_root: Path | None = None,
) -> None:
    """Verify request, preservation, and optional semantic trust before publish."""
    expected = () if semantic_contract is None else semantic_contract.expected_bindings
    try:
        verify_document_obligations(
            after,
            obligations,
            grounded_operations=operations,
            semantic_requirement_ids=frozenset(item.requirement_id for item in expected),
            before=before,
            report_context=report_context,
        )
    except ValueError as error:
        raise DocumentPostconditionError("obligations", str(error)) from error
    try:
        verify_document_preservation(before, after, operations)
    except ValueError as error:
        raise DocumentPostconditionError("preservation", str(error)) from error
    if not expected and not semantic_evidence:
        return
    if semantic_contract is None:
        raise DocumentPostconditionError("semantic", "semantic_expected_set_missing")
    try:
        if expected and not semantic_evidence:
            raise ValueError("semantic_evidence_set_mismatch")
        release = semantic_contract.trusted_release
        if release is None:
            raise ValueError("semantic_original_release_missing")
        release = revalidate_deployed_catalog_release(release)
        verify_semantic_publication(
            after,
            observed=semantic_evidence,
            contract=semantic_contract,
            release=release,
            source_base_dir=source_base_dir,
            source_allowed_root=source_allowed_root,
        )
    except SemanticCatalogTrustError as error:
        raise DocumentPostconditionError("semantic", error.code) from error
    except ValueError as error:
        raise DocumentPostconditionError("semantic", str(error)) from error


def _document_sections_for_obligation(
    sections: list[object],
    obligation: RequestObligation,
) -> list[dict[str, Any]]:
    """Limit post-lowering checks to the host-bound request section scope."""
    normalized_sections = [section for section in sections if isinstance(section, dict)]
    scope_key = obligation.scope_key
    if scope_key is None:
        return normalized_sections
    scope_kind, separator, scope_name = scope_key.partition(":")
    if not separator or scope_kind not in {"existing", "new"}:
        raise ValueError("Post-lowering obligation has an invalid host scope binding.")
    normalized_scope = _normalize_requirement_key(scope_name)
    matches = [
        section
        for section in normalized_sections
        if normalized_scope
        in {
            _normalize_requirement_key(str(section.get("id", ""))),
            _normalize_requirement_key(str(section.get("title", ""))),
            _normalize_requirement_key(str(section.get("semantic_id", ""))),
        }
    ]
    if len(matches) == 1:
        return matches
    if not matches and len(normalized_sections) == 1:
        return normalized_sections
    raise ValueError("Post-lowering obligation scope did not resolve to one section.")


def _binding_matches_compiled_slot(
    binding: dict[str, Any],
    binding_index: int,
    slot_key: str | None,
) -> bool:
    """Match a binding only when it occupies its independently compiled slot."""
    if slot_key is None:
        return True
    if slot_key.endswith(".binding.raster"):
        return str(binding.get("kind", "")).casefold() == "raster"
    match = re.search(r"\.binding\.(\d+)$", slot_key)
    if match is None:
        return False
    return binding_index == int(match.group(1)) - 1


__all__ = [
    "CanonicalRequirementSet",
    "CollectionSemantics",
    "DocumentPostconditionError",
    "ObligationKind",
    "ObligationState",
    "OwnerKind",
    "RequestCompilationResult",
    "RequestCompilationStatus",
    "RequestObligation",
    "RequirementProvenance",
    "ScopeBindingResult",
    "ScopeBindingStatus",
    "ScopeDeclaration",
    "ScopeDeclarationSet",
    "SharedScopeRule",
    "SupportedAnchor",
    "compile_request_contract",
    "compile_semantic_publication_contract",
    "extract_supported_anchors",
    "extract_supported_obligations",
    "validate_report_obligations",
    "validate_section_obligations",
    "verify_anchor_coverage",
    "verify_document_preservation",
    "verify_document_obligations",
    "verify_document_postconditions",
    "verify_obligation_spans",
    "verify_worker_correction_scope",
]
