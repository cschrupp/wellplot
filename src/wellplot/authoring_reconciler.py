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

"""Provider-neutral reconciliation of partial authoring intent.

The reconciler compares a desired intent with a canonical document and emits a
typed, ordered plan.  It does not load files, call MCP, or mutate the document.
The next slice translates these operations to :mod:`wellplot.authoring_service`
requests and verifies each postcondition.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .authoring_context import (
    AuthoringChannelAlias,
    AuthoringChannelInput,
    AuthoringContextIssue,
    AuthoringContextResolution,
    resolve_authoring_context,
)
from .model.authoring import AuthoringDocumentSpec
from .model.intent import (
    AuthoringAnnotationIntent,
    AuthoringClearIntent,
    AuthoringCurveBindingIntent,
    AuthoringDocumentIntent,
    AuthoringFillIntent,
    AuthoringHeaderFieldIntent,
    AuthoringHeaderIntent,
    AuthoringRasterBindingIntent,
    AuthoringRemarkIntent,
    AuthoringSectionIntent,
    AuthoringServiceTitleIntent,
    AuthoringTrackIntent,
)


class _ReconcilerModel(BaseModel):
    """Strict base model for reconciliation results."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AuthoringOperationPhase(StrEnum):
    """Execution phase for one planned operation."""

    REPORT = "report"
    SECTIONS = "sections"
    TRACKS = "tracks"
    BINDINGS = "bindings"
    CONTENT = "content"
    PRESENTATION = "presentation"
    FINALIZE = "finalize"


class AuthoringOperationAction(StrEnum):
    """Mutation kind represented by one planned operation."""

    CREATE = "create"
    UPDATE = "update"
    REMOVE = "remove"
    MOVE = "move"


class AuthoringOperationObjectKind(StrEnum):
    """Canonical object family addressed by one reconciliation operation."""

    REPORT = "report"
    PAGE = "page"
    DEPTH = "depth"
    OUTPUT = "output"
    HEADER = "header"
    HEADER_SLOT = "header_slot"
    TAIL = "tail"
    SECTION = "section"
    TRACK = "track"
    CURVE_BINDING = "curve_binding"
    RASTER_BINDING = "raster_binding"
    FILL = "fill"
    ANNOTATION = "annotation"
    REMARK = "remark"


class AuthoringOperation(_ReconcilerModel):
    """One deterministic mutation with explicit scope and dependencies."""

    operation_id: str = Field(min_length=1)
    phase: AuthoringOperationPhase
    action: AuthoringOperationAction
    object_kind: AuthoringOperationObjectKind
    object_id: str = Field(min_length=1)
    section_id: str | None = None
    track_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class AuthoringReconciliationIssue(_ReconcilerModel):
    """A deterministic issue that prevents safe plan execution."""

    path: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class AuthoringReconciliationPlan(_ReconcilerModel):
    """Ordered desired-state operations and reconciliation diagnostics."""

    ready: bool
    operations: list[AuthoringOperation] = Field(default_factory=list)
    issues: list[AuthoringReconciliationIssue] = Field(default_factory=list)
    unchanged_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


_MISSING = object()
_IDENTITY_FIELDS = {
    "section_id",
    "track_id",
    "binding_id",
    "fill_id",
    "annotation_id",
    "remark_id",
    "slot_id",
}
_CHILD_FIELDS = {"sections", "tracks", "bindings", "fills", "annotations", "remarks"}
_STRUCTURAL_TRACK_FIELDS = {"title", "width_mm"}
_SINGLETON_FIELDS = {
    "output": "output",
    "page": "page",
    "depth": "depth",
    "tail": "tail",
}


def _plain(value: object) -> object:
    """Convert models and tuples to ordinary comparison/plan values."""
    if isinstance(value, BaseModel):
        return {
            key: _plain(item)
            for key, item in value.model_dump(mode="python", exclude_none=False).items()
        }
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    """Return a mapping representation for a canonical or intent object."""
    plain = _plain(value)
    return plain if isinstance(plain, Mapping) else {}


def _value(value: object, key: str) -> object:
    """Read one mapping value while preserving explicit ``None``."""
    if isinstance(value, Mapping) and key in value:
        return value[key]
    return _MISSING


def _items(value: object) -> Sequence[object]:
    """Return a safe sequence for an optional canonical child collection."""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _same(left: object, right: object) -> bool:
    """Compare model-shaped values without enum or tuple representation noise."""
    return _plain(left) == _plain(right)


def _is_clear(value: object) -> bool:
    """Return whether a desired value is an explicit clear marker."""
    return isinstance(value, AuthoringClearIntent)


def _path(base: str, field: str) -> str:
    """Append a field to a stable reconciler path."""
    return f"{base}.{field}" if base else field


def _effective_field(
    model: BaseModel,
    field_name: str,
    base_path: str,
    decisions: Mapping[str, object],
) -> object:
    """Get an explicit field or a non-preserved contextual resolution."""
    if field_name in model.model_fields_set:
        return getattr(model, field_name)
    decision = decisions.get(_path(base_path, field_name))
    if decision is None:
        return _MISSING
    source = getattr(decision, "source", None)
    if str(source) == "preserved" or getattr(source, "value", source) == "preserved":
        return _MISSING
    return getattr(decision, "value", _MISSING)


def _decision_map(resolution: AuthoringContextResolution) -> dict[str, object]:
    """Index contextual decisions by their stable path."""
    return {decision.path: decision for decision in resolution.decisions}


def _patch_for_model(
    model: BaseModel,
    current: object,
    *,
    base_path: str,
    decisions: Mapping[str, object],
    ignored: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Build a minimal patch from explicit and non-preserved desired fields."""
    current_mapping = _mapping(current)
    patch: dict[str, Any] = {}
    for field_name in model.__class__.model_fields:
        if field_name in ignored or field_name in _IDENTITY_FIELDS:
            continue
        direct = field_name in model.model_fields_set
        decision = decisions.get(_path(base_path, field_name))
        if not direct and decision is None:
            continue
        if not direct and getattr(getattr(decision, "source", None), "value", None) == "preserved":
            continue
        desired = getattr(model, field_name) if direct else getattr(decision, "value", _MISSING)
        if desired is _MISSING:
            continue
        if _is_clear(desired):
            patch[field_name] = _plain(desired)
            continue
        if isinstance(desired, BaseModel) and desired.__class__.__module__.endswith("intent"):
            nested = _patch_for_model(
                desired,
                _value(current_mapping, field_name),
                base_path=_path(base_path, field_name),
                decisions=decisions,
            )
            if nested:
                patch[field_name] = nested
            continue
        if (
            field_name in _CHILD_FIELDS
            and isinstance(desired, list)
            and any(isinstance(item, BaseModel) for item in desired)
        ):
            # Child identities are reconciled as separate operations below.
            continue
        desired_plain = _plain(desired)
        current_value = _value(current_mapping, field_name)
        if current_value is _MISSING or not _same(current_value, desired_plain):
            patch[field_name] = desired_plain
    return patch


def _find_by_id(items: object, field_name: str, expected: str) -> object:
    """Find one stable child identity in a canonical collection."""
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        return _MISSING
    for item in items:
        candidate = _value(_mapping(item), field_name)
        if candidate == expected:
            return item
        if field_name in {"section_id", "track_id"} and _value(_mapping(item), "id") == expected:
            return item
    return _MISSING


def _section(existing: AuthoringDocumentSpec | None, section_id: str) -> object:
    """Find a section without leaking a mutable canonical object."""
    if existing is None:
        return _MISSING
    return _find_by_id(existing.sections, "section_id", section_id)


def _track(section: object, track_id: str) -> object:
    """Find one track inside a section."""
    return _find_by_id(_value(_mapping(section), "tracks"), "track_id", track_id)


def _binding(track: object, binding_id: str) -> object:
    """Find one binding inside a track."""
    return _find_by_id(_value(_mapping(track), "bindings"), "binding_id", binding_id)


def _child_scope(
    section_id: str | None,
    track_id: str | None,
    *,
    fallback_section_id: str | None = None,
    fallback_track_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve child scope from explicit identity or its containing object."""
    return section_id or fallback_section_id, track_id or fallback_track_id


def _raw_intent(value: BaseModel) -> dict[str, Any]:
    """Serialize a partial intent while retaining explicit clear markers."""
    return _plain(value.model_dump(mode="python", exclude_unset=True))  # type: ignore[return-value]


class _PlanBuilder:
    """Collect operations in dependency phases with stable operation IDs."""

    def __init__(self) -> None:
        self.operations: dict[AuthoringOperationPhase, list[AuthoringOperation]] = {
            phase: [] for phase in AuthoringOperationPhase
        }
        self._keys: dict[tuple[object, ...], str] = {}

    def add(
        self,
        *,
        phase: AuthoringOperationPhase,
        action: AuthoringOperationAction,
        object_kind: str,
        object_id: str,
        section_id: str | None = None,
        track_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        depends_on: Sequence[str] = (),
        reason: str,
        key_suffix: str = "",
    ) -> str:
        """Add one operation once and return its stable ID."""
        key = (phase, action, object_kind, object_id, section_id, track_id, key_suffix)
        existing = self._keys.get(key)
        if existing is not None:
            return existing
        operation_id = ":".join(
            part
            for part in (
                action.value,
                object_kind,
                section_id,
                track_id,
                object_id,
                key_suffix or None,
            )
            if part
        )
        operation_id = operation_id.replace(" ", "_")
        dependency_ids = list(dict.fromkeys(depends_on))
        operation = AuthoringOperation(
            operation_id=operation_id,
            phase=phase,
            action=action,
            object_kind=object_kind,
            object_id=object_id,
            section_id=section_id,
            track_id=track_id,
            payload=dict(payload or {}),
            depends_on=dependency_ids,
            reason=reason,
        )
        self.operations[phase].append(operation)
        self._keys[key] = operation_id
        return operation_id

    def flatten(self) -> list[AuthoringOperation]:
        """Return operations in the declared dependency order."""
        return [
            operation
            for phase in AuthoringOperationPhase
            for operation in self.operations[phase]
        ]


def _add_issue(
    issues: list[AuthoringReconciliationIssue],
    *,
    path: str,
    code: str,
    message: str,
) -> None:
    """Append a unique reconciliation issue."""
    if not any(issue.path == path and issue.code == code for issue in issues):
        issues.append(AuthoringReconciliationIssue(path=path, code=code, message=message))


def _context_issues(
    issues: list[AuthoringReconciliationIssue],
    context_issues: Sequence[AuthoringContextIssue],
) -> None:
    """Copy blocking contextual resolution issues into the plan."""
    for issue in context_issues:
        _add_issue(issues, path=issue.path, code=issue.code, message=issue.message)


def _track_mapping(
    intent: AuthoringTrackIntent,
    *,
    base_path: str,
    decisions: Mapping[str, object],
    issues: list[AuthoringReconciliationIssue],
) -> dict[str, Any]:
    """Build a create-shaped track mapping from partial desired state."""
    result: dict[str, Any] = {"id": intent.track_id}
    for field_name in (
        "title",
        "kind",
        "width_mm",
        "x_scale",
        "grid",
        "track_header",
        "extensions",
    ):
        value = _effective_field(intent, field_name, base_path, decisions)
        if value is _MISSING:
            continue
        if _is_clear(value):
            _add_issue(
                issues,
                path=_path(base_path, field_name),
                code="clear_on_create",
                message=f"Cannot clear required track field {field_name!r} while creating a track.",
            )
            continue
        result[field_name] = _plain(value)
    kind = result.get("kind")
    missing_fields: list[str] = []
    if not isinstance(result.get("title"), str):
        missing_fields.append("display title")
    if not isinstance(kind, str):
        missing_fields.append("track form")
    if not isinstance(result.get("width_mm"), (int, float)):
        missing_fields.append("track width")
    if missing_fields:
        _add_issue(
            issues,
            path=base_path,
            code="track_create_incomplete",
            message=(
                f"Cannot create track {intent.track_id!r}: missing "
                f"{', '.join(missing_fields)}. These values could not be resolved "
                "from the request, existing draft, or generic form defaults."
            ),
        )
    if not isinstance(kind, str):
        _add_issue(
            issues,
            path=_path(base_path, "kind"),
            code="track_create_incomplete",
            message="Creating a track requires an explicit or resolved kind.",
        )
        kind = "normal"
    if kind in {"normal", "reference", "array"}:
        result["bindings"] = []
    if kind == "normal":
        result["fills"] = []
    if kind == "annotation":
        result["annotations"] = []
    return result


def _section_mapping(
    intent: AuthoringSectionIntent,
    *,
    base_path: str,
    decisions: Mapping[str, object],
    issues: list[AuthoringReconciliationIssue],
    bootstrap_tracks: Sequence[AuthoringTrackIntent] | None = None,
) -> dict[str, Any]:
    """Build a create-shaped section with one required bootstrap track."""
    result: dict[str, Any] = {"id": intent.section_id}
    for field_name in ("title", "subtitle", "depth_range", "data_source", "extensions"):
        value = _effective_field(intent, field_name, base_path, decisions)
        if value is _MISSING:
            continue
        if _is_clear(value):
            _add_issue(
                issues,
                path=_path(base_path, field_name),
                code="clear_on_create",
                message=f"Cannot clear section field {field_name!r} while creating a section.",
            )
            continue
        result[field_name] = _plain(value)
    tracks = intent.tracks if bootstrap_tracks is None else bootstrap_tracks
    if isinstance(tracks, list):
        result["tracks"] = [
            _track_mapping(
                track,
                base_path=f"{base_path}.tracks[{track.track_id}]",
                decisions=decisions,
                issues=issues,
            )
            for track in tracks
        ]
    else:
        result["tracks"] = []
    if not isinstance(result.get("title"), str) or not result["tracks"]:
        _add_issue(
            issues,
            path=base_path,
            code="section_create_incomplete",
            message="Creating a section requires title and at least one track.",
        )
    return result


def _current_header_slot(header: object, slot_id: str) -> object:
    """Find a general, service-title, or detail header slot by stable ID."""
    mapping = _mapping(header)
    for collection_name in ("general_fields", "service_titles"):
        item = _find_by_id(_value(mapping, collection_name), "slot_id", slot_id)
        if item is not _MISSING:
            return item
    detail = _value(mapping, "detail")
    detail_mapping = _mapping(detail)
    rows = _value(detail_mapping, "rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return _MISSING
    for row in rows:
        for collection_name in ("values", "columns"):
            items = _value(_mapping(row), collection_name)
            if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
                continue
            if collection_name == "columns":
                for column in items:
                    item = _find_by_id(_value(_mapping(column), "cells"), "slot_id", slot_id)
                    if item is not _MISSING:
                        return item
            else:
                item = _find_by_id(items, "slot_id", slot_id)
                if item is not _MISSING:
                    return item
    return _MISSING


def _add_header_slot_operations(
    builder: _PlanBuilder,
    header_intent: AuthoringHeaderIntent,
    current_header: object,
    *,
    decisions: Mapping[str, object],
    unchanged: list[str],
) -> None:
    """Plan field-level updates for stable header slots."""
    collections = (
        ("general_fields", header_intent.general_fields),
        ("service_titles", header_intent.service_titles),
        ("detail_fields", header_intent.detail_fields),
    )
    for collection_name, items in collections:
        if not isinstance(items, list):
            continue
        for _index, item in enumerate(items):
            if not isinstance(item, (AuthoringHeaderFieldIntent, AuthoringServiceTitleIntent)):
                continue
            base_path = f"header.{collection_name}[{item.slot_id}]"
            current = _current_header_slot(current_header, item.slot_id)
            patch = _patch_for_model(
                item,
                current,
                base_path=base_path,
                decisions=decisions,
                ignored={"slot_id"},
            )
            if not patch:
                unchanged.append(base_path)
                continue
            action = (
                AuthoringOperationAction.UPDATE
                if current is not _MISSING
                else AuthoringOperationAction.CREATE
            )
            builder.add(
                phase=AuthoringOperationPhase.REPORT,
                action=action,
                object_kind="header_slot",
                object_id=item.slot_id,
                payload=(
                    {"patch": patch}
                    if action == AuthoringOperationAction.UPDATE
                    else {"object": _raw_intent(item)}
                ),
                reason=f"Apply requested {collection_name} header slot values.",
                key_suffix=collection_name,
            )


def _track_children(
    intent: AuthoringTrackIntent,
) -> tuple[list[object], list[object], list[object]]:
    """Return binding, fill, and annotation child intents from one track."""
    bindings = intent.bindings if isinstance(intent.bindings, list) else []
    fills = intent.fills if isinstance(intent.fills, list) else []
    annotations = intent.annotations if isinstance(intent.annotations, list) else []
    return list(bindings), list(fills), list(annotations)


def _add_track_clear_operations(
    builder: _PlanBuilder,
    intent: AuthoringTrackIntent,
    *,
    section_id: str,
    current_track: object,
) -> None:
    """Turn explicit child-collection clears into idempotent removals."""
    current_mapping = _mapping(current_track)
    if isinstance(intent.bindings, AuthoringClearIntent):
        for binding in _items(_value(current_mapping, "bindings")):
            binding_mapping = _mapping(binding)
            kind = _value(binding_mapping, "kind")
            object_kind = "curve_binding" if kind == "curve" else "raster_binding"
            binding_id = _value(binding_mapping, "binding_id")
            if isinstance(binding_id, str):
                builder.add(
                    phase=AuthoringOperationPhase.FINALIZE,
                    action=AuthoringOperationAction.REMOVE,
                    object_kind=object_kind,
                    object_id=binding_id,
                    section_id=section_id,
                    track_id=intent.track_id,
                    reason="Remove bindings from the explicitly cleared collection.",
                )
    if isinstance(intent.fills, AuthoringClearIntent):
        for fill in _items(_value(current_mapping, "fills")):
            fill_id = _value(_mapping(fill), "fill_id")
            if isinstance(fill_id, str):
                builder.add(
                    phase=AuthoringOperationPhase.FINALIZE,
                    action=AuthoringOperationAction.REMOVE,
                    object_kind="fill",
                    object_id=fill_id,
                    section_id=section_id,
                    track_id=intent.track_id,
                    reason="Remove fills from the explicitly cleared collection.",
                )
    if isinstance(intent.annotations, AuthoringClearIntent):
        for annotation in _items(_value(current_mapping, "annotations")):
            annotation_id = _value(_mapping(annotation), "annotation_id")
            if isinstance(annotation_id, str):
                builder.add(
                    phase=AuthoringOperationPhase.FINALIZE,
                    action=AuthoringOperationAction.REMOVE,
                    object_kind="annotation",
                    object_id=annotation_id,
                    section_id=section_id,
                    track_id=intent.track_id,
                    reason="Remove annotations from the explicitly cleared collection.",
                )


def _add_binding_operation(
    builder: _PlanBuilder,
    intent: AuthoringCurveBindingIntent | AuthoringRasterBindingIntent,
    *,
    section_id: str,
    track_id: str,
    current_track: object,
    base_path: str,
    decisions: Mapping[str, object],
    issues: list[AuthoringReconciliationIssue],
    track_dependency: str | None,
    unchanged: list[str],
) -> None:
    """Plan one scalar or raster binding create/update operation."""
    current = _binding(current_track, intent.binding_id)
    current_mapping = _mapping(current)
    current_kind = _value(current_mapping, "kind")
    expected_kind = "curve" if isinstance(intent, AuthoringCurveBindingIntent) else "raster"
    if current is not _MISSING and current_kind != expected_kind:
        _add_issue(
            issues,
            path=base_path,
            code="binding_kind_mismatch",
            message=(
                f"Binding {intent.binding_id!r} already has kind {current_kind!r}, "
                f"not {expected_kind!r}."
            ),
        )
        return
    channel = _effective_field(intent, "channel", base_path, decisions)
    if current is _MISSING:
        if not isinstance(channel, str):
            _add_issue(
                issues,
                path=_path(base_path, "channel"),
                code="binding_create_incomplete",
                message="Creating a binding requires a resolved source channel.",
            )
        payload = _patch_for_model(
            intent,
            _MISSING,
            base_path=base_path,
            decisions=decisions,
            ignored={"kind", "binding_id", "section_id", "track_id"},
        )
        payload.update({"kind": expected_kind, "binding_id": intent.binding_id})
        dependencies = [track_dependency] if track_dependency else []
        builder.add(
            phase=AuthoringOperationPhase.BINDINGS,
            action=AuthoringOperationAction.CREATE,
            object_kind=f"{expected_kind}_binding",
            object_id=intent.binding_id,
            section_id=section_id,
            track_id=track_id,
            payload={"object": payload},
            depends_on=dependencies,
            reason="Create the requested source-channel binding.",
        )
        return
    if isinstance(channel, str) and _value(current_mapping, "channel") != channel:
        _add_issue(
            issues,
            path=_path(base_path, "channel"),
            code="binding_channel_change_unsupported",
            message="Existing binding channels are immutable; create a new binding ID instead.",
        )
    ignored = {"kind", "binding_id", "section_id", "track_id", "channel"}
    patch = _patch_for_model(
        intent,
        current,
        base_path=base_path,
        decisions=decisions,
        ignored=ignored,
    )
    if not patch:
        unchanged.append(base_path)
        return
    builder.add(
        phase=AuthoringOperationPhase.PRESENTATION,
        action=AuthoringOperationAction.UPDATE,
        object_kind=f"{expected_kind}_binding",
        object_id=intent.binding_id,
        section_id=section_id,
        track_id=track_id,
        payload={"patch": patch},
        reason="Apply requested binding labels, scales, styles, and display settings.",
        key_suffix="presentation",
    )


def _add_fill_operation(
    builder: _PlanBuilder,
    intent: AuthoringFillIntent,
    *,
    section_id: str,
    track_id: str,
    current_track: object,
    base_path: str,
    decisions: Mapping[str, object],
    issues: list[AuthoringReconciliationIssue],
    unchanged: list[str],
    track_dependency: str | None = None,
) -> None:
    """Plan one fill create or update operation."""
    current = _find_by_id(_value(_mapping(current_track), "fills"), "fill_id", intent.fill_id)
    if current is _MISSING:
        payload = _raw_intent(intent)
        payload.pop("section_id", None)
        payload.pop("track_id", None)
        if "kind" not in payload:
            _add_issue(
                issues,
                path=_path(base_path, "kind"),
                code="fill_create_incomplete",
                message="Creating a fill requires a fill kind.",
            )
        builder.add(
            phase=AuthoringOperationPhase.CONTENT,
            action=AuthoringOperationAction.CREATE,
            object_kind="fill",
            object_id=intent.fill_id,
            section_id=section_id,
            track_id=track_id,
            payload={"object": payload},
            reason="Create the requested fill relation after its bindings exist.",
            depends_on=[
                operation.operation_id
                for operation in builder.operations[AuthoringOperationPhase.BINDINGS]
                if operation.section_id == section_id and operation.track_id == track_id
            ] or ([track_dependency] if track_dependency else []),
        )
        return
    patch = _patch_for_model(
        intent,
        current,
        base_path=base_path,
        decisions=decisions,
        ignored={"fill_id", "section_id", "track_id"},
    )
    if not patch:
        unchanged.append(base_path)
        return
    builder.add(
        phase=AuthoringOperationPhase.PRESENTATION,
        action=AuthoringOperationAction.UPDATE,
        object_kind="fill",
        object_id=intent.fill_id,
        section_id=section_id,
        track_id=track_id,
        payload={"patch": patch},
        reason="Apply requested fill targets and presentation settings.",
        key_suffix="presentation",
    )


def _add_annotation_operation(
    builder: _PlanBuilder,
    intent: AuthoringAnnotationIntent,
    *,
    section_id: str,
    track_id: str,
    current_track: object,
    base_path: str,
    issues: list[AuthoringReconciliationIssue],
    unchanged: list[str],
    track_dependency: str | None = None,
) -> None:
    """Plan one typed annotation replacement."""
    current = _find_by_id(
        _value(_mapping(current_track), "annotations"), "annotation_id", intent.annotation_id
    )
    annotation = intent.annotation
    if isinstance(annotation, AuthoringClearIntent):
        if current is not _MISSING:
            builder.add(
                phase=AuthoringOperationPhase.FINALIZE,
                action=AuthoringOperationAction.REMOVE,
                object_kind="annotation",
                object_id=intent.annotation_id,
                section_id=section_id,
                track_id=track_id,
                reason="Remove the explicitly cleared annotation object.",
            )
        return
    if annotation is None:
        _add_issue(
            issues,
            path=_path(base_path, "annotation"),
            code="annotation_create_incomplete",
            message="Creating an annotation requires a typed annotation object.",
        )
        return
    desired = _plain(annotation)
    if current is _MISSING:
        builder.add(
            phase=AuthoringOperationPhase.CONTENT,
            action=AuthoringOperationAction.CREATE,
            object_kind="annotation",
            object_id=intent.annotation_id,
            section_id=section_id,
            track_id=track_id,
            payload={"object": desired},
            depends_on=[track_dependency] if track_dependency else [],
            reason="Create the requested typed annotation object.",
        )
        return
    if _same(current, desired):
        unchanged.append(base_path)
        return
    builder.add(
        phase=AuthoringOperationPhase.PRESENTATION,
        action=AuthoringOperationAction.UPDATE,
        object_kind="annotation",
        object_id=intent.annotation_id,
        section_id=section_id,
        track_id=track_id,
        payload={"object": desired},
        reason="Replace the requested typed annotation object.",
    )


def _process_track(
    builder: _PlanBuilder,
    intent: AuthoringTrackIntent,
    *,
    section_id: str,
    current_section: object,
    base_path: str,
    decisions: Mapping[str, object],
    issues: list[AuthoringReconciliationIssue],
    unchanged: list[str],
    embedded_in_section_create: bool = False,
    section_dependency: str | None = None,
) -> str | None:
    """Reconcile one track and all of its explicitly requested children."""
    current = _track(current_section, intent.track_id)
    current_kind = _value(_mapping(current), "kind")
    desired_kind = _effective_field(intent, "kind", base_path, decisions)
    if current is not _MISSING and isinstance(desired_kind, str) and current_kind != desired_kind:
        _add_issue(
            issues,
            path=_path(base_path, "kind"),
            code="track_kind_change_unsupported",
            message="Existing track kinds are immutable; replace the track explicitly instead.",
        )
    create_id: str | None = None
    if current is _MISSING and not embedded_in_section_create:
        track_object = _track_mapping(
            intent,
            base_path=base_path,
            decisions=decisions,
            issues=issues,
        )
        create_id = builder.add(
            phase=AuthoringOperationPhase.TRACKS,
            action=AuthoringOperationAction.CREATE,
            object_kind="track",
            object_id=intent.track_id,
            section_id=section_id,
            payload={"object": track_object},
            depends_on=[section_dependency] if section_dependency else [],
            reason="Create the requested track form before adding content.",
        )
    elif current is not _MISSING:
        structural_patch = _patch_for_model(
            intent,
            current,
            base_path=base_path,
            decisions=decisions,
            ignored={
                "section_id",
                "track_id",
                "kind",
                "x_scale",
                "grid",
                "track_header",
                "extensions",
                "bindings",
                "fills",
                "annotations",
            },
        )
        if structural_patch:
            builder.add(
                phase=AuthoringOperationPhase.TRACKS,
                action=AuthoringOperationAction.UPDATE,
                object_kind="track",
                object_id=intent.track_id,
                section_id=section_id,
                payload={"patch": structural_patch},
                reason="Apply requested track title and width.",
                key_suffix="structure",
            )
        else:
            unchanged.append(f"{base_path}.structure")
    track_dependency = create_id or section_dependency
    track_for_children = (
        _MISSING if current is _MISSING and embedded_in_section_create else current
    )
    _add_track_clear_operations(
        builder,
        intent,
        section_id=section_id,
        current_track=track_for_children,
    )
    presentation_patch = (
        _patch_for_model(
            intent,
            track_for_children,
            base_path=base_path,
            decisions=decisions,
            ignored={
                "section_id",
                "track_id",
                "kind",
                "title",
                "width_mm",
                "bindings",
                "fills",
                "annotations",
            },
        )
        if current is not _MISSING
        else {}
    )
    if presentation_patch:
        builder.add(
            phase=AuthoringOperationPhase.PRESENTATION,
            action=AuthoringOperationAction.UPDATE,
            object_kind="track",
            object_id=intent.track_id,
            section_id=section_id,
            payload={"patch": presentation_patch},
            reason="Apply requested track scales, grids, headers, and extensions.",
            depends_on=[track_dependency] if track_dependency else [],
            key_suffix="presentation",
        )
    bindings, fills, annotations = _track_children(intent)
    for child in bindings:
        child_base = f"{base_path}.bindings[{child.binding_id}]"
        _add_binding_operation(
            builder,
            child,
            section_id=section_id,
            track_id=intent.track_id,
            current_track=track_for_children,
            base_path=child_base,
            decisions=decisions,
            issues=issues,
            track_dependency=track_dependency,
            unchanged=unchanged,
        )
    for child in fills:
        child_base = f"{base_path}.fills[{child.fill_id}]"
        _add_fill_operation(
            builder,
            child,
            section_id=section_id,
            track_id=intent.track_id,
            current_track=track_for_children,
            base_path=child_base,
            decisions=decisions,
            issues=issues,
            unchanged=unchanged,
            track_dependency=track_dependency,
        )
    for child in annotations:
        child_base = f"{base_path}.annotations[{child.annotation_id}]"
        _add_annotation_operation(
            builder,
            child,
            section_id=section_id,
            track_id=intent.track_id,
            current_track=track_for_children,
            base_path=child_base,
            issues=issues,
            unchanged=unchanged,
            track_dependency=track_dependency,
        )
    return create_id


def _add_order_operations(
    builder: _PlanBuilder,
    *,
    object_kind: str,
    desired_ids: Sequence[str],
    current_ids: Sequence[str],
    section_id: str | None,
    parent_dependencies: Mapping[str, str],
    unchanged: list[str],
) -> None:
    """Plan stable ordering changes after create operations."""
    for desired_index, object_id in enumerate(desired_ids):
        if object_id not in current_ids:
            continue
        current_index = list(current_ids).index(object_id)
        if current_index == desired_index:
            continue
        builder.add(
            phase=AuthoringOperationPhase.FINALIZE,
            action=AuthoringOperationAction.MOVE,
            object_kind=object_kind,
            object_id=object_id,
            section_id=section_id,
            payload={"new_index": desired_index},
            depends_on=[parent_dependencies[object_id]] if object_id in parent_dependencies else [],
            reason=f"Place {object_kind} {object_id!r} at the requested ordered position.",
        )


def _process_remark(
    builder: _PlanBuilder,
    intent: AuthoringRemarkIntent,
    *,
    existing: AuthoringDocumentSpec | None,
    base_path: str,
    decisions: Mapping[str, object],
    unchanged: list[str],
) -> None:
    """Plan one report remark update or creation."""
    current = _find_by_id(
        existing.remarks if existing is not None else (),
        "remark_id",
        intent.remark_id,
    )
    if current is _MISSING:
        builder.add(
            phase=AuthoringOperationPhase.REPORT,
            action=AuthoringOperationAction.CREATE,
            object_kind="remark",
            object_id=intent.remark_id,
            payload={"object": _raw_intent(intent)},
            reason="Create the requested report remark block.",
        )
        return
    patch = _patch_for_model(
        intent,
        current,
        base_path=base_path,
        decisions=decisions,
        ignored={"remark_id"},
    )
    if not patch:
        unchanged.append(base_path)
        return
    builder.add(
        phase=AuthoringOperationPhase.PRESENTATION,
        action=AuthoringOperationAction.UPDATE,
        object_kind="remark",
        object_id=intent.remark_id,
        payload={"patch": patch},
        reason="Apply requested report remark content and presentation.",
    )


def _add_removal_operations(
    builder: _PlanBuilder,
    *,
    intent: AuthoringDocumentIntent,
    existing: AuthoringDocumentSpec | None,
    issues: list[AuthoringReconciliationIssue],
) -> None:
    """Plan explicit object removals last and reject document-setting removal."""
    for removal in intent.removals:
        if removal.object_kind in {"report", "page", "depth", "output", "header", "tail"}:
            _add_issue(
                issues,
                path=f"removals[{removal.object_id}]",
                code="document_setting_removal_unsupported",
                message=f"Document-level object {removal.object_kind!r} cannot be removed.",
            )
            continue
        present = False
        if removal.object_kind == "section":
            present = _section(existing, removal.object_id) is not _MISSING
        elif removal.object_kind == "remark":
            present = (
                _find_by_id(
                    existing.remarks if existing is not None else (),
                    "remark_id",
                    removal.object_id,
                )
                is not _MISSING
            )
        elif removal.section_id and removal.track_id:
            section = _section(existing, removal.section_id)
            track = _track(section, removal.track_id)
            if removal.object_kind == "track":
                present = track is not _MISSING
            elif removal.object_kind in {"curve_binding", "raster_binding"}:
                binding = _binding(track, removal.object_id)
                present = binding is not _MISSING and _value(_mapping(binding), "kind") == (
                    "curve" if removal.object_kind == "curve_binding" else "raster"
                )
            elif removal.object_kind in {"fill", "annotation"}:
                collection = _value(
                    _mapping(track), "fills" if removal.object_kind == "fill" else "annotations"
                )
                field = "fill_id" if removal.object_kind == "fill" else "annotation_id"
                present = _find_by_id(collection, field, removal.object_id) is not _MISSING
        if not present:
            continue
        builder.add(
            phase=AuthoringOperationPhase.FINALIZE,
            action=AuthoringOperationAction.REMOVE,
            object_kind=removal.object_kind,
            object_id=removal.object_id,
            section_id=removal.section_id,
            track_id=removal.track_id,
            reason="Apply the explicit object removal after all desired updates.",
        )


def _add_root_clear_operations(
    builder: _PlanBuilder,
    intent: AuthoringDocumentIntent,
    *,
    existing: AuthoringDocumentSpec | None,
    issues: list[AuthoringReconciliationIssue],
) -> None:
    """Plan explicit root collection clears without treating them as omissions."""
    if isinstance(intent.sections, AuthoringClearIntent):
        _add_issue(
            issues,
            path="sections",
            code="sections_clear_unsupported",
            message="A canonical document must retain at least one section.",
        )
    if isinstance(intent.remarks, AuthoringClearIntent):
        for remark in existing.remarks if existing is not None else ():
            remark_id = _value(_mapping(remark), "remark_id")
            if isinstance(remark_id, str):
                builder.add(
                    phase=AuthoringOperationPhase.FINALIZE,
                    action=AuthoringOperationAction.REMOVE,
                    object_kind="remark",
                    object_id=remark_id,
                    reason="Remove remarks from the explicitly cleared collection.",
                )

    clear_bindings = {
        "curve_bindings": "curve",
        "raster_bindings": "raster",
    }
    for field_name, binding_kind in clear_bindings.items():
        if not isinstance(getattr(intent, field_name), AuthoringClearIntent):
            continue
        for section in existing.sections if existing is not None else ():
            section_id = _value(_mapping(section), "id")
            if not isinstance(section_id, str):
                continue
            for track in _items(_value(_mapping(section), "tracks")):
                track_id = _value(_mapping(track), "id")
                if not isinstance(track_id, str):
                    continue
                for binding in _items(_value(_mapping(track), "bindings")):
                    binding_mapping = _mapping(binding)
                    if _value(binding_mapping, "kind") != binding_kind:
                        continue
                    binding_id = _value(binding_mapping, "binding_id")
                    if isinstance(binding_id, str):
                        builder.add(
                            phase=AuthoringOperationPhase.FINALIZE,
                            action=AuthoringOperationAction.REMOVE,
                            object_kind=f"{binding_kind}_binding",
                            object_id=binding_id,
                            section_id=section_id,
                            track_id=track_id,
                            reason="Remove bindings from the explicitly cleared collection.",
                        )

    for field_name, object_kind, child_field, identity_field in (
        ("fills", "fill", "fills", "fill_id"),
        ("annotations", "annotation", "annotations", "annotation_id"),
    ):
        if not isinstance(getattr(intent, field_name), AuthoringClearIntent):
            continue
        for section in existing.sections if existing is not None else ():
            section_id = _value(_mapping(section), "id")
            if not isinstance(section_id, str):
                continue
            for track in _items(_value(_mapping(section), "tracks")):
                track_id = _value(_mapping(track), "id")
                if not isinstance(track_id, str):
                    continue
                for child in _items(_value(_mapping(track), child_field)):
                    child_id = _value(_mapping(child), identity_field)
                    if isinstance(child_id, str):
                        builder.add(
                            phase=AuthoringOperationPhase.FINALIZE,
                            action=AuthoringOperationAction.REMOVE,
                            object_kind=object_kind,
                            object_id=child_id,
                            section_id=section_id,
                            track_id=track_id,
                            reason="Remove objects from the explicitly cleared collection.",
                        )


def reconcile_authoring(
    desired: AuthoringDocumentIntent | AuthoringContextResolution,
    *,
    existing: AuthoringDocumentSpec | None = None,
    scaffold: AuthoringDocumentSpec | None = None,
    defaults: Mapping[str, Any] | None = None,
    available_channels: Mapping[str, Sequence[AuthoringChannelInput]] | None = None,
    channel_aliases: Sequence[AuthoringChannelAlias | Mapping[str, Any]] = (),
    header_aliases: Mapping[str, Sequence[str]] | None = None,
) -> AuthoringReconciliationPlan:
    """Return an idempotent ordered plan for one partial desired state.

    A raw intent is resolved first using the explicit contextual inputs.  A
    previously resolved intent can be passed directly to avoid repeating that
    work in a planner/executor pipeline.
    """
    resolution = (
        desired
        if isinstance(desired, AuthoringContextResolution)
        else resolve_authoring_context(
            desired,
            existing=existing,
            scaffold=scaffold,
            defaults=defaults,
            available_channels=available_channels,
            channel_aliases=channel_aliases,
            header_aliases=header_aliases,
        )
    )
    issues: list[AuthoringReconciliationIssue] = []
    _context_issues(issues, resolution.issues)
    if not resolution.ready:
        return AuthoringReconciliationPlan(ready=False, issues=issues, warnings=resolution.warnings)

    intent = resolution.resolved_intent
    decisions = _decision_map(resolution)
    builder = _PlanBuilder()
    unchanged: list[str] = []

    report_patch: dict[str, Any] = {}
    for field_name in ("title", "subtitle"):
        desired_value = _effective_field(intent, field_name, "", decisions)
        if desired_value is _MISSING:
            continue
        if _is_clear(desired_value) or existing is None or not _same(
            _value(_mapping(existing), field_name), desired_value
        ):
            report_patch[field_name] = _plain(desired_value)
    if report_patch:
        builder.add(
            phase=AuthoringOperationPhase.REPORT,
            action=AuthoringOperationAction.UPDATE,
            object_kind="report",
            object_id="report",
            payload={"patch": report_patch},
            reason="Apply requested report title and subtitle.",
        )
    elif any(field in intent.model_fields_set for field in ("title", "subtitle")):
        unchanged.append("report")

    for field_name, object_kind in _SINGLETON_FIELDS.items():
        child = getattr(intent, field_name)
        if child is None:
            continue
        current = getattr(existing, field_name, _MISSING) if existing is not None else _MISSING
        if isinstance(child, AuthoringClearIntent):
            builder.add(
                phase=AuthoringOperationPhase.REPORT,
                action=AuthoringOperationAction.UPDATE,
                object_kind=object_kind,
                object_id=object_kind,
                payload={"clear": _plain(child)},
                reason=f"Apply the explicit clear for {object_kind} settings.",
            )
            continue
        patch = _patch_for_model(
            child,
            current,
            base_path=field_name,
            decisions=decisions,
        )
        if patch:
            builder.add(
                phase=AuthoringOperationPhase.REPORT,
                action=AuthoringOperationAction.UPDATE,
                object_kind=object_kind,
                object_id=object_kind,
                payload={"patch": patch},
                reason=f"Apply requested {object_kind} settings.",
            )
        else:
            unchanged.append(field_name)

    if isinstance(intent.header, AuthoringClearIntent):
        builder.add(
            phase=AuthoringOperationPhase.REPORT,
            action=AuthoringOperationAction.UPDATE,
            object_kind="header",
            object_id="header",
            payload={"clear": _plain(intent.header)},
            reason="Apply the explicit header clear.",
        )
    elif isinstance(intent.header, AuthoringHeaderIntent):
        current_header = (
            existing.header
            if existing is not None and existing.header is not None
            else {}
        )
        header_patch = _patch_for_model(
            intent.header,
            current_header,
            base_path="header",
            decisions=decisions,
            ignored={"general_fields", "service_titles", "detail_fields"},
        )
        if header_patch:
            builder.add(
                phase=AuthoringOperationPhase.REPORT,
                action=AuthoringOperationAction.UPDATE,
                object_kind="header",
                object_id="header",
                payload={"patch": header_patch},
                reason="Apply requested header metadata and detail layout.",
            )
        _add_header_slot_operations(
            builder,
            intent.header,
            current_header,
            decisions=decisions,
            unchanged=unchanged,
        )

    section_create_ids: dict[str, str] = {}
    section_intents = intent.sections if isinstance(intent.sections, list) else []
    for section_intent in section_intents:
        section_base = f"sections[{section_intent.section_id}]"
        current_section = _section(existing, section_intent.section_id)
        if current_section is _MISSING:
            section_object = _section_mapping(
                section_intent,
                base_path=section_base,
                decisions=decisions,
                issues=issues,
                # AuthoringSectionSpec requires one track at creation time.
                # The remaining tracks are emitted in the TRACKS phase below.
                bootstrap_tracks=(section_intent.tracks[:1] if section_intent.tracks else []),
            )
            section_create_ids[section_intent.section_id] = builder.add(
                phase=AuthoringOperationPhase.SECTIONS,
                action=AuthoringOperationAction.CREATE,
                object_kind="section",
                object_id=section_intent.section_id,
                payload={"object": section_object},
                reason="Create the requested report section before its children.",
            )
        else:
            section_patch = _patch_for_model(
                section_intent,
                current_section,
                base_path=section_base,
                decisions=decisions,
                ignored={"section_id", "tracks"},
            )
            if section_patch:
                builder.add(
                    phase=AuthoringOperationPhase.SECTIONS,
                    action=AuthoringOperationAction.UPDATE,
                    object_kind="section",
                    object_id=section_intent.section_id,
                    payload={"patch": section_patch},
                    reason="Apply requested section title, depth range, and source settings.",
                )
            else:
                unchanged.append(f"{section_base}.structure")
        if isinstance(section_intent.tracks, list):
            current_tracks = _value(_mapping(current_section), "tracks")
            if not isinstance(current_tracks, Sequence) or isinstance(current_tracks, (str, bytes)):
                current_tracks = ()
            current_track_ids = [
                str(_value(_mapping(track), "id"))
                for track in current_tracks or ()
                if _value(_mapping(track), "id") is not _MISSING
            ]
            embedded = current_section is _MISSING
            bootstrap_track_id = (
                section_intent.tracks[0].track_id
                if embedded and section_intent.tracks
                else None
            )
            track_dependencies: dict[str, str] = {}
            for track_intent in section_intent.tracks:
                track_base = f"{section_base}.tracks[{track_intent.track_id}]"
                track_id = _process_track(
                    builder,
                    track_intent,
                    section_id=section_intent.section_id,
                    current_section=current_section,
                    base_path=track_base,
                    decisions=decisions,
                    issues=issues,
                    unchanged=unchanged,
                    embedded_in_section_create=(
                        embedded and track_intent.track_id == bootstrap_track_id
                    ),
                    section_dependency=section_create_ids.get(section_intent.section_id),
                )
                if track_id:
                    track_dependencies[track_intent.track_id] = track_id
            _add_order_operations(
                builder,
                object_kind="track",
                desired_ids=[track.track_id for track in section_intent.tracks],
                current_ids=current_track_ids,
                section_id=section_intent.section_id,
                parent_dependencies=track_dependencies,
                unchanged=unchanged,
            )

    if section_intents:
        current_section_ids = [
            str(_value(_mapping(section), "id"))
            for section in (existing.sections if existing is not None else ())
            if _value(_mapping(section), "id") is not _MISSING
        ]
        _add_order_operations(
            builder,
            object_kind="section",
            desired_ids=[section.section_id for section in section_intents],
            current_ids=current_section_ids,
            section_id=None,
            parent_dependencies=section_create_ids,
            unchanged=unchanged,
        )

    if isinstance(intent.remarks, list):
        current_remark_ids = [
            str(_value(_mapping(remark), "remark_id"))
            for remark in (existing.remarks if existing is not None else ())
            if _value(_mapping(remark), "remark_id") is not _MISSING
        ]
        for remark in intent.remarks:
            _process_remark(
                builder,
                remark,
                existing=existing,
                base_path=f"remarks[{remark.remark_id}]",
                decisions=decisions,
                unchanged=unchanged,
            )
        _add_order_operations(
            builder,
            object_kind="remark",
            desired_ids=[remark.remark_id for remark in intent.remarks],
            current_ids=current_remark_ids,
            section_id=None,
            parent_dependencies={},
            unchanged=unchanged,
        )

    # Direct child collections are supported for callers that do not nest them
    # under a section/track intent.  Scope is mandatory because object identity
    # alone is not enough once the same channel is bound in multiple sections.
    processed_bindings: set[tuple[str, str, str]] = set()
    for collection_name, expected_kind, items in (
        ("curve_bindings", "curve", intent.curve_bindings),
        ("raster_bindings", "raster", intent.raster_bindings),
    ):
        if not isinstance(items, list):
            continue
        for item in items:
            section_id, track_id = _child_scope(item.section_id, item.track_id)
            if not section_id or not track_id:
                _add_issue(
                    issues,
                    path=f"{collection_name}[{item.binding_id}]",
                    code="binding_scope_missing",
                    message="Direct binding intents require section_id and track_id.",
                )
                continue
            key = (expected_kind, section_id, item.binding_id)
            if key in processed_bindings:
                continue
            processed_bindings.add(key)
            current_section = _section(existing, section_id)
            current_track = _track(current_section, track_id)
            _add_binding_operation(
                builder,
                item,
                section_id=section_id,
                track_id=track_id,
                current_track=current_track,
                base_path=f"{collection_name}[{item.binding_id}]",
                decisions=decisions,
                issues=issues,
                track_dependency=section_create_ids.get(section_id),
                unchanged=unchanged,
            )

    for collection_name, items in (
        ("fills", intent.fills),
        ("annotations", intent.annotations),
    ):
        if not isinstance(items, list):
            continue
        for item in items:
            section_id, track_id = _child_scope(item.section_id, item.track_id)
            object_id = (
                item.fill_id
                if isinstance(item, AuthoringFillIntent)
                else item.annotation_id
            )
            if not section_id or not track_id:
                _add_issue(
                    issues,
                    path=f"{collection_name}[{object_id}]",
                    code="content_scope_missing",
                    message="Direct content intents require section_id and track_id.",
                )
                continue
            current_section = _section(existing, section_id)
            current_track = _track(current_section, track_id)
            base_path = f"{collection_name}[{object_id}]"
            if isinstance(item, AuthoringFillIntent):
                _add_fill_operation(
                    builder,
                    item,
                    section_id=section_id,
                    track_id=track_id,
                    current_track=current_track,
                    base_path=base_path,
                    decisions=decisions,
                    issues=issues,
                    unchanged=unchanged,
                    track_dependency=section_create_ids.get(section_id),
                )
            else:
                _add_annotation_operation(
                    builder,
                    item,
                    section_id=section_id,
                    track_id=track_id,
                    current_track=current_track,
                    base_path=base_path,
                    issues=issues,
                    unchanged=unchanged,
                    track_dependency=section_create_ids.get(section_id),
                )

    _add_root_clear_operations(builder, intent, existing=existing, issues=issues)
    _add_removal_operations(builder, intent=intent, existing=existing, issues=issues)
    operations = builder.flatten()
    return AuthoringReconciliationPlan(
        ready=not issues,
        operations=operations,
        issues=issues,
        unchanged_paths=list(dict.fromkeys(unchanged)),
        warnings=resolution.warnings,
    )


__all__ = [
    "AuthoringOperation",
    "AuthoringOperationAction",
    "AuthoringOperationObjectKind",
    "AuthoringOperationPhase",
    "AuthoringReconciliationIssue",
    "AuthoringReconciliationPlan",
    "reconcile_authoring",
]
