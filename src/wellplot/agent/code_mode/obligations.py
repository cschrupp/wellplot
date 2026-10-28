"""Bounded request-owned obligations for the canonical semantic engine."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from ...model.intent import AuthoringDocumentIntent
    from .enrichment import ResolvedSectionContext
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
    field: FieldName
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
            identity = f"{self.owner_kind}:{self.owner_ref}:{self.field}:{self.start_byte}"
            object.__setattr__(
                self, "requirement_id", hashlib.sha256(identity.encode()).hexdigest()[:24]
            )
        return self


class SupportedAnchor(BaseModel):
    """An independent request anchor before obligation construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1)
    start_byte: int = Field(ge=0)
    end_byte: int = Field(gt=0)
    kind: Literal["explicit", "target", "preservation", "presentation", "scope"]
    field: FieldName
    family: str | None = None
    required_fields: tuple[FieldName, ...] = ()


class CanonicalRequirementSet(BaseModel):
    """Single value-bearing, versioned compilation of request semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    language_version: str = Field(min_length=1)
    requirements: tuple[RequestObligation, ...] = ()
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
    field: FieldName
    slot_key: str | None = None
    code: str = Field(min_length=1)
    expected_value: str | float | int | bool | None = None


class ValidationIssueSet(BaseModel):
    """Stable, ordered collection of unsatisfied canonical requirements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issues: tuple[ValidationIssue, ...] = ()


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
    field: FieldName,
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
        ("explicit", _SCALE_PREFIX_RANGE_RE),
        ("explicit", _FILL_COLOR_RE),
        ("explicit", _FILL_ALPHA_RE),
    )


def extract_supported_anchors(request: str) -> tuple[SupportedAnchor, ...]:
    """Return the independent, bounded anchor inventory used for coverage."""
    data = request.encode("utf-8")
    anchors: list[SupportedAnchor] = []
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
    obligations: list[RequestObligation] = []
    for match in _REPORT_TITLE_RE.finditer(request):
        obligations.append(
            _make_obligation(
                request=request,
                request_sha256=request_sha256,
                match=match,
                kind=ObligationKind.EXPLICIT_FIELD,
                owner_kind=OwnerKind.REPORT,
                owner_ref="report",
                field="title",
                value=match.group("value"),
            )
        )
    for pattern in (_ADD_TRACK_RE, _TRACK_LINE_RE):
        for match in pattern.finditer(request):
            owner = match.groupdict().get("title") or match.group("owner")
            if match.groupdict().get("title"):
                obligations.append(
                    _make_obligation(
                        request=request,
                        request_sha256=request_sha256,
                        match=match,
                        kind=ObligationKind.EXPLICIT_FIELD,
                        owner_kind=OwnerKind.TRACK,
                        owner_ref=owner,
                        field="title",
                        value=match.group("title"),
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
    return _append_conflicts(obligations)


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
    obligations = list(extract_supported_obligations(request))
    anchors = extract_supported_anchors(request)
    scopes = _request_scope_declarations(request, request_sha256)
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
    obligations: tuple[RequestObligation, ...],
    *,
    anchors: tuple[SupportedAnchor, ...] | None = None,
) -> None:
    """Require every independently recognized anchor to have an obligation."""
    anchors = anchors if anchors is not None else extract_supported_anchors(request)
    for anchor in anchors:
        if anchor.kind == "scope":
            continue
        if not any(
            item.field == anchor.field
            and item.start_byte <= anchor.start_byte
            and item.end_byte >= anchor.end_byte
            for item in obligations
        ):
            raise ValueError("Supported request anchor was not converted to an obligation.")


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
    if (object_kind == "report" and not path) or _identity_matches(value, object_id):
        found.append(path)
    for key, child in value.items():
        if isinstance(child, (Mapping, list, tuple)):
            found.extend(
                _object_paths(
                    child,
                    object_kind=object_kind,
                    object_id=object_id,
                    path=path + (str(key),),
                )
            )
    return found


def _changed_paths(left: object, right: object, path: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    """Return changed JSON paths, treating collection shape changes atomically."""
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        changed: set[tuple[str, ...]] = set()
        for key in set(left) | set(right):
            changed |= _changed_paths(left.get(key), right.get(key), path + (str(key),))
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
) -> None:
    """Reject candidate changes outside the canonical reconciliation operations."""
    before_json = _plain_json(before)
    after_json = _plain_json(after)
    changed = _changed_paths(before_json, after_json)
    if not changed:
        return
    allowed: set[tuple[str, ...]] = set()
    for operation in operations:
        object_kind = str(getattr(operation, "object_kind", "")).casefold()
        object_kind = object_kind.rsplit(".", 1)[-1]
        object_id = str(getattr(operation, "object_id", ""))
        action = str(getattr(operation, "action", "")).casefold().rsplit(".", 1)[-1]
        payload = getattr(operation, "payload", {})
        prefixes = _object_paths(before_json, object_kind=object_kind, object_id=object_id)
        prefixes += _object_paths(after_json, object_kind=object_kind, object_id=object_id)
        if object_kind == "header":
            prefixes = [("header",)]
        if object_kind == "report":
            prefixes = [()]
        if not prefixes:
            continue
        patch = payload.get("patch") if isinstance(payload, Mapping) else None
        for prefix in prefixes:
            if action == "update" and isinstance(patch, Mapping):
                allowed.update(prefix + (str(key),) for key in patch)
            else:
                allowed.add(prefix)
                # Collection creates/removes are represented by a changed list
                # at the parent path, not by the newly addressed item path.
                if action in {"create", "remove", "move"} and prefix:
                    allowed.add(prefix[:-1])
    if any(not any(path[: len(prefix)] == prefix for prefix in allowed) for path in changed):
        raise ValueError(
            "Candidate document changed outside the authorized reconciliation envelope."
        )


def validate_report_obligations(
    response: object, obligations: tuple[RequestObligation, ...]
) -> None:
    """Require report-owned obligations to be represented by the worker response."""
    title = getattr(response, "title", None)
    for item in obligations:
        if (
            item.owner_kind is OwnerKind.REPORT
            and item.field == "title"
            and (item.state is ObligationState.CONFLICTING or title != item.value)
        ):
            raise ValueError("Requested report title was not satisfied.")


def validate_section_obligations(
    action: SectionSemanticAction,
    obligations: tuple[RequestObligation, ...],
    *,
    section_context: ResolvedSectionContext | None = None,
    section_title: str | None = None,
) -> None:
    """Require every supported section obligation before canonical lowering."""
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
        if item.owner_kind is OwnerKind.TRACK:
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


def verify_document_obligations(
    document: object,
    obligations: tuple[RequestObligation, ...],
    *,
    grounded_operations: Sequence[object] = (),
) -> None:
    """Verify the reconciled candidate before persistence."""
    dump = document.model_dump(mode="json")
    if not isinstance(dump, dict):
        raise ValueError("Candidate document is not JSON-shaped.")
    sections = dump.get("sections", ())
    if not isinstance(sections, list):
        raise ValueError("Candidate document has no section inventory.")
    grounded_binding_ids = set()
    for operation in grounded_operations:
        object_kind = str(getattr(operation, "object_kind", "")).casefold()
        object_kind = object_kind.rsplit(".", 1)[-1]
        action = str(getattr(operation, "action", "")).casefold()
        action = action.rsplit(".", 1)[-1]
        if object_kind == "curve_binding" and action in {"add", "create", "update"}:
            grounded_binding_ids.add(str(getattr(operation, "object_id", "")))
    for item in obligations:
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
        if (
            item.owner_kind is OwnerKind.REPORT
            and item.field == "title"
            and dump.get("title") != item.value
        ):
            raise ValueError("Post-lowering report title obligation failed.")
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
                                and binding.get("channel") == item.value
                            )
                            or owner in track_identity
                            or owner in binding_identity
                        ):
                            matches.append(binding)
            if not any(binding.get("channel") == item.value for binding in matches):
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
            fills = [
                fill
                for section in scoped_sections
                for track in section.get("tracks", ())
                for fill in track.get("fills", ())
            ]
            if not any(fill.get(item.field) == item.value for fill in fills):
                raise ValueError(f"Post-lowering fill {item.field} obligation failed.")


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
    "extract_supported_anchors",
    "extract_supported_obligations",
    "validate_report_obligations",
    "validate_section_obligations",
    "verify_anchor_coverage",
    "verify_document_preservation",
    "verify_document_obligations",
    "verify_obligation_spans",
    "verify_worker_correction_scope",
]
