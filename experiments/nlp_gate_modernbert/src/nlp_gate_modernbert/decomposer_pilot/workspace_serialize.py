"""Q5 model-visible ProjectedWorkspace serializer (omit fixture_id; stable orders)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

SERIALIZER_VERSION = "decomposer_pilot_preflight_01.workspace_serialize.v1"

# Nested arrays preserved as-is (aliases, TrackFact.curves, supported_depth_units).
_TOP_LEVEL_KEYS = (
    "curves",
    "tracks",
    "fills",
    "focus_curve_handle",
    "focus_track_ref",
    "depth_unit",
    "supported_depth_units",
)


def _curve_sort_key(c: Mapping[str, Any]) -> tuple[str, str]:
    cid = c.get("id")
    handle = c.get("handle")
    primary = str(cid) if cid is not None else (str(handle) if handle is not None else "")
    secondary = str(handle) if handle is not None else ""
    return (primary, secondary)


def serialize_projected_workspace(workspace: Mapping[str, Any] | Any) -> str:
    """Canonical JSON for model-visible workspace.

    - omit fixture_id (harness-only)
    - exclude_none
    - tracks sorted by ref; curves by (id or handle); fills by ref
    - preserve nested array order (aliases, track.curves, supported_depth_units)
    - sort_keys=True, separators=(",",":"), ensure_ascii=False
    """
    if hasattr(workspace, "model_dump"):
        data = workspace.model_dump(exclude_none=True)
    else:
        data = dict(workspace)

    data.pop("fixture_id", None)

    curves = list(data.get("curves") or [])
    tracks = list(data.get("tracks") or [])
    fills = list(data.get("fills") or [])

    curves_sorted = sorted(curves, key=_curve_sort_key)
    tracks_sorted = sorted(tracks, key=lambda t: t.get("ref") if isinstance(t, dict) else getattr(t, "ref"))
    fills_sorted = sorted(fills, key=lambda f: str(f.get("ref") if isinstance(f, dict) else getattr(f, "ref")))

    out: dict[str, Any] = {
        "curves": curves_sorted,
        "tracks": tracks_sorted,
        "fills": fills_sorted,
    }
    for key in (
        "focus_curve_handle",
        "focus_track_ref",
        "depth_unit",
        "supported_depth_units",
    ):
        if key in data and data[key] is not None:
            out[key] = data[key]

    # Drop any unexpected keys beyond the allowlist (defense in depth).
    out = {k: out[k] for k in _TOP_LEVEL_KEYS if k in out}

    return json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def serializer_source_sha256() -> str:
    """Hash of this module's source bytes (implementation identity)."""
    from pathlib import Path

    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def serializer_spec() -> dict[str, Any]:
    return {
        "version": SERIALIZER_VERSION,
        "omit_fields": ["fixture_id"],
        "exclude_none": True,
        "sort_tracks_by": "ref",
        "sort_curves_by": "(id or handle)",
        "sort_fills_by": "ref",
        "preserve_nested_array_order": [
            "aliases",
            "TrackFact.curves",
            "supported_depth_units",
        ],
        "json_dumps": {
            "sort_keys": True,
            "separators": [",", ":"],
            "ensure_ascii": False,
        },
        "implementation_sha256": serializer_source_sha256(),
    }
