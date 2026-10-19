"""Derive ClosedNormalizedProgram JSON Schema, XOR-patch ClosedSemanticQuery, canonicalize."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.nl_program_eval.closed_schema import ClosedNormalizedProgram

CONSTRAINT_ARTIFACT_NAME = "decomposer_pilot_preflight_01_constraint.schema.json"

CONSTRAINT_PATCH_VERSION = "decomposer_pilot_preflight_01.constraint_patch.v1"
CANONICAL_JSON_VERSION = "decomposer_pilot_preflight_01.canonical_json.v1"
CANONICAL_JSON_SPEC = {
    "sort_keys": True,
    "separators": [",", ":"],
    "ensure_ascii": False,
}

# Matches ClosedSemanticQuery._xor presence: str(value).strip() != ""
NON_WHITESPACE_STRING = {
    "type": "string",
    "pattern": ".*\\S.*",
}


def canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patcher_source_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def raw_pydantic_schema() -> dict[str, Any]:
    return ClosedNormalizedProgram.model_json_schema()


def _kind_enum_from_raw(raw_query: dict[str, Any]) -> list[str]:
    kind = raw_query["properties"]["kind"]
    return list(kind["enum"])


def build_xor_closed_semantic_query(raw_query: dict[str, Any]) -> dict[str, Any]:
    """Replace nullable text/local_ref with oneOf exclusive non-whitespace branches."""
    kind_enum = _kind_enum_from_raw(raw_query)
    kind_schema = {
        "enum": kind_enum,
        "title": raw_query["properties"]["kind"].get("title", "Kind"),
        "type": "string",
    }
    text_schema = {
        **NON_WHITESPACE_STRING,
        "title": raw_query["properties"]["text"].get("title", "Text"),
    }
    local_ref_schema = {
        **NON_WHITESPACE_STRING,
        "title": raw_query["properties"]["local_ref"].get("title", "Local Ref"),
    }
    return {
        "title": raw_query.get("title", "ClosedSemanticQuery"),
        "oneOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": copy.deepcopy(kind_schema),
                    "text": text_schema,
                },
                "required": ["kind", "text"],
            },
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": copy.deepcopy(kind_schema),
                    "local_ref": local_ref_schema,
                },
                "required": ["kind", "local_ref"],
            },
        ],
    }


def assert_patched_subseteq_raw(raw: dict[str, Any], patched: dict[str, Any]) -> None:
    """Patched must not widen properties/enums vs raw ClosedSemanticQuery."""
    raw_q = raw["$defs"]["ClosedSemanticQuery"]
    patched_q = patched["$defs"]["ClosedSemanticQuery"]
    raw_props = set(raw_q["properties"])
    raw_kind = set(raw_q["properties"]["kind"]["enum"])

    if "oneOf" not in patched_q:
        raise AssertionError("patched ClosedSemanticQuery must use oneOf")

    for branch in patched_q["oneOf"]:
        props = set(branch["properties"])
        if not props.issubset(raw_props):
            raise AssertionError(f"widened properties: {props - raw_props}")
        kind_enum = set(branch["properties"]["kind"]["enum"])
        if not kind_enum.issubset(raw_kind):
            raise AssertionError(f"widened kind enum: {kind_enum - raw_kind}")
        if branch.get("additionalProperties") is not False:
            raise AssertionError("branch must set additionalProperties: false")
        for field in ("text", "local_ref"):
            if field not in branch["properties"]:
                continue
            field_schema = branch["properties"][field]
            if field_schema.get("type") != "string":
                raise AssertionError(f"{field} must be type string")
            if field_schema.get("pattern") != NON_WHITESPACE_STRING["pattern"]:
                raise AssertionError(
                    f"{field} must use pattern {NON_WHITESPACE_STRING['pattern']!r}"
                )

    if set(patched.get("$defs", {})) != set(raw.get("$defs", {})):
        raise AssertionError("$defs key set changed beyond ClosedSemanticQuery replace")


def patch_constraint_schema(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = copy.deepcopy(raw if raw is not None else raw_pydantic_schema())
    raw_query = schema["$defs"]["ClosedSemanticQuery"]
    schema["$defs"]["ClosedSemanticQuery"] = build_xor_closed_semantic_query(raw_query)
    assert_patched_subseteq_raw(
        raw if raw is not None else raw_pydantic_schema(),
        schema,
    )
    return schema


def build_constraint_artifact() -> tuple[dict[str, Any], bytes, str, str]:
    """Return (patched_dict, canonical_bytes, raw_sha256, patched_sha256)."""
    raw = raw_pydantic_schema()
    raw_bytes = canonical_json_bytes(raw)
    patched = patch_constraint_schema(raw)
    patched_bytes = canonical_json_bytes(patched)
    return patched, patched_bytes, sha256_bytes(raw_bytes), sha256_bytes(patched_bytes)


def constraint_identity() -> dict[str, Any]:
    return {
        "constraint_patch_version": CONSTRAINT_PATCH_VERSION,
        "constraint_patcher_source_sha256": patcher_source_sha256(),
        "canonical_json_version": CANONICAL_JSON_VERSION,
        "canonical_json_spec": dict(CANONICAL_JSON_SPEC),
    }


def write_constraint_artifact(evidence_dir: Path) -> dict[str, Any]:
    patched, patched_bytes, raw_sha, patched_sha = build_constraint_artifact()
    out = evidence_dir / CONSTRAINT_ARTIFACT_NAME
    out.write_bytes(patched_bytes)
    return {
        "path": str(out),
        "raw_pydantic_schema_sha256": raw_sha,
        "patched_constraint_schema_sha256": patched_sha,
        "constraint_source": (
            "ClosedNormalizedProgram.model_json_schema() + XOR oneOf patch "
            "with non-whitespace pattern on text/local_ref"
        ),
        "bytes_written": len(patched_bytes),
        **constraint_identity(),
    }
