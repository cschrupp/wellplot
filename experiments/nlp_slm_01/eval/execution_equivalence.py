"""Execution equivalence via deterministic lowering."""

from __future__ import annotations

from typing import Any

from lowerer.apply import apply_well_ir
from lowerer.context import DocumentState, WorkspaceContext
from well_ir.canonicalize import parse_well_ir
from well_ir.envelopes import WellIrResult


def _as_result(value: WellIrResult | dict[str, Any]) -> WellIrResult:
    if isinstance(value, dict):
        return parse_well_ir(value)
    return value  # type: ignore[return-value]


def execution_equivalent(
    predicted: WellIrResult | dict[str, Any],
    gold: WellIrResult | dict[str, Any],
    d0: DocumentState,
    workspace: WorkspaceContext | None = None,
) -> bool:
    pred = _as_result(predicted)
    g = _as_result(gold)
    if pred.status != g.status:
        return False
    if pred.status != "ok":
        return True
    d_pred = apply_well_ir(d0, pred, workspace).document
    d_gold = apply_well_ir(d0, g, workspace).document
    return d_pred.model_dump(mode="json") == d_gold.model_dump(mode="json")
