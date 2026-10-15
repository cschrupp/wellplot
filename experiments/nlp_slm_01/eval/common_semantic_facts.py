"""Architecture-neutral CommonSemanticFacts projection."""

from __future__ import annotations

from typing import Any

from well_ir.envelopes import OkEnvelope, WellIrResult
from well_ir.operations import (
    ConfigureCurveDisplay,
    DefineFill,
    PlaceCurve,
    SetInterval,
)
from well_ir.targets import AbsoluteTrackTarget, RelativeTarget


def from_well_ir(result: WellIrResult) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "requested_curves": [],
        "placements": [],
        "track_relationships": [],
        "scales": [],
        "scale_directions": [],
        "depth_interval": None,
        "fills": [],
        "envelope_state": result.status,
    }
    if not isinstance(result, OkEnvelope):
        return facts
    for op in result.ops:
        if isinstance(op, PlaceCurve):
            facts["requested_curves"].append(op.curve.ref)
            if isinstance(op.target, AbsoluteTrackTarget):
                facts["placements"].append(
                    {"curve": op.curve.ref, "track": op.target.reference.ref}
                )
            elif isinstance(op.target, RelativeTarget):
                facts["track_relationships"].append(
                    {
                        "curve": op.curve.ref,
                        "relation": op.target.relation,
                        "reference": op.target.reference.ref,
                    }
                )
        elif isinstance(op, ConfigureCurveDisplay):
            if op.direction is not None:
                facts["scale_directions"].append(
                    {"curve": op.curve.ref, "direction": op.direction}
                )
            if op.min is not None or op.max is not None:
                facts["scales"].append(
                    {"curve": op.curve.ref, "min": op.min, "max": op.max}
                )
        elif isinstance(op, SetInterval):
            facts["depth_interval"] = {
                "top": op.top,
                "bottom": op.bottom,
                "unit": op.unit,
            }
        elif isinstance(op, DefineFill):
            facts["fills"].append(
                {"curve": op.curve.ref, "mode": op.mode, "threshold": op.threshold}
            )
    return facts


def facts_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    keys = [
        "requested_curves",
        "placements",
        "track_relationships",
        "scales",
        "scale_directions",
        "depth_interval",
        "fills",
        "envelope_state",
    ]
    return all(a.get(k) == b.get(k) for k in keys)
