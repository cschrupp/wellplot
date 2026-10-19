from __future__ import annotations

from lowerer.apply import apply_well_ir, check_invariants
from lowerer.context import default_triple_combo_d0, default_workspace_from_d0
from well_ir.canonicalize import parse_well_ir


def test_place_with_and_reverse() -> None:
    d0 = default_triple_combo_d0()
    ws = default_workspace_from_d0(d0)
    result = parse_well_ir(
        {
            "status": "ok",
            "well_ir_version": "1.0",
            "ops": [
                {
                    "op": "place_curve",
                    "curve": {"kind": "curve", "ref": "RHOB"},
                    "target": {
                        "mode": "relative",
                        "relation": "with",
                        "reference": {"kind": "curve", "ref": "NPHI"},
                    },
                },
                {
                    "op": "configure_curve_display",
                    "curve": {"kind": "curve", "ref": "RHOB"},
                    "direction": "decreasing",
                },
            ],
        }
    )
    out = apply_well_ir(d0, result, ws).document
    assert out.curve_map()["RHOB"].track == out.curve_map()["NPHI"].track
    assert out.curve_map()["RHOB"].direction == "decreasing"
    assert not check_invariants(
        out,
        [
            {
                "kind": "curve_on_track",
                "curve": "RHOB",
                "track": out.curve_map()["NPHI"].track,
            },
            {"kind": "scale_direction", "curve": "RHOB", "direction": "decreasing"},
        ],
    )


def test_create_track_local_ref() -> None:
    d0 = default_triple_combo_d0()
    n_tracks = len(d0.tracks)
    result = parse_well_ir(
        {
            "status": "ok",
            "well_ir_version": "1.0",
            "ops": [
                {
                    "op": "create_track",
                    "bind": "$track1",
                    "kind": "normal",
                    "target": {
                        "mode": "relative",
                        "relation": "beside",
                        "reference": {"kind": "track", "ref": 2},
                    },
                },
                {
                    "op": "place_curve",
                    "curve": {"kind": "curve", "ref": "CALI"},
                    "target": {
                        "mode": "track",
                        "reference": {"kind": "track", "local_ref": "$track1"},
                    },
                },
            ],
        }
    )
    out = apply_well_ir(d0, result).document
    assert len(out.tracks) == n_tracks + 1
    assert "CALI" in out.curve_map()
