"""WELL-IR 1.2-candidate domain-semantic operations."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from .selectors import ResolvedRef
from .targets import PlacementTarget

ScaleDirection = Literal["increasing", "decreasing"]
LineStyle = Literal["solid", "dashed", "dotted"]
FillMode = Literal[
    "to_upper_limit",
    "to_lower_limit",
    "baseline_split",
    "between_curves",
    "between_instances",
]
ScaleKind = Literal["linear", "log", "logarithmic", "tangential"]


class ScalePatch(BaseModel):
    kind: ScaleKind | None = None
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool | None = None
    unit: str | None = None


class StylePatch(BaseModel):
    line_style: LineStyle | None = None
    color: str | None = None
    width: float | None = None
    alpha: float | None = None


class PlaceCurve(BaseModel):
    op: Literal["place_curve"] = "place_curve"
    curve: ResolvedRef
    target: PlacementTarget


class MoveCurve(BaseModel):
    op: Literal["move_curve"] = "move_curve"
    curve: ResolvedRef
    target: PlacementTarget


class RemoveCurve(BaseModel):
    op: Literal["remove_curve"] = "remove_curve"
    curve: ResolvedRef


class ConfigureCurveDisplay(BaseModel):
    op: Literal["configure_curve_display"] = "configure_curve_display"
    curve: ResolvedRef
    # 1.0 flat fields (still accepted)
    min: float | None = None
    max: float | None = None
    direction: ScaleDirection | None = None
    line_style: LineStyle | None = None
    # 1.2 nested patches
    scale: ScalePatch | None = None
    style: StylePatch | None = None


class SetInterval(BaseModel):
    op: Literal["set_interval"] = "set_interval"
    top: float
    bottom: float | None = None
    base: float | None = None
    unit: Literal["m", "ft", "cm", "mm", "in"] = "m"

    @model_validator(mode="before")
    @classmethod
    def _alias_base(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("bottom") is None and data.get("base") is not None:
            out = dict(data)
            out["bottom"] = data["base"]
            return out
        return data

    @model_validator(mode="after")
    def _require_bottom(self) -> SetInterval:
        if self.bottom is None:
            raise ValueError("set_interval requires bottom or base")
        return self


class DefineFill(BaseModel):
    op: Literal["define_fill"] = "define_fill"
    bind: str | None = None
    curve: ResolvedRef
    mode: FillMode | None = None
    kind: FillMode | None = None
    threshold: float | None = None
    other_curve: ResolvedRef | None = None
    baseline: float | dict[str, Any] | None = None
    color: str | None = None
    alpha: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _alias_kind_mode(cls, data: Any) -> Any:
        if isinstance(data, dict):
            out = dict(data)
            if out.get("mode") is None and out.get("kind") is not None:
                out["mode"] = out["kind"]
            elif out.get("kind") is None and out.get("mode") is not None:
                out["kind"] = out["mode"]
            bl = out.get("baseline")
            if isinstance(bl, dict) and "value" in bl:
                out["baseline"] = bl["value"]
            return out
        return data

    @model_validator(mode="after")
    def _require_mode(self) -> DefineFill:
        if self.mode is None and self.kind is None:
            raise ValueError("define_fill requires mode or kind")
        return self


class RemoveFill(BaseModel):
    op: Literal["remove_fill"] = "remove_fill"
    fill: ResolvedRef


class CreateTrack(BaseModel):
    op: Literal["create_track"] = "create_track"
    bind: str
    kind: Literal["normal", "reference", "array"] = "normal"
    target: PlacementTarget | None = None
    title: str | None = None
    width_mm: float | None = None


WellIrOp = Annotated[
    Union[
        PlaceCurve,
        MoveCurve,
        RemoveCurve,
        ConfigureCurveDisplay,
        SetInterval,
        DefineFill,
        RemoveFill,
        CreateTrack,
    ],
    Field(discriminator="op"),
]
