"""Minimal post-OK projected effects (Q3). No effect before successful adjudication."""

from __future__ import annotations

from nlp_gate_modernbert.mb02.contracts import CurveFact, ProjectedWorkspace, TrackFact
from nlp_gate_modernbert.mb02.resolve import match_curves
from nlp_gate_modernbert.scope_runtime.contracts import LocalBindingTable, ScopeNormalizedRequest


def workspace_summary(ws: ProjectedWorkspace) -> dict:
    return {
        "fixture_id": ws.fixture_id,
        "tracks": [{"ref": t.ref, "title": t.title, "id": t.id} for t in ws.tracks],
        "curves": [
            {
                "id": c.handle or c.id,
                "channel": c.channel,
                "track_ref": c.track_ref,
                "scale_kind": c.scale_kind,
                "scale_min": c.scale_min,
                "scale_max": c.scale_max,
                "scale_reverse": c.scale_reverse,
            }
            for c in ws.curves
        ],
        "fills": [{"ref": f.ref, "curve": f.curve, "mode": f.mode} for f in ws.fills],
    }


def next_ephemeral_track_ref(ws: ProjectedWorkspace) -> int:
    """Deterministic experiment-local projected identity (not host persistent ID)."""
    existing = [t.ref for t in ws.tracks]
    return (max(existing) + 1) if existing else 1


def _curve_mut(ws: ProjectedWorkspace, curve_query: str) -> CurveFact | None:
    m = match_curves(ws, curve_query)
    if m.candidate_count != 1:
        return None
    cid = m.candidate_ids[0]
    for c in ws.curves:
        if (c.handle or c.id) == cid or c.id == cid:
            return c
    return None


def apply_effect(
    req: ScopeNormalizedRequest,
    ws: ProjectedWorkspace,
    bindings: LocalBindingTable,
    *,
    resolved_track_ref: int | None = None,
) -> tuple[ProjectedWorkspace, dict[str, int], str | None]:
    """Apply authorized effect; return (new_ws, binds_published, effect_label).

    DEFINE_FILL / REMOVE_FILL: no projected state change (deferred).
    """
    op = req.requested_operation
    published: dict[str, int] = {}

    if op == "CREATE_TRACK":
        ref = next_ephemeral_track_ref(ws)
        title = req.track_title
        # width_mm is request-representable (Q1A) but not required as later adjudication fact
        track = TrackFact(ref=ref, id=f"projected_track_{ref}", title=title, curves=[])
        new_tracks = list(ws.tracks) + [track]
        new_ws = ws.model_copy(update={"tracks": new_tracks})
        return new_ws, published, f"CREATE_TRACK→projected_ref={ref}"

    if op == "PLACE_CURVE":
        if not req.query or not req.query.text:
            return ws, published, None
        curve = _curve_mut(ws, req.query.text)
        if curve is None:
            return ws, published, None
        track_ref = resolved_track_ref
        if track_ref is None and req.target and req.target.text:
            # already adapted to "track N"
            import re

            m = re.search(r"(\d+)", req.target.text)
            track_ref = int(m.group(1)) if m else None
        if track_ref is None:
            return ws, published, None
        updated = []
        for c in ws.curves:
            if c is curve or (c.handle or c.id) == (curve.handle or curve.id):
                updated.append(c.model_copy(update={"track_ref": track_ref}))
            else:
                updated.append(c)
        # update track membership lists
        new_tracks = []
        cid = curve.handle or curve.id
        for t in ws.tracks:
            members = [x for x in t.curves if x != cid]
            if t.ref == track_ref and cid not in members:
                members = list(members) + [cid]
            new_tracks.append(t.model_copy(update={"curves": members}))
        return (
            ws.model_copy(update={"curves": updated, "tracks": new_tracks}),
            published,
            f"PLACE_CURVE→track_ref={track_ref}",
        )

    if op == "CONFIGURE_CURVE_DISPLAY":
        if not req.query or not req.query.text:
            return ws, published, None
        curve = _curve_mut(ws, req.query.text)
        if curve is None:
            return ws, published, None
        patch: dict = {}
        if req.scale_bounds is not None:
            if req.scale_bounds.kind is not None:
                patch["scale_kind"] = req.scale_bounds.kind
            if req.scale_bounds.minimum is not None:
                patch["scale_min"] = float(req.scale_bounds.minimum)
            if req.scale_bounds.maximum is not None:
                patch["scale_max"] = float(req.scale_bounds.maximum)
        dirs = list(req.scale_direction_claims or [])
        if "decreasing" in dirs and "increasing" not in dirs:
            patch["scale_reverse"] = True
        elif "increasing" in dirs and "decreasing" not in dirs:
            patch["scale_reverse"] = False
        updated = []
        for c in ws.curves:
            if c is curve or (c.handle or c.id) == (curve.handle or curve.id):
                updated.append(c.model_copy(update=patch))
            else:
                updated.append(c)
        return (
            ws.model_copy(update={"curves": updated}),
            published,
            f"CONFIGURE_CURVE_DISPLAY→{patch}",
        )

    if op in {"DEFINE_FILL", "REMOVE_FILL"}:
        return ws, published, f"{op}:deferred_no_projected_state"

    return ws, published, None


def publish_binds_after_create_track(
    produces_binds: dict[str, str],
    projected_track_ref: int,
    bindings: LocalBindingTable,
) -> dict[str, int]:
    published: dict[str, int] = {}
    for name, kind in produces_binds.items():
        if kind != "track":
            continue
        bindings.publish(name, projected_track_ref)
        published[name] = projected_track_ref
    return published
