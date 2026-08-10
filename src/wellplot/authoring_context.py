###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################

"""Deterministic contextual resolution for authoring intents.

This module resolves references before a reconciler or executor is involved.
It deliberately does not load files, call MCP tools, or mutate a document.
Callers provide the current document, optional scaffold/default mappings, and
source-channel inspection results explicitly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from enum import StrEnum
from re import sub
from typing import Any, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from .model.authoring import AuthoringDocumentSpec, AuthoringHeaderSpec
from .model.intent import (
    AuthoringClearIntent,
    AuthoringCurveBindingIntent,
    AuthoringDocumentIntent,
    AuthoringRasterBindingIntent,
    AuthoringRemoveIntent,
    AuthoringSectionIntent,
    AuthoringTrackIntent,
)


class _ContextModel(BaseModel):
    """Strict base model for contextual resolution results."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AuthoringResolutionSource(StrEnum):
    """Source selected for one effective authoring value."""

    EXPLICIT = "explicit"
    PRESERVED = "preserved"
    DEFAULT = "default"
    SCAFFOLD = "scaffold"


class AuthoringResolutionStatus(StrEnum):
    """Outcome status for one contextual resolution decision."""

    RESOLVED = "resolved"
    CLEARED = "cleared"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"
    INVALID = "invalid"


class AuthoringChannelAlias(_ContextModel):
    """Reusable semantic alias entry for source-channel resolution."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    mnemonics: list[str] = Field(default_factory=list)


class AuthoringChannelCandidate(_ContextModel):
    """One source channel available to a section context."""

    mnemonic: str = Field(min_length=1)
    kind: str = Field(default="scalar", min_length=1)
    aliases: list[str] = Field(default_factory=list)
    unit: str | None = Field(default=None, min_length=1)
    description: str = ""
    value_shape: list[int] = Field(default_factory=list)
    source_path: str | None = Field(default=None, min_length=1)


class AuthoringSourceContext(_ContextModel):
    """Inspected metadata for one source available to an authoring request."""

    source_path: str = Field(min_length=1)
    source_format: str = Field(min_length=1)
    dataset_name: str = ""
    channels: list[AuthoringChannelCandidate] = Field(default_factory=list)
    metadata_keys: list[str] = Field(default_factory=list)
    depth_unit: str | None = Field(default=None, min_length=1)
    depth_min: float | None = None
    depth_max: float | None = None
    sample_count: int | None = None
    warnings: list[str] = Field(default_factory=list)


class AuthoringSectionContext(_ContextModel):
    """Current or requested section context used during intent extraction."""

    section_id: str = Field(min_length=1)
    title: str = ""
    source_path: str | None = Field(default=None, min_length=1)
    source_format: str = "auto"
    depth_range: list[float] | None = None
    track_ids: list[str] = Field(default_factory=list)
    track_kinds: list[str] = Field(default_factory=list)
    available_channels: list[AuthoringChannelCandidate] = Field(default_factory=list)


class AuthoringResolutionDecision(_ContextModel):
    """One precedence or contextual-reference decision."""

    path: str = Field(min_length=1)
    source: AuthoringResolutionSource
    status: AuthoringResolutionStatus
    value: Any = None
    requested: Any = None
    matched_alias: str | None = None
    candidates: list[str] = Field(default_factory=list)


class AuthoringContextIssue(_ContextModel):
    """A deterministic issue that blocks safe desired-state resolution."""

    path: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    candidates: list[str] = Field(default_factory=list)


class AuthoringContextSnapshot(_ContextModel):
    """Read-only context inventory prepared before desired-state extraction."""

    draft_logfile: str = Field(min_length=1)
    object_inventory: dict[str, Any] = Field(default_factory=dict)
    sections: list[AuthoringSectionContext] = Field(default_factory=list)
    sources: list[AuthoringSourceContext] = Field(default_factory=list)
    requested_source_slots: dict[str, str] = Field(default_factory=dict)
    header_slots: dict[str, Any] = Field(default_factory=dict)
    issues: list[AuthoringContextIssue] = Field(default_factory=list)


class AuthoringContextResolution(_ContextModel):
    """Resolved intent plus decisions and blocking contextual issues."""

    ready: bool
    resolved_intent: AuthoringDocumentIntent
    resolved_values: dict[str, Any] = Field(default_factory=dict)
    decisions: list[AuthoringResolutionDecision] = Field(default_factory=list)
    issues: list[AuthoringContextIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


AuthoringChannelInput: TypeAlias = str | AuthoringChannelCandidate | Mapping[str, Any]

_MISSING = object()
_IDENTITY_FIELDS = (
    "section_id",
    "track_id",
    "binding_id",
    "fill_id",
    "annotation_id",
    "remark_id",
    "slot_id",
    "id",
)


def _normalize_token(value: object) -> str:
    """Normalize a human or source token for deterministic comparison."""
    return sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _plain_value(value: object) -> object:
    """Convert model values to JSON-compatible structures for result payloads."""
    if isinstance(value, BaseModel):
        return value.model_dump(
            mode="python",
            exclude_unset=isinstance(value, AuthoringDocumentIntent),
        )
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain_value(item) for key, item in value.items()}
    return value


def _mapping_value(value: object, key: str) -> object:
    """Read a mapping key while preserving an explicit ``None`` value."""
    if isinstance(value, Mapping) and key in value:
        return value[key]
    return _MISSING


def _context_path_key(value: object) -> str:
    """Normalize a source path enough to join inspection and section records."""
    return str(value).strip().replace("\\", "/").removeprefix("./").lower()


def _source_slot_section_id(slot: str, section_ids: Sequence[str]) -> str:
    """Match a short source slot to an existing section naming convention."""
    normalized_slot = _normalize_token(slot)
    for section_id in section_ids:
        normalized_section = _normalize_token(section_id)
        if normalized_section == normalized_slot:
            return section_id
        if normalized_section.removesuffix("pass") == normalized_slot:
            return section_id

    pass_suffixes = {
        section_id[len(section_id.removesuffix("_pass")) :]
        for section_id in section_ids
        if section_id.endswith("_pass")
    }
    if len(pass_suffixes) == 1 and not normalized_slot.endswith("pass"):
        suffix = next(iter(pass_suffixes))
        candidate = f"{slot}{suffix}"
        if candidate:
            return candidate
    return slot


def build_authoring_context_snapshot(
    *,
    draft_logfile: str,
    existing: AuthoringDocumentSpec,
    summary: Mapping[str, Any],
    source_inspections: Mapping[str, Mapping[str, Any]],
    requested_source_slots: Mapping[str, str] | None = None,
    header_slots: Mapping[str, Any] | None = None,
    issues: Sequence[AuthoringContextIssue] = (),
) -> AuthoringContextSnapshot:
    """Build one typed, read-only context snapshot from inspected MCP data."""
    source_contexts: list[AuthoringSourceContext] = []
    source_by_key: dict[str, AuthoringSourceContext] = {}
    for requested_path, raw_inspection in source_inspections.items():
        if not isinstance(raw_inspection, Mapping):
            continue
        source_path = str(raw_inspection.get("source_path") or requested_path).strip()
        if not source_path:
            continue
        index = raw_inspection.get("index")
        index_mapping = index if isinstance(index, Mapping) else {}
        channels: list[AuthoringChannelCandidate] = []
        for raw_channel in raw_inspection.get("channels", []):
            if not isinstance(raw_channel, Mapping):
                continue
            mnemonic = str(raw_channel.get("mnemonic", "")).strip()
            if not mnemonic:
                continue
            channels.append(
                AuthoringChannelCandidate(
                    mnemonic=mnemonic,
                    kind=str(raw_channel.get("kind", "scalar")).strip() or "scalar",
                    unit=(
                        str(raw_channel["value_unit"]).strip()
                        if raw_channel.get("value_unit")
                        else None
                    ),
                    description=str(raw_channel.get("description", "")),
                    value_shape=[
                        int(value)
                        for value in raw_channel.get("value_shape", [])
                        if isinstance(value, int)
                    ],
                    source_path=source_path,
                )
            )
        source_context = AuthoringSourceContext(
            source_path=source_path,
            source_format=(
                str(raw_inspection.get("source_format_detected", "auto")).strip()
                or "auto"
            ),
            dataset_name=str(raw_inspection.get("dataset_name", "")),
            channels=channels,
            metadata_keys=[
                str(key) for key in raw_inspection.get("metadata_keys", []) if str(key)
            ],
            depth_unit=(
                str(index_mapping["depth_unit"]).strip()
                if index_mapping.get("depth_unit")
                else None
            ),
            depth_min=index_mapping.get("depth_min"),
            depth_max=index_mapping.get("depth_max"),
            sample_count=index_mapping.get("sample_count"),
            warnings=[
                str(warning)
                for warning in raw_inspection.get("warnings", [])
                if str(warning).strip()
            ],
        )
        source_contexts.append(source_context)
        source_by_key[_context_path_key(requested_path)] = source_context
        source_by_key[_context_path_key(source_path)] = source_context

    raw_source_slots = {
        str(slot).strip(): str(path).strip()
        for slot, path in (requested_source_slots or {}).items()
        if str(slot).strip() and str(path).strip()
    }
    summary_section_ids = [
        str(section.get("id", "")).strip()
        for section in summary.get("sections", [])
        if isinstance(section, Mapping) and str(section.get("id", "")).strip()
    ]
    source_slots = {
        _source_slot_section_id(slot, summary_section_ids): path
        for slot, path in raw_source_slots.items()
    }
    sections: list[AuthoringSectionContext] = []
    section_ids: set[str] = set()
    for raw_section in summary.get("sections", []):
        if not isinstance(raw_section, Mapping):
            continue
        section_id = str(raw_section.get("id", "")).strip()
        if not section_id:
            continue
        section_ids.add(section_id)
        summary_source_path = str(raw_section.get("source_path", "")).strip() or None
        source_path = source_slots.get(section_id, summary_source_path)
        source_context = source_by_key.get(_context_path_key(source_path)) if source_path else None
        summary_channels = raw_section.get("available_channels", [])
        available_channels = (
            list(source_context.channels)
            if source_context is not None
            else [
                AuthoringChannelCandidate(mnemonic=str(channel).strip())
                for channel in summary_channels
                if str(channel).strip()
            ]
        )
        sections.append(
            AuthoringSectionContext(
                section_id=section_id,
                title=str(raw_section.get("title", "")),
                source_path=source_path,
                source_format=(
                    source_context.source_format
                    if source_context is not None
                    else str(raw_section.get("source_format", "auto"))
                ),
                depth_range=raw_section.get("depth_range"),
                track_ids=[
                    str(track_id)
                    for track_id in raw_section.get("track_ids", [])
                    if str(track_id).strip()
                ],
                track_kinds=[
                    str(track_kind)
                    for track_kind in raw_section.get("track_kinds", [])
                    if str(track_kind).strip()
                ],
                available_channels=available_channels,
            )
        )

    for section_id, source_path in source_slots.items():
        if section_id in section_ids:
            continue
        source_context = source_by_key.get(_context_path_key(source_path))
        sections.append(
            AuthoringSectionContext(
                section_id=section_id,
                source_path=source_path,
                source_format=(source_context.source_format if source_context else "auto"),
                available_channels=(list(source_context.channels) if source_context else []),
            )
        )

    object_inventory = {
        "name": existing.name,
        "title": existing.title,
        "section_ids": [section.id for section in existing.sections],
        "sections": [
            {
                "id": section.id,
                "title": section.title,
                "track_ids": [track.id for track in section.tracks],
                "track_kinds": [track.kind for track in section.tracks],
                "binding_ids": [
                    binding.binding_id
                    for track in section.tracks
                    for binding in track.bindings
                    if getattr(binding, "binding_id", None)
                ],
            }
            for section in existing.sections
        ],
    }
    return AuthoringContextSnapshot(
        draft_logfile=draft_logfile,
        object_inventory=object_inventory,
        sections=sections,
        sources=source_contexts,
        requested_source_slots=source_slots,
        header_slots=dict(header_slots or {}),
        issues=list(issues),
    )


def _default_path_candidates(path: str) -> tuple[str, ...]:
    """Return exact and identity-wildcard forms for a default lookup path."""
    wildcard = sub(r"\[[^\]]+\]", "[*]", path)
    if wildcard == path:
        return (path,)
    return (path, wildcard)


def _nested_default_value(defaults: object, path: str) -> object:
    """Look up a dotted default path in either flat or nested catalog data."""
    if not isinstance(defaults, Mapping):
        return _MISSING
    for candidate in _default_path_candidates(path):
        if candidate in defaults:
            return defaults[candidate]
    current: object = defaults
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return _MISSING
        current = current[segment]
    return current


def _identity(value: object) -> tuple[str, str] | None:
    """Return the first stable identity field available on an object."""
    for field_name in _IDENTITY_FIELDS:
        candidate = _mapping_value(value, field_name)
        if isinstance(candidate, str) and candidate.strip():
            return field_name, candidate.strip()
    return None


def _find_list_item(items: object, identity: tuple[str, str] | None) -> object:
    """Find a matching existing/default list item by stable identity."""
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)) or identity is None:
        return _MISSING
    field_name, expected = identity
    candidate_fields = [field_name]
    if field_name in {"section_id", "track_id"}:
        candidate_fields.append("id")
    for item in items:
        for candidate_field in candidate_fields:
            candidate = _mapping_value(item, candidate_field)
            if isinstance(candidate, str) and candidate.strip() == expected:
                return item
    return _MISSING


def _child_path(path: str, item: object, index: int) -> str:
    """Build a stable path for a child object, falling back to its index."""
    identity = _identity(item)
    if identity is None:
        return f"{path}[{index}]"
    return f"{path}[{identity[1]}]"


def _model_mapping(value: object) -> object:
    """Return a mapping view for a canonical or intent model."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python", exclude_none=False)
    return value


def _fallback_value(
    *,
    field_name: str,
    path: str,
    existing: object,
    defaults: object,
    scaffold: object,
) -> tuple[object, AuthoringResolutionSource | None]:
    """Select one omitted field according to the G3 precedence order."""
    existing_value = _mapping_value(existing, field_name)
    if existing_value is not _MISSING:
        return existing_value, AuthoringResolutionSource.PRESERVED

    default_value = _nested_default_value(defaults, path)
    if default_value is not _MISSING:
        return default_value, AuthoringResolutionSource.DEFAULT
    default_value = _mapping_value(defaults, field_name)
    if default_value is not _MISSING:
        return default_value, AuthoringResolutionSource.DEFAULT

    scaffold_value = _mapping_value(scaffold, field_name)
    if scaffold_value is not _MISSING:
        return scaffold_value, AuthoringResolutionSource.SCAFFOLD
    return _MISSING, None


def _walk_intent(
    model: BaseModel,
    *,
    path: str,
    existing: object,
    defaults: object,
    scaffold: object,
    root_defaults: Mapping[str, Any],
    decisions: list[AuthoringResolutionDecision],
    resolved_values: dict[str, Any],
) -> None:
    """Collect field-level precedence decisions recursively."""
    existing_mapping = _model_mapping(existing)
    scaffold_mapping = _model_mapping(scaffold)
    for field_name in model.__class__.model_fields:
        field_path = f"{path}.{field_name}" if path else field_name
        supplied = field_name in model.model_fields_set
        current = getattr(model, field_name)
        if supplied:
            if isinstance(current, AuthoringClearIntent):
                decision = AuthoringResolutionDecision(
                    path=field_path,
                    source=AuthoringResolutionSource.EXPLICIT,
                    status=AuthoringResolutionStatus.CLEARED,
                    value=_plain_value(current),
                )
                decisions.append(decision)
                resolved_values[field_path] = _plain_value(current)
                continue
            if isinstance(current, BaseModel) and not isinstance(current, AuthoringDocumentIntent):
                nested_existing = _mapping_value(existing_mapping, field_name)
                nested_scaffold = _mapping_value(scaffold_mapping, field_name)
                nested_defaults = _mapping_value(defaults, field_name)
                if nested_defaults is _MISSING:
                    nested_defaults = root_defaults
                _walk_intent(
                    current,
                    path=field_path,
                    existing=nested_existing,
                    defaults=nested_defaults,
                    scaffold=nested_scaffold,
                    root_defaults=root_defaults,
                    decisions=decisions,
                    resolved_values=resolved_values,
                )
                continue
            if isinstance(current, list):
                decisions.append(
                    AuthoringResolutionDecision(
                        path=field_path,
                        source=AuthoringResolutionSource.EXPLICIT,
                        status=AuthoringResolutionStatus.RESOLVED,
                        value=_plain_value(current),
                    )
                )
                resolved_values[field_path] = _plain_value(current)
                existing_items = _mapping_value(existing_mapping, field_name)
                scaffold_items = _mapping_value(scaffold_mapping, field_name)
                default_items = _mapping_value(defaults, field_name)
                for index, item in enumerate(current):
                    if not isinstance(item, BaseModel):
                        continue
                    item_identity = _identity(item.model_dump(mode="python", exclude_unset=True))
                    item_path = _child_path(field_path, item.model_dump(mode="python"), index)
                    default_item = _find_list_item(default_items, item_identity)
                    if default_item is _MISSING:
                        default_item = defaults if isinstance(defaults, Mapping) else root_defaults
                    _walk_intent(
                        item,
                        path=item_path,
                        existing=_find_list_item(existing_items, item_identity),
                        defaults=default_item,
                        scaffold=_find_list_item(scaffold_items, item_identity),
                        root_defaults=root_defaults,
                        decisions=decisions,
                        resolved_values=resolved_values,
                    )
                continue
            decisions.append(
                AuthoringResolutionDecision(
                    path=field_path,
                    source=AuthoringResolutionSource.EXPLICIT,
                    status=AuthoringResolutionStatus.RESOLVED,
                    value=_plain_value(current),
                )
            )
            resolved_values[field_path] = _plain_value(current)
            continue

        fallback, source = _fallback_value(
            field_name=field_name,
            path=field_path,
            existing=existing_mapping,
            defaults=defaults,
            scaffold=scaffold_mapping,
        )
        if fallback is _MISSING or source is None:
            continue
        decision = AuthoringResolutionDecision(
            path=field_path,
            source=source,
            status=AuthoringResolutionStatus.RESOLVED,
            value=_plain_value(fallback),
        )
        decisions.append(decision)
        resolved_values[field_path] = _plain_value(fallback)


def _header_slots(header: AuthoringHeaderSpec) -> list[tuple[str, set[str]]]:
    """Build stable lookup tokens for all slots in one header structure."""
    slots: list[tuple[str, set[str]]] = []
    for field in header.general_fields:
        slots.append(
            (
                field.slot_id,
                {
                    _normalize_token(field.slot_id),
                    _normalize_token(field.key),
                    _normalize_token(field.label),
                    *(_normalize_token(alias) for alias in field.aliases),
                },
            )
        )
    for index, title in enumerate(header.service_titles, start=1):
        slots.append(
            (
                title.slot_id,
                {_normalize_token(title.slot_id), f"servicetitle{index}", f"title{index}"},
            )
        )
    if header.detail is not None:
        for row in header.detail.rows:
            row_tokens = {
                _normalize_token(row.row_id),
                _normalize_token(row.label or ""),
                *(_normalize_token(label) for label in row.label_cells),
            }
            for value in row.values:
                slots.append((value.slot_id, {_normalize_token(value.slot_id), *row_tokens}))
            for column in row.columns:
                for cell in column.cells:
                    slots.append((cell.slot_id, {_normalize_token(cell.slot_id), *row_tokens}))
    return slots


def _header_alias_tokens(
    aliases: Mapping[str, Sequence[str]] | None,
) -> dict[str, set[str]]:
    """Normalize configurable header aliases by canonical key."""
    normalized: dict[str, set[str]] = {}
    for key, values in (aliases or {}).items():
        normalized[_normalize_token(key)] = {
            _normalize_token(key),
            *(_normalize_token(value) for value in values),
        }
    return normalized


def _resolve_header_aliases(
    intent: AuthoringDocumentIntent,
    *,
    existing: AuthoringDocumentSpec | None,
    scaffold: AuthoringDocumentSpec | None,
    header_aliases: Mapping[str, Sequence[str]] | None,
    decisions: list[AuthoringResolutionDecision],
    issues: list[AuthoringContextIssue],
) -> None:
    """Resolve general, service-title, and detail slot aliases in-place."""
    if not isinstance(intent.header, BaseModel) or isinstance(intent.header, AuthoringClearIntent):
        return
    requested_collections = [
        ("general_fields", getattr(intent.header, "general_fields", None)),
        ("detail_fields", getattr(intent.header, "detail_fields", None)),
        ("service_titles", getattr(intent.header, "service_titles", None)),
    ]
    if not any(isinstance(items, list) and items for _name, items in requested_collections):
        return
    source_header = (existing.header if existing is not None else None) or (
        scaffold.header if scaffold is not None else None
    )
    if source_header is None:
        issues.append(
            AuthoringContextIssue(
                path="header",
                code="header_context_missing",
                message="Header slot aliases require an existing or scaffold header.",
            )
        )
        return
    aliases_by_key = _header_alias_tokens(header_aliases)
    slots = _header_slots(source_header)
    for collection_name, items in requested_collections:
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, BaseModel):
                continue
            item_path = f"header.{collection_name}[{index}]"
            lookup_tokens = {_normalize_token(item.slot_id)}
            for field_name in ("key", "label"):
                value = getattr(item, field_name, None)
                if isinstance(value, str):
                    normalized = _normalize_token(value)
                    lookup_tokens.add(normalized)
                    lookup_tokens.update(aliases_by_key.get(normalized, set()))
            matches = [slot_id for slot_id, tokens in slots if lookup_tokens.intersection(tokens)]
            if len(matches) != 1:
                code = "header_slot_missing" if not matches else "header_slot_ambiguous"
                status = (
                    "No matching header slot"
                    if not matches
                    else "Multiple matching header slots"
                )
                issues.append(
                    AuthoringContextIssue(
                        path=f"{item_path}.slot_id",
                        code=code,
                        message=f"{status} for {item.slot_id!r}.",
                        candidates=matches,
                    )
                )
                continue
            resolved_slot = matches[0]
            requested_slot = item.slot_id
            if requested_slot != resolved_slot:
                item.slot_id = resolved_slot
            decisions.append(
                AuthoringResolutionDecision(
                    path=f"{item_path}.slot_id",
                    source=AuthoringResolutionSource.EXPLICIT,
                    status=AuthoringResolutionStatus.RESOLVED,
                    value=resolved_slot,
                    requested=requested_slot,
                    matched_alias=requested_slot if requested_slot != resolved_slot else None,
                    candidates=[resolved_slot],
                )
            )


def _channel_alias_entry(
    requested: str,
    aliases: Sequence[AuthoringChannelAlias],
) -> AuthoringChannelAlias | None:
    """Return the semantic alias entry matching one requested channel token."""
    normalized = _normalize_token(requested)
    for entry in aliases:
        terms = [entry.id, entry.label, *entry.aliases, *entry.mnemonics]
        if normalized in {_normalize_token(term) for term in terms}:
            return entry
    return None


def _channel_candidates(
    values: Sequence[AuthoringChannelInput],
) -> list[AuthoringChannelCandidate]:
    """Normalize caller-provided source-channel inspection data."""
    candidates: list[AuthoringChannelCandidate] = []
    for value in values:
        if isinstance(value, AuthoringChannelCandidate):
            candidates.append(value)
        elif isinstance(value, str):
            candidates.append(AuthoringChannelCandidate(mnemonic=value))
        else:
            candidates.append(AuthoringChannelCandidate.model_validate(value))
    return candidates


def _candidate_matches(
    requested: str,
    candidates: Sequence[AuthoringChannelCandidate],
    aliases: Sequence[AuthoringChannelAlias],
) -> tuple[list[AuthoringChannelCandidate], str | None]:
    """Match a requested channel exactly or through one semantic alias."""
    normalized = _normalize_token(requested)
    exact = [
        candidate
        for candidate in candidates
        if normalized == _normalize_token(candidate.mnemonic)
        or normalized in {_normalize_token(alias) for alias in candidate.aliases}
    ]
    if exact:
        return exact, None
    alias = _channel_alias_entry(requested, aliases)
    if alias is None:
        return [], None
    alias_terms = {
        _normalize_token(term)
        for term in [alias.id, alias.label, *alias.aliases, *alias.mnemonics]
    }
    matches = [
        candidate
        for candidate in candidates
        if _normalize_token(candidate.mnemonic) in alias_terms
        or bool(alias_terms.intersection(_normalize_token(item) for item in candidate.aliases))
    ]
    return matches, alias.id


def _iter_binding_targets(
    intent: AuthoringDocumentIntent,
) -> list[tuple[str, object, str | None, str | None]]:
    """Return all nested and direct binding intents with their scope paths."""
    targets: list[tuple[str, object, str | None, str | None]] = []
    if isinstance(intent.sections, list):
        for section in intent.sections:
            if not isinstance(section, AuthoringSectionIntent) or not isinstance(
                section.tracks, list
            ):
                continue
            for track in section.tracks:
                if not isinstance(track, AuthoringTrackIntent) or not isinstance(
                    track.bindings, list
                ):
                    continue
                section_id = section.section_id
                track_id = track.track_id
                for index, binding in enumerate(track.bindings):
                    if isinstance(
                        binding,
                        (AuthoringCurveBindingIntent, AuthoringRasterBindingIntent),
                    ):
                        targets.append(
                            (
                                f"sections[{section_id}].tracks[{track_id}].bindings[{index}]",
                                binding,
                                section_id,
                                track_id,
                            )
                        )
    for field_name, bindings in (
        ("curve_bindings", intent.curve_bindings),
        ("raster_bindings", intent.raster_bindings),
    ):
        if not isinstance(bindings, list):
            continue
        for index, binding in enumerate(bindings):
            if isinstance(
                binding,
                (AuthoringCurveBindingIntent, AuthoringRasterBindingIntent),
            ):
                targets.append(
                    (f"{field_name}[{index}]", binding, binding.section_id, binding.track_id)
                )
    return targets


def _binding_scope_key(
    binding: AuthoringCurveBindingIntent | AuthoringRasterBindingIntent,
    *,
    section_id: str | None,
    track_id: str | None,
) -> tuple[str, str | None, str | None, str]:
    """Return one logical identity for a binding declaration."""
    return (binding.kind, section_id, track_id, binding.binding_id)


def _merge_duplicate_binding(
    primary: AuthoringCurveBindingIntent | AuthoringRasterBindingIntent,
    duplicate: AuthoringCurveBindingIntent | AuthoringRasterBindingIntent,
    *,
    primary_path: str,
    duplicate_path: str,
    issues: list[AuthoringContextIssue],
) -> bool:
    """Merge non-conflicting fields from one alternate binding declaration."""
    conflicts: list[str] = []
    for field_name in duplicate.model_fields_set:
        if field_name in {"kind", "binding_id", "section_id", "track_id"}:
            continue
        duplicate_value = getattr(duplicate, field_name)
        if field_name in primary.model_fields_set:
            primary_value = getattr(primary, field_name)
            if _plain_value(primary_value) != _plain_value(duplicate_value):
                conflicts.append(field_name)
            continue
        setattr(primary, field_name, deepcopy(duplicate_value))
    if conflicts:
        issues.append(
            AuthoringContextIssue(
                path=f"{duplicate_path}.binding_id",
                code="duplicate_binding_definition",
                message=(
                    f"Binding {duplicate.binding_id!r} is declared at both "
                    f"{primary_path} and {duplicate_path} with conflicting fields: "
                    f"{', '.join(conflicts)}."
                ),
            )
        )
        return False
    return True


def _coalesce_alternate_binding_references(
    intent: AuthoringDocumentIntent,
    *,
    issues: list[AuthoringContextIssue],
) -> None:
    """Coalesce equivalent nested and root-level binding references.

    The desired-state schema supports both nested bindings and direct root
    binding collections. Providers can reasonably emit both for the same
    requested object. They are alternate representations, not two binding
    instances, when their scoped identity matches. Repeated declarations in
    the same collection remain visible to the duplicate-identity validator.
    """
    canonical: dict[
        tuple[str, str | None, str | None, str],
        tuple[
            AuthoringCurveBindingIntent | AuthoringRasterBindingIntent,
            str,
            str,
        ],
    ] = {}

    if isinstance(intent.sections, list):
        for section in intent.sections:
            if not isinstance(section, AuthoringSectionIntent) or not isinstance(
                section.tracks, list
            ):
                continue
            for track in section.tracks:
                if not isinstance(track, AuthoringTrackIntent) or not isinstance(
                    track.bindings, list
                ):
                    continue
                for index, binding in enumerate(track.bindings):
                    if not isinstance(
                        binding,
                        (AuthoringCurveBindingIntent, AuthoringRasterBindingIntent),
                    ):
                        continue
                    path = (
                        f"sections[{section.section_id}].tracks[{track.track_id}]"
                        f".bindings[{index}]"
                    )
                    key = _binding_scope_key(
                        binding,
                        section_id=section.section_id,
                        track_id=track.track_id,
                    )
                    if key not in canonical:
                        canonical[key] = (binding, path, "nested")

    for collection_name in ("curve_bindings", "raster_bindings"):
        bindings = getattr(intent, collection_name)
        if not isinstance(bindings, list):
            continue
        retained: list[AuthoringCurveBindingIntent | AuthoringRasterBindingIntent] = []
        for index, binding in enumerate(bindings):
            path = f"{collection_name}[{index}]"
            key = _binding_scope_key(
                binding,
                section_id=binding.section_id,
                track_id=binding.track_id,
            )
            previous = canonical.get(key)
            if previous is None or previous[2] != "nested":
                canonical.setdefault(key, (binding, path, "direct"))
                retained.append(binding)
                continue
            _merge_duplicate_binding(
                previous[0],
                binding,
                primary_path=previous[1],
                duplicate_path=path,
                issues=issues,
            )
        setattr(intent, collection_name, retained)


def _existing_binding_channel(
    document: AuthoringDocumentSpec | None,
    *,
    section_id: str | None,
    track_id: str | None,
    binding_id: str,
) -> str | None:
    """Find one existing binding channel by stable scoped identity."""
    if document is None or section_id is None or track_id is None:
        return None
    for section in document.sections:
        if section.id != section_id:
            continue
        for track in section.tracks:
            if track.id != track_id:
                continue
            for binding in getattr(track, "bindings", ()):
                if binding.binding_id == binding_id:
                    return binding.channel
    return None


def _resolve_channels(
    intent: AuthoringDocumentIntent,
    *,
    existing: AuthoringDocumentSpec | None,
    available_channels: Mapping[str, Sequence[AuthoringChannelInput]] | None,
    channel_aliases: Sequence[AuthoringChannelAlias],
    decisions: list[AuthoringResolutionDecision],
    issues: list[AuthoringContextIssue],
) -> None:
    """Resolve channel aliases and enforce source-channel kind compatibility."""
    seen_bindings: dict[str, str] = {}
    for path, binding, section_id, track_id in _iter_binding_targets(intent):
        binding_id = binding.binding_id
        previous = seen_bindings.get(binding_id)
        if previous is not None:
            issues.append(
                AuthoringContextIssue(
                    path=f"{path}.binding_id",
                    code="duplicate_binding_id",
                    message=f"Binding id {binding_id!r} is already used at {previous}.",
                )
            )
        else:
            seen_bindings[binding_id] = path

        requested = binding.channel
        if isinstance(requested, AuthoringClearIntent):
            issues.append(
                AuthoringContextIssue(
                    path=f"{path}.channel",
                    code="required_channel_cleared",
                    message="A binding channel is required and cannot be cleared.",
                )
            )
            continue
        if requested is None:
            requested = _existing_binding_channel(
                existing,
                section_id=section_id,
                track_id=track_id,
                binding_id=binding_id,
            )
            if requested is None:
                issues.append(
                    AuthoringContextIssue(
                        path=f"{path}.channel",
                        code="channel_missing",
                        message="A new binding must specify a source channel.",
                    )
                )
                continue
            binding.channel = requested

        if available_channels is None or section_id is None:
            issues.append(
                AuthoringContextIssue(
                    path=f"{path}.channel",
                    code="channel_context_missing",
                    message=(
                        "Source-channel availability and section scope are required "
                        "before binding."
                    ),
                )
            )
            continue
        raw_candidates = available_channels.get(section_id)
        if raw_candidates is None:
            issues.append(
                AuthoringContextIssue(
                    path=f"{path}.channel",
                    code="section_channel_context_missing",
                    message=f"No inspected channel set is available for section {section_id!r}.",
                )
            )
            continue
        candidates = _channel_candidates(raw_candidates)
        matches, matched_alias = _candidate_matches(str(requested), candidates, channel_aliases)
        if len(matches) != 1:
            code = "channel_missing" if not matches else "channel_ambiguous"
            message = (
                f"No source channel matches {requested!r}."
                if not matches
                else f"Multiple source channels match {requested!r}."
            )
            issues.append(
                AuthoringContextIssue(
                    path=f"{path}.channel",
                    code=code,
                    message=message,
                    candidates=[candidate.mnemonic for candidate in matches],
                )
            )
            continue
        candidate = matches[0]
        normalized_kind = _normalize_token(candidate.kind)
        is_raster = isinstance(binding, AuthoringRasterBindingIntent)
        compatible = (
            normalized_kind in {"array", "raster", "arraychannel", "rasterchannel"}
            if is_raster
            else normalized_kind in {"scalar", "scalarchannel"}
        )
        if not compatible:
            expected = "array/raster" if is_raster else "scalar"
            issues.append(
                AuthoringContextIssue(
                    path=f"{path}.channel",
                    code="channel_kind_incompatible",
                    message=(
                        f"Binding kind {binding.kind!r} requires a {expected} source channel, "
                        f"but {candidate.mnemonic!r} is {candidate.kind!r}."
                    ),
                    candidates=[candidate.mnemonic],
                )
            )
            continue
        binding.channel = candidate.mnemonic
        decisions.append(
            AuthoringResolutionDecision(
                path=f"{path}.channel",
                source=AuthoringResolutionSource.EXPLICIT,
                status=AuthoringResolutionStatus.RESOLVED,
                value=candidate.mnemonic,
                requested=requested,
                matched_alias=matched_alias,
                candidates=[candidate.mnemonic],
            )
        )


def _track_kind(
    track: AuthoringTrackIntent,
    *,
    section_id: str,
    existing: AuthoringDocumentSpec | None,
    decisions: Sequence[AuthoringResolutionDecision],
) -> str | None:
    """Resolve a track kind from explicit or preserved structural context."""
    if isinstance(track.kind, str):
        return track.kind
    decision_path = f"sections[{section_id}].tracks[{track.track_id}].kind"
    for decision in decisions:
        if decision.path == decision_path and isinstance(decision.value, str):
            return decision.value
    if existing is None:
        return None
    for section in existing.sections:
        if section.id != section_id:
            continue
        for existing_track in section.tracks:
            if existing_track.id == track.track_id:
                return existing_track.kind
    return None


def _add_compatibility_issue(
    issues: list[AuthoringContextIssue],
    *,
    path: str,
    message: str,
) -> None:
    """Append one standardized compatibility issue."""
    issues.append(
        AuthoringContextIssue(
            path=path,
            code="content_track_incompatible",
            message=message,
        )
    )


def _validate_track_content_compatibility(
    intent: AuthoringDocumentIntent,
    *,
    existing: AuthoringDocumentSpec | None,
    decisions: Sequence[AuthoringResolutionDecision],
    issues: list[AuthoringContextIssue],
) -> None:
    """Reject content whose requested parent track kind cannot own it."""
    if not isinstance(intent.sections, list):
        return
    for section in intent.sections:
        if not isinstance(section, AuthoringSectionIntent) or not isinstance(section.tracks, list):
            continue
        for track in section.tracks:
            if not isinstance(track, AuthoringTrackIntent):
                continue
            kind = _track_kind(
                track,
                section_id=section.section_id,
                existing=existing,
                decisions=decisions,
            )
            if kind is None:
                # An unresolved form is diagnosed by reconciliation with the
                # missing user-facing track fields. Do not mislabel its
                # children as incompatible before that resolution can run.
                continue
            if isinstance(track.bindings, list):
                for index, binding in enumerate(track.bindings):
                    if isinstance(binding, AuthoringRasterBindingIntent) and kind != "array":
                        _add_compatibility_issue(
                            issues,
                            path=f"sections[{section.section_id}].tracks[{track.track_id}].bindings[{index}]",
                            message="Raster bindings require an array track.",
                        )
                    if isinstance(binding, AuthoringCurveBindingIntent) and kind not in {
                        "normal",
                        "reference",
                        "array",
                    }:
                        _add_compatibility_issue(
                            issues,
                            path=f"sections[{section.section_id}].tracks[{track.track_id}].bindings[{index}]",
                            message="Curve bindings require a normal, reference, or array track.",
                        )
            if isinstance(track.fills, list) and kind != "normal":
                _add_compatibility_issue(
                    issues,
                    path=f"sections[{section.section_id}].tracks[{track.track_id}].fills",
                    message="Curve fills currently require a normal track.",
                )
            if isinstance(track.annotations, list) and kind != "annotation":
                _add_compatibility_issue(
                    issues,
                    path=f"sections[{section.section_id}].tracks[{track.track_id}].annotations",
                    message="Annotation objects require an annotation track.",
                )


class AuthoringContextResolver:
    """Resolve one desired state against explicit authoring context."""

    def __init__(
        self,
        *,
        channel_aliases: Sequence[AuthoringChannelAlias | Mapping[str, Any]] = (),
        header_aliases: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        """Initialize reusable alias catalogs without loading provider state."""
        self.channel_aliases = tuple(
            item
            if isinstance(item, AuthoringChannelAlias)
            else AuthoringChannelAlias.model_validate(item)
            for item in channel_aliases
        )
        self.header_aliases = deepcopy(dict(header_aliases or {}))

    def resolve(
        self,
        intent: AuthoringDocumentIntent,
        *,
        existing: AuthoringDocumentSpec | None = None,
        scaffold: AuthoringDocumentSpec | None = None,
        defaults: Mapping[str, Any] | None = None,
        available_channels: Mapping[str, Sequence[AuthoringChannelInput]] | None = None,
    ) -> AuthoringContextResolution:
        """Resolve aliases, precedence, and compatibility without mutation."""
        resolved_intent = intent.model_copy(deep=True)
        decisions: list[AuthoringResolutionDecision] = []
        issues: list[AuthoringContextIssue] = []
        resolved_values: dict[str, Any] = {}
        root_defaults = dict(defaults or {})

        _resolve_header_aliases(
            resolved_intent,
            existing=existing,
            scaffold=scaffold,
            header_aliases=self.header_aliases,
            decisions=decisions,
            issues=issues,
        )
        _coalesce_alternate_binding_references(resolved_intent, issues=issues)
        _resolve_channels(
            resolved_intent,
            existing=existing,
            available_channels=available_channels,
            channel_aliases=self.channel_aliases,
            decisions=decisions,
            issues=issues,
        )
        _walk_intent(
            resolved_intent,
            path="",
            existing=existing,
            defaults=root_defaults,
            scaffold=scaffold,
            root_defaults=root_defaults,
            decisions=decisions,
            resolved_values=resolved_values,
        )
        _validate_track_content_compatibility(
            resolved_intent,
            existing=existing,
            decisions=decisions,
            issues=issues,
        )
        for index, removal in enumerate(resolved_intent.removals):
            if isinstance(removal, AuthoringRemoveIntent):
                path = f"removals[{index}]"
                decisions.append(
                    AuthoringResolutionDecision(
                        path=path,
                        source=AuthoringResolutionSource.EXPLICIT,
                        status=AuthoringResolutionStatus.RESOLVED,
                        value=_plain_value(removal),
                    )
                )
                resolved_values[path] = _plain_value(removal)
        return AuthoringContextResolution(
            ready=not issues,
            resolved_intent=resolved_intent,
            resolved_values=resolved_values,
            decisions=decisions,
            issues=issues,
            warnings=[],
        )


def resolve_authoring_context(
    intent: AuthoringDocumentIntent,
    *,
    existing: AuthoringDocumentSpec | None = None,
    scaffold: AuthoringDocumentSpec | None = None,
    defaults: Mapping[str, Any] | None = None,
    available_channels: Mapping[str, Sequence[AuthoringChannelInput]] | None = None,
    channel_aliases: Sequence[AuthoringChannelAlias | Mapping[str, Any]] = (),
    header_aliases: Mapping[str, Sequence[str]] | None = None,
) -> AuthoringContextResolution:
    """Resolve one desired state using an explicit contextual input bundle."""
    return AuthoringContextResolver(
        channel_aliases=channel_aliases,
        header_aliases=header_aliases,
    ).resolve(
        intent,
        existing=existing,
        scaffold=scaffold,
        defaults=defaults,
        available_channels=available_channels,
    )


__all__ = [
    "AuthoringChannelAlias",
    "AuthoringChannelCandidate",
    "AuthoringContextIssue",
    "AuthoringContextResolution",
    "AuthoringContextResolver",
    "AuthoringContextSnapshot",
    "AuthoringSectionContext",
    "AuthoringSourceContext",
    "AuthoringResolutionDecision",
    "AuthoringResolutionSource",
    "AuthoringResolutionStatus",
    "build_authoring_context_snapshot",
    "resolve_authoring_context",
]
