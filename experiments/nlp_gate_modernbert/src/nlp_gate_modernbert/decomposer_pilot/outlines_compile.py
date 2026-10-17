"""Compile Outlines JsonSchema from exact patched constraint bytes (no generate)."""

from __future__ import annotations

from typing import Any


def compile_json_schema(patched_schema_bytes: bytes) -> Any:
    """Build Outlines JsonSchema from exact patched UTF-8 JSON bytes.

    Raises on compile failure. Does not call model.generate / forward.
    """
    from outlines.types import JsonSchema

    text = patched_schema_bytes.decode("utf-8")
    # Pass exact string so Outlines does not re-serialize with ensure_ascii=True.
    return JsonSchema(text)


def compile_attestation(patched_schema_bytes: bytes) -> dict[str, Any]:
    js = compile_json_schema(patched_schema_bytes)
    schema_attr = getattr(js, "schema", None)
    return {
        "backend": "outlines.types.JsonSchema",
        "compiled": True,
        "schema_type": type(js).__qualname__,
        "schema_attr_present": schema_attr is not None,
        "input_bytes": len(patched_schema_bytes),
    }
