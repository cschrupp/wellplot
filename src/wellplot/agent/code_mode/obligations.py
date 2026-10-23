"""Bounded request-owned obligations for the canonical semantic engine."""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

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
]


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

    @model_validator(mode="after")
    def validate_span(self) -> RequestObligation:
        """Require an ordered span and value/state consistency."""
        if self.end_byte <= self.start_byte:
            raise ValueError("Obligation span must be non-empty.")
        if self.state is ObligationState.UNRESOLVED and self.value is not None:
            raise ValueError("Unresolved obligations cannot assert a value.")
        return self


class SupportedAnchor(BaseModel):
    """An independent request anchor before obligation construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1)
    start_byte: int = Field(ge=0)
    end_byte: int = Field(gt=0)
    kind: Literal["explicit", "target", "preservation"]


_REPORT_TITLE_RE = re.compile(
    r"\b(?:rename|set|change)\s+(?:this|the)?\s*report\s+['\"](?P<value>[^'\"]+)['\"]",
    re.IGNORECASE,
)
_ADD_TRACK_RE = re.compile(
    r"\badd\s+(?:a|an)(?:\s+new)?\s+(?P<kind>normal|reference|array)\s+track\s+"
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
    r"\b(?:in|within)\s+(?:the\s+)?(?P<target>[A-Za-z][A-Za-z0-9 _-]{1,48}?)\s+section\b",
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
    r"\b(?i:on)\s+(?i:the\s+)?(?P<target>[A-Za-z][A-Za-z0-9_. -]{0,32}?)\s*[:,]\s*"
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
_FILL_COLOR_RE = re.compile(r"\busing\s+(?P<color>#[0-9a-f]{6})\b", re.IGNORECASE)
_FILL_ALPHA_RE = re.compile(r"\bat\s+(?P<alpha>[0-9]+(?:\.[0-9]+)?)%\s+opacity\b", re.IGNORECASE)


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
    grouped: dict[tuple[OwnerKind, str, str], set[object]] = {}
    forbidden: set[tuple[OwnerKind, str, str]] = set()
    for item in obligations:
        if item.state is ObligationState.SET:
            grouped.setdefault((item.owner_kind, item.owner_ref, item.field), set()).add(item.value)
        elif item.state is ObligationState.FORBIDDEN:
            forbidden.add((item.owner_kind, item.owner_ref, item.field))
    conflicts = {key for key, values in grouped.items() if len(values) > 1 or key in forbidden}
    return tuple(
        item.model_copy(update={"state": ObligationState.CONFLICTING})
        if (item.owner_kind, item.owner_ref, item.field) in conflicts
        else item
        for item in obligations
    )


def _patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    """Return the independent supported-anchor patterns."""
    return (
        ("explicit", _REPORT_TITLE_RE),
        ("explicit", _ADD_TRACK_RE),
        ("explicit", _TRACK_LINE_RE),
        ("target", _SECTION_TARGET_RE),
        ("target", _TRACK_TARGET_RE),
        ("explicit", _TARGET_CHANNEL_RE),
        ("explicit", _CHANNEL_RE),
        ("explicit", _CHANNEL_LIST_RE),
        ("explicit", _QUOTED_CHANNEL_RE),
        ("explicit", _SOURCE_RE),
        ("explicit", _SCALE_RE),
        ("explicit", _SCALE_CLAUSE_RE),
        ("explicit", _FILL_COLOR_RE),
        ("explicit", _FILL_ALPHA_RE),
    )


def extract_supported_anchors(request: str) -> tuple[SupportedAnchor, ...]:
    """Return the independent, bounded anchor inventory used for coverage."""
    data = request.encode("utf-8")
    anchors: list[SupportedAnchor] = []
    for kind, pattern in _patterns():
        for match in pattern.finditer(request):
            start = _byte_offset(request, match.start())
            end = _byte_offset(request, match.end())
            anchors.append(
                SupportedAnchor(
                    text=data[start:end].decode("utf-8"),
                    start_byte=start,
                    end_byte=end,
                    kind=kind,  # type: ignore[arg-type]
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
    for pattern in (_SECTION_TARGET_RE, _TRACK_TARGET_RE):
        for match in pattern.finditer(request):
            target = match.group("target").strip()
            obligations.append(
                _make_obligation(
                    request=request,
                    request_sha256=request_sha256,
                    match=match,
                    kind=ObligationKind.TARGET_REFERENCE,
                    owner_kind=OwnerKind.SECTION
                    if "section" in match.group(0).casefold()
                    else OwnerKind.TRACK,
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
                scope="global",
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
    for pattern in (_SCALE_RE, _SCALE_CLAUSE_RE):
        for match in pattern.finditer(request):
            owner = match.groupdict().get("owner") or "request"
            for field, value in (
                ("scale_kind", match.group("kind").lower()),
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
    return _append_conflicts(obligations)


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
            if literal not in span_text:
                raise ValueError("Obligation value is not present in its request span.")


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
    action: SectionSemanticAction, obligations: tuple[RequestObligation, ...]
) -> None:
    """Require every supported section obligation before canonical lowering."""
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
        if item.owner_ref.casefold() == "request":
            if item.field == "channel":
                return [
                    binding
                    for binding in bindings
                    if getattr(binding, "channel", None) == item.value
                ]
            return bindings
        owner = item.owner_ref.casefold()
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
                if getattr(track, "semantic_id", None) == item.owner_ref
                or getattr(track, "title", None) == item.owner_ref
            ]
            if len(matches) != 1:
                raise ValueError("Requested track identity is unresolved or ambiguous.")
            if item.field == "target":
                continue
            actual = getattr(matches[0], item.field, None)
            if item.field == "width_mm" and actual is not None:
                actual = float(actual)
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
            if item.field in {"channel", "label"}:
                actual = getattr(binding, item.field, None)
            else:
                scale = getattr(binding, "scale", None)
                scale_field = {
                    "scale_kind": "kind",
                    "scale_minimum": "minimum",
                    "scale_maximum": "maximum",
                }.get(item.field)
                actual = getattr(scale, scale_field, None) if scale_field else None
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
        if (
            item.owner_kind is OwnerKind.SECTION
            and item.field == "target"
            and (section is None or getattr(section, "title", None) != item.value)
        ):
            raise ValueError("Requested section target was not satisfied.")


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
    document: object, obligations: tuple[RequestObligation, ...]
) -> None:
    """Verify the reconciled candidate before persistence."""
    dump = document.model_dump(mode="json")
    if not isinstance(dump, dict):
        raise ValueError("Candidate document is not JSON-shaped.")
    sections = dump.get("sections", ())
    if not isinstance(sections, list):
        raise ValueError("Candidate document has no section inventory.")
    for item in obligations:
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
            tracks = [track for section in sections for track in section.get("tracks", ())]
            matches = [
                track
                for track in tracks
                if item.owner_ref in {track.get("id"), track.get("title"), track.get("semantic_id")}
            ]
            if len(matches) != 1:
                raise ValueError(f"Post-lowering track {item.field} obligation failed.")
            if item.field != "target" and matches[0].get(item.field) != item.value:
                raise ValueError(f"Post-lowering track {item.field} obligation failed.")
        if item.owner_kind is OwnerKind.BINDING and item.field == "channel":
            matches = []
            owner = item.owner_ref.casefold()
            for section in sections:
                for track in section.get("tracks", ()):
                    track_identity = {
                        str(track.get("id", "")).casefold(),
                        str(track.get("title", "")).casefold(),
                        str(track.get("semantic_id", "")).casefold(),
                    }
                    for binding in track.get("bindings", ()):
                        binding_identity = {
                            str(binding.get("id", "")).casefold(),
                            str(binding.get("channel", "")).casefold(),
                            str(binding.get("label", "")).casefold(),
                        }
                        if (
                            (owner == "request" and binding.get("channel") == item.value)
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
            for section in sections:
                for track in section.get("tracks", ()):
                    track_identity = {
                        str(track.get("id", "")).casefold(),
                        str(track.get("title", "")).casefold(),
                        str(track.get("semantic_id", "")).casefold(),
                    }
                    for binding in track.get("bindings", ()):
                        binding_identity = {
                            str(binding.get("id", "")).casefold(),
                            str(binding.get("channel", "")).casefold(),
                            str(binding.get("label", "")).casefold(),
                        }
                        if (
                            owner == "request"
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
                for section in sections
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
                item.value in {section.get("id"), section.get("title")} for section in sections
            )
        ):
            raise ValueError("Post-lowering section target obligation failed.")
        if item.owner_kind is OwnerKind.FILL:
            fills = [
                fill
                for section in sections
                for track in section.get("tracks", ())
                for fill in track.get("fills", ())
            ]
            if not any(fill.get(item.field) == item.value for fill in fills):
                raise ValueError(f"Post-lowering fill {item.field} obligation failed.")


__all__ = [
    "ObligationKind",
    "ObligationState",
    "OwnerKind",
    "RequestObligation",
    "SupportedAnchor",
    "extract_supported_anchors",
    "extract_supported_obligations",
    "validate_report_obligations",
    "validate_section_obligations",
    "verify_document_obligations",
    "verify_obligation_spans",
    "verify_worker_correction_scope",
]
