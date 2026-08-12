###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Typed request compilation contracts for the provider-facing agent layer."""

from __future__ import annotations

import re
from collections.abc import Iterable
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from ..model.intent import (
    AuthoringClearIntent,
    AuthoringDocumentIntent,
    AuthoringRemoveIntent,
    AuthoringSectionIntent,
    AuthoringTrackIntent,
)


class AuthoringRequestItem(BaseModel):
    """One deterministic request item that must be accounted for by the provider."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    item_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class AuthoringRequestManifest(BaseModel):
    """Compact, stable request inventory used for intent coverage validation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    items: list[AuthoringRequestItem] = Field(min_length=1)


AuthoringCoverageStatus = Literal[
    "mapped",
    "preserved",
    "unsupported",
    "inconsistent",
]

AuthoringRequestAction = Literal[
    "add",
    "update",
    "remove",
    "clear",
    "preserve",
    "set",
    "explain",
]

AuthoringRequestObjectFamily = Literal[
    "report",
    "header",
    "section",
    "track",
    "curve_binding",
    "raster_binding",
    "fill",
    "annotation",
    "page",
    "output",
    "depth",
    "remarks",
    "unknown",
]


class AuthoringRequestInventoryItem(BaseModel):
    """One compact provider classification for a natural-language request item."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_item_id: str = Field(min_length=1)
    status: AuthoringCoverageStatus
    action: AuthoringRequestAction
    object_family: AuthoringRequestObjectFamily
    target: str | None = Field(default=None, min_length=1)
    parent_scope: str | None = Field(default=None, min_length=1)
    explicit_values: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(default=None, min_length=1)


class AuthoringRequestInventory(BaseModel):
    """Compact provider output used before scoped typed-intent compilation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    items: list[AuthoringRequestInventoryItem] = Field(min_length=1)


class AuthoringIntentCoverage(BaseModel):
    """Provider claim linking one request item to typed intent paths."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_item_id: str = Field(min_length=1)
    status: AuthoringCoverageStatus
    intent_paths: list[str] = Field(default_factory=list)
    reason: str | None = Field(default=None, min_length=1)


class AuthoringIntentSubmission(BaseModel):
    """One typed desired state plus coverage for the request manifest."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    intent: AuthoringDocumentIntent
    coverage: list[AuthoringIntentCoverage] = Field(min_length=1)


AuthoringCompilationScope = Literal[
    "report",
    "structure",
    "scalar",
    "raster",
    "annotation",
]


class _ScopedCompilationModel(BaseModel):
    """Strict base for generated provider-facing scoped intent views."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _project_model(
    name: str,
    source: type[BaseModel],
    field_names: tuple[str, ...],
    *,
    overrides: dict[str, tuple[object, object]] | None = None,
) -> type[BaseModel]:
    """Generate a strict model view from canonical Pydantic field definitions."""
    definitions: dict[str, tuple[object, object]] = {}
    for field_name in field_names:
        source_field = source.model_fields[field_name]
        definitions[field_name] = (
            source_field.annotation,
            deepcopy(source_field),
        )
    if overrides:
        definitions.update(overrides)
    return create_model(
        name,
        __base__=_ScopedCompilationModel,
        __module__=__name__,
        **definitions,
    )


AuthoringTrackStructureIntent = _project_model(
    "AuthoringTrackStructureIntent",
    AuthoringTrackIntent,
    (
        "track_id",
        "section_id",
        "title",
        "kind",
        "width_mm",
        "x_scale",
        "grid",
        "track_header",
        "extensions",
    ),
)

_section_tracks_field = deepcopy(AuthoringSectionIntent.model_fields["tracks"])
AuthoringSectionStructureIntent = _project_model(
    "AuthoringSectionStructureIntent",
    AuthoringSectionIntent,
    (
        "section_id",
        "title",
        "subtitle",
        "depth_range",
        "data_source",
        "tracks",
        "extensions",
    ),
    overrides={
        "tracks": (
            list[AuthoringTrackStructureIntent] | AuthoringClearIntent | None,
            _section_tracks_field,
        )
    },
)

_document_sections_field = deepcopy(AuthoringDocumentIntent.model_fields["sections"])


def _remove_intent_model(
    name: str,
    object_kinds: tuple[str, ...],
    *,
    include_parent_scope: bool = True,
) -> type[BaseModel]:
    """Generate one removal view restricted to a compilation scope."""
    object_kind_field = deepcopy(AuthoringRemoveIntent.model_fields["object_kind"])
    field_names = ("operation", "object_kind", "object_id")
    if include_parent_scope:
        field_names += ("section_id", "track_id")
    return _project_model(
        name,
        AuthoringRemoveIntent,
        field_names,
        overrides={
            "object_kind": (
                Literal.__getitem__(object_kinds),
                object_kind_field,
            )
        },
    )


AuthoringReportRemoveIntent = _remove_intent_model(
    "AuthoringReportRemoveIntent",
    ("report", "page", "depth", "output", "header", "tail", "remark"),
    include_parent_scope=False,
)
AuthoringStructureRemoveIntent = _remove_intent_model(
    "AuthoringStructureRemoveIntent",
    ("section", "track"),
)
AuthoringScalarRemoveIntent = _remove_intent_model(
    "AuthoringScalarRemoveIntent",
    ("curve_binding", "fill"),
)
AuthoringRasterRemoveIntent = _remove_intent_model(
    "AuthoringRasterRemoveIntent",
    ("raster_binding",),
)
AuthoringAnnotationRemoveIntent = _remove_intent_model(
    "AuthoringAnnotationRemoveIntent",
    ("annotation",),
)


def _removals_override(remove_model: type[BaseModel]) -> dict[str, tuple[object, object]]:
    """Return one generated removals-field definition for a scoped fragment."""
    return {
        "removals": (
            list[remove_model],
            deepcopy(AuthoringDocumentIntent.model_fields["removals"]),
        )
    }


AuthoringReportIntentFragment = _project_model(
    "AuthoringReportIntentFragment",
    AuthoringDocumentIntent,
    (
        "title",
        "subtitle",
        "output",
        "page",
        "depth",
        "header",
        "tail",
        "remarks",
        "removals",
    ),
    overrides=_removals_override(AuthoringReportRemoveIntent),
)
AuthoringStructureIntentFragment = _project_model(
    "AuthoringStructureIntentFragment",
    AuthoringDocumentIntent,
    ("sections", "removals"),
    overrides={
        "sections": (
            list[AuthoringSectionStructureIntent] | AuthoringClearIntent | None,
            _document_sections_field,
        ),
        **_removals_override(AuthoringStructureRemoveIntent),
    },
)
AuthoringScalarIntentFragment = _project_model(
    "AuthoringScalarIntentFragment",
    AuthoringDocumentIntent,
    ("curve_bindings", "fills", "removals"),
    overrides=_removals_override(AuthoringScalarRemoveIntent),
)
AuthoringRasterIntentFragment = _project_model(
    "AuthoringRasterIntentFragment",
    AuthoringDocumentIntent,
    ("raster_bindings", "removals"),
    overrides=_removals_override(AuthoringRasterRemoveIntent),
)
AuthoringAnnotationIntentFragment = _project_model(
    "AuthoringAnnotationIntentFragment",
    AuthoringDocumentIntent,
    ("annotations", "removals"),
    overrides=_removals_override(AuthoringAnnotationRemoveIntent),
)


def _submission_model(
    name: str,
    fragment_model: type[BaseModel],
) -> type[BaseModel]:
    """Generate one submission wrapper for a scoped canonical intent view."""
    return create_model(
        name,
        __base__=_ScopedCompilationModel,
        __module__=__name__,
        intent=(fragment_model, ...),
        coverage=(list[AuthoringIntentCoverage], Field(min_length=1)),
    )


AuthoringReportIntentSubmission = _submission_model(
    "AuthoringReportIntentSubmission",
    AuthoringReportIntentFragment,
)
AuthoringStructureIntentSubmission = _submission_model(
    "AuthoringStructureIntentSubmission",
    AuthoringStructureIntentFragment,
)
AuthoringScalarIntentSubmission = _submission_model(
    "AuthoringScalarIntentSubmission",
    AuthoringScalarIntentFragment,
)
AuthoringRasterIntentSubmission = _submission_model(
    "AuthoringRasterIntentSubmission",
    AuthoringRasterIntentFragment,
)
AuthoringAnnotationIntentSubmission = _submission_model(
    "AuthoringAnnotationIntentSubmission",
    AuthoringAnnotationIntentFragment,
)

_SCOPE_SUBMISSION_MODELS: dict[str, type[BaseModel]] = {
    "report": AuthoringReportIntentSubmission,
    "structure": AuthoringStructureIntentSubmission,
    "scalar": AuthoringScalarIntentSubmission,
    "raster": AuthoringRasterIntentSubmission,
    "annotation": AuthoringAnnotationIntentSubmission,
}
_SCOPE_ORDER: tuple[AuthoringCompilationScope, ...] = (
    "report",
    "structure",
    "scalar",
    "raster",
    "annotation",
)

_OBJECT_FAMILY_SCOPES: dict[str, AuthoringCompilationScope] = {
    "report": "report",
    "header": "report",
    "page": "report",
    "output": "report",
    "depth": "report",
    "remarks": "report",
    "section": "structure",
    "track": "structure",
    "curve_binding": "scalar",
    "fill": "scalar",
    "raster_binding": "raster",
    "annotation": "annotation",
}


def _strip_bullet(line: str) -> str:
    """Remove one common bullet or numbered-list prefix."""
    return re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", line).strip()


def _is_bullet(line: str) -> bool:
    """Return whether one line starts a list item."""
    return bool(re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", line))


def build_request_manifest(text: str) -> AuthoringRequestManifest:
    """Split a natural-language request into stable, reviewable request items."""
    items: list[str] = []
    current: str | None = None
    paragraph: list[str] = []

    def flush_current() -> None:
        nonlocal current
        if current:
            items.append(current.strip())
        current = None

    def flush_paragraph() -> None:
        if paragraph:
            items.append(" ".join(paragraph).strip())
            paragraph.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_current()
            flush_paragraph()
            continue
        if _is_bullet(raw_line):
            flush_paragraph()
            flush_current()
            current = _strip_bullet(raw_line)
            continue
        if current is not None:
            current = f"{current} {line}".strip()
            continue
        if line.endswith(":"):
            flush_paragraph()
            paragraph.append(line)
            continue
        paragraph.append(line)

    flush_current()
    flush_paragraph()
    normalized_items = [item for item in items if item]
    if not normalized_items and text.strip():
        normalized_items = [text.strip()]
    return AuthoringRequestManifest(
        items=[
            AuthoringRequestItem(item_id=f"request-{index:03d}", text=item)
            for index, item in enumerate(normalized_items, start=1)
        ]
    )


def validate_intent_coverage(
    manifest: AuthoringRequestManifest,
    coverage: Iterable[AuthoringIntentCoverage],
) -> list[str]:
    """Return deterministic errors for incomplete or contradictory coverage."""
    entries = list(coverage)
    expected_ids = {item.item_id for item in manifest.items}
    seen_ids: set[str] = set()
    errors: list[str] = []
    for entry in entries:
        if entry.request_item_id in seen_ids:
            errors.append(f"Duplicate coverage for {entry.request_item_id!r}.")
        seen_ids.add(entry.request_item_id)
        if entry.request_item_id not in expected_ids:
            errors.append(f"Coverage references unknown request item {entry.request_item_id!r}.")
        if entry.status in {"mapped", "preserved"} and not entry.intent_paths:
            errors.append(f"Coverage for {entry.request_item_id!r} needs at least one intent path.")
        if entry.status in {"unsupported", "inconsistent"} and not entry.reason:
            errors.append(
                f"Coverage for {entry.request_item_id!r} needs a reason for status "
                f"{entry.status!r}."
            )
    missing_ids = sorted(expected_ids - seen_ids)
    errors.extend(f"Missing coverage for request item {item_id!r}." for item_id in missing_ids)
    return errors


def validate_request_inventory(
    manifest: AuthoringRequestManifest,
    inventory: Iterable[AuthoringRequestInventoryItem],
) -> list[str]:
    """Return deterministic errors for an incomplete compact request inventory."""
    entries = list(inventory)
    expected_ids = {item.item_id for item in manifest.items}
    seen_ids: set[str] = set()
    errors: list[str] = []
    for entry in entries:
        if entry.request_item_id in seen_ids:
            errors.append(f"Duplicate inventory for {entry.request_item_id!r}.")
        seen_ids.add(entry.request_item_id)
        if entry.request_item_id not in expected_ids:
            errors.append(f"Inventory references unknown request item {entry.request_item_id!r}.")
        if entry.status in {"mapped", "preserved"}:
            if entry.object_family == "unknown":
                errors.append(
                    f"Inventory for {entry.request_item_id!r} needs a known object family."
                )
            if entry.action == "explain":
                errors.append(f"Inventory for {entry.request_item_id!r} needs an authoring action.")
        if entry.status in {"unsupported", "inconsistent"} and not entry.reason:
            errors.append(
                f"Inventory for {entry.request_item_id!r} needs a reason for status "
                f"{entry.status!r}."
            )
    missing_ids = sorted(expected_ids - seen_ids)
    errors.extend(f"Missing inventory for request item {item_id!r}." for item_id in missing_ids)
    return errors


def group_request_inventory(
    inventory: AuthoringRequestInventory,
) -> dict[AuthoringCompilationScope, tuple[AuthoringRequestInventoryItem, ...]]:
    """Group actionable inventory items by canonical compilation scope."""
    grouped: dict[AuthoringCompilationScope, list[AuthoringRequestInventoryItem]] = {}
    for item in inventory.items:
        if item.status in {"unsupported", "inconsistent"}:
            continue
        scope = _OBJECT_FAMILY_SCOPES.get(item.object_family)
        if scope is None:
            continue
        grouped.setdefault(scope, []).append(item)
    return {scope: tuple(grouped[scope]) for scope in _SCOPE_ORDER if scope in grouped}


def scoped_submission_model(scope: AuthoringCompilationScope) -> type[BaseModel]:
    """Return the generated submission model for one canonical object scope."""
    return _SCOPE_SUBMISSION_MODELS[scope]


def _reject_duplicate_identities(payload: dict[str, Any]) -> None:
    """Reject duplicate canonical identities before contextual resolution."""
    identity_fields = {
        "sections": "section_id",
        "curve_bindings": "binding_id",
        "raster_bindings": "binding_id",
        "fills": "fill_id",
        "annotations": "annotation_id",
        "remarks": "remark_id",
    }
    for field_name, identity_field in identity_fields.items():
        values = payload.get(field_name)
        if not isinstance(values, list):
            continue
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, dict):
                continue
            identity = str(value.get(identity_field, "")).strip()
            if identity and identity in seen:
                raise ValueError(f"Duplicate {identity_field} {identity!r} in {field_name}.")
            seen.add(identity)

    sections = payload.get("sections")
    if not isinstance(sections, list):
        return
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_id", "")).strip()
        tracks = section.get("tracks")
        if not isinstance(tracks, list):
            continue
        seen_tracks: set[str] = set()
        for track in tracks:
            if not isinstance(track, dict):
                continue
            track_id = str(track.get("track_id", "")).strip()
            if track_id and track_id in seen_tracks:
                raise ValueError(f"Duplicate track_id {track_id!r} in section {section_id!r}.")
            seen_tracks.add(track_id)


def merge_scoped_intents(fragments: Iterable[BaseModel]) -> AuthoringDocumentIntent:
    """Merge non-overlapping scoped fragments into one canonical desired state."""
    merged: dict[str, Any] = {}
    removals: list[dict[str, Any]] = []
    for fragment in fragments:
        payload = fragment.model_dump(mode="json", exclude_unset=True)
        for field_name, value in payload.items():
            if field_name == "removals":
                if isinstance(value, list):
                    for removal in value:
                        if isinstance(removal, dict) and removal not in removals:
                            removals.append(removal)
                continue
            if field_name in merged and merged[field_name] != value:
                raise ValueError(f"Conflicting scoped intent values for field {field_name!r}.")
            merged[field_name] = value
    if removals:
        merged["removals"] = removals
    _reject_duplicate_identities(merged)
    return AuthoringDocumentIntent.model_validate(merged)


__all__ = [
    "AuthoringCoverageStatus",
    "AuthoringCompilationScope",
    "AuthoringAnnotationIntentFragment",
    "AuthoringAnnotationIntentSubmission",
    "AuthoringIntentCoverage",
    "AuthoringIntentSubmission",
    "AuthoringRasterIntentFragment",
    "AuthoringRasterIntentSubmission",
    "AuthoringReportIntentFragment",
    "AuthoringReportIntentSubmission",
    "AuthoringRequestAction",
    "AuthoringRequestItem",
    "AuthoringRequestInventory",
    "AuthoringRequestInventoryItem",
    "AuthoringRequestManifest",
    "AuthoringScalarIntentFragment",
    "AuthoringScalarIntentSubmission",
    "AuthoringSectionStructureIntent",
    "AuthoringStructureIntentFragment",
    "AuthoringStructureIntentSubmission",
    "AuthoringTrackStructureIntent",
    "build_request_manifest",
    "group_request_inventory",
    "merge_scoped_intents",
    "scoped_submission_model",
    "validate_intent_coverage",
    "validate_request_inventory",
]
