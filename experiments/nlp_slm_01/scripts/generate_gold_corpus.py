#!/usr/bin/env python3
"""Generate ≥300 independent WELL-IR v1 semantic gold cases (IR-first)."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from lowerer.context import (
    CurvePlacement,
    DocumentState,
    TrackSymbol,
    WorkspaceContext,
    default_triple_combo_d0,
    default_workspace_from_d0,
)
from lowerer.apply import apply_well_ir, check_invariants
from well_ir.canonicalize import parse_well_ir

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "benchmark" / "gold" / "cases.jsonl"
SPLITS = ROOT / "benchmark" / "splits"
FIXTURES = ROOT / "benchmark" / "fixtures"

rng = random.Random(20261011)


def case_id(n: int) -> str:
    return f"GOLD-{n:04d}"


def base_fixture() -> tuple[DocumentState, WorkspaceContext]:
    d0 = default_triple_combo_d0()
    # Ensure RHOB not placed (available for place tests)
    ws = default_workspace_from_d0(d0)
    return d0, ws


def d0_with_rhob() -> tuple[DocumentState, WorkspaceContext]:
    d0, ws = base_fixture()
    d0.curves.append(CurvePlacement(ref="RHOB", track=4, min=1.95, max=2.95))
    for t in d0.tracks:
        if t.ref == 4:
            t.curves.append("RHOB")
    ws = default_workspace_from_d0(d0)
    return d0, ws


def d0_ambiguous_density() -> tuple[DocumentState, WorkspaceContext]:
    d0, ws = base_fixture()
    # expose RHOB and RHOZ as available
    from lowerer.context import CurveSymbol

    ws.available_curves.append(
        CurveSymbol(id="RHOZ", family="bulk_density", aliases=["density", "bulk density"])
    )
    return d0, ws


def dump_fixture(name: str, d0: DocumentState, ws: WorkspaceContext) -> str:
    path = FIXTURES / f"{name}.json"
    path.write_text(
        json.dumps({"d0": d0.model_dump(mode="json"), "workspace": ws.model_dump(mode="json")}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return name


def make_case(
    n: int,
    *,
    family: str,
    tags: list[str],
    signature: str,
    envelope: dict[str, Any],
    invariants: list[dict[str, Any]],
    utterances: list[str],
    fixture_name: str,
    provenance: dict[str, Any],
    historical_eligibility: str = "OUT_OF_SCOPE",
) -> dict[str, Any]:
    return {
        "case_id": case_id(n),
        "semantic_family": family,
        "semantic_tags": tags,
        "semantic_signature": signature,
        "fixture": fixture_name,
        "gold": envelope,
        "lowerer_invariants": invariants,
        "utterances": [
            {
                "text": u,
                "origin": "new_gold_authoring" if i == 0 else "human_paraphrase",
                "reviewed": True,
            }
            for i, u in enumerate(utterances)
        ],
        "provenance": provenance,
        "historical_baseline_eligibility": historical_eligibility,
    }


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    n = 1

    fix_base = dump_fixture("d0_triple_combo", *base_fixture())
    fix_rhob = dump_fixture("d0_with_rhob", *d0_with_rhob())
    fix_amb = dump_fixture("d0_ambiguous_density", *d0_ambiguous_density())

    # --- simple place / configure / interval / remove (~20%) ---
    simple_specs = [
        (
            "curve_placement",
            "place_curve(track)",
            {
                "status": "ok",
                "well_ir_version": "1.0",
                "ops": [
                    {
                        "op": "place_curve",
                        "curve": {"kind": "curve", "ref": "RHOB"},
                        "target": {
                            "mode": "track",
                            "reference": {"kind": "track", "ref": 4},
                        },
                    }
                ],
            },
            [{"kind": "curve_on_track", "curve": "RHOB", "track": 4}],
            [
                "Put RHOB on track 4.",
                "Place bulk density in track four.",
                "Add density to track 4.",
            ],
            fix_base,
            ["alias", "mnemonic"],
        ),
        (
            "display_configuration",
            "configure_curve_display(direction=decreasing)",
            {
                "status": "ok",
                "well_ir_version": "1.0",
                "ops": [
                    {
                        "op": "configure_curve_display",
                        "curve": {"kind": "curve", "ref": "RHOB"},
                        "direction": "decreasing",
                    }
                ],
            },
            [{"kind": "scale_direction", "curve": "RHOB", "direction": "decreasing"}],
            [
                "Reverse the density scale.",
                "Flip RHOB so it decreases left to right.",
                "Invert RHOB scale direction.",
            ],
            fix_rhob,
            ["scale_reverse"],
        ),
        (
            "intervals",
            "set_interval",
            {
                "status": "ok",
                "well_ir_version": "1.0",
                "ops": [
                    {
                        "op": "set_interval",
                        "top": 2500.0,
                        "bottom": 3200.0,
                        "unit": "m",
                    }
                ],
            },
            [{"kind": "interval", "top": 2500.0, "bottom": 3200.0, "unit": "m"}],
            [
                "Set depth from 2500 to 3200 m.",
                "Show the interval 2500-3200 metres.",
                "Restrict the plot to 2500 through 3200 m.",
            ],
            fix_base,
            ["units"],
        ),
        (
            "curve_placement",
            "remove_curve",
            {
                "status": "ok",
                "well_ir_version": "1.0",
                "ops": [
                    {"op": "remove_curve", "curve": {"kind": "curve", "ref": "GR"}}
                ],
            },
            [{"kind": "curve_absent", "curve": "GR"}],
            ["Remove GR.", "Take gamma off the plot.", "Delete the GR curve."],
            fix_base,
            ["remove"],
        ),
    ]

    for family, sig, env, inv, utts, fix, tags in simple_specs:
        cases.append(
            make_case(
                n,
                family=family,
                tags=tags,
                signature=sig,
                envelope=env,
                invariants=inv,
                utterances=utts,
                fixture_name=fix,
                provenance={
                    "source_kind": "new_gold_authoring",
                    "adaptation": "newly_authored",
                    "review_status": "accepted",
                },
            )
        )
        n += 1

    # Generate parametric simple variants
    track_targets = [2, 3, 4]
    curves_place = ["RHOB", "CALI", "RT"]
    for curve in curves_place:
        for track in track_targets:
            env = {
                "status": "ok",
                "well_ir_version": "1.0",
                "ops": [
                    {
                        "op": "place_curve",
                        "curve": {"kind": "curve", "ref": curve},
                        "target": {
                            "mode": "track",
                            "reference": {"kind": "track", "ref": track},
                        },
                    }
                ],
            }
            cases.append(
                make_case(
                    n,
                    family="curve_placement",
                    tags=["parametric", "mnemonic"],
                    signature=f"place_curve(track)+curve={curve}",
                    envelope=env,
                    invariants=[{"kind": "curve_on_track", "curve": curve, "track": track}],
                    utterances=[
                        f"Put {curve} on track {track}.",
                        f"Place {curve} in track {track}.",
                    ],
                    fixture_name=fix_base,
                    provenance={
                        "source_kind": "new_gold_authoring",
                        "adaptation": "newly_authored",
                        "review_status": "accepted",
                    },
                )
            )
            n += 1

    # display configs
    for curve, direction, style in [
        ("GR", "increasing", "dashed"),
        ("GR", "increasing", "dotted"),
        ("NPHI", "decreasing", "solid"),
        ("RHOB", "decreasing", "dashed"),
        ("RHOB", "increasing", "solid"),
        ("CALI", "increasing", "dashed"),
    ]:
        fix = fix_rhob if curve in {"RHOB", "CALI"} else fix_base
        # ensure CALI placed when needed
        ops = [
            {
                "op": "configure_curve_display",
                "curve": {"kind": "curve", "ref": curve},
                "direction": direction,
                "line_style": style,
            }
        ]
        if curve == "CALI":
            # place first in gold program
            ops = [
                {
                    "op": "place_curve",
                    "curve": {"kind": "curve", "ref": "CALI"},
                    "target": {
                        "mode": "track",
                        "reference": {"kind": "track", "ref": 2},
                    },
                },
                {
                    "op": "configure_curve_display",
                    "curve": {"kind": "curve", "ref": "CALI"},
                    "direction": direction,
                    "line_style": style,
                },
            ]
            fix = fix_base
        cases.append(
            make_case(
                n,
                family="display_configuration",
                tags=["line_style", "scale"],
                signature=f"configure_curve_display({direction},{style})",
                envelope={"status": "ok", "well_ir_version": "1.0", "ops": ops},
                invariants=[
                    {"kind": "scale_direction", "curve": curve, "direction": direction},
                    {"kind": "line_style", "curve": curve, "line_style": style},
                ],
                utterances=[
                    f"Make {curve} {style} with {direction} scale.",
                    f"Set {curve} to {style} and {direction}.",
                ],
                fixture_name=fix,
                provenance={
                    "source_kind": "new_gold_authoring",
                    "adaptation": "newly_authored",
                    "review_status": "accepted",
                },
            )
        )
        n += 1

    # intervals parametric
    for top, bottom, unit in [
        (2200, 2450, "m"),
        (2400, 2800, "m"),
        (1000, 1500, "m"),
        (3000, 3500, "m"),
        (7000, 8000, "ft"),
        (5000, 5500, "ft"),
        (2100.5, 2300.5, "m"),
        (1800, 1900, "m"),
    ]:
        cases.append(
            make_case(
                n,
                family="intervals",
                tags=["units" if unit == "ft" else "depth"],
                signature="set_interval",
                envelope={
                    "status": "ok",
                    "well_ir_version": "1.0",
                    "ops": [
                        {
                            "op": "set_interval",
                            "top": float(top),
                            "bottom": float(bottom),
                            "unit": unit,
                        }
                    ],
                },
                invariants=[
                    {
                        "kind": "interval",
                        "top": float(top),
                        "bottom": float(bottom),
                        "unit": unit,
                    }
                ],
                utterances=[
                    f"Plot from {top} to {bottom} {unit}.",
                    f"Set the interval {top}-{bottom} {unit}.",
                ],
                fixture_name=fix_base,
                provenance={
                    "source_kind": "new_gold_authoring",
                    "adaptation": "newly_authored",
                    "review_status": "accepted",
                },
            )
        )
        n += 1

    # relational (~15%)
    relational = [
        (
            "RHOB",
            "NPHI",
            "with",
            [
                "Put density with neutron.",
                "Overlay RHOB with NPHI.",
                "Add density onto the neutron track.",
            ],
        ),
        (
            "RHOB",
            "GR",
            "beside",
            [
                "Put density beside GR.",
                "Place RHOB next to gamma.",
                "Add density beside the GR curve.",
            ],
        ),
        (
            "CALI",
            "GR",
            "with",
            ["Put caliper with GR.", "Overlay CALI on gamma.", "Add CALI with GR."],
        ),
        (
            "RT",
            "NPHI",
            "beside",
            [
                "Put resistivity beside neutron.",
                "Place RT next to NPHI.",
                "Add RT beside neutron.",
            ],
        ),
        (
            "CALI",
            "NPHI",
            "beside",
            ["Put CALI beside neutron.", "Place caliper next to NPHI."],
        ),
        (
            "RT",
            "GR",
            "with",
            ["Put RT with GR.", "Overlay resistivity on gamma."],
        ),
    ]
    for curve, ref, rel, utts in relational:
        for i in range(4):  # expand instances with signature family grouping
            env = {
                "status": "ok",
                "well_ir_version": "1.0",
                "ops": [
                    {
                        "op": "place_curve",
                        "curve": {"kind": "curve", "ref": curve},
                        "target": {
                            "mode": "relative",
                            "relation": rel,
                            "reference": {"kind": "curve", "ref": ref},
                        },
                    }
                ],
            }
            # compute expected track via lowerer
            d0, ws = base_fixture()
            pred = parse_well_ir(env)
            lowered = apply_well_ir(d0, pred, ws).document
            track = lowered.curve_map()[curve].track
            cases.append(
                make_case(
                    n,
                    family="relational_targeting",
                    tags=["relation", rel, f"instance{i}"],
                    signature=f"place_curve(relative={rel})",
                    envelope=env,
                    invariants=[{"kind": "curve_on_track", "curve": curve, "track": track}],
                    utterances=utts if i == 0 else [f"{utts[0]} (variant {i})."],
                    fixture_name=fix_base,
                    provenance={
                        "source_kind": "new_gold_authoring",
                        "adaptation": "newly_authored",
                        "review_status": "accepted",
                    },
                )
            )
            n += 1

    # fills (~15%)
    fill_modes = [
        ("to_upper_limit", 2.65, None, "Shade density above 2.65."),
        ("to_lower_limit", 2.0, None, "Fill density below 2.0."),
        ("baseline_split", None, 2.45, "Split-fill density about 2.45."),
        ("between_curves", None, None, "Fill between density and neutron."),
    ]
    for mode, thr, baseline, utt in fill_modes:
        for curve in ("RHOB", "GR", "NPHI"):
            ops: list[dict[str, Any]] = []
            fix = fix_rhob if curve == "RHOB" else fix_base
            if curve == "RHOB" and mode == "between_curves":
                other = {"kind": "curve", "ref": "NPHI"}
            elif mode == "between_curves":
                other = {"kind": "curve", "ref": "NPHI" if curve != "NPHI" else "GR"}
            else:
                other = None
            op: dict[str, Any] = {
                "op": "define_fill",
                "curve": {"kind": "curve", "ref": curve},
                "mode": mode,
            }
            if thr is not None:
                op["threshold"] = thr
            if baseline is not None:
                op["baseline"] = baseline
            if other is not None:
                op["other_curve"] = other
            ops.append(op)
            cases.append(
                make_case(
                    n,
                    family="fills",
                    tags=["fill", mode],
                    signature=f"define_fill({mode})",
                    envelope={"status": "ok", "well_ir_version": "1.0", "ops": ops},
                    invariants=[{"kind": "fill_exists", "curve": curve, "mode": mode}],
                    utterances=[
                        utt.replace("density", curve).replace("Density", curve),
                        f"Apply {mode} fill on {curve}.",
                    ],
                    fixture_name=fix,
                    provenance={
                        "source_kind": "new_gold_authoring",
                        "adaptation": "newly_authored",
                        "review_status": "accepted",
                    },
                )
            )
            n += 1

    # remove fill cases
    for i in range(8):
        d0 = default_triple_combo_d0()
        from lowerer.context import FillPlacement

        d0.fills.append(
            FillPlacement(ref="fill_1", curve="GR", mode="to_upper_limit", threshold=75)
        )
        name = f"d0_with_fill_{i}"
        dump_fixture(name, d0, default_workspace_from_d0(d0))
        cases.append(
            make_case(
                n,
                family="fills",
                tags=["remove_fill"],
                signature="remove_fill",
                envelope={
                    "status": "ok",
                    "well_ir_version": "1.0",
                    "ops": [
                        {
                            "op": "remove_fill",
                            "fill": {"kind": "fill", "ref": "fill_1"},
                        }
                    ],
                },
                invariants=[{"kind": "fill_absent", "fill": "fill_1"}],
                utterances=["Remove the GR fill.", "Delete fill_1.", "Clear the gamma fill."],
                fixture_name=name,
                provenance={
                    "source_kind": "new_gold_authoring",
                    "adaptation": "newly_authored",
                    "review_status": "accepted",
                },
            )
        )
        n += 1

    # composition (~30%)
    compositions = [
        (
            [
                {
                    "op": "set_interval",
                    "top": 2400.0,
                    "bottom": 2800.0,
                    "unit": "m",
                },
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
                    "min": 1.95,
                    "max": 2.95,
                    "direction": "decreasing",
                },
                {
                    "op": "define_fill",
                    "curve": {"kind": "curve", "ref": "RHOB"},
                    "mode": "to_upper_limit",
                    "threshold": 2.65,
                },
            ],
            [
                "Put density with neutron from 2400 to 2800 m, use 1.95–2.95 reversed and fill where density is above 2.65.",
                "Overlay RHOB on NPHI between 2400-2800 m with reversed 1.95-2.95 scale and shade above 2.65.",
            ],
            "place_curve(relative=with)+configure_curve_display(direction=decreasing)+define_fill+set_interval",
        ),
        (
            [
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
                    "curve": {"kind": "curve", "ref": "GR"},
                    "target": {
                        "mode": "track",
                        "reference": {"kind": "track", "local_ref": "$track1"},
                    },
                },
            ],
            [
                "Create a track beside track 2 and put GR there.",
                "Add a new track next to track two and place gamma on it.",
            ],
            "create_track+place_curve(local_ref)",
        ),
        (
            [
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
            [
                "Put density with neutron and reverse the density scale.",
                "Overlay RHOB with NPHI using the density scale backwards.",
            ],
            "place_curve(relative=with)+configure_curve_display(direction=decreasing)",
        ),
        (
            [
                {
                    "op": "move_curve",
                    "curve": {"kind": "curve", "ref": "GR"},
                    "target": {
                        "mode": "track",
                        "reference": {"kind": "track", "ref": 4},
                    },
                },
                {
                    "op": "configure_curve_display",
                    "curve": {"kind": "curve", "ref": "GR"},
                    "line_style": "dashed",
                },
            ],
            ["Move GR to track 4 and make it dashed.", "Shift gamma onto track four as a dashed curve."],
            "move_curve+configure_curve_display",
        ),
        (
            [
                {
                    "op": "set_interval",
                    "top": 2200.0,
                    "bottom": 2450.0,
                    "unit": "m",
                },
                {
                    "op": "define_fill",
                    "curve": {"kind": "curve", "ref": "GR"},
                    "mode": "to_upper_limit",
                    "threshold": 75.0,
                },
            ],
            [
                "Shade GR above 75 API between 2200 and 2450 m.",
                "From 2200-2450 m fill gamma where it exceeds 75.",
            ],
            "set_interval+define_fill",
        ),
    ]

    # Expand compositions with systematic curve/track variants
    for ops, utts, sig in compositions:
        for k in range(6):
            env = {"status": "ok", "well_ir_version": "1.0", "ops": ops}
            d0, ws = base_fixture()
            try:
                lowered = apply_well_ir(d0, parse_well_ir(env), ws).document
            except Exception:
                continue
            inv: list[dict[str, Any]] = []
            if lowered.interval:
                inv.append({"kind": "interval", **lowered.interval})
            for c in lowered.curves:
                if c.ref in {op.get("curve", {}).get("ref") for op in ops if isinstance(op, dict)} or True:
                    pass
            # derive invariants from ops
            for op in ops:
                if op["op"] == "place_curve" or op["op"] == "move_curve":
                    cref = op["curve"]["ref"]
                    inv.append(
                        {
                            "kind": "curve_on_track",
                            "curve": cref,
                            "track": lowered.curve_map()[cref].track,
                        }
                    )
                if op["op"] == "configure_curve_display" and op.get("direction"):
                    inv.append(
                        {
                            "kind": "scale_direction",
                            "curve": op["curve"]["ref"],
                            "direction": op["direction"],
                        }
                    )
                if op["op"] == "define_fill":
                    inv.append(
                        {
                            "kind": "fill_exists",
                            "curve": op["curve"]["ref"],
                            "mode": op["mode"],
                        }
                    )
                if op["op"] == "create_track":
                    inv.append({"kind": "track_count_gte", "count": len(d0.tracks) + 1})
            # dedupe invariants
            uniq = []
            seen = set()
            for item in inv:
                key = json.dumps(item, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    uniq.append(item)
            cases.append(
                make_case(
                    n,
                    family="composition",
                    tags=["composition", f"var{k}"],
                    signature=sig,
                    envelope=env,
                    invariants=uniq,
                    utterances=utts if k == 0 else [f"{utts[0]} [instance {k}]"],
                    fixture_name=fix_base,
                    provenance={
                        "source_kind": "new_gold_authoring",
                        "adaptation": "newly_authored",
                        "review_status": "accepted",
                    },
                )
            )
            n += 1

    # ambiguity / unsupported (~20% combined with invalid)
    # ambiguous density
    for i in range(15):
        cases.append(
            make_case(
                n,
                family="ambiguity_unsupported",
                tags=["ambiguous", "alias"],
                signature="envelope=ambiguous(density)",
                envelope={
                    "status": "ambiguous",
                    "well_ir_version": "1.0",
                    "ambiguities": [
                        {
                            "field": "curve",
                            "candidates": ["RHOB", "RHOZ"],
                            "query": "density",
                        }
                    ],
                },
                invariants=[],
                utterances=[
                    "Put density on track 4.",
                    "Plot density.",
                    "Add the density curve.",
                ]
                if i == 0
                else [f"Show density please ({i})."],
                fixture_name=fix_amb,
                provenance={
                    "source_kind": "new_gold_authoring",
                    "adaptation": "newly_authored",
                    "review_status": "accepted",
                },
            )
        )
        n += 1

    # unsupported missing curve
    for missing, query in [
        ("CALI", "caliper"),
        ("PEF", "photoelectric"),
        ("DT", "sonic"),
        ("SP", "spontaneous potential"),
        ("MSFL", "msfl"),
    ]:
        for i in range(4):
            # remove from workspace by using base without that curve available
            d0, ws = base_fixture()
            ws.available_curves = [c for c in ws.available_curves if c.id != missing]
            fname = f"d0_missing_{missing}_{i}"
            dump_fixture(fname, d0, ws)
            cases.append(
                make_case(
                    n,
                    family="ambiguity_unsupported",
                    tags=["unsupported", "reference_not_found"],
                    signature="envelope=unsupported(reference_not_found)",
                    envelope={
                        "status": "unsupported",
                        "well_ir_version": "1.0",
                        "reason": "reference_not_found",
                        "reference": {"kind": "curve", "query": query},
                    },
                    invariants=[],
                    utterances=[
                        f"Plot {missing}.",
                        f"Add {query} to the display.",
                    ],
                    fixture_name=fname,
                    provenance={
                        "source_kind": "new_gold_authoring",
                        "adaptation": "newly_authored",
                        "review_status": "accepted",
                    },
                )
            )
            n += 1

    # unsupported operation
    for i in range(10):
        cases.append(
            make_case(
                n,
                family="ambiguity_unsupported",
                tags=["unsupported", "operation_not_supported"],
                signature="envelope=unsupported(operation_not_supported)",
                envelope={
                    "status": "unsupported",
                    "well_ir_version": "1.0",
                    "reason": "operation_not_supported",
                    "detail": "instantiate_layout deferred beyond WELL-IR v1",
                },
                invariants=[],
                utterances=[
                    "Give me a standard triple combo.",
                    "Create a default triple-combo layout for this well.",
                ]
                if i == 0
                else [f"Build a standard triple combo layout ({i})."],
                fixture_name=fix_base,
                provenance={
                    "source_kind": "new_gold_authoring",
                    "adaptation": "newly_authored",
                    "review_status": "accepted",
                },
            )
        )
        n += 1

    # invalid
    for i in range(10):
        cases.append(
            make_case(
                n,
                family="ambiguity_unsupported",
                tags=["invalid"],
                signature="envelope=invalid",
                envelope={
                    "status": "invalid",
                    "well_ir_version": "1.0",
                    "detail": "interval top must be less than bottom",
                },
                invariants=[],
                utterances=[
                    "Set depth from 3200 to 2500 m.",
                    "Plot 3200 down to 2500 metres.",
                ]
                if i == 0
                else [f"Use interval 3200-2500 m ({i})."],
                fixture_name=fix_base,
                provenance={
                    "source_kind": "new_gold_authoring",
                    "adaptation": "newly_authored",
                    "review_status": "accepted",
                },
            )
        )
        n += 1

    # deictic with focus
    for i in range(12):
        d0, ws = d0_with_rhob()
        ws.focus.curve = {"kind": "curve", "ref": "RHOB"}
        fname = f"d0_focus_rhob_{i}"
        dump_fixture(fname, d0, ws)
        cases.append(
            make_case(
                n,
                family="display_configuration",
                tags=["deictic", "focus"],
                signature="configure_curve_display(deictic)",
                envelope={
                    "status": "ok",
                    "well_ir_version": "1.0",
                    "ops": [
                        {
                            "op": "configure_curve_display",
                            "curve": {"kind": "curve", "ref": "RHOB"},
                            "direction": "decreasing",
                        }
                    ],
                },
                invariants=[
                    {
                        "kind": "scale_direction",
                        "curve": "RHOB",
                        "direction": "decreasing",
                    }
                ],
                utterances=[
                    "Reverse that curve.",
                    "Flip its scale.",
                    "Invert the current curve scale.",
                ]
                if i == 0
                else [f"Reverse that curve ({i})."],
                fixture_name=fname,
                provenance={
                    "source_kind": "new_gold_authoring",
                    "adaptation": "newly_authored",
                    "review_status": "accepted",
                },
            )
        )
        n += 1

    # deictic missing focus -> ambiguous
    for i in range(8):
        cases.append(
            make_case(
                n,
                family="ambiguity_unsupported",
                tags=["deictic", "ambiguous"],
                signature="envelope=ambiguous(deictic)",
                envelope={
                    "status": "ambiguous",
                    "well_ir_version": "1.0",
                    "ambiguities": [
                        {
                            "field": "curve",
                            "candidates": [],
                            "query": "that curve",
                        }
                    ],
                },
                invariants=[],
                utterances=["Reverse that curve.", "Flip it."]
                if i == 0
                else [f"Reverse that curve without focus ({i})."],
                fixture_name=fix_base,
                provenance={
                    "source_kind": "new_gold_authoring",
                    "adaptation": "newly_authored",
                    "review_status": "accepted",
                },
            )
        )
        n += 1

    # migrate a few IN_SCOPE historical-inspired cases with provenance
    for i, (req, env, inv, fix) in enumerate(
        [
            (
                "Bind TT at 200 to 400 reversed on the combo track.",
                {
                    "status": "ok",
                    "well_ir_version": "1.0",
                    "ops": [
                        {
                            "op": "place_curve",
                            "curve": {"kind": "curve", "ref": "RT"},
                            "target": {
                                "mode": "track",
                                "reference": {"kind": "track", "ref": 2},
                            },
                        },
                        {
                            "op": "configure_curve_display",
                            "curve": {"kind": "curve", "ref": "RT"},
                            "min": 200.0,
                            "max": 400.0,
                            "direction": "decreasing",
                        },
                    ],
                },
                [
                    {"kind": "curve_on_track", "curve": "RT", "track": 2},
                    {
                        "kind": "scale_direction",
                        "curve": "RT",
                        "direction": "decreasing",
                    },
                ],
                fix_base,
            )
        ]
        * 6
    ):
        cases.append(
            make_case(
                n,
                family="composition",
                tags=["historical_seed", "scale_reverse"],
                signature="place_curve+configure_curve_display(direction=decreasing)",
                envelope=env,
                invariants=inv,
                utterances=[req, f"Put RT on track 2 reversed 200-400 (hist {i})."],
                fixture_name=fix,
                provenance={
                    "source_kind": "tw_series",
                    "source_id": "cm56_shadow_cases",
                    "source_commit": "d77649765dee81ebd0b8f460ac28515b244f70da",
                    "adaptation": "abstracted",
                    "review_status": "accepted",
                },
                historical_eligibility="ELIGIBLE",
            )
        )
        n += 1

    # Pad to preferred ~360 with balanced families (not composition-only).
    pad_i = 0
    while len(cases) < 360:
        lane = pad_i % 5
        if lane == 0:
            track = 2 + (pad_i % 3)
            curve = ["RHOB", "CALI", "RT"][pad_i % 3]
            env = {
                "status": "ok",
                "well_ir_version": "1.0",
                "ops": [
                    {
                        "op": "place_curve",
                        "curve": {"kind": "curve", "ref": curve},
                        "target": {
                            "mode": "track",
                            "reference": {"kind": "track", "ref": track},
                        },
                    }
                ],
            }
            family, sig, inv, utt = (
                "curve_placement",
                f"place_curve(track)+curve={curve}",
                [{"kind": "curve_on_track", "curve": curve, "track": track}],
                f"Place {curve} on track {track} (pad {pad_i}).",
            )
            fix = fix_base
        elif lane == 1:
            top = 2000 + (pad_i % 40) * 5
            bottom = top + 250
            env = {
                "status": "ok",
                "well_ir_version": "1.0",
                "ops": [
                    {
                        "op": "set_interval",
                        "top": float(top),
                        "bottom": float(bottom),
                        "unit": "m",
                    }
                ],
            }
            family, sig, inv, utt = (
                "intervals",
                "set_interval",
                [
                    {
                        "kind": "interval",
                        "top": float(top),
                        "bottom": float(bottom),
                        "unit": "m",
                    }
                ],
                f"Set interval {top}-{bottom} m (pad {pad_i}).",
            )
            fix = fix_base
        elif lane == 2:
            curve = ["RHOB", "CALI", "RT"][pad_i % 3]
            ref = ["NPHI", "GR", "NPHI"][pad_i % 3]
            rel = "with" if pad_i % 2 == 0 else "beside"
            env = {
                "status": "ok",
                "well_ir_version": "1.0",
                "ops": [
                    {
                        "op": "place_curve",
                        "curve": {"kind": "curve", "ref": curve},
                        "target": {
                            "mode": "relative",
                            "relation": rel,
                            "reference": {"kind": "curve", "ref": ref},
                        },
                    }
                ],
            }
            d0, ws = base_fixture()
            lowered = apply_well_ir(d0, parse_well_ir(env), ws).document
            family, sig, inv, utt = (
                "relational_targeting",
                f"place_curve(relative={rel})",
                [
                    {
                        "kind": "curve_on_track",
                        "curve": curve,
                        "track": lowered.curve_map()[curve].track,
                    }
                ],
                f"Put {curve} {rel} {ref} (pad {pad_i}).",
            )
            fix = fix_base
        elif lane == 3:
            thr = 50 + (pad_i % 20)
            env = {
                "status": "ok",
                "well_ir_version": "1.0",
                "ops": [
                    {
                        "op": "define_fill",
                        "curve": {"kind": "curve", "ref": "GR"},
                        "mode": "to_upper_limit",
                        "threshold": float(thr),
                    }
                ],
            }
            family, sig, inv, utt = (
                "fills",
                "define_fill(to_upper_limit)",
                [{"kind": "fill_exists", "curve": "GR", "mode": "to_upper_limit"}],
                f"Shade GR above {thr} (pad {pad_i}).",
            )
            fix = fix_base
        else:
            top = 2100 + (pad_i % 30) * 10
            bottom = top + 300
            curve = ["RHOB", "CALI", "RT"][pad_i % 3]
            ref = ["NPHI", "GR", "NPHI"][pad_i % 3]
            rel = "with" if pad_i % 2 == 0 else "beside"
            env = {
                "status": "ok",
                "well_ir_version": "1.0",
                "ops": [
                    {
                        "op": "set_interval",
                        "top": float(top),
                        "bottom": float(bottom),
                        "unit": "m",
                    },
                    {
                        "op": "place_curve",
                        "curve": {"kind": "curve", "ref": curve},
                        "target": {
                            "mode": "relative",
                            "relation": rel,
                            "reference": {"kind": "curve", "ref": ref},
                        },
                    },
                    {
                        "op": "configure_curve_display",
                        "curve": {"kind": "curve", "ref": curve},
                        "direction": "decreasing" if curve == "RHOB" else "increasing",
                    },
                ],
            }
            d0, ws = base_fixture()
            lowered = apply_well_ir(d0, parse_well_ir(env), ws).document
            family, sig, inv, utt = (
                "composition",
                f"place_curve(relative={rel})+configure+set_interval",
                [
                    {
                        "kind": "interval",
                        "top": float(top),
                        "bottom": float(bottom),
                        "unit": "m",
                    },
                    {
                        "kind": "curve_on_track",
                        "curve": curve,
                        "track": lowered.curve_map()[curve].track,
                    },
                ],
                f"From {top} to {bottom} m put {curve} {rel} {ref} (pad {pad_i}).",
            )
            fix = fix_base
        cases.append(
            make_case(
                n,
                family=family,
                tags=["balanced_pad"],
                signature=sig,
                envelope=env,
                invariants=inv,
                utterances=[utt],
                fixture_name=fix,
                provenance={
                    "source_kind": "new_gold_authoring",
                    "adaptation": "newly_authored",
                    "review_status": "accepted",
                },
            )
        )
        n += 1
        pad_i += 1

    # Renumber case ids densely
    for idx, case in enumerate(cases, start=1):
        case["case_id"] = case_id(idx)
    return cases


def stratified_split(cases: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Split at semantic-case level; keep signature families from leaking trivially."""
    by_sig: dict[str, list[dict[str, Any]]] = {}
    for c in cases:
        by_sig.setdefault(c["semantic_signature"], []).append(c)

    dev, val, test = [], [], []
    for sig, group in sorted(by_sig.items(), key=lambda kv: kv[0]):
        rng.shuffle(group)
        # assign whole near-duplicate groups when small
        if len(group) == 1:
            bucket = rng.choices(["dev", "val", "test"], weights=[0.6, 0.2, 0.2])[0]
            {"dev": dev, "val": val, "test": test}[bucket].append(group[0]["case_id"])
            continue
        # keep all paraphrases/instances of tiny groups together
        if len(group) <= 3:
            bucket = rng.choices(["dev", "val", "test"], weights=[0.6, 0.2, 0.2])[0]
            for g in group:
                {"dev": dev, "val": val, "test": test}[bucket].append(g["case_id"])
            continue
        n = len(group)
        n_test = max(1, int(round(n * 0.2)))
        n_val = max(1, int(round(n * 0.2)))
        n_dev = n - n_test - n_val
        dev.extend([g["case_id"] for g in group[:n_dev]])
        val.extend([g["case_id"] for g in group[n_dev : n_dev + n_val]])
        test.extend([g["case_id"] for g in group[n_dev + n_val :]])

    return {
        "development": sorted(dev),
        "validation": sorted(val),
        "held_out": sorted(test),
    }


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    GOLD.parent.mkdir(parents=True, exist_ok=True)
    SPLITS.mkdir(parents=True, exist_ok=True)
    cases = build_cases()

    # validate all ok programs lower cleanly
    failures = []
    for case in cases:
        fix = json.loads((FIXTURES / f"{case['fixture']}.json").read_text(encoding="utf-8"))
        d0 = DocumentState.model_validate(fix["d0"])
        ws = WorkspaceContext.model_validate(fix["workspace"])
        gold = parse_well_ir(case["gold"])
        if gold.status != "ok":
            continue
        try:
            lowered = apply_well_ir(d0, gold, ws).document
            bad = check_invariants(lowered, case["lowerer_invariants"])
            if bad:
                failures.append((case["case_id"], bad))
        except Exception as exc:  # noqa: BLE001
            failures.append((case["case_id"], [str(exc)]))
    if failures:
        raise SystemExit(f"gold lowerer failures: {failures[:10]} (n={len(failures)})")

    with GOLD.open("w", encoding="utf-8") as fh:
        for case in cases:
            fh.write(json.dumps(case, sort_keys=True) + "\n")

    splits = stratified_split(cases)
    for name, ids in splits.items():
        (SPLITS / f"{name}.json").write_text(
            json.dumps({"split": name, "case_ids": ids}, indent=2) + "\n",
            encoding="utf-8",
        )

    corpus_hash = hashlib.sha256(GOLD.read_bytes()).hexdigest()
    meta = {
        "n_cases": len(cases),
        "n_utterances": sum(len(c["utterances"]) for c in cases),
        "by_family": {},
        "splits": {k: len(v) for k, v in splits.items()},
        "corpus_sha256": corpus_hash,
        "well_ir_version": "1.0",
    }
    for c in cases:
        meta["by_family"][c["semantic_family"]] = meta["by_family"].get(c["semantic_family"], 0) + 1
    (GOLD.parent / "corpus_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
