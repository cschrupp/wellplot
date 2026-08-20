"""Thin model-facing MCP projection over the deterministic authoring service."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

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
    SectionPatch,
    UpdateDepthRequest,
    UpdateOutputRequest,
    UpdatePageRequest,
    UpdateRemarkRequest,
    UpdateReportRequest,
    UpdateSectionRequest,
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
        return value.model_dump(mode="json", exclude_none=True)
    return None


def _mutation(
    logfile_path: str,
    target: Mapping[str, object],
    root: str | Path,
    mutate: Callable[[], object],
) -> dict[str, object]:
    before = _snapshot(logfile_path, target, root)
    mutate()
    after = _snapshot(logfile_path, target, root)
    return {
        "ok": True,
        "changed": before != after,
        "target": dict(target),
        "before": before or {},
        "after": after or {},
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
        "track": track.model_dump(mode="json", exclude_none=True),
        "bindings": [item.model_dump(mode="json", exclude_none=True) for item in bindings],
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
    return {
        "ok": True,
        "changed": before != after,
        "target": _target("track", track_id, {"section_id": section_id}),
        "before": before,
        "after": after,
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
    return {
        "ok": True,
        "changed": before != after,
        "target": {"object_kind": "document", "object_id": "document"},
        "before": {"style": before},
        "after": {"style": after},
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
    path, authoring = _rooted_authoring(_path(arguments), root)
    section_id = str(_required(arguments, "section_id"))
    patch = _flat_patch(arguments, {"title", "subtitle", "depth_range"})
    result = authoring.update(
        UpdateSectionRequest(
            section_id=section_id,
            patch=SectionPatch.model_validate(patch),
        )
    )
    _persist_authoring(path, authoring, root)
    return result


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
            raise TemplateValidationError("remark is required for adding a remark.")
        result = authoring.create(
            CreateRemarkRequest(
                remark=AuthoringRemarkSpec.model_validate(dict(payload)),
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
            if args.get("source_data_file") is not None:
                raise TemplateValidationError("source_data_file requires a logfile template.")
            return service.create_logfile_draft(
                output,
                source_logfile_path=str(source) if source is not None else None,
                example_id=str(kind) if kind is not None else None,
                overwrite=bool(args.get("overwrite", False)),
                root=root,
            )

        return _mutation(output, _target("document", "document", {}), root, create)

    if name == "inspect_authoring":
        result = service.inspect_authoring_objects(
            logfile_path,
            object_kind=str(_required(args, "object_kind")),
            section_id=args.get("section_id"),
            track_id=args.get("track_id"),
            root=root,
        )
        return {"ok": True, "items": result.objects, "warnings": [], "next_steps": []}

    if name == "inspect_source":
        items: list[object] = []
        source_path = args.get("source_path")
        source_summary: Mapping[str, object] | None = None
        if source_path is not None:
            source_summary_value = _json_safe(
                asdict(
                    service.inspect_data_source(
                        str(source_path),
                        source_format=str(args.get("source_format", "auto")),
                        root=root,
                    )
                )
            )
            source_summary = (
                source_summary_value if isinstance(source_summary_value, Mapping) else None
            )
            items.append(source_summary_value)
        elif logfile_path:
            items.append(_json_safe(asdict(service.inspect_logfile(logfile_path, root=root))))
        else:
            raise TemplateValidationError("inspect_source requires logfile_path or source_path.")
        channels = args.get("channels")
        if isinstance(channels, list) and channels:
            items.append(
                _json_safe(
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
        return {"ok": True, "items": [asdict(result)], "warnings": [], "next_steps": []}

    if name == "validate_logfile":
        result = service.validate_logfile(logfile_path, root=root)
        return {
            "ok": result.valid,
            "valid": result.valid,
            "errors": [] if result.valid else [result.message],
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
            return {
                "ok": True,
                "changed": before != after,
                "target": target,
                "before": before or {},
                "after": after or {},
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
            return _mutation(
                logfile_path,
                _target("section", section_id, args),
                root,
                lambda: service.set_section_view(
                    logfile_path,
                    section_id=section_id,
                    title=args.get("title"),
                    subtitle=args.get("subtitle"),
                    depth_range=args.get("depth_range"),
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
        payload = args.get(
            {"report": "patch", "page": "page", "output": "output", "depth": "depth"}[kind], {}
        )

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
        arguments = profile.input_model.model_validate(kwargs).model_dump(
            mode="python",
            exclude_none=True,
        )
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
