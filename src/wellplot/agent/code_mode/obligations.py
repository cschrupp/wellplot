"""Bounded, request-owned semantic obligations for the canonical engine.

This module intentionally recognizes only a small vocabulary of explicit
request facts. Unknown language is not promoted into executable semantics.
"""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
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


class RequestObligation(BaseModel):
    """One typed fact grounded in exact UTF-8 request bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ObligationKind
    owner_kind: OwnerKind
    owner_ref: str = Field(min_length=1)
    field: str = Field(min_length=1)
    value: str | float | int | bool | None = None
    state: ObligationState = ObligationState.SET
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_byte: int = Field(ge=0)
    end_byte: int = Field(gt=0)
    span_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_span(self) -> RequestObligation:
        """Require a non-empty, ordered request span."""
        if self.end_byte <= self.start_byte:
            raise ValueError("Obligation span must be non-empty.")
        if self.state is ObligationState.UNRESOLVED and self.value is not None:
            raise ValueError("Unresolved obligations cannot assert a value.")
        return self


_REPORT_TITLE_RE = re.compile(
    r"\b(?:rename|set|change)\s+(?:this|the)?\s*report\s+['\"](?P<value>[^'\"]+)['\"]",
    re.IGNORECASE,
)
_TRACK_RE = re.compile(
    r"\bTrack\s+(?P<owner>[A-Za-z0-9_. -]+?)\s*:\s*"
    r"(?P<kind>normal|reference|array)\b[^\n;]*?"
    r"\bwidth\s+(?P<width>[0-9]+(?:\.[0-9]+)?)\s*mm\b",
    re.IGNORECASE,
)
_CHANNEL_RE = re.compile(
    r"\b(?:use|plot|bind|select)\s+(?P<channel>[A-Z][A-Z0-9_]*)\b",
    re.IGNORECASE,
)
_SOURCE_RE = re.compile(r"(?P<source>[A-Za-z0-9_./ -]+\.(?:las|dlis))\b", re.IGNORECASE)
_TARGET_RE = re.compile(
    r"\b(?:in|on|to)\s+(?:the\s+)?"
    r"(?P<target>[A-Za-z][A-Za-z0-9 _-]{1,48}?)"
    r"(?=\s+(?:with|using|and|at|for)\b|[,.;:]|$)",
    re.IGNORECASE,
)


def _request_identity(request: str) -> tuple[bytes, str]:
    """Return exact request bytes and their identity."""
    data = request.encode("utf-8")
    return data, hashlib.sha256(data).hexdigest()


def _make_obligation(
    *,
    data: bytes,
    request_sha256: str,
    match: re.Match[str],
    kind: ObligationKind,
    owner_kind: OwnerKind,
    owner_ref: str,
    field: str,
    value: str | float | None,
) -> RequestObligation:
    """Build an obligation from a host-owned regex span."""
    start, end = match.span()
    span = data[start:end]
    return RequestObligation(
        kind=kind,
        owner_kind=owner_kind,
        owner_ref=owner_ref.strip(),
        field=field,
        value=value.strip() if isinstance(value, str) else value,
        request_sha256=request_sha256,
        start_byte=start,
        end_byte=end,
        span_sha256=hashlib.sha256(span).hexdigest(),
    )


def extract_supported_obligations(request: str) -> tuple[RequestObligation, ...]:
    """Extract only explicit, supported request anchors."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Authoritative request must be non-empty.")
    data, request_sha256 = _request_identity(request)
    obligations: list[RequestObligation] = []
    for match in _REPORT_TITLE_RE.finditer(request):
        obligations.append(
            _make_obligation(
                data=data,
                request_sha256=request_sha256,
                match=match,
                kind=ObligationKind.EXPLICIT_FIELD,
                owner_kind=OwnerKind.REPORT,
                owner_ref="report",
                field="title",
                value=match.group("value"),
            )
        )
    for match in _TRACK_RE.finditer(request):
        owner = match.group("owner").strip()
        obligations.extend(
            (
                _make_obligation(
                    data=data,
                    request_sha256=request_sha256,
                    match=match,
                    kind=ObligationKind.EXPLICIT_FIELD,
                    owner_kind=OwnerKind.TRACK,
                    owner_ref=owner,
                    field="kind",
                    value=match.group("kind").lower(),
                ),
                _make_obligation(
                    data=data,
                    request_sha256=request_sha256,
                    match=match,
                    kind=ObligationKind.EXPLICIT_FIELD,
                    owner_kind=OwnerKind.TRACK,
                    owner_ref=owner,
                    field="width_mm",
                    value=float(match.group("width")),
                ),
            )
        )
    for match in _CHANNEL_RE.finditer(request):
        obligations.append(
            _make_obligation(
                data=data,
                request_sha256=request_sha256,
                match=match,
                kind=ObligationKind.EXPLICIT_FIELD,
                owner_kind=OwnerKind.BINDING,
                owner_ref="request",
                field="channel",
                value=match.group("channel").upper(),
            )
        )
    for match in _SOURCE_RE.finditer(request):
        obligations.append(
            _make_obligation(
                data=data,
                request_sha256=request_sha256,
                match=match,
                kind=ObligationKind.EXPLICIT_FIELD,
                owner_kind=OwnerKind.SOURCE,
                owner_ref="request",
                field="source",
                value=match.group("source"),
            )
        )
    for match in _TARGET_RE.finditer(request):
        target = match.group("target").strip()
        if target.lower() in {"it", "this", "that"}:
            continue
        obligations.append(
            _make_obligation(
                data=data,
                request_sha256=request_sha256,
                match=match,
                kind=ObligationKind.TARGET_REFERENCE,
                owner_kind=OwnerKind.SECTION,
                owner_ref=target,
                field="target",
                value=target,
            )
        )
    return tuple(obligations)


def verify_obligation_spans(request: str, obligations: tuple[RequestObligation, ...]) -> None:
    """Re-slice and verify every obligation against the authoritative request."""
    data, request_sha256 = _request_identity(request)
    for obligation in obligations:
        if obligation.request_sha256 != request_sha256:
            raise ValueError("Obligation request identity mismatch.")
        span = data[obligation.start_byte : obligation.end_byte]
        if hashlib.sha256(span).hexdigest() != obligation.span_sha256:
            raise ValueError("Obligation span digest mismatch.")
        if obligation.value is not None:
            text = span.decode("utf-8").lower()
            literal = str(obligation.value).lower()
            if isinstance(obligation.value, float):
                literal = literal.rstrip("0").rstrip(".")
            if literal not in text:
                raise ValueError("Obligation value is not present in its claimed request span.")


def validate_report_obligations(
    response: object, obligations: tuple[RequestObligation, ...]
) -> None:
    """Require report-owned obligations to be represented by the worker response."""
    title = getattr(response, "title", None)
    for obligation in obligations:
        if (
            obligation.owner_kind is OwnerKind.REPORT
            and obligation.field == "title"
            and title != obligation.value
        ):
            raise ValueError("Requested report title was not satisfied.")


def validate_section_obligations(
    action: SectionSemanticAction,
    obligations: tuple[RequestObligation, ...],
) -> None:
    """Require track and channel obligations before canonical lowering."""
    tracks = []
    if hasattr(action, "tracks"):
        tracks.extend(action.tracks or ())
    if hasattr(action, "track") and action.track is not None:
        tracks.append(action.track)
    for obligation in obligations:
        if obligation.owner_kind is OwnerKind.TRACK:
            matches = [
                track
                for track in tracks
                if getattr(track, "semantic_id", None) == obligation.owner_ref
                or getattr(track, "title", None) == obligation.owner_ref
            ]
            if len(matches) != 1:
                raise ValueError("Requested track identity is unresolved or ambiguous.")
            track = matches[0]
            actual = getattr(track, obligation.field, None)
            expected = obligation.value
            if obligation.field == "width_mm" and actual is not None:
                actual = float(actual)
            if actual != expected:
                raise ValueError(f"Requested track {obligation.field} was not satisfied.")
        if obligation.owner_kind is OwnerKind.BINDING and obligation.field == "channel":
            channels = [
                getattr(binding, "channel", None)
                for track in tracks
                for binding in getattr(track, "bindings", ())
            ]
            if obligation.value not in channels:
                raise ValueError("Requested channel was not satisfied.")


def verify_document_obligations(
    document: object,
    obligations: tuple[RequestObligation, ...],
) -> None:
    """Verify obligations against the reconciled candidate before persistence."""
    dump = document.model_dump(mode="json")
    if not isinstance(dump, dict):
        raise ValueError("Candidate document is not JSON-shaped.")
    if any(
        item.owner_kind is OwnerKind.REPORT
        and item.field == "title"
        and dump.get("title") != item.value
        for item in obligations
    ):
        raise ValueError("Post-lowering report title obligation failed.")
    sections = dump.get("sections", ())
    if not isinstance(sections, list):
        raise ValueError("Candidate document has no section inventory.")
    for item in obligations:
        if item.owner_kind is OwnerKind.TARGET_REFERENCE:
            continue
        if item.owner_kind is OwnerKind.TRACK:
            tracks = [track for section in sections for track in section.get("tracks", ())]
            matches = [
                track
                for track in tracks
                if track.get("id") == item.owner_ref
                or track.get("title") == item.owner_ref
                or track.get("semantic_id") == item.owner_ref
            ]
            if len(matches) != 1 or matches[0].get(item.field) != item.value:
                raise ValueError(f"Post-lowering track {item.field} obligation failed.")
        if item.owner_kind is OwnerKind.BINDING and item.field == "channel":
            channels = [
                binding.get("channel")
                for section in sections
                for track in section.get("tracks", ())
                for binding in track.get("bindings", ())
            ]
            if item.value not in channels:
                raise ValueError("Post-lowering channel obligation failed.")


__all__ = [
    "ObligationKind",
    "ObligationState",
    "OwnerKind",
    "RequestObligation",
    "extract_supported_obligations",
    "validate_report_obligations",
    "validate_section_obligations",
    "verify_document_obligations",
    "verify_obligation_spans",
]
