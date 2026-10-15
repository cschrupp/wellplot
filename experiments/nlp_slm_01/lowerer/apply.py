"""Deterministic WELL-IR → DocumentState lowering."""

from __future__ import annotations

from typing import Any

from well_ir.envelopes import OkEnvelope, WellIrResult
from well_ir.operations import (
    ConfigureCurveDisplay,
    CreateTrack,
    DefineFill,
    MoveCurve,
    PlaceCurve,
    RemoveCurve,
    RemoveFill,
    SetInterval,
)
from well_ir.selectors import ResolvedRef
from well_ir.targets import AbsoluteTrackTarget, RelativeTarget

from .context import CurvePlacement, DocumentState, FillPlacement, TrackSymbol, WorkspaceContext
from .errors import PreconditionError


class LoweringResult:
    def __init__(self, document: DocumentState, local_binds: dict[str, int] | None = None) -> None:
        self.document = document
        self.local_binds = local_binds or {}


def apply_well_ir(
    d0: DocumentState,
    result: WellIrResult,
    workspace: WorkspaceContext | None = None,
) -> LoweringResult:
    """Apply an ok WELL-IR program. Non-ok envelopes leave D0 unchanged."""
    _ = workspace
    if not isinstance(result, OkEnvelope):
        return LoweringResult(d0.clone())

    doc = d0.clone()
    local_tracks: dict[str, int] = {}
    fill_counter = len(doc.fills)

    for op in result.ops:
        if isinstance(op, SetInterval):
            if op.top >= op.bottom:
                raise PreconditionError("interval top must be < bottom")
            doc.interval = {"top": op.top, "bottom": op.bottom, "unit": op.unit}
        elif isinstance(op, CreateTrack):
            if not op.bind.startswith("$"):
                raise PreconditionError("create_track.bind must be a local_ref")
            if op.bind in local_tracks:
                raise PreconditionError(f"local_ref already bound: {op.bind}")
            new_ref = max((t.ref for t in doc.tracks), default=0) + 1
            if isinstance(op.target, RelativeTarget) and op.target.relation == "beside":
                anchor = _resolve_track(op.target.reference, doc, local_tracks)
                # insert after anchor by renumbering logical refs is avoided;
                # assign next ref and record adjacency in id suffix
                track = TrackSymbol(
                    ref=new_ref,
                    id=f"track_{new_ref}_beside_{anchor}",
                    kind=op.kind,
                )
            else:
                track = TrackSymbol(ref=new_ref, id=f"track_{new_ref}", kind=op.kind)
            doc.tracks.append(track)
            local_tracks[op.bind] = new_ref
        elif isinstance(op, PlaceCurve):
            curve_id = _resolve_curve(op.curve, doc, local_tracks)
            track_ref = _resolve_target_track(op.target, doc, local_tracks)
            if any(c.ref == curve_id for c in doc.curves):
                # re-place moves existing
                for c in doc.curves:
                    if c.ref == curve_id:
                        _detach_curve_from_tracks(doc, curve_id)
                        c.track = track_ref
                        break
            else:
                doc.curves.append(CurvePlacement(ref=curve_id, track=track_ref))
            _attach_curve_to_track(doc, curve_id, track_ref)
        elif isinstance(op, MoveCurve):
            curve_id = _resolve_curve(op.curve, doc, local_tracks)
            placement = doc.curve_map().get(curve_id)
            if placement is None:
                raise PreconditionError(f"curve not placed: {curve_id}")
            track_ref = _resolve_target_track(op.target, doc, local_tracks)
            _detach_curve_from_tracks(doc, curve_id)
            placement.track = track_ref
            _attach_curve_to_track(doc, curve_id, track_ref)
        elif isinstance(op, RemoveCurve):
            curve_id = _resolve_curve(op.curve, doc, local_tracks)
            if curve_id not in doc.curve_map():
                raise PreconditionError(f"curve not placed: {curve_id}")
            _detach_curve_from_tracks(doc, curve_id)
            doc.curves = [c for c in doc.curves if c.ref != curve_id]
            doc.fills = [f for f in doc.fills if f.curve != curve_id]
        elif isinstance(op, ConfigureCurveDisplay):
            curve_id = _resolve_curve(op.curve, doc, local_tracks)
            placement = doc.curve_map().get(curve_id)
            if placement is None:
                raise PreconditionError(f"curve not placed: {curve_id}")
            if op.min is not None:
                placement.min = op.min
            if op.max is not None:
                placement.max = op.max
            if op.direction is not None:
                placement.direction = op.direction
            if op.line_style is not None:
                placement.line_style = op.line_style
        elif isinstance(op, DefineFill):
            curve_id = _resolve_curve(op.curve, doc, local_tracks)
            if curve_id not in doc.curve_map():
                raise PreconditionError(f"curve not placed: {curve_id}")
            fill_counter += 1
            fill_ref = op.bind[1:] if op.bind and op.bind.startswith("$") else f"fill_{fill_counter}"
            if op.bind and op.bind.startswith("$"):
                fill_ref = op.bind[1:]
            other = None
            if op.other_curve is not None:
                other = _resolve_curve(op.other_curve, doc, local_tracks)
            doc.fills.append(
                FillPlacement(
                    ref=fill_ref,
                    curve=curve_id,
                    mode=op.mode,
                    threshold=op.threshold,
                    other_curve=other,
                    baseline=op.baseline,
                )
            )
        elif isinstance(op, RemoveFill):
            fill_id = _resolve_fill(op.fill, doc)
            doc.fills = [f for f in doc.fills if f.ref != fill_id]
        else:
            raise PreconditionError(f"unsupported op for lowerer: {type(op)}")

    return LoweringResult(doc, local_tracks)


def check_invariants(doc: DocumentState, invariants: list[dict[str, Any]]) -> list[str]:
    """Return list of failed invariant descriptions (empty if all pass)."""
    failures: list[str] = []
    cmap = doc.curve_map()
    fmap = doc.fill_map()
    tmap = doc.track_map()
    for inv in invariants:
        kind = inv.get("kind")
        if kind == "curve_on_track":
            c, t = inv["curve"], inv["track"]
            if c not in cmap or cmap[c].track != t:
                failures.append(f"curve_on_track failed: {c}@{t}")
        elif kind == "curve_absent":
            if inv["curve"] in cmap:
                failures.append(f"curve_absent failed: {inv['curve']}")
        elif kind == "scale_direction":
            c = inv["curve"]
            if c not in cmap or cmap[c].direction != inv["direction"]:
                failures.append(f"scale_direction failed: {c}")
        elif kind == "scale_bounds":
            c = inv["curve"]
            if c not in cmap or cmap[c].min != inv.get("min") or cmap[c].max != inv.get("max"):
                failures.append(f"scale_bounds failed: {c}")
        elif kind == "interval":
            if doc.interval != {
                "top": inv["top"],
                "bottom": inv["bottom"],
                "unit": inv.get("unit", "m"),
            }:
                failures.append("interval failed")
        elif kind == "fill_exists":
            curve = inv["curve"]
            mode = inv.get("mode")
            found = any(
                f.curve == curve and (mode is None or f.mode == mode) for f in doc.fills
            )
            if not found:
                failures.append(f"fill_exists failed: {curve}/{mode}")
        elif kind == "fill_absent":
            if inv["fill"] in fmap:
                failures.append(f"fill_absent failed: {inv['fill']}")
        elif kind == "track_count_gte":
            if len(doc.tracks) < inv["count"]:
                failures.append("track_count_gte failed")
        elif kind == "line_style":
            c = inv["curve"]
            if c not in cmap or cmap[c].line_style != inv["line_style"]:
                failures.append(f"line_style failed: {c}")
        elif kind == "track_exists":
            if inv["track"] not in tmap:
                failures.append(f"track_exists failed: {inv['track']}")
        else:
            failures.append(f"unknown invariant kind: {kind}")
    return failures


def _resolve_curve(ref: ResolvedRef, doc: DocumentState, local: dict[str, int]) -> str:
    if ref.kind != "curve":
        raise PreconditionError("expected curve ref")
    if ref.local_ref is not None:
        raise PreconditionError("curve local_ref not supported in v1 lowerer")
    assert isinstance(ref.ref, str)
    return ref.ref


def _resolve_fill(ref: ResolvedRef, doc: DocumentState) -> str:
    if ref.kind != "fill" or not isinstance(ref.ref, str):
        raise PreconditionError("expected fill ref")
    if ref.ref not in {f.ref for f in doc.fills}:
        raise PreconditionError(f"unknown fill: {ref.ref}")
    return ref.ref


def _resolve_track(ref: ResolvedRef, doc: DocumentState, local: dict[str, int]) -> int:
    if ref.kind != "track":
        raise PreconditionError("expected track ref")
    if ref.local_ref is not None:
        if ref.local_ref not in local:
            raise PreconditionError(f"unbound local_ref: {ref.local_ref}")
        return local[ref.local_ref]
    assert isinstance(ref.ref, int)
    if ref.ref not in doc.track_map():
        raise PreconditionError(f"unknown track: {ref.ref}")
    return ref.ref


def _resolve_target_track(
    target: AbsoluteTrackTarget | RelativeTarget,
    doc: DocumentState,
    local: dict[str, int],
) -> int:
    if isinstance(target, AbsoluteTrackTarget):
        return _resolve_track(target.reference, doc, local)
    if target.reference.kind == "track":
        anchor = _resolve_track(target.reference, doc, local)
        if target.relation == "beside":
            # place onto next existing track if present else anchor
            refs = sorted(doc.track_map())
            for r in refs:
                if r > anchor:
                    return r
            return anchor
        return anchor
    # relative to curve
    curve_id = _resolve_curve(target.reference, doc, local)
    placement = doc.curve_map().get(curve_id)
    if placement is None:
        raise PreconditionError(f"reference curve not placed: {curve_id}")
    if target.relation == "with":
        return placement.track
    # beside → prefer next track
    refs = sorted(doc.track_map())
    for r in refs:
        if r > placement.track:
            return r
    return placement.track


def _detach_curve_from_tracks(doc: DocumentState, curve_id: str) -> None:
    for track in doc.tracks:
        track.curves = [c for c in track.curves if c != curve_id]


def _attach_curve_to_track(doc: DocumentState, curve_id: str, track_ref: int) -> None:
    track = doc.track_map().get(track_ref)
    if track is None:
        raise PreconditionError(f"unknown track: {track_ref}")
    if curve_id not in track.curves:
        track.curves.append(curve_id)
