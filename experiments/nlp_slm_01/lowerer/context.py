"""Workspace symbol table and document state for SLM-01 lowering."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field


class CurveSymbol(BaseModel):
    id: str
    family: str | None = None
    aliases: list[str] = Field(default_factory=list)


class TrackSymbol(BaseModel):
    model_config = {"extra": "ignore"}

    ref: int
    id: str
    kind: Literal["normal", "reference", "array"] = "normal"
    curves: list[str] = Field(default_factory=list)
    title: str | None = None


class FillSymbol(BaseModel):
    ref: str
    curve: str
    mode: str


class FocusState(BaseModel):
    curve: dict[str, Any] | None = None
    track: dict[str, Any] | None = None


class WorkspaceContext(BaseModel):
    """Symbol table supplied to the semantic compiler and lowerer."""

    model_config = {"extra": "ignore"}

    available_curves: list[CurveSymbol] = Field(default_factory=list)
    current_tracks: list[TrackSymbol] = Field(default_factory=list)
    fills: list[FillSymbol] = Field(default_factory=list)
    focus: FocusState = Field(default_factory=FocusState)
    depth_unit: Literal["m", "ft"] = "m"
    fixture_id: str | None = None


class CurvePlacement(BaseModel):
    model_config = {"extra": "ignore"}

    ref: str
    track: int
    min: float | None = None
    max: float | None = None
    direction: Literal["increasing", "decreasing"] = "increasing"
    line_style: Literal["solid", "dashed", "dotted"] = "solid"
    channel: str | None = None
    handle: str | None = None
    label: str | None = None
    scale_kind: str | None = None


class FillPlacement(BaseModel):
    ref: str
    curve: str
    mode: str
    threshold: float | None = None
    other_curve: str | None = None
    baseline: float | None = None


class DocumentState(BaseModel):
    """Authoritative D0/D1 document state for SLM experiments (promotion-ready)."""

    model_config = {"extra": "ignore"}

    tracks: list[TrackSymbol] = Field(default_factory=list)
    curves: list[CurvePlacement] = Field(default_factory=list)
    fills: list[FillPlacement] = Field(default_factory=list)
    interval: dict[str, Any] | None = None
    section: dict[str, Any] | None = None

    def clone(self) -> DocumentState:
        return DocumentState.model_validate(deepcopy(self.model_dump()))

    def curve_map(self) -> dict[str, CurvePlacement]:
        return {c.ref: c for c in self.curves}

    def track_map(self) -> dict[int, TrackSymbol]:
        return {t.ref: t for t in self.tracks}

    def fill_map(self) -> dict[str, FillPlacement]:
        return {f.ref: f for f in self.fills}


def default_triple_combo_d0() -> DocumentState:
    """Minimal synthetic D0 used by many gold fixtures."""
    return DocumentState(
        tracks=[
            TrackSymbol(ref=1, id="track_1", kind="reference", curves=[]),
            TrackSymbol(ref=2, id="track_2", kind="normal", curves=["GR"]),
            TrackSymbol(ref=3, id="track_3", kind="normal", curves=["NPHI"]),
            TrackSymbol(ref=4, id="track_4", kind="normal", curves=[]),
        ],
        curves=[
            CurvePlacement(ref="GR", track=2, min=0, max=150),
            CurvePlacement(ref="NPHI", track=3, min=0.45, max=-0.15, direction="decreasing"),
        ],
        fills=[],
        interval={"top": 2000.0, "bottom": 3500.0, "unit": "m"},
    )


def default_workspace_from_d0(d0: DocumentState) -> WorkspaceContext:
    families = {
        "GR": "gamma_ray",
        "CALI": "caliper",
        "RHOB": "bulk_density",
        "RHOZ": "bulk_density",
        "NPHI": "neutron_porosity",
        "TNPH": "neutron_porosity",
        "RT": "resistivity",
        "ILD": "resistivity",
    }
    available = []
    seen = {c.ref for c in d0.curves}
    for curve in d0.curves:
        available.append(
            CurveSymbol(
                id=curve.ref,
                family=families.get(curve.ref),
                aliases=_aliases_for(curve.ref),
            )
        )
    # Off-document but available in well (common for place_curve tests)
    for extra in ("RHOB", "CALI", "RT"):
        if extra not in seen:
            available.append(
                CurveSymbol(id=extra, family=families.get(extra), aliases=_aliases_for(extra))
            )
            seen.add(extra)
    return WorkspaceContext(
        available_curves=available,
        current_tracks=list(d0.tracks),
        fills=[
            FillSymbol(ref=f.ref, curve=f.curve, mode=f.mode) for f in d0.fills
        ],
        depth_unit=(d0.interval or {}).get("unit", "m"),
    )


def _aliases_for(mnemonic: str) -> list[str]:
    table = {
        "GR": ["gamma", "gamma ray", "gamma-ray"],
        "RHOB": ["density", "bulk density", "rhob"],
        "RHOZ": ["density", "bulk density"],
        "NPHI": ["neutron", "neutron porosity", "nphi"],
        "TNPH": ["neutron", "neutron porosity"],
        "CALI": ["caliper", "cal"],
        "RT": ["resistivity", "res"],
        "ILD": ["resistivity", "deep resistivity"],
    }
    return table.get(mnemonic, [])
