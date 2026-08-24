"""Thin model-facing MCP projection over the deterministic authoring service."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..agent.tool_contract import StableToolProfile, stable_tool_profile
from ..authoring_service import (
    AuthoringService,
    AuthoringTarget,
    CreateRemarkRequest,
    CreateSectionRequest,
    MoveRequest,
    RemarkPatch,
    RemoveRequest,
    ReportPatch,
    UpdateDepthRequest,
    UpdateOutputRequest,
    UpdatePageRequest,
    UpdateRemarkRequest,
    UpdateReportRequest,
)
from ..errors import TemplateValidationError
from ..model.authoring import (
    AuthoringOutputSpec,
    AuthoringRemarkSpec,
    AuthoringSectionSpec,
)
from . import service
from .telemetry import dispatch_started, emit_dispatch_event, new_request_id

ImageFactory = Callable[[bytes], object]
_REMARK_CONTENT_ERROR = (
    "edit_remarks(operation='add') requires actual remark content. "
    "Provide either non-empty remark.text or at least one item in remark.lines. "
    "A title/alignment alone is not a valid remark."
)
_DEPTH_RANGE_ERROR = (
    "depth_range must use {minimum: number, maximum: number, unit: string?} "
    "with maximum greater than minimum and no extra fields."
)


class DepthRangeInput(BaseModel):
    """Public MCP representation of one ordered section depth range."""

    model_config = ConfigDict(extra="forbid")

    minimum: float
    maximum: float
    unit: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_order(self) -> DepthRangeInput:
        """Reject zero-height and reversed section windows at the boundary."""
        if self.maximum <= self.minimum:
            raise ValueError("maximum must be greater than minimum")
        return self


def _depth_range_input(
    value: object,
    *,
    tool_name: str,
) -> tuple[tuple[float, float], str | None]:
    """Convert the public range object to the domain tuple and unit pair."""
    if not isinstance(value, Mapping):
        raise TemplateValidationError(
            f"{tool_name} depth_range must use an object with numeric minimum and maximum "
            "and optional unit; lists are not supported."
        )
    try:
        parsed = DepthRangeInput.model_validate(value)
    except ValidationError as exc:
        raise TemplateValidationError(f"{tool_name} {_DEPTH_RANGE_ERROR}") from exc
    return (parsed.minimum, parsed.maximum), parsed.unit


def _json_safe(value: object) -> object:
    """Convert inspection values, including NumPy scalars, to JSON-safe values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump(mode="json"))
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except (TypeError, ValueError):
            pass
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return _json_safe(tolist())
        except (TypeError, ValueError):
            pass
    return str(value)


def _required(arguments: Mapping[str, object], key: str) -> object:
    if key not in arguments or arguments[key] is None:
        raise TemplateValidationError(f"Stable tool requires {key!r}.")
    return arguments[key]


def _path(arguments: Mapping[str, object]) -> str:
    return str(_required(arguments, "logfile_path"))


def _rooted_authoring(logfile_path: str, root: str | Path) -> tuple[Path, AuthoringService]:
    server_root = service.resolve_server_root(root)
    resolved = service._resolve_user_path(
        logfile_path,
        root=server_root,
        context="logfile_path",
    )
    spec = service.load_logfile(resolved, allowed_root=server_root)
    return resolved, AuthoringService.from_mapping(service.report_to_dict(spec))


def _persist_authoring(
    logfile_path: Path,
    authoring: AuthoringService,
    root: str | Path,
) -> None:
    service._persist_validated_logfile_mapping(
        service.authoring_document_to_logfile_mapping(authoring.document),
        logfile_path=logfile_path,
        root=service.resolve_server_root(root),
    )


def _snapshot(
    logfile_path: str,
    target: Mapping[str, object],
    root: str | Path,
) -> dict[str, object] | None:
    try:
        _, authoring = _rooted_authoring(logfile_path, root)
        if target.get("object_kind") == "document":
            value: object = authoring.document
        else:
            value = authoring.get(AuthoringTarget.model_validate(dict(target)))
    except (FileNotFoundError, KeyError, TemplateValidationError, ValueError):
        return None
    if isinstance(value, BaseModel):
        return _normalize_authoring_snapshot(value.model_dump(mode="json", exclude_none=True))
    return None


_IDENTITY_FIELDS = (
    "id",
    "binding_id",
    "fill_id",
    "annotation_id",
    "remark_id",
    "slot_id",
    "channel",
    "title",
    "label",
    "kind",
)
_COLLECTION_FIELDS = ("tracks", "bindings", "annotations", "fills", "remarks", "rows")
_COMPATIBILITY_DIFF_FIELDS = {"extensions"}


def _object_summary(value: object) -> dict[str, object]:
    """Return a bounded identity summary for an added or removed object."""
    if not isinstance(value, Mapping):
        return {"value": _json_safe(value)}
    summary = {
        key: _json_safe(value[key])
        for key in _IDENTITY_FIELDS
        if key in value and value[key] is not None
    }
    for key in _COLLECTION_FIELDS:
        collection = value.get(key)
        if isinstance(collection, list):
            summary[f"{key}_count"] = len(collection)
    return summary or {"field_count": len(value)}


def _added_or_removed_value(value: object) -> object:
    """Return compact evidence for a value that exists on one side only."""
    if isinstance(value, Mapping):
        return _object_summary(value)
    if isinstance(value, list):
        if len(value) <= 12 and all(not isinstance(item, (Mapping, list)) for item in value):
            return _json_safe(value)
        return {"count": len(value)}
    return _json_safe(value)


def _normalize_authoring_snapshot(value: object) -> object:
    """Remove serialization defaults that do not represent an authored change."""
    if isinstance(value, list):
        return [_normalize_authoring_snapshot(item) for item in value]
    if not isinstance(value, Mapping):
        return value
    normalized = {str(key): _normalize_authoring_snapshot(item) for key, item in value.items()}
    channel = normalized.get("channel")
    if isinstance(channel, str) and normalized.get("label") == channel:
        normalized.pop("label", None)
    return normalized


def _collection_identifier(value: Mapping[str, object]) -> str | None:
    """Return a stable identifier for one nested authoring collection item."""
    for key in ("id", "binding_id", "fill_id", "annotation_id", "remark_id", "slot_id"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None


def _diff_collection(
    before: list[object],
    after: list[object],
    *,
    path: str,
    changed_fields: list[str],
) -> tuple[object, object]:
    """Return a compact change summary for one list-valued authoring property."""
    before_items = [item for item in before if isinstance(item, Mapping)]
    after_items = [item for item in after if isinstance(item, Mapping)]
    before_ids = {_collection_identifier(item): item for item in before_items}
    after_ids = {_collection_identifier(item): item for item in after_items}
    has_stable_ids = (
        len(before_items) == len(before)
        and len(after_items) == len(after)
        and None not in before_ids
        and None not in after_ids
        and len(before_ids) == len(before)
        and len(after_ids) == len(after)
    )
    if has_stable_ids:
        before_changes: dict[str, object] = {}
        after_changes: dict[str, object] = {}
        for identifier in sorted(set(before_ids) | set(after_ids)):
            item_path = f"{path}[{identifier}]"
            previous = before_ids.get(identifier)
            current = after_ids.get(identifier)
            if previous is None:
                changed_fields.append(item_path)
                before_changes[identifier] = {}
                after_changes[identifier] = _object_summary(current)
                continue
            if current is None:
                changed_fields.append(item_path)
                before_changes[identifier] = _object_summary(previous)
                after_changes[identifier] = {}
                continue
            previous_change, current_change = _diff_value(
                previous,
                current,
                path=item_path,
                changed_fields=changed_fields,
            )
            if previous_change != {} or current_change != {}:
                before_changes[identifier] = previous_change
                after_changes[identifier] = current_change
        return {"by_id": before_changes}, {"by_id": after_changes}
    if (
        len(before) <= 12
        and len(after) <= 12
        and all(not isinstance(item, (Mapping, list)) for item in [*before, *after])
    ):
        changed_fields.append(path)
        return _json_safe(before), _json_safe(after)
    changed_fields.append(path)
    return {"count": len(before)}, {"count": len(after)}


def _diff_value(
    before: object,
    after: object,
    *,
    path: str,
    changed_fields: list[str],
) -> tuple[object, object]:
    """Return changed values only, retaining nested identities where available."""
    if before == after:
        return {}, {}
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        before_changes: dict[str, object] = {}
        after_changes: dict[str, object] = {}
        for key in sorted(set(before) | set(after)):
            # Compatibility extensions are materialized by legacy YAML conversion.
            # They are not accepted by stable tools, so reporting them as an edit
            # would bury the requested mutation under serialization noise.
            if key in _COMPATIBILITY_DIFF_FIELDS:
                continue
            item_path = f"{path}.{key}" if path else str(key)
            previous = before.get(key)
            current = after.get(key)
            if key not in before:
                changed_fields.append(item_path)
                before_changes[str(key)] = {}
                after_changes[str(key)] = _added_or_removed_value(current)
                continue
            if key not in after:
                changed_fields.append(item_path)
                before_changes[str(key)] = _added_or_removed_value(previous)
                after_changes[str(key)] = {}
                continue
            previous_change, current_change = _diff_value(
                previous,
                current,
                path=item_path,
                changed_fields=changed_fields,
            )
            if previous_change != {} or current_change != {}:
                before_changes[str(key)] = previous_change
                after_changes[str(key)] = current_change
        return before_changes, after_changes
    if isinstance(before, list) and isinstance(after, list):
        return _diff_collection(before, after, path=path, changed_fields=changed_fields)
    changed_fields.append(path or "value")
    return _json_safe(before), _json_safe(after)


def _mutation_evidence(
    before: Mapping[str, object] | None,
    after: Mapping[str, object] | None,
) -> tuple[bool, list[str], dict[str, object], dict[str, object]]:
    """Build compact persisted-change evidence without returning full objects."""
    if before is None and after is None:
        return False, [], {}, {}
    if before is None:
        return True, ["created"], {}, _object_summary(after)
    if after is None:
        return True, ["removed"], _object_summary(before), {}
    changed_fields: list[str] = []
    previous, current = _diff_value(before, after, path="", changed_fields=changed_fields)
    return bool(changed_fields), changed_fields, dict(previous), dict(current)


def _draft_text(logfile_path: str, root: str | Path) -> str | None:
    """Return the current draft text without loading source data or rendering."""
    resolved = service._resolve_user_path(
        logfile_path,
        root=service.resolve_server_root(root),
        context="logfile_path",
    )
    if not resolved.is_file():
        return None
    return resolved.read_text(encoding="utf-8")


def _mutation(
    logfile_path: str,
    target: Mapping[str, object],
    root: str | Path,
    mutate: Callable[[], object],
) -> dict[str, object]:
    before = _snapshot(logfile_path, target, root)
    mutation_result = mutate()
    after = _snapshot(logfile_path, target, root)
    changed, changed_fields, before_change, after_change = _mutation_evidence(before, after)
    return {
        "ok": True,
        "changed": changed,
        "target": dict(target),
        "changed_fields": changed_fields,
        "before": before_change,
        "after": after_change,
        "already_exists": bool(getattr(mutation_result, "already_exists", False)),
        "id_map": dict(getattr(mutation_result, "id_map", {}) or {}),
        "warnings": [],
        "next_steps": [],
    }


def _scale_snapshot(
    logfile_path: str,
    *,
    section_id: str,
    track_id: str,
    root: str | Path,
) -> dict[str, object]:
    """Capture a track and its curve bindings for scale postconditions."""
    _, authoring = _rooted_authoring(logfile_path, root)
    track = authoring.get(
        AuthoringTarget(object_kind="track", object_id=track_id, section_id=section_id)
    )
    bindings = [
        authoring.get(ref)
        for ref in authoring.list("curve_binding", section_id=section_id, track_id=track_id)
    ]
    return {
        "track": _normalize_authoring_snapshot(track.model_dump(mode="json", exclude_none=True)),
        "bindings": [
            _normalize_authoring_snapshot(item.model_dump(mode="json", exclude_none=True))
            for item in bindings
        ],
    }


def _scale_mutation(
    logfile_path: str,
    *,
    section_id: str,
    track_id: str,
    root: str | Path,
    mutate: Callable[[], object],
) -> dict[str, object]:
    """Apply one synchronized scale update and return before/after evidence."""
    before = _scale_snapshot(
        logfile_path,
        section_id=section_id,
        track_id=track_id,
        root=root,
    )
    mutate()
    after = _scale_snapshot(
        logfile_path,
        section_id=section_id,
        track_id=track_id,
        root=root,
    )
    changed, changed_fields, before_change, after_change = _mutation_evidence(before, after)
    return {
        "ok": True,
        "changed": changed,
        "target": _target("track", track_id, {"section_id": section_id}),
        "changed_fields": changed_fields,
        "before": before_change,
        "after": after_change,
        "warnings": [],
        "next_steps": [],
    }


def _matplotlib_style_snapshot(
    logfile_path: str,
    root: str | Path,
) -> dict[str, object]:
    """Return the persisted report-wide Matplotlib style as JSON-safe data."""
    resolved_logfile = service._resolve_user_path(
        logfile_path,
        root=service.resolve_server_root(root),
        context="logfile_path",
    )
    _, mapping = service._normalize_logfile_mapping_from_path(
        resolved_logfile,
        allowed_root=service.resolve_server_root(root),
    )
    render_mapping = service._logfile_mapping_render(mapping)
    matplotlib_mapping = render_mapping.get("matplotlib")
    if not isinstance(matplotlib_mapping, Mapping):
        return {}
    style = matplotlib_mapping.get("style")
    return _json_safe(style) if isinstance(style, Mapping) else {}


def _matplotlib_style_mutation(
    logfile_path: str,
    *,
    style_patch: Mapping[str, object],
    root: str | Path,
) -> dict[str, object]:
    """Apply report style and expose a deterministic before/after postcondition."""
    before = _matplotlib_style_snapshot(logfile_path, root)
    service.set_matplotlib_style(
        logfile_path,
        style_patch=dict(style_patch),
        root=root,
    )
    after = _matplotlib_style_snapshot(logfile_path, root)
    changed, changed_fields, before_change, after_change = _mutation_evidence(
        {"style": before},
        {"style": after},
    )
    return {
        "ok": True,
        "changed": changed,
        "target": {"object_kind": "document", "object_id": "document"},
        "changed_fields": changed_fields,
        "before": before_change,
        "after": after_change,
        "warnings": [],
        "next_steps": [],
    }


def _flat_patch(arguments: Mapping[str, object], keys: set[str]) -> dict[str, object]:
    patch = arguments.get("patch")
    values = dict(patch) if isinstance(patch, Mapping) else {}
    for key in keys:
        if key in arguments and arguments[key] is not None:
            values[key] = arguments[key]
    return values


def _target(kind: str, object_id: str, arguments: Mapping[str, object]) -> dict[str, object]:
    value: dict[str, object] = {"object_kind": kind, "object_id": object_id}
    for key in ("section_id", "track_id"):
        if arguments.get(key) is not None:
            value[key] = str(arguments[key])
    return value


_SUMMARY_OBJECT_FIELDS = (
    "subtitle",
    "width_mm",
    "depth_range",
    "scale",
    "value",
    "unit",
    "provenance",
    "availability",
    "render_mode",
    "profile",
    "normalization",
    "show_raster",
)
_VOCABULARY_FAMILIES = {
    "track": ("track_kinds", "track_patch_keys", "track_archetypes", "move_track_selectors"),
    "scale": ("scale_kinds",),
    "fill": ("curve_fill_kinds",),
    "annotation": ("annotation_object_kinds", "annotation_patch_keys"),
    "header": ("heading_patch_keys", "heading_field_catalog", "header_archetypes"),
    "section": ("section_patch_keys",),
    "page": (
        "page_patch_keys",
        "render_patch_keys",
        "depth_axis_patch_keys",
        "report_detail_kinds",
    ),
    "curve_binding": ("curve_binding_patch_keys",),
    "raster_binding": ("raster_binding_patch_keys",),
}


def _authoring_object_summary(item: Mapping[str, object]) -> dict[str, object]:
    """Project one canonical authoring object into a compact inspection row."""
    reference = item.get("ref")
    raw_object = item.get("object")
    object_mapping = raw_object if isinstance(raw_object, Mapping) else {}
    summary = _object_summary(object_mapping)
    for field in _SUMMARY_OBJECT_FIELDS:
        value = object_mapping.get(field)
        if value is not None:
            summary[field] = _json_safe(value)
    compact_reference = (
        {
            key: _json_safe(reference[key])
            for key in ("object_kind", "object_id", "section_id", "track_id", "index")
            if isinstance(reference, Mapping) and reference.get(key) is not None
        }
        if isinstance(reference, Mapping)
        else _json_safe(reference)
    )
    return {"ref": compact_reference, "summary": summary}


def _compact_vocabulary_value(value: object) -> object:
    """Summarize one vocabulary member without hiding its usable scalar values."""
    if isinstance(value, list):
        if all(isinstance(item, str) for item in value):
            return list(value)
        identifiers = [
            str(item[key])
            for item in value
            if isinstance(item, Mapping)
            for key in ("id", "key", "name")
            if isinstance(item.get(key), str)
        ]
        return {"count": len(value), "ids": identifiers}
    if isinstance(value, Mapping):
        return {"count": len(value), "keys": sorted(str(key) for key in value)}
    return _json_safe(value)


def _compact_target_summary(value: object) -> dict[str, object] | None:
    """Keep target context useful without returning binding and annotation payloads."""
    if not isinstance(value, Mapping):
        return None
    keys = (
        "target_kind",
        "target_path",
        "section_ids",
        "track_ids_by_section",
        "available_channels_by_section",
        "heading_general_field_keys",
        "has_heading",
        "has_remarks",
        "has_tail",
    )
    return {key: _json_safe(value[key]) for key in keys if key in value}


def _vocabulary_inspection(
    result: object,
    *,
    family: object,
    detail: object,
) -> dict[str, object]:
    """Apply the public vocabulary scope and detail controls to one service result."""
    normalized_detail = str(detail or "summary").strip().lower()
    if normalized_detail not in {"summary", "full"}:
        raise TemplateValidationError("inspect_vocab detail must be 'summary' or 'full'.")
    normalized_family = str(family or "").strip().lower()
    if normalized_family and normalized_family not in _VOCABULARY_FAMILIES:
        allowed = ", ".join(sorted(_VOCABULARY_FAMILIES))
        raise TemplateValidationError(
            f"Unsupported inspect_vocab family {family!r}. Allowed: {allowed}."
        )
    payload = asdict(result)
    selected_keys = (
        _VOCABULARY_FAMILIES[normalized_family]
        if normalized_family
        else tuple(key for keys in _VOCABULARY_FAMILIES.values() for key in keys)
    )
    values = {key: payload[key] for key in selected_keys if key in payload}
    response: dict[str, object] = {
        "family": normalized_family or "all",
        "detail": normalized_detail,
        "resource_uris": payload["resource_uris"],
    }
    if normalized_detail == "full":
        response["values"] = _json_safe(values)
        response["target_summary"] = _json_safe(payload.get("target_summary"))
        return response
    response["available_families"] = sorted(_VOCABULARY_FAMILIES)
    response["values"] = (
        {key: _compact_vocabulary_value(value) for key, value in values.items()}
        if normalized_family
        else {}
    )
    response["target_summary"] = _compact_target_summary(payload.get("target_summary"))
    return response


def _source_inspection_summary(
    value: Mapping[str, object],
    *,
    include_metadata: bool,
) -> dict[str, object]:
    """Project raw source metadata into the default model-facing source summary."""
    channels = value.get("channels")
    channel_summaries = []
    if isinstance(channels, list):
        channel_summaries = [
            {
                key: _json_safe(channel[key])
                for key in (
                    "mnemonic",
                    "kind",
                    "value_unit",
                    "description",
                    "value_shape",
                    "sample_axis_count",
                    "sample_unit",
                )
                if isinstance(channel, Mapping) and key in channel
            }
            for channel in channels
            if isinstance(channel, Mapping)
        ]
    summary = {
        key: _json_safe(value[key])
        for key in (
            "source_path",
            "source_format_detected",
            "dataset_name",
            "index",
            "channel_count",
            "warnings",
        )
        if key in value
    }
    summary["channels"] = channel_summaries
    if include_metadata:
        summary["metadata_keys"] = _json_safe(value.get("metadata_keys", []))
        summary["well_metadata"] = _json_safe(value.get("well_metadata", {}))
        summary["provenance"] = _json_safe(value.get("provenance", {}))
    return summary


def _logfile_source_summary(value: Mapping[str, object]) -> dict[str, object]:
    """Return source-relevant draft identity without the full page configuration."""
    sections = value.get("sections")
    section_summaries = (
        [
            {
                key: _json_safe(section[key])
                for key in (
                    "id",
                    "title",
                    "source_path",
                    "source_format",
                    "depth_range",
                    "track_ids",
                    "track_kinds",
                )
                if isinstance(section, Mapping) and key in section
            }
            for section in sections
            if isinstance(section, Mapping)
        ]
        if isinstance(sections, list)
        else []
    )
    return {
        "name": _json_safe(value.get("name")),
        "section_ids": _json_safe(value.get("section_ids", [])),
        "sections": section_summaries,
    }


def _channel_availability_summary(value: Mapping[str, object]) -> dict[str, object]:
    """Return requested-channel evidence without echoing full source metadata."""
    return {
        key: _json_safe(value[key])
        for key in (
            "target_kind",
            "source_path",
            "source_format_detected",
            "logfile_path",
            "section_id",
            "requested_channels",
            "found_channels",
            "missing_channels",
            "resolutions",
            "warnings",
        )
        if key in value
    }


def _direct_section_add(arguments: Mapping[str, object], root: str | Path) -> object:
    path, authoring = _rooted_authoring(_path(arguments), root)
    payload = arguments.get("section")
    if not isinstance(payload, Mapping):
        raise TemplateValidationError("section is required for edit_section operation 'add'.")
    section = AuthoringSectionSpec.model_validate(dict(payload))
    result = authoring.create(CreateSectionRequest(section=section))
    _persist_authoring(path, authoring, root)
    return result


def _direct_section_remove(arguments: Mapping[str, object], root: str | Path) -> object:
    path, authoring = _rooted_authoring(_path(arguments), root)
    section_id = str(_required(arguments, "section_id"))
    result = authoring.remove(
        RemoveRequest(target=AuthoringTarget(object_kind="section", object_id=section_id))
    )
    _persist_authoring(path, authoring, root)
    return result


def _direct_section_update(arguments: Mapping[str, object], root: str | Path) -> object:
    logfile_path = _path(arguments)
    section_id = str(_required(arguments, "section_id"))
    patch = _flat_patch(arguments, {"title", "subtitle", "depth_range"})
    depth_range = patch.pop("depth_range", None)
    normalized_range: tuple[float, float] | None = None
    depth_range_unit: str | None = None
    if depth_range is not None:
        normalized_range, depth_range_unit = _depth_range_input(
            depth_range,
            tool_name="edit_section",
        )
    return service.update_section(
        logfile_path,
        section_id=section_id,
        title=patch.get("title"),
        subtitle=patch.get("subtitle"),
        depth_range=normalized_range,
        depth_range_unit=depth_range_unit,
        root=root,
    )


def _direct_section_move(arguments: Mapping[str, object], root: str | Path) -> object:
    path, authoring = _rooted_authoring(_path(arguments), root)
    section_id = str(_required(arguments, "section_id"))
    result = authoring.move(
        MoveRequest(
            object_kind="section",
            object_id=section_id,
            new_index=int(_required(arguments, "new_index")),
        )
    )
    _persist_authoring(path, authoring, root)
    return result


def _clear_binding_family(
    logfile_path: str,
    *,
    section_id: str,
    track_id: str,
    object_kind: str,
    root: str | Path,
) -> object:
    path, authoring = _rooted_authoring(logfile_path, root)
    refs = authoring.list(object_kind, section_id=section_id, track_id=track_id)
    for ref in refs:
        authoring.remove(
            RemoveRequest(
                target=AuthoringTarget(
                    object_kind=object_kind,
                    object_id=ref.object_id,
                    section_id=section_id,
                    track_id=track_id,
                )
            )
        )
    _persist_authoring(path, authoring, root)
    return refs


def _annotation_index(
    logfile_path: str,
    *,
    section_id: str,
    track_id: str,
    value: object,
    root: str | Path,
) -> int:
    text = str(value)
    if text.isdigit():
        return int(text)
    _, authoring = _rooted_authoring(logfile_path, root)
    for ref in authoring.list("annotation", section_id=section_id, track_id=track_id):
        if ref.object_id == text:
            return ref.index
    raise TemplateValidationError(f"Unknown annotation_id {text!r}.")


def _binding_channel_from_id(
    arguments: Mapping[str, object],
    *,
    object_kind: str,
    root: str | Path,
) -> str | None:
    """Resolve an existing binding channel from its canonical binding id."""
    binding_id = arguments.get("binding_id")
    if binding_id is None:
        return None
    try:
        _, authoring = _rooted_authoring(_path(arguments), root)
        refs = authoring.list(
            object_kind,
            section_id=str(arguments.get("section_id")),
            track_id=str(arguments.get("track_id")),
        )
        for ref in refs:
            if ref.object_id != str(binding_id):
                continue
            binding = authoring.get(ref)
            channel = getattr(binding, "channel", None)
            return str(channel) if channel is not None else None
    except (KeyError, TypeError, ValueError, TemplateValidationError):
        return None
    return None


def _remarks_mutation(arguments: Mapping[str, object], root: str | Path) -> object:
    path, authoring = _rooted_authoring(_path(arguments), root)
    operation = str(_required(arguments, "operation"))
    if operation == "clear":
        authoring.replace_document(authoring.document.model_copy(update={"remarks": []}))
        result: object = authoring.document
    elif operation == "add":
        payload = arguments.get("remark")
        if not isinstance(payload, Mapping):
            raise TemplateValidationError(_REMARK_CONTENT_ERROR)
        text = payload.get("text")
        lines = payload.get("lines")
        if not (isinstance(text, str) and text) and not (
            isinstance(lines, list) and lines
        ):
            raise TemplateValidationError(_REMARK_CONTENT_ERROR)
        try:
            remark = AuthoringRemarkSpec.model_validate(dict(payload))
        except ValidationError as exc:
            detail = exc.errors()[0].get("msg", "invalid remark fields")
            raise TemplateValidationError(
                f"edit_remarks(operation='add') received invalid remark fields: {detail}."
            ) from exc
        result = authoring.create(
            CreateRemarkRequest(
                remark=remark,
                index=arguments.get("new_index"),
            )
        )
    elif operation == "update":
        result = authoring.update(
            UpdateRemarkRequest(
                remark_id=str(_required(arguments, "remark_id")),
                patch=RemarkPatch.model_validate(arguments.get("patch", {})),
            )
        )
    elif operation == "remove":
        result = authoring.remove(
            RemoveRequest(
                target=AuthoringTarget(
                    object_kind="remark", object_id=str(_required(arguments, "remark_id"))
                )
            )
        )
    elif operation == "move":
        result = authoring.move(
            MoveRequest(
                object_kind="remark",
                object_id=str(_required(arguments, "remark_id")),
                new_index=int(_required(arguments, "new_index")),
            )
        )
    else:
        raise TemplateValidationError(f"Unsupported remarks operation {operation!r}.")
    _persist_authoring(path, authoring, root)
    return result


def dispatch_stable_tool(
    name: str,
    arguments: Mapping[str, object],
    *,
    root: str | Path,
    image_factory: ImageFactory | None = None,
) -> object:
    """Dispatch one stable model-facing responsibility to deterministic service code."""
    args = dict(arguments)
    operation = str(args.get("operation", ""))
    raw_logfile_path = args.get("logfile_path")
    logfile_path = "" if raw_logfile_path is None else str(raw_logfile_path)

    if name == "create_draft":
        output = _path(args)

        def create() -> object:
            if operation == "save":
                return service.save_logfile_text(
                    str(_required(args, "yaml_text")),
                    output,
                    overwrite=bool(args.get("overwrite", False)),
                    root=root,
                )
            if operation not in {"create", "clone"}:
                raise TemplateValidationError(f"Unsupported draft operation {operation!r}.")
            source = args.get("source_logfile_path")
            kind = args.get("kind")
            return service.create_logfile_draft(
                output,
                source_logfile_path=str(source) if source is not None else None,
                example_id=str(kind) if kind is not None else None,
                overwrite=bool(args.get("overwrite", False)),
                root=root,
            )

        before_text = _draft_text(output, root)
        create()
        after_text = _draft_text(output, root)
        summary = service.inspect_logfile(output, root=root)
        starter = args.get("kind") or args.get("source_logfile_path") or "yaml_text"
        return {
            "ok": True,
            "changed": before_text != after_text,
            "logfile_path": output,
            "starter": str(starter),
            "section_ids": summary.section_ids,
            "section_count": len(summary.section_ids),
            "warnings": [],
            "next_steps": [],
        }

    if name == "inspect_authoring":
        result = service.inspect_authoring_objects(
            logfile_path,
            object_kind=str(_required(args, "object_kind")),
            section_id=args.get("section_id"),
            track_id=args.get("track_id"),
            root=root,
        )
        detail = str(args.get("detail", "summary")).strip().lower()
        if detail not in {"summary", "full"}:
            raise TemplateValidationError("inspect_authoring detail must be 'summary' or 'full'.")
        items = (
            result.objects
            if detail == "full"
            else [
                _authoring_object_summary(item)
                for item in result.objects
                if isinstance(item, Mapping)
            ]
        )
        return {
            "ok": True,
            "items": items,
            "warnings": [],
            "next_steps": [],
        }

    if name == "inspect_source":
        items: list[object] = []
        source_path = args.get("source_path")
        source_summary: Mapping[str, object] | None = None
        if source_path is not None:
            source_summary_value = _source_inspection_summary(
                asdict(
                    service.inspect_data_source(
                        str(source_path),
                        source_format=str(args.get("source_format", "auto")),
                        root=root,
                    )
                ),
                include_metadata=bool(args.get("include_metadata", False)),
            )
            source_summary = source_summary_value
            items.append(source_summary_value)
        elif logfile_path:
            items.append(
                _logfile_source_summary(asdict(service.inspect_logfile(logfile_path, root=root)))
            )
        else:
            raise TemplateValidationError("inspect_source requires logfile_path or source_path.")
        channels = args.get("channels")
        if isinstance(channels, list) and channels:
            items.append(
                _channel_availability_summary(
                    asdict(
                        service.check_channel_availability(
                            [str(channel) for channel in channels],
                            source_path=str(source_path) if source_path is not None else None,
                            logfile_path=(logfile_path or None) if source_path is None else None,
                            section_id=args.get("section_id"),
                            root=root,
                        )
                    )
                )
            )
        response: dict[str, object] = {
            "ok": True,
            "items": items,
            "warnings": [],
            "next_steps": [],
            "source_path": None,
            "source_format_detected": None,
            "channel_count": None,
            "available_channels": [],
        }
        if source_summary is not None:
            channels = source_summary.get("channels", [])
            response["source_path"] = source_summary.get("source_path")
            response["source_format_detected"] = source_summary.get("source_format_detected")
            response["channel_count"] = source_summary.get("channel_count")
            response["available_channels"] = (
                [
                    channel.get("mnemonic")
                    for channel in channels
                    if isinstance(channel, Mapping) and channel.get("mnemonic")
                ]
                if isinstance(channels, list)
                else []
            )
        return response

    if name == "inspect_vocab":
        result = service.inspect_authoring_vocab(root=root)
        return {
            "ok": True,
            "items": [
                _vocabulary_inspection(
                    result,
                    family=args.get("family"),
                    detail=args.get("detail", "summary"),
                )
            ],
            "warnings": [],
            "next_steps": [],
        }

    if name == "validate_logfile":
        result = service.validate_logfile(
            logfile_path,
            level=args.get("level") or "render",
            root=root,
        )
        return {
            "ok": result.valid,
            "valid": result.valid,
            "errors": [] if result.valid else [result.message],
            "validation_level": result.validation_level,
            "warnings": [],
            "next_steps": [],
        }

    if name == "preview_logfile":
        if image_factory is None:
            raise RuntimeError("Preview image support is unavailable.")
        page = args.get("page")
        page_index = 0 if page is None else int(page)
        section_id = args.get("section_id")
        track_id = args.get("track_id")
        focus = str(args.get("focus") or "").strip().lower()
        if track_id is not None:
            image = service.preview_track_png(
                logfile_path,
                section_id=str(_required(args, "section_id")),
                track_ids=[str(track_id)],
                page_index=page_index,
                root=root,
            )
        elif section_id is not None and focus not in {"report", "document"}:
            image = service.preview_section_png(
                logfile_path,
                section_id=str(section_id),
                page_index=page_index,
                root=root,
            )
        else:
            image = service.preview_logfile_png(
                logfile_path,
                page_index=page_index,
                root=root,
            )
        return image_factory(image)

    if name == "render_logfile":
        output_path = args.get("output_path")
        if output_path is None:
            output_path = service.inspect_logfile(logfile_path, root=root).configured_output_path
        result = service.render_logfile_to_file(
            logfile_path,
            str(output_path),
            overwrite=bool(args.get("overwrite", False)),
            root=root,
        )
        return {
            "ok": True,
            "artifact": result.output_path,
            "output_path": result.output_path,
            "backend": result.backend,
            "page_count": result.page_count,
            "warnings": [],
            "next_steps": [],
        }

    if not logfile_path:
        raise TemplateValidationError(f"{name} requires logfile_path.")

    if name == "edit_header":
        if operation == "apply_values":
            target = _target("header", "header", args)
            before = _snapshot(logfile_path, target, root)
            applied = service.apply_header_values(
                logfile_path,
                values=dict(_required(args, "values")),
                overwrite_policy=str(args.get("overwrite_policy", "fill_empty")),
                root=root,
            )
            after = _snapshot(logfile_path, target, root)
            changed, changed_fields, before_change, after_change = _mutation_evidence(
                before,
                after,
            )
            return {
                "ok": True,
                "changed": changed,
                "target": target,
                "changed_fields": changed_fields,
                "before": before_change,
                "after": after_change,
                "logfile_path": applied.logfile_path,
                "overwrite_policy": applied.overwrite_policy,
                "applied_assignments": applied.applied_assignments,
                "skipped_assignments": applied.skipped_assignments,
                "heading_summary": applied.heading_summary,
                "warnings": applied.warnings,
                "next_steps": [],
            }
        if operation == "apply_archetype":
            target = _target("header", "header", args)
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.apply_header_archetype(
                    logfile_path,
                    archetype_id=str(_required(args, "archetype_id")),
                    preserve_existing_values=bool(args.get("preserve_existing_values", True)),
                    root=root,
                ),
            )
        if operation == "set_service_title":
            slot_id = str(_required(args, "service_title"))
            target = _target("service_title", slot_id, args)
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.update_service_title(
                    logfile_path,
                    slot_id=slot_id,
                    patch=_flat_patch(
                        args,
                        {
                            "value",
                            "source_key",
                            "unit",
                            "provenance",
                            "availability",
                            "font_size",
                            "auto_adjust",
                            "bold",
                            "italic",
                            "alignment",
                        },
                    ),
                    root=root,
                ),
            )
        slot_id = str(_required(args, "slot_id"))
        target = _target("header_slot", slot_id, args)
        patch = _flat_patch(
            args,
            {"value", "source_key", "unit", "provenance", "availability"},
        )
        if operation == "clear_slot":
            patch["value"] = None
        return _mutation(
            logfile_path,
            target,
            root,
            lambda: service.update_header_slot(
                logfile_path,
                slot_id=slot_id,
                patch=patch,
                root=root,
            ),
        )

    if name == "edit_report_settings":
        if operation == "set_matplotlib_style":
            style_patch = _required(args, "style_patch")
            if not isinstance(style_patch, Mapping):
                raise TemplateValidationError("style_patch must be an object.")
            return _matplotlib_style_mutation(
                logfile_path,
                style_patch=style_patch,
                root=root,
            )
        if operation == "set_section_view":
            section_id = str(_required(args, "section_id"))
            depth_range = args.get("depth_range")
            normalized_range: tuple[float, float] | None = None
            depth_range_unit: str | None = None
            if depth_range is not None:
                normalized_range, depth_range_unit = _depth_range_input(
                    depth_range,
                    tool_name="edit_report_settings",
                )
            return _mutation(
                logfile_path,
                _target("section", section_id, args),
                root,
                lambda: service.set_section_view(
                    logfile_path,
                    section_id=section_id,
                    title=args.get("title"),
                    subtitle=args.get("subtitle"),
                    depth_range=normalized_range,
                    depth_range_unit=depth_range_unit,
                    page_patch=args.get("page"),
                    render_patch=args.get("output"),
                    root=root,
                ),
            )
        kind = {
            "set_report": "report",
            "set_page": "page",
            "set_output": "output",
            "set_depth": "depth",
        }.get(operation)
        if kind is None:
            raise TemplateValidationError(f"Unsupported report-settings operation {operation!r}.")
        if kind == "report":
            payload = _flat_patch(args, {"title", "subtitle"})
        else:
            payload = args.get({"page": "page", "output": "output", "depth": "depth"}[kind], {})

        def apply_settings() -> object:
            path, authoring = _rooted_authoring(logfile_path, root)
            if kind == "report":
                result = authoring.update(
                    UpdateReportRequest(patch=ReportPatch.model_validate(payload))
                )
            elif kind == "page":
                result = authoring.update(
                    UpdatePageRequest(patch=service.PagePatch.model_validate(payload))
                )
            elif kind == "output":
                result = authoring.update(
                    UpdateOutputRequest(output=AuthoringOutputSpec.model_validate(payload))
                )
            else:
                result = authoring.update(
                    UpdateDepthRequest(patch=service.DepthPatch.model_validate(payload))
                )
            _persist_authoring(path, authoring, root)
            return result

        return _mutation(logfile_path, _target(kind, kind, args), root, apply_settings)

    if name == "edit_remarks":
        if operation == "update":
            args["patch"] = _flat_patch(
                args,
                {"title", "text", "lines", "alignment", "font_size", "title_font_size", "border"},
            )
        return _mutation(
            logfile_path,
            _target("report", "report", args),
            root,
            lambda: _remarks_mutation(args, root),
        )

    if name == "edit_section":
        section_id = str(args.get("section_id", ""))
        target = _target("section", section_id, args)
        if operation == "add":
            return _mutation(logfile_path, target, root, lambda: _direct_section_add(args, root))
        if operation == "remove":
            return _mutation(logfile_path, target, root, lambda: _direct_section_remove(args, root))
        if operation == "move":
            return _mutation(logfile_path, target, root, lambda: _direct_section_move(args, root))
        return _mutation(
            logfile_path,
            target,
            root,
            lambda: _direct_section_update(args, root),
        )

    if name == "replicate_section_structure":
        source_section_id = str(_required(args, "source_section_id"))
        target_section_id = str(_required(args, "target_section_id"))
        target = {"object_kind": "section", "object_id": target_section_id}
        return _mutation(
            logfile_path,
            target,
            root,
            lambda: service.replicate_section_structure(
                logfile_path,
                source_section_id=source_section_id,
                target_section_id=target_section_id,
                source_path=args.get("source_path"),
                source_format=str(args.get("source_format", "auto")),
                title=args.get("title"),
                subtitle=args.get("subtitle"),
                include_bindings=bool(args.get("include_bindings", True)),
                overwrite=bool(args.get("overwrite", False)),
                root=root,
            ),
        )

    if name == "edit_track":
        if operation == "add":
            required_fields = ("section_id", "track_id", "title", "kind", "width_mm")
            missing = [field for field in required_fields if args.get(field) is None]
            if missing:
                raise TemplateValidationError(
                    "edit_track(operation='add') requires section_id, track_id, title, "
                    "kind, and width_mm in the same call. "
                    f"Missing: {', '.join(missing)}."
                )
        section_id = str(_required(args, "section_id"))
        track_id = str(_required(args, "track_id"))
        target = _target("track", track_id, args)
        if operation == "add":
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.add_track(
                    logfile_path,
                    section_id=section_id,
                    id=track_id,
                    title=str(_required(args, "title")),
                    kind=str(_required(args, "kind")),
                    width_mm=float(_required(args, "width_mm")),
                    x_scale=args.get("x_scale"),
                    grid=args.get("grid"),
                    track_header=args.get("track_header"),
                    reference=args.get("reference"),
                    annotations=args.get("annotations"),
                    root=root,
                ),
            )
        if operation == "set_scales":
            return _scale_mutation(
                logfile_path,
                section_id=section_id,
                track_id=track_id,
                root=root,
                mutate=lambda: service.set_track_scales(
                    logfile_path,
                    section_id=section_id,
                    track_id=track_id,
                    x_scale=args.get("x_scale"),
                    curve_scale=args.get("curve_scale"),
                    channel_scales=args.get("channel_scales"),
                    sync_grid_to_scale=bool(args.get("sync_grid_to_scale", True)),
                    root=root,
                ),
            )
        if operation == "remove":
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.remove_track(
                    logfile_path, section_id=section_id, track_id=track_id, root=root
                ),
            )
        if operation == "move":
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.move_track(
                    logfile_path,
                    section_id=section_id,
                    track_id=track_id,
                    position=args.get("new_index"),
                    root=root,
                ),
            )
        if operation == "clear_bindings":
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.clear_track_bindings(
                    logfile_path, section_id=section_id, track_id=track_id, root=root
                ),
            )
        return _mutation(
            logfile_path,
            target,
            root,
            lambda: service.update_track(
                logfile_path,
                section_id=section_id,
                track_id=track_id,
                patch=_flat_patch(
                    args, {"title", "width_mm", "x_scale", "grid", "track_header", "reference"}
                ),
                root=root,
            ),
        )

    if name in {"edit_curve_binding", "edit_raster_binding"}:
        section_id = str(_required(args, "section_id"))
        track_id = str(_required(args, "track_id"))
        binding_id = args.get("binding_id")
        if args.get("channel") is None:
            inferred_channel = _binding_channel_from_id(
                args,
                object_kind="curve_binding" if name == "edit_curve_binding" else "raster_binding",
                root=root,
            )
            if inferred_channel is not None:
                args["channel"] = inferred_channel
        target = _target("track", track_id, args)
        is_curve = name == "edit_curve_binding"
        if operation == "add":
            if is_curve:
                return _mutation(
                    logfile_path,
                    target,
                    root,
                    lambda: service.bind_curve(
                        logfile_path,
                        section_id=section_id,
                        track_id=track_id,
                        channel=str(_required(args, "channel")),
                        binding_id=binding_id,
                        label=args.get("label"),
                        style=args.get("style"),
                        scale=args.get("scale"),
                        header_display=args.get("header_display"),
                        root=root,
                    ),
                )
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.bind_raster(
                    logfile_path,
                    section_id=section_id,
                    track_id=track_id,
                    channel=str(_required(args, "channel")),
                    label=args.get("label"),
                    style=args.get("style"),
                    profile=args.get("profile"),
                    normalization=args.get("normalization"),
                    show_raster=args.get("show_raster"),
                    raster_alpha=args.get("alpha"),
                    color_limits=args.get("color_limits"),
                    root=root,
                ),
            )
        if operation == "remove":
            if is_curve:
                return _mutation(
                    logfile_path,
                    target,
                    root,
                    lambda: service.remove_curve_binding(
                        logfile_path,
                        section_id=section_id,
                        track_id=track_id,
                        channel=str(_required(args, "channel")),
                        binding_id=binding_id,
                        root=root,
                    ),
                )
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.remove_raster_binding(
                    logfile_path,
                    section_id=section_id,
                    track_id=track_id,
                    channel=str(_required(args, "channel")),
                    root=root,
                ),
            )
        if operation == "clear":
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: _clear_binding_family(
                    logfile_path,
                    section_id=section_id,
                    track_id=track_id,
                    object_kind="curve_binding" if is_curve else "raster_binding",
                    root=root,
                ),
            )
        if is_curve:
            patch = _flat_patch(
                args,
                {
                    "label",
                    "style",
                    "scale",
                    "header_display",
                    "wrap",
                    "render_mode",
                    "callouts",
                    "fill",
                },
            )
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.update_curve_binding(
                    logfile_path,
                    section_id=section_id,
                    track_id=track_id,
                    channel=str(_required(args, "channel")),
                    binding_id=binding_id,
                    patch=patch,
                    root=root,
                ),
            )
        patch = _flat_patch(
            args,
            {
                "label",
                "style",
                "profile",
                "normalization",
                "waveform_normalization",
                "interpolation",
                "show_raster",
                "alpha",
                "color_limits",
                "colorbar",
                "sample_axis",
                "waveform",
            },
        )
        return _mutation(
            logfile_path,
            target,
            root,
            lambda: service.update_raster_binding(
                logfile_path,
                section_id=section_id,
                track_id=track_id,
                channel=str(_required(args, "channel")),
                patch=patch,
                root=root,
            ),
        )

    if name == "edit_fill":
        section_id = str(_required(args, "section_id"))
        track_id = str(_required(args, "track_id"))
        target = _target("track", track_id, args)
        if operation == "remove":
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.remove_curve_fill(
                    logfile_path,
                    section_id=section_id,
                    track_id=track_id,
                    channel=str(_required(args, "channel")),
                    binding_id=args.get("binding_id"),
                    root=root,
                ),
            )
        if operation == "add" or operation == "update":
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.add_curve_fill(
                    logfile_path,
                    section_id=section_id,
                    track_id=track_id,
                    channel=str(_required(args, "channel")),
                    kind=str(_required(args, "kind")),
                    binding_id=args.get("binding_id"),
                    other_element_id=args.get("other_binding_id"),
                    label=args.get("label"),
                    color=args.get("color"),
                    alpha=args.get("alpha"),
                    crossover=args.get("crossover"),
                    root=root,
                ),
            )
        if operation == "clear":
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.remove_curve_fill(
                    logfile_path,
                    section_id=section_id,
                    track_id=track_id,
                    channel=str(_required(args, "channel")),
                    binding_id=args.get("binding_id"),
                    root=root,
                ),
            )

    if name == "edit_annotation":
        section_id = str(_required(args, "section_id"))
        track_id = str(_required(args, "track_id"))
        target = _target("track", track_id, args)
        if operation == "add":
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.add_annotation_object(
                    logfile_path,
                    section_id=section_id,
                    track_id=track_id,
                    annotation=dict(_required(args, "annotation")),
                    root=root,
                ),
            )
        if operation == "update":
            annotation_index = _annotation_index(
                logfile_path,
                section_id=section_id,
                track_id=track_id,
                value=_required(args, "annotation_id"),
                root=root,
            )
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.update_annotation_object(
                    logfile_path,
                    section_id=section_id,
                    track_id=track_id,
                    annotation_index=annotation_index,
                    patch=dict(args.get("patch", {})),
                    root=root,
                ),
            )
        if operation in {"remove", "clear"}:
            annotation_index = _annotation_index(
                logfile_path,
                section_id=section_id,
                track_id=track_id,
                value=_required(args, "annotation_id"),
                root=root,
            )
            return _mutation(
                logfile_path,
                target,
                root,
                lambda: service.remove_annotation_object(
                    logfile_path,
                    section_id=section_id,
                    track_id=track_id,
                    annotation_index=annotation_index,
                    root=root,
                ),
            )

    raise TemplateValidationError(f"Unsupported stable MCP tool or operation: {name}/{operation}.")


def _tool_function(
    profile: StableToolProfile,
    callback: Callable[[Mapping[str, object]], object],
) -> Callable[..., object]:
    parameters: list[inspect.Parameter] = []
    for name, field in profile.input_model.model_fields.items():
        default = inspect.Parameter.empty if field.is_required() else field.default
        parameters.append(
            inspect.Parameter(
                name,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=field.rebuild_annotation(),
                default=default,
            )
        )

    def invoke(**kwargs: object) -> object:
        try:
            validated = profile.input_model.model_validate(kwargs)
        except ValidationError as exc:
            depth_range_error = any(
                error.get("loc", ())
                and error["loc"][0] == "depth_range"
                for error in exc.errors()
            )
            if profile.name in {"edit_section", "edit_report_settings"} and depth_range_error:
                raise TemplateValidationError(
                    f"{profile.name} {_DEPTH_RANGE_ERROR}"
                ) from exc
            if profile.name == "edit_remarks" and kwargs.get("operation") == "add":
                payload = kwargs.get("remark")
                text = payload.get("text") if isinstance(payload, Mapping) else None
                lines = payload.get("lines") if isinstance(payload, Mapping) else None
                if not (isinstance(text, str) and text) and not (
                    isinstance(lines, list) and lines
                ):
                    raise TemplateValidationError(_REMARK_CONTENT_ERROR) from exc
                detail = exc.errors()[0].get("msg", "invalid remark fields")
                raise TemplateValidationError(
                    "edit_remarks(operation='add') received invalid remark fields: "
                    f"{detail}."
                ) from exc
            raise
        arguments = validated.model_dump(mode="python", exclude_none=True)
        return callback(arguments)

    invoke.__name__ = profile.name
    invoke.__doc__ = profile.description
    invoke.__signature__ = inspect.Signature(
        parameters,
        return_annotation=profile.output_model or object,
    )
    return invoke


def register_stable_tools(
    mcp: object,
    *,
    root: str | Path,
    image_factory: ImageFactory,
    annotation_factory: Callable[[Mapping[str, bool]], object],
) -> tuple[str, ...]:
    """Register exactly the approved stable model-facing MCP responsibilities."""
    names: list[str] = []
    for profile in stable_tool_profile():

        def callback(
            arguments: Mapping[str, object],
            name: str = profile.name,
        ) -> object:
            request_id = new_request_id()
            started_at = dispatch_started()
            try:
                result = dispatch_stable_tool(
                    name, arguments, root=root, image_factory=image_factory
                )
            except Exception as exc:
                emit_dispatch_event(
                    root=root,
                    request_id=request_id,
                    tool_name=name,
                    arguments=arguments,
                    started_at=started_at,
                    error=exc,
                )
                raise
            emit_dispatch_event(
                root=root,
                request_id=request_id,
                tool_name=name,
                arguments=arguments,
                started_at=started_at,
                result=result,
            )
            return result

        tool = _tool_function(profile, callback)
        mcp.add_tool(
            tool,
            name=profile.name,
            description=profile.description,
            annotations=annotation_factory(profile.annotations),
            structured_output=profile.name not in {"preview_logfile"},
        )
        names.append(profile.name)
    return tuple(names)
