"""Project fixture → ProjectedWorkspace (experiment-side; reuses fixture_loader)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.mb02.contracts import CurveFact, FillFact, ProjectedWorkspace, TrackFact
from nlp_gate_modernbert.paths import SLM01_ROOT

# One-way import into SLM-01 fixture loader (read-only contracts).
_SLM01 = str(SLM01_ROOT)
if _SLM01 not in sys.path:
    sys.path.insert(0, _SLM01)

from benchmark.fixture_loader import load_fixture  # noqa: E402


def _norm_alias(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").split())


def project_workspace(fixture_id: str) -> ProjectedWorkspace:
    raw = load_fixture(fixture_id)
    d0 = raw.get("d0") or {}
    ws = raw.get("workspace") or {}
    manifest = raw.get("d5_manifest") or {}

    # Alias index from workspace.available_curves
    alias_by_id: dict[str, list[str]] = {}
    for ac in ws.get("available_curves") or []:
        cid = str(ac.get("id"))
        alias_by_id[cid] = [_norm_alias(a) for a in (ac.get("aliases") or [])]
        alias_by_id[cid].append(_norm_alias(cid))

    curves: list[CurveFact] = []
    for c in d0.get("curves") or []:
        cid = str(c.get("handle") or c.get("ref") or c.get("channel"))
        channel = c.get("channel") or (None if str(c.get("ref", "")).startswith("curve-") else c.get("ref"))
        aliases = list(alias_by_id.get(cid, []))
        if channel:
            aliases.extend(alias_by_id.get(str(channel), []))
        # dedupe
        seen: set[str] = set()
        uniq: list[str] = []
        for a in aliases:
            if a not in seen:
                seen.add(a)
                uniq.append(a)
        label = c.get("label")
        if label:
            uniq.append(_norm_alias(str(label)))
        # also tokenize label words as weak aliases (wide/narrow CBL)
        if label:
            for tok in _norm_alias(str(label)).split():
                if len(tok) > 2 and tok not in uniq:
                    uniq.append(tok)
        curves.append(
            CurveFact(
                id=cid,
                channel=str(channel) if channel else None,
                handle=c.get("handle"),
                label=str(label) if label else None,
                aliases=uniq,
                track_ref=int(c["track"]) if c.get("track") is not None else None,
                scale_kind=c.get("scale_kind"),
                scale_min=c.get("min"),
                scale_max=c.get("max"),
                scale_reverse=(c.get("direction") == "decreasing")
                if c.get("direction") is not None
                else None,
            )
        )

    # Curves present only in available_curves (not yet placed) — still resolvable
    placed_ids = {c.id for c in curves} | {c.channel for c in curves if c.channel}
    for ac in ws.get("available_curves") or []:
        cid = str(ac.get("id"))
        if cid in placed_ids:
            continue
        aliases = [_norm_alias(a) for a in (ac.get("aliases") or [])]
        aliases.append(_norm_alias(cid))
        curves.append(
            CurveFact(
                id=cid,
                channel=cid,
                handle=None,
                aliases=aliases,
                track_ref=None,
            )
        )

    tracks = [
        TrackFact(
            ref=int(t["ref"]),
            id=t.get("id"),
            title=t.get("title"),
            curves=[str(x) for x in (t.get("curves") or [])],
        )
        for t in (ws.get("current_tracks") or d0.get("tracks") or [])
    ]

    fills = [
        FillFact(ref=str(f.get("ref")), curve=f.get("curve"), mode=f.get("mode"))
        for f in (ws.get("fills") or d0.get("fills") or [])
    ]

    focus_curve = None
    focus_track = None
    # Prefer D5 manifest focus.curve_handle (fixture_loader historically missed this)
    focus = manifest.get("focus") if isinstance(manifest, dict) else None
    if focus is None:
        focus = ws.get("focus")
    if isinstance(focus, dict):
        focus_curve = focus.get("curve_handle") or focus.get("curve")
        if isinstance(focus_curve, dict):
            focus_curve = focus_curve.get("ref") or focus_curve.get("handle")
        focus_track = focus.get("track")
        if isinstance(focus_track, dict):
            focus_track = focus_track.get("ref")
        if focus_track is not None:
            focus_track = int(focus_track)

    return ProjectedWorkspace(
        fixture_id=fixture_id,
        curves=curves,
        tracks=tracks,
        fills=fills,
        focus_curve_handle=str(focus_curve) if focus_curve else None,
        focus_track_ref=focus_track,
        depth_unit=ws.get("depth_unit") or (d0.get("interval") or {}).get("unit"),
    )
