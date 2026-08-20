"""Stable, compact model-facing tool profile for agent authoring."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache, reduce
from importlib.resources import files
from operator import or_
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, create_model

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
    input_model: type[BaseModel]
    input_schema: Schema
    output_model: type[BaseModel] | None
    output_schema: Schema | None
    annotations: dict[str, bool]


class _StableResult(BaseModel):
    """Common schema for compact structured stable-tool responses."""

    model_config = ConfigDict(extra="forbid")

    warnings: list[str]
    next_steps: list[str]


class StableInspectionResult(_StableResult):
    """Structured result for scoped deterministic inspection tools."""

    ok: bool
    items: list[dict[str, Any]]


class StableValidationResult(_StableResult):
    """Structured result for deterministic validation tools."""

    ok: bool
    valid: bool
    errors: list[str]


class StableArtifactResult(_StableResult):
    """Structured result for persisted artifact tools."""

    ok: bool
    artifact: str


class StableRenderArtifactResult(StableArtifactResult):
    """Structured result for persisted renders with renderer metadata."""

    output_path: str
    backend: str
    page_count: int


class StableMutationResult(_StableResult):
    """Structured result for one persisted authoring mutation."""

    ok: bool
    changed: bool
    target: dict[str, Any]
    before: dict[str, Any]
    after: dict[str, Any]


class StableHeaderMutationResult(StableMutationResult):
    """Structured result for header fills with assignment evidence."""

    logfile_path: str | None = None
    overwrite_policy: str | None = None
    applied_assignments: list[dict[str, Any]] = Field(default_factory=list)
    skipped_assignments: list[dict[str, Any]] = Field(default_factory=list)
    heading_summary: dict[str, Any] = Field(default_factory=dict)


class StableSourceInspectionResult(StableInspectionResult):
    """Structured result for source inspection and channel discovery."""

    source_path: str | None = None
    source_format_detected: str | None = None
    channel_count: int | None = None
    available_channels: list[str] = Field(default_factory=list)


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


def _union(variants: list[object]) -> object:
    """Build one runtime union annotation from JSON-schema variants."""
    if not variants:
        return Any
    if len(variants) == 1:
        return variants[0]
    return reduce(or_, variants)


def _schema_annotation(schema: Mapping[str, object], model_name: str) -> object:
    """Translate the compact contract schema into one Pydantic field annotation."""
    variants = schema.get("anyOf") or schema.get("oneOf")
    if isinstance(variants, list):
        return _union(
            [
                _schema_annotation(item, f"{model_name}Variant{index}")
                for index, item in enumerate(variants)
                if isinstance(item, Mapping)
            ]
        )

    schema_type = schema.get("type")
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        annotation: object = Literal[tuple(enum)]
    elif schema_type == "string":
        annotation = str
    elif schema_type == "boolean":
        annotation = bool
    elif schema_type == "integer":
        annotation = int
    elif schema_type == "number":
        annotation = float
    elif schema_type == "null":
        annotation = type(None)
    elif schema_type == "array":
        items = schema.get("items")
        item_annotation = (
            _schema_annotation(items, f"{model_name}Item") if isinstance(items, Mapping) else Any
        )
        annotation = list[item_annotation]
    elif schema_type == "object":
        properties = schema.get("properties")
        annotation = (
            _model_from_schema(model_name, schema, extra="forbid")
            if isinstance(properties, Mapping)
            else dict[str, Any]
        )
    else:
        annotation = Any

    constraints: dict[str, object] = {}
    if isinstance(schema.get("minLength"), int):
        constraints["min_length"] = schema["minLength"]
    if isinstance(schema.get("minimum"), (int, float)):
        constraints["ge"] = schema["minimum"]
    if isinstance(schema.get("maximum"), (int, float)):
        constraints["le"] = schema["maximum"]
    if isinstance(schema.get("exclusiveMinimum"), (int, float)):
        constraints["gt"] = schema["exclusiveMinimum"]
    return Annotated[annotation, Field(**constraints)] if constraints else annotation


def _model_from_schema(
    model_name: str,
    schema: Mapping[str, object],
    *,
    extra: str,
) -> type[BaseModel]:
    """Create one typed Pydantic model from the compact stable contract schema."""
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        raise ValueError(f"{model_name} requires an object schema with properties.")
    required = {str(item) for item in schema.get("required", []) if isinstance(item, str)}
    fields: dict[str, object] = {}
    for field_name, raw_schema in properties.items():
        if not isinstance(raw_schema, Mapping):
            continue
        name = str(field_name)
        annotation = _schema_annotation(raw_schema, f"{model_name}{name.title().replace('_', '')}")
        if name in required:
            fields[name] = (annotation, ...)
            continue
        fields[name] = (annotation | None, raw_schema.get("default"))
    return create_model(
        model_name,
        __config__=ConfigDict(extra=extra),
        **fields,
    )


def _output_model(name: str, mode: str) -> type[BaseModel] | None:
    """Return the single typed output envelope for one stable responsibility."""
    if name == "preview_logfile":
        return None
    if name == "inspect_source":
        return StableSourceInspectionResult
    if name == "edit_header":
        return StableHeaderMutationResult
    if name == "render_logfile":
        return StableRenderArtifactResult
    if mode == "inspection":
        return StableInspectionResult
    if mode == "validation":
        return StableValidationResult
    if mode == "artifact":
        return StableArtifactResult
    return StableMutationResult


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


@lru_cache(maxsize=1)
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
            fields["remark"] = {
                "type": "object",
                "additionalProperties": False,
                "properties": _fields(
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
                ),
            }
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
        input_model = _model_from_schema(
            f"{entry['id']}Arguments",
            {
                "type": "object",
                "properties": fields,
                "required": required,
            },
            # FastMCP builds the public top-level parameter model from a callable
            # signature with its default extra-value behavior. Keep this model in
            # lockstep so the profile matches the stdio schema byte-for-byte.
            extra="ignore",
        )
        output_model = _output_model(str(entry["id"]), mode)
        profile.append(
            StableToolProfile(
                name=str(entry["id"]),
                description=str(entry["description"]),
                input_model=input_model,
                input_schema=input_model.model_json_schema(by_alias=True),
                output_model=output_model,
                output_schema=(
                    output_model.model_json_schema(by_alias=True)
                    if output_model is not None
                    else None
                ),
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
            len(json.dumps(item.output_schema, sort_keys=True))
            for item in profile
            if item.output_schema is not None
        ),
        "description_chars": sum(len(item.description) for item in profile),
        "combined_schema_chars": sum(
            len(json.dumps({"input": item.input_schema, "output": item.output_schema}))
            for item in profile
        ),
    }
