"""Load SLM fixtures in d0+workspace or D5 semantic-manifest form."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "benchmark" / "fixtures"

_FAMILIES = {
    "GR": "gamma_ray",
    "CALI": "caliper",
    "RHOB": "bulk_density",
    "RHOZ": "bulk_density",
    "NPHI": "neutron_porosity",
    "TNPH": "neutron_porosity",
    "RT": "resistivity",
    "ILD": "resistivity",
    "CBL": "cement_bond",
    "VDL": "variable_density",
}


def _aliases_for(channel: str, extra: list[str] | None = None) -> list[str]:
    base = {
        "GR": ["gamma", "gamma ray", "gamma-ray"],
        "NPHI": ["neutron", "neutron porosity", "nphi"],
        "RHOB": ["density", "bulk density", "rhob"],
        "CALI": ["caliper", "cal"],
        "RT": ["resistivity", "res"],
        "ILD": ["resistivity", "deep resistivity"],
        "CBL": ["cbl", "cement bond"],
    }.get(channel, [])
    out = list(base)
    for a in extra or []:
        if a not in out:
            out.append(a)
    return out


def project_d5_manifest(manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Project D5 semantic manifest → (d0, workspace) for prompt/export compatibility.

    Curve `ref` prefers request-local handle (curve-N) when present so duplicate
    channels remain distinguishable under WELL-IR 1.2-candidate.
    """
    tracks_d0: list[dict[str, Any]] = []
    track_curves: dict[int, list[str]] = {}
    for t in manifest.get("tracks") or []:
        ref = int(t["ref"])
        track_curves[ref] = []
        tracks_d0.append(
            {
                "ref": ref,
                "id": t.get("id") or f"track_{ref}",
                "kind": t.get("kind") or "normal",
                "title": t.get("title"),
                "curves": track_curves[ref],
            }
        )

    curves_d0: list[dict[str, Any]] = []
    available: list[dict[str, Any]] = []
    seen_channels: set[str] = set()
    for c in manifest.get("existing_curves") or []:
        handle = c.get("handle")
        channel = c.get("channel") or c.get("ref")
        ref = handle or channel
        track_ref = int(c.get("track_ref") or c.get("track") or 1)
        scale = c.get("scale") or {}
        direction = "decreasing" if scale.get("reverse") else "increasing"
        curves_d0.append(
            {
                "ref": ref,
                "channel": channel,
                "handle": handle,
                "label": c.get("label"),
                "track": track_ref,
                "min": scale.get("minimum"),
                "max": scale.get("maximum"),
                "direction": direction,
                "scale_kind": scale.get("kind"),
                "line_style": "solid",
            }
        )
        if track_ref in track_curves:
            track_curves[track_ref].append(str(ref))
        if channel and channel not in seen_channels:
            seen_channels.add(channel)
            available.append(
                {
                    "id": channel,
                    "family": _FAMILIES.get(channel),
                    "aliases": _aliases_for(channel, list(c.get("aliases") or [])),
                }
            )
        # Also expose handle as resolvable id when distinct
        if handle and handle != channel:
            available.append(
                {
                    "id": handle,
                    "family": _FAMILIES.get(channel or ""),
                    "aliases": [channel] if channel else [],
                }
            )

    # Channels present in sources but not yet placed
    for src in manifest.get("sources") or []:
        for ch in src.get("channels") or []:
            mnemonic = ch.get("mnemonic")
            if mnemonic and mnemonic not in seen_channels:
                seen_channels.add(mnemonic)
                available.append(
                    {
                        "id": mnemonic,
                        "family": _FAMILIES.get(mnemonic),
                        "aliases": list(ch.get("aliases") or []) + _aliases_for(mnemonic),
                    }
                )

    fills_d0: list[dict[str, Any]] = []
    fills_ws: list[dict[str, Any]] = []
    for i, f in enumerate(manifest.get("fills") or []):
        ref = f.get("handle") or f.get("ref") or f"fill-{i+1}"
        curve = f.get("curve") or f.get("curve_ref") or ""
        mode = f.get("mode") or f.get("kind") or "unknown"
        fills_d0.append({"ref": ref, "curve": curve, "mode": mode})
        fills_ws.append({"ref": ref, "curve": curve, "mode": mode})

    section = manifest.get("section") or {}
    depth_unit = section.get("depth_unit") or "m"
    interval = None
    if section.get("depth_range"):
        dr = section["depth_range"]
        interval = {
            "top": dr.get("top") or dr.get("minimum"),
            "bottom": dr.get("base") or dr.get("bottom") or dr.get("maximum"),
            "unit": depth_unit,
        }

    focus = manifest.get("focus")
    focus_state = {"curve": None, "track": None}
    if isinstance(focus, dict):
        focus_state = {
            "curve": focus.get("curve"),
            "track": focus.get("track"),
        }
    elif isinstance(focus, str):
        focus_state = {"curve": {"ref": focus}, "track": None}

    d0 = {
        "tracks": tracks_d0,
        "curves": curves_d0,
        "fills": fills_d0,
        "interval": interval,
        "section": section,
    }
    workspace = {
        "available_curves": available,
        "current_tracks": [
            {
                "ref": t["ref"],
                "id": t["id"],
                "kind": t["kind"] if t["kind"] in {"normal", "reference"} else "normal",
                "curves": list(t["curves"]),
                "title": t.get("title"),
            }
            for t in tracks_d0
        ],
        "fills": fills_ws,
        "focus": focus_state,
        "depth_unit": depth_unit if depth_unit in {"m", "ft"} else "m",
        "fixture_id": manifest.get("fixture_id"),
    }
    return d0, workspace


def load_fixture(fixture_id: str) -> dict[str, Any]:
    """Return dict with at least d0 + workspace (+ optional d5_manifest)."""
    path = FIXTURES / f"{fixture_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "d0" in raw and "workspace" in raw:
        return raw
    if raw.get("fixture_format") == "d5_semantic_manifest_r1" or "manifest" in raw:
        manifest = raw.get("manifest") or raw
        d0, workspace = project_d5_manifest(manifest)
        return {
            "fixture_format": "d5_semantic_manifest_r1",
            "d5_manifest": manifest,
            "d0": d0,
            "workspace": workspace,
        }
    # Bare D5 manifest saved without wrapper
    if "existing_curves" in raw and "tracks" in raw and "d0" not in raw:
        d0, workspace = project_d5_manifest(raw)
        return {
            "fixture_format": "d5_semantic_manifest_r1",
            "d5_manifest": raw,
            "d0": d0,
            "workspace": workspace,
        }
    raise ValueError(f"Unrecognized fixture shape: {path}")
