"""Canonicalization and validation helpers for WELL-IR results."""

from __future__ import annotations

import json
from typing import Any

from pydantic import TypeAdapter, ValidationError

from .envelopes import OkEnvelope, WellIrResult
from .selectors import ResolvedRef


_RESULT_ADAPTER = TypeAdapter(WellIrResult)


def parse_well_ir(data: dict[str, Any] | str) -> WellIrResult:
    """Parse and validate a WELL-IR result envelope."""
    payload: Any = json.loads(data) if isinstance(data, str) else data
    return _RESULT_ADAPTER.validate_python(payload)


def canonicalize(result: WellIrResult) -> dict[str, Any]:
    """Return a stable JSON-serializable dict (sorted keys, exclude unset)."""
    return result.model_dump(mode="json", exclude_unset=False)


def canonicalize_json(result: WellIrResult) -> str:
    """Stable JSON string for hashing / exact-match recording."""
    return json.dumps(canonicalize(result), sort_keys=True, separators=(",", ":"))


def assert_ok_refs_resolved(result: WellIrResult) -> None:
    """Enforce ok-program invariant: every selector is uniquely bound."""
    if not isinstance(result, OkEnvelope):
        return
    for op in result.ops:
        for value in op.model_dump().values():
            _walk_refs(value)


def _walk_refs(value: Any) -> None:
    if isinstance(value, dict):
        if "kind" in value and ("ref" in value or "local_ref" in value):
            ResolvedRef.model_validate(value)
        for child in value.values():
            _walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            _walk_refs(child)


def validation_error_to_invalid(exc: ValidationError) -> dict[str, Any]:
    from .envelopes import InvalidEnvelope

    return canonicalize(InvalidEnvelope(detail=str(exc.errors())))
