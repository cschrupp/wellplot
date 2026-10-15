"""Normalized semantic IR equivalence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from well_ir.canonicalize import canonicalize, parse_well_ir
from well_ir.envelopes import OkEnvelope, WellIrResult


def _as_result(value: WellIrResult | dict[str, Any] | BaseModel) -> WellIrResult:
    if isinstance(value, dict):
        return parse_well_ir(value)
    return value  # type: ignore[return-value]


def normalized_equal(a: WellIrResult | dict[str, Any], b: WellIrResult | dict[str, Any]) -> bool:
    ra = _as_result(a)
    rb = _as_result(b)
    if ra.status != rb.status:
        return False
    if ra.status != "ok":
        return canonicalize(ra) == canonicalize(rb)
    assert isinstance(ra, OkEnvelope) and isinstance(rb, OkEnvelope)
    return _normalize_ops(ra) == _normalize_ops(rb)


def _normalize_ops(result: OkEnvelope) -> list[dict[str, Any]]:
    ops = []
    for op in result.ops:
        d = op.model_dump(mode="json", exclude_unset=True)
        ops.append(d)
    return ops
