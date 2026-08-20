"""Stable, compact model-facing tool profile for agent authoring."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any

import yaml
from pydantic import BaseModel

from wellplot.authoring_service import (
    HeaderValuePatch,
    UpdateCurveBindingRequest,
    UpdateRasterBindingRequest,
    UpdateRemarkRequest,
    UpdateSectionRequest,
    UpdateTrackRequest,
)
from wellplot.model.authoring import AuthoringRemarkSpec

ASSET_PACKAGE = "wellplot.mcp.assets"
CONTRACT_ASSET = "defaults/stable_tool_contract.yaml"
Schema = dict[str, Any]
_STRING: Schema = {"type": "string", "minLength": 1}


@dataclass(frozen=True)
class StableToolProfile:
    """One bounded model-facing responsibility."""

    name: str
    description: str
    input_schema: Schema
    output_schema: Schema
    annotations: dict[str, bool]


def _resolve(value: object, root: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    reference = value.get("$ref")
    definitions = root.get("$defs")
    if isinstance(reference, str) and isinstance(definitions, Mapping):
        resolved = definitions.get(reference.rsplit("/", 1)[-1])
        if isinstance(resolved, Mapping):
            return resolved
    return value


def _compact(value: object, root: Mapping[str, object], depth: int = 0) -> Schema:
    """Keep validation constraints while dropping generated model metadata."""
    resolved = _resolve(value, root)
    if depth > 3:
        return {"type": "object"}
    result = {
        key: resolved[key]
        for key in (
            "type",
            "enum",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "minLength",
            "default",
        )
        if key in resolved
    }
    for key in ("anyOf", "oneOf"):
        variants = resolved.get(key)
        if isinstance(variants, list):
            result[key] = [_compact(item, root, depth + 1) for item in variants]
    properties = resolved.get("properties")
    if isinstance(properties, Mapping):
        result["type"] = "object"
        result["properties"] = {
            str(name): _compact(item, root, depth + 1) for name, item in properties.items()
        }
    required = resolved.get("required")
    if isinstance(required, list):
        result["required"] = [str(item) for item in required]
    if resolved.get("additionalProperties") is False:
        result["additionalProperties"] = False
    return result or {"type": "object"}


def _fields(model: type[BaseModel], field_name: str, names: tuple[str, ...]) -> dict[str, Schema]:
    root = model.model_json_schema()
    if field_name:
        field = root.get("properties", {}).get(field_name)
        properties = _resolve(_resolve(field, root), root).get("properties", {})
    else:
        properties = root.get("properties", {})
    if not isinstance(properties, Mapping):
        return {}
    return {name: _compact(properties[name], root) for name in names if name in properties}


def _field_schema(value: object) -> Schema:
    if value == "string":
        return dict(_STRING)
    if value == "string_list":
        return {"type": "array", "items": dict(_STRING)}
    if value == "boolean":
        return {"type": "boolean"}
    if value == "number":
        return {"type": "number"}
    if value == "index":
        return {"type": "integer", "minimum": 0}
    if value == "object":
        return {"type": "object"}
    if value == "object_list":
        return {"type": "array", "items": {"type": "object"}}
    if isinstance(value, list):
        return {"type": "string", "enum": list(value)}
    return {"type": "object"}


def _object(properties: Mapping[str, object], required: list[str] | None = None) -> Schema:
    result: Schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": dict(properties),
    }
    if required:
        result["required"] = required
    return result


def _output(mode: str) -> Schema:
    if mode == "inspection":
        properties = {"ok": {"type": "boolean"}, "items": "object_list"}
        required = ["ok", "warnings", "next_steps"]
    elif mode == "validation":
        properties = {
            "ok": {"type": "boolean"},
            "valid": {"type": "boolean"},
            "errors": "string_list",
        }
        required = ["ok", "valid", "errors", "warnings", "next_steps"]
    elif mode == "artifact":
        properties = {"ok": {"type": "boolean"}, "artifact": "string"}
        required = ["ok", "artifact", "warnings", "next_steps"]
    else:
        properties = {
            "ok": {"type": "boolean"},
            "changed": {"type": "boolean"},
            "target": {"type": "object"},
            "before": {"type": "object"},
            "after": {"type": "object"},
        }
        required = ["ok", "changed", "target", "before", "after", "warnings", "next_steps"]
    properties.update({"warnings": "string_list", "next_steps": "string_list"})
    return _object({key: _field_schema(value) for key, value in properties.items()}, required)


@lru_cache(maxsize=1)
def _canonical_fields() -> dict[str, dict[str, Schema]]:
    return {
        "header": _fields(
            HeaderValuePatch, "", ("value", "source_key", "unit", "provenance", "availability")
        ),
        "section": _fields(UpdateSectionRequest, "patch", ("title", "subtitle", "depth_range")),
        "track": _fields(UpdateTrackRequest, "patch", ("title", "width_mm", "x_scale")),
        "curve": _fields(
            UpdateCurveBindingRequest, "patch", ("label", "scale", "style", "render_mode", "wrap")
        ),
        "raster": _fields(
            UpdateRasterBindingRequest,
            "patch",
            ("label", "style", "profile", "normalization", "show_raster", "alpha", "color_limits"),
        ),
        "remark": _fields(
            UpdateRemarkRequest,
            "patch",
            ("title", "text", "lines", "alignment", "font_size", "border"),
        ),
    }


@lru_cache(maxsize=1)
def _contract_data() -> tuple[dict[str, object], ...]:
    payload = yaml.safe_load(files(ASSET_PACKAGE).joinpath(CONTRACT_ASSET).read_text())
    if not isinstance(payload, Mapping) or payload.get("version") != 1:
        raise ValueError(f"{CONTRACT_ASSET} must declare version 1.")
    tools = payload.get("tools")
    if not isinstance(tools, list) or len(tools) != 17:
        raise ValueError(f"{CONTRACT_ASSET} must define exactly 17 tools.")
    if not all(isinstance(item, Mapping) for item in tools):
        raise ValueError(f"{CONTRACT_ASSET} tools must be mappings.")
    return tuple(dict(item) for item in tools)


def stable_tool_profile() -> tuple[StableToolProfile, ...]:
    """Return the bounded model-facing profile without registering MCP tools."""
    canonical = _canonical_fields()
    profile: list[StableToolProfile] = []
    for entry in _contract_data():
        fields = {
            str(name): _field_schema(value) for name, value in dict(entry.get("fields", {})).items()
        }
        canonical_name = entry.get("canonical_fields")
        if isinstance(canonical_name, str):
            fields = {**canonical.get(canonical_name, {}), **fields}
        if entry.get("id") == "edit_remarks":
            fields["remark"] = _object(
                _fields(
                    AuthoringRemarkSpec,
                    "",
                    (
                        "remark_id",
                        "title",
                        "text",
                        "lines",
                        "alignment",
                        "font_size",
                        "title_font_size",
                        "border",
                    ),
                )
            )
        mode = str(entry.get("mode", "mutation"))
        operations = entry.get("operations")
        if isinstance(operations, list):
            fields = {"operation": {"type": "string", "enum": operations}, **fields}
            fields["logfile_path"] = _STRING
            required = ["logfile_path", "operation"]
        else:
            required = [str(item) for item in entry.get("required", [])]
        annotations = {
            "readOnlyHint": bool(entry.get("read_only", False)),
            "idempotentHint": bool(entry.get("idempotent", False)),
            "destructiveHint": bool(entry.get("destructive", False)),
            "openWorldHint": bool(entry.get("open_world", False)),
        }
        profile.append(
            StableToolProfile(
                name=str(entry["id"]),
                description=str(entry["description"]),
                input_schema=_object(fields, required or None),
                output_schema=_output(mode),
                annotations=annotations,
            )
        )
    return tuple(profile)


def stable_tool_budget() -> dict[str, int]:
    """Return machine-checkable profile counts and serialized schema sizes."""
    profile = stable_tool_profile()
    return {
        "tool_count": len(profile),
        "input_schema_chars": sum(
            len(json.dumps(item.input_schema, sort_keys=True)) for item in profile
        ),
        "output_schema_chars": sum(
            len(json.dumps(item.output_schema, sort_keys=True)) for item in profile
        ),
        "description_chars": sum(len(item.description) for item in profile),
        "combined_schema_chars": sum(
            len(json.dumps({"input": item.input_schema, "output": item.output_schema}))
            for item in profile
        ),
    }
