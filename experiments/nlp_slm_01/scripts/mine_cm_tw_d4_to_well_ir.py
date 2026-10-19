#!/usr/bin/env python3
"""Mine CM/TW/D4 NL and map to WELL-IR v1 candidate SFT rows (SLM-02 dictionary pass).

Does not edit sealed gold/splits/held-out. Emits candidates for human review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HIST_TW = Path("/home/user/projects/wellplot-historical/tests/fixtures/typed_worker")
WELLPLOT = ROOT.parents[1]  # repo root
OUT_DEFAULT = ROOT / "artifacts" / "exports" / "cm_tw_d4_mapped_candidates.jsonl"
SUMMARY_DEFAULT = ROOT / "artifacts" / "exports" / "cm_tw_d4_mapped_summary.json"

WELL_IR_VERSION = "1.0"

# Curve mnemonics commonly seen in CM/D4 that exist in SLM fixtures
KNOWN_CURVES = {
    "gr": "GR",
    "gamma": "GR",
    "gamma ray": "GR",
    "ecgr": "GR",
    "ecgr_stgc": "GR",
    "nphi": "NPHI",
    "neutron": "NPHI",
    "rhob": "RHOB",
    "density": None,  # ambiguous in d0_ambiguous_density
    "bulk density": None,
    "rt": "RT",
    "resistivity": "RT",
    "ild": "RT",
    "cali": "CALI",
    "caliper": "CALI",
    "tens": None,  # not in default workspace → unsupported
    "tension": None,
    "vdl": None,  # outside WELL-IR v1 plot ops
    "cbl": None,
    "dens": "RHOB",
    "pef": None,
    "sp": None,
    "dt": None,
}


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def cand_id(source_kind: str, case_id: str, utterance: str) -> str:
    return f"MAP-{source_kind}-{sha(case_id + '|' + utterance)}"


def envelope_ok(ops: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "ok", "well_ir_version": WELL_IR_VERSION, "ops": ops}


def envelope_ambiguous(field: str, candidates: list[str], query: str) -> dict[str, Any]:
    return {
        "status": "ambiguous",
        "well_ir_version": WELL_IR_VERSION,
        "ambiguities": [{"field": field, "candidates": candidates, "query": query}],
    }


def envelope_unsupported(
    reason: str, *, kind: str | None = None, query: str | None = None, detail: str | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": "unsupported",
        "well_ir_version": WELL_IR_VERSION,
        "reason": reason,
    }
    if kind and query is not None:
        out["reference"] = {"kind": kind, "query": query}
    if detail:
        out["detail"] = detail
    return out


def detect_curve_token(text: str) -> tuple[str | None, str | None]:
    """Return (resolved_ref_or_None, raw_query). None ref means ambiguous or unknown."""
    t = text.lower()
    # Prefer explicit mnemonics
    for pat, ref in [
        (r"\brhob\b", "RHOB"),
        (r"\bnphi\b", "NPHI"),
        (r"\becgr(?:_stgc)?\b", "GR"),
        (r"\bgr\b", "GR"),
        (r"\brt\b", "RT"),
        (r"\bild\b", "RT"),
        (r"\bcali\b", "CALI"),
        (r"\btens\b", None),
        (r"\bvdl\b", None),
        (r"\bcbl\b", None),
        (r"\bpef\b", None),
        (r"\bdens\b", "RHOB"),
    ]:
        if re.search(pat, t):
            return ref, re.search(pat, t).group(0)  # type: ignore[union-attr]
    if "bulk density" in t or re.search(r"\bdensity\b", t):
        return None, "density"
    if "gamma ray" in t or re.search(r"\bgamma\b", t):
        return "GR", "gamma"
    if "neutron" in t:
        return "NPHI", "neutron"
    if "resistivity" in t:
        return "RT", "resistivity"
    if "caliper" in t:
        return "CALI", "caliper"
    if "tension" in t:
        return None, "tension"
    return None, None


def parse_scale(text: str) -> tuple[float | None, float | None, str | None]:
    """Extract min/max and optional direction from phrases like '0 to 150' or '200 to 0'."""
    t = text.lower().replace("–", "-").replace("—", "-")
    m = re.search(
        r"(?:from|range|scale|spanning|linear|logarithmically)?\s*"
        r"(-?\d+(?:\.\d+)?)\s*(?:to|–|-)\s*(-?\d+(?:\.\d+)?)",
        t,
    )
    if not m:
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*[-–]\s*(-?\d+(?:\.\d+)?)", t)
    if not m:
        return None, None, None
    a, b = float(m.group(1)), float(m.group(2))
    direction = None
    if "reverse" in t or b < a:
        direction = "decreasing"
    elif b > a:
        direction = "increasing"
    return a, b, direction


def is_report_only(text: str, family: str | None) -> bool:
    if family == "REPORT_ONLY":
        return True
    t = text.lower()
    report_markers = [
        "handover brief",
        "report cover",
        "prepared-by",
        "preparer",
        "subtitle",
        "disposition:",
        "interpretation packet",
        "field-review packet",
        "rename this report",
        "credit the",
    ]
    return any(m in t for m in report_markers)


def is_cbl_construct(text: str) -> bool:
    t = text.lower()
    return any(
        x in t
        for x in [
            "cbl_main",
            "cbl_repeat",
            "cased-hole",
            "variable density log",
            "cement bond",
            "main_pass",
            "repeat_pass",
            "vdl raster",
            "array track",
            "two new log plot sections",
            "main pass from the main source",
        ]
    )


def map_cm_case(source_path: str, case: dict[str, Any]) -> list[dict[str, Any]]:
    req = (case.get("request") or "").strip()
    case_id = str(case.get("case_id") or "unknown")
    family = case.get("family")
    rows: list[dict[str, Any]] = []

    def reject(reason: str) -> None:
        rows.append(
            {
                "candidate_id": cand_id("cm", case_id, req),
                "decision": "reject",
                "reject_reason": reason,
                "source": {
                    "kind": "cm",
                    "path": source_path,
                    "case_id": case_id,
                    "family": family,
                },
                "utterance": req,
                "semantic_family": None,
                "fixture": None,
                "gold": None,
                "map_rationale": reason,
                "split_hint": None,
            }
        )

    if not req:
        reject("empty_request")
        return rows

    if is_report_only(req, family if isinstance(family, str) else None):
        rows.append(
            _admit(
                source_kind="cm",
                source_path=source_path,
                case_id=case_id,
                utterance=req,
                semantic_family="ambiguity_unsupported",
                fixture="d0_base",
                gold=envelope_unsupported(
                    "operation_not_supported",
                    detail="report_metadata_outside_well_ir_v1",
                ),
                rationale="CM report/handover metadata → unsupported operation_not_supported",
                tags=["unsupported", "operation_not_supported", "mined_cm_report"],
            )
        )
        return rows

    if is_cbl_construct(req) or "array track" in req.lower() or "vdl" in req.lower():
        rows.append(
            _admit(
                source_kind="cm",
                source_path=source_path,
                case_id=case_id,
                utterance=req,
                semantic_family="ambiguity_unsupported",
                fixture="d0_base",
                gold=envelope_unsupported(
                    "operation_not_supported",
                    detail="cbl_vdl_or_multi_section_construct",
                ),
                rationale="CBL/VDL/multi-section construct outside WELL-IR v1 ops",
                tags=["unsupported", "operation_not_supported", "mined_cm_cbl"],
            )
        )
        return rows

    curve_ref, curve_q = detect_curve_token(req)
    amin, amax, direction = parse_scale(req)
    t = req.lower()
    creates_track = bool(
        re.search(r"\b(create|build|add)\b.*\btrack\b", t)
        or re.search(r"\bnew normal track\b", t)
        or re.search(r"\bnormal track (titled|named|called)\b", t)
    )
    bindish = bool(re.search(r"\b(bind|plot|show|display|place)\b", t))

    # Unknown / missing curve in default workspace
    if curve_q in {"tens", "tension", "pef", "sp", "dt", "vdl", "cbl"} or (
        curve_ref is None and curve_q not in {None, "density"}
    ):
        rows.append(
            _admit(
                source_kind="cm",
                source_path=source_path,
                case_id=case_id,
                utterance=req,
                semantic_family="ambiguity_unsupported",
                fixture="d0_base",
                gold=envelope_unsupported(
                    "reference_not_found",
                    kind="curve",
                    query=curve_q or "unknown",
                ),
                rationale=f"curve query '{curve_q}' not in default SLM workspace → unsupported",
                tags=["unsupported", "reference_not_found", "mined_cm"],
            )
        )
        return rows

    # Ambiguous density wording
    if curve_ref is None and curve_q == "density":
        rows.append(
            _admit(
                source_kind="cm",
                source_path=source_path,
                case_id=case_id,
                utterance=req,
                semantic_family="ambiguity_unsupported",
                fixture="d0_ambiguous_density",
                gold=envelope_ambiguous("curve", ["RHOB", "RHOZ"], "density"),
                rationale="density alias with RHOB/RHOZ available → ambiguous",
                tags=["ambiguous", "alias", "mined_cm"],
            )
        )
        return rows

    if curve_ref and creates_track and bindish:
        ops: list[dict[str, Any]] = [
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
                "curve": {"kind": "curve", "ref": curve_ref},
                "target": {
                    "mode": "track",
                    "reference": {"kind": "track", "local_ref": "$track1"},
                },
            },
        ]
        if amin is not None and amax is not None:
            cfg: dict[str, Any] = {
                "op": "configure_curve_display",
                "curve": {"kind": "curve", "ref": curve_ref},
                "min": amin,
                "max": amax,
            }
            if direction:
                cfg["direction"] = direction
            ops.append(cfg)
        rows.append(
            _admit(
                source_kind="cm",
                source_path=source_path,
                case_id=case_id,
                utterance=req,
                semantic_family="composition",
                fixture="d0_base",
                gold=envelope_ok(ops),
                rationale="CM create-track+bind → create_track+place_curve(+configure)",
                tags=["composition", "mined_cm_track_bind"],
            )
        )
        return rows

    if curve_ref and bindish and amin is not None and amax is not None and not creates_track:
        # Display-only style if curve already typically present (GR/NPHI) else place+configure
        if curve_ref in {"GR", "NPHI"}:
            cfg = {
                "op": "configure_curve_display",
                "curve": {"kind": "curve", "ref": curve_ref},
                "min": amin,
                "max": amax,
            }
            if direction:
                cfg["direction"] = direction
            rows.append(
                _admit(
                    source_kind="cm",
                    source_path=source_path,
                    case_id=case_id,
                    utterance=req,
                    semantic_family="display_configuration",
                    fixture="d0_base",
                    gold=envelope_ok([cfg]),
                    rationale="CM scale/bind on existing curve → configure_curve_display",
                    tags=["display", "mined_cm_scale"],
                )
            )
        else:
            ops = [
                {
                    "op": "place_curve",
                    "curve": {"kind": "curve", "ref": curve_ref},
                    "target": {
                        "mode": "track",
                        "reference": {"kind": "track", "ref": 4},
                    },
                },
                {
                    "op": "configure_curve_display",
                    "curve": {"kind": "curve", "ref": curve_ref},
                    "min": amin,
                    "max": amax,
                },
            ]
            if direction:
                ops[1]["direction"] = direction
            rows.append(
                _admit(
                    source_kind="cm",
                    source_path=source_path,
                    case_id=case_id,
                    utterance=req,
                    semantic_family="composition",
                    fixture="d0_base",
                    gold=envelope_ok(ops),
                    rationale="CM place+scale → place_curve+configure_curve_display",
                    tags=["composition", "mined_cm_place_scale"],
                )
            )
        return rows

    reject("no_confident_well_ir_mapping")
    return rows


def map_d4_case(case: dict[str, Any]) -> list[dict[str, Any]]:
    req = (case.get("request") or "").strip()
    case_id = str(case.get("case_id") or case.get("turn_id") or "unknown")
    outcome = case.get("expected_outcome")
    path = "tests/fixtures/nlp_d4_live_cases.json"
    rows: list[dict[str, Any]] = []

    if not req:
        return rows

    if is_cbl_construct(req) or outcome == "DIRECT_CORRECT" and "finish the supported" in req.lower():
        rows.append(
            _admit(
                source_kind="d4",
                source_path=path,
                case_id=case_id,
                utterance=req,
                semantic_family="ambiguity_unsupported",
                fixture="d0_base",
                gold=envelope_unsupported(
                    "operation_not_supported",
                    detail="d4_cbl_construct_or_report_scaffold",
                ),
                rationale="D4 CBL construct / scaffold finish → unsupported",
                tags=["unsupported", "operation_not_supported", "mined_d4"],
            )
        )
        return rows

    if "rename this report" in req.lower():
        rows.append(
            _admit(
                source_kind="d4",
                source_path=path,
                case_id=case_id,
                utterance=req,
                semantic_family="ambiguity_unsupported",
                fixture="d0_base",
                gold=envelope_unsupported(
                    "operation_not_supported", detail="report_rename"
                ),
                rationale="D4 report rename → unsupported",
                tags=["unsupported", "operation_not_supported", "mined_d4"],
            )
        )
        return rows

    # Missing data / alias failure → unsupported reference
    if outcome in {"SAFE_ACTIONABLE_FAILURE"} and (
        "missing_" in req.lower() or "alias" in req.lower() or "not found" in req.lower()
    ):
        curve_ref, curve_q = detect_curve_token(req)
        rows.append(
            _admit(
                source_kind="d4",
                source_path=path,
                case_id=case_id,
                utterance=req,
                semantic_family="ambiguity_unsupported",
                fixture="d0_base",
                gold=envelope_unsupported(
                    "reference_not_found",
                    kind="curve",
                    query=curve_q or "missing_source",
                ),
                rationale="D4 safe failure on missing/alias source → unsupported reference_not_found",
                tags=["unsupported", "reference_not_found", "mined_d4"],
            )
        )
        return rows

    # Clarification / which section → ambiguous targeting
    if outcome == "CORRECT_AFTER_CLARIFICATION" or "only to" in req.lower() and "upper" in req.lower():
        rows.append(
            _admit(
                source_kind="d4",
                source_path=path,
                case_id=case_id,
                utterance=req.split("Apply that")[0].strip()
                if "Apply that" in req
                else req,
                semantic_family="ambiguity_unsupported",
                fixture="d0_base",
                gold=envelope_ambiguous(
                    "target",
                    ["Main Log", "Main Log – Upper"],
                    "which section",
                ),
                rationale="D4 multi-section targeting needs clarification → ambiguous",
                tags=["ambiguous", "deictic", "mined_d4"],
            )
        )
        # Also admit the clarified follow-up as composition/display when scale present
        if "20" in req and "110" in req and "gamma" in req.lower():
            rows.append(
                _admit(
                    source_kind="d4",
                    source_path=path,
                    case_id=case_id + ":clarified",
                    utterance=req,
                    semantic_family="display_configuration",
                    fixture="d0_base",
                    gold=envelope_ok(
                        [
                            {
                                "op": "configure_curve_display",
                                "curve": {"kind": "curve", "ref": "GR"},
                                "min": 20.0,
                                "max": 110.0,
                                "direction": "increasing",
                            }
                        ]
                    ),
                    rationale="D4 clarified GR scale change → configure_curve_display",
                    tags=["display", "mined_d4_clarified"],
                )
            )
        return rows

    curve_ref, curve_q = detect_curve_token(req)
    amin, amax, direction = parse_scale(req)
    t = req.lower()

    if "fill" in t and curve_ref:
        mode = "to_lower_limit" if "lower" in t else "to_upper_limit"
        rows.append(
            _admit(
                source_kind="d4",
                source_path=path,
                case_id=case_id,
                utterance=req,
                semantic_family="fills",
                fixture="d0_base",
                gold=envelope_ok(
                    [
                        {
                            "op": "define_fill",
                            "curve": {"kind": "curve", "ref": curve_ref},
                            "mode": mode,
                        }
                    ]
                ),
                rationale="D4 fill-to-boundary → define_fill",
                tags=["fills", "mined_d4"],
            )
        )
        return rows

    if re.search(r"\b(append|add)\b.*\btrack\b", t) and curve_ref:
        ops: list[dict[str, Any]] = [
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
                "curve": {"kind": "curve", "ref": curve_ref},
                "target": {
                    "mode": "track",
                    "reference": {"kind": "track", "local_ref": "$track1"},
                },
            },
        ]
        if amin is not None and amax is not None:
            cfg: dict[str, Any] = {
                "op": "configure_curve_display",
                "curve": {"kind": "curve", "ref": curve_ref},
                "min": amin,
                "max": amax,
            }
            if direction:
                cfg["direction"] = direction
            ops.append(cfg)
        rows.append(
            _admit(
                source_kind="d4",
                source_path=path,
                case_id=case_id,
                utterance=req,
                semantic_family="composition",
                fixture="d0_base",
                gold=envelope_ok(ops),
                rationale="D4 append track + plot → create_track+place_curve(+configure)",
                tags=["composition", "mined_d4"],
            )
        )
        return rows

    if curve_ref and amin is not None and amax is not None:
        cfg = {
            "op": "configure_curve_display",
            "curve": {"kind": "curve", "ref": curve_ref},
            "min": amin,
            "max": amax,
        }
        if direction:
            cfg["direction"] = direction
        rows.append(
            _admit(
                source_kind="d4",
                source_path=path,
                case_id=case_id,
                utterance=req,
                semantic_family="display_configuration",
                fixture="d0_base",
                gold=envelope_ok([cfg]),
                rationale="D4 curve scale change → configure_curve_display",
                tags=["display", "mined_d4"],
            )
        )
        return rows

    rows.append(
        {
            "candidate_id": cand_id("d4", case_id, req),
            "decision": "reject",
            "reject_reason": "no_confident_well_ir_mapping",
            "source": {"kind": "d4", "path": path, "case_id": case_id, "outcome": outcome},
            "utterance": req,
            "semantic_family": None,
            "fixture": None,
            "gold": None,
            "map_rationale": "no_confident_well_ir_mapping",
            "split_hint": None,
        }
    )
    return rows


def map_tw_stub(path: Path) -> list[dict[str, Any]]:
    """TW corpora are CBL worker projections; admit one unsupported exemplar per corpus."""
    rel = str(path.relative_to(HIST_TW)) if path.is_relative_to(HIST_TW) else str(path)
    utt = (
        "Using main and repeat CBL passes, finish the supported cased-hole CBL/VDL report "
        "with main_pass and repeat_pass sections."
    )
    return [
        _admit(
            source_kind="tw",
            source_path=rel,
            case_id=path.parent.name,
            utterance=utt,
            semantic_family="ambiguity_unsupported",
            fixture="d0_base",
            gold=envelope_unsupported(
                "operation_not_supported",
                detail="tw_cbl_worker_projection",
            ),
            rationale="TW CBL golden/projection corpus → unsupported (not WELL-IR plot delta)",
            tags=["unsupported", "operation_not_supported", "mined_tw"],
        )
    ]


def _composition_ops(
    curve: str, amin: float | None, amax: float | None, direction: str | None
) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = [
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
            "curve": {"kind": "curve", "ref": curve},
            "target": {
                "mode": "track",
                "reference": {"kind": "track", "local_ref": "$track1"},
            },
        },
    ]
    if amin is not None and amax is not None:
        cfg: dict[str, Any] = {
            "op": "configure_curve_display",
            "curve": {"kind": "curve", "ref": curve},
            "min": amin,
            "max": amax,
        }
        if direction:
            cfg["direction"] = direction
        ops.append(cfg)
    return ops


def expand_composition_paraphrases() -> list[dict[str, Any]]:
    """Second-pass controlled CM-style NL over frozen composition gold ops (~40–60 admits)."""
    # (curve, title, amin, amax, direction, scale_phrase)
    specs: list[tuple[str, str, float, float, str | None, str]] = [
        ("GR", "Gamma Ray", 0.0, 150.0, "increasing", "linear scale from 0 to 150"),
        ("GR", "Natural Gamma", -5.0, 125.0, "increasing", "linear scale from -5 to 125"),
        ("GR", "Gamma Check", 15.0, 165.0, "increasing", "scale from 15 to 165"),
        ("GR", "Selected Gamma Ray", 0.0, 150.0, "increasing", "linear scale from 0 to 150"),
        ("GR", "Petrophysics GR", -10.0, 140.0, "increasing", "linearly from -10 to 140"),
        ("RT", "Resistivity", 200.0, 0.0, "decreasing", "linear scale from 200 to 0"),
        ("RT", "Deep Resistivity", 0.2, 2000.0, "increasing", "logarithmic scale from 0.2 to 2000"),
        ("RT", "Resistivity Reverse", 350.0, 25.0, "decreasing", "from 350 down to 25"),
        ("RT", "Resistivity QC", 0.2, 2000.0, "increasing", "logarithmic 0.2 to 2000"),
        ("RT", "Resistivity Panel", 0.2, 2000.0, "increasing", "log scale 0.2–2000"),
        ("RHOB", "Density", 1.65, 2.65, "increasing", "linear scale from 1.65 to 2.65"),
        ("RHOB", "Bulk Density", 1.95, 2.95, "increasing", "scale from 1.95 to 2.95"),
        ("RHOB", "Density QC", 1.0, 3.0, "increasing", "linear scale from 1 to 3"),
        ("NPHI", "Neutron", 0.45, -0.15, "decreasing", "linear scale from 0.45 to -0.15"),
        ("NPHI", "Neutron Porosity", 0.6, 0.0, "decreasing", "scale from 0.6 to 0"),
        ("CALI", "Caliper", 6.0, 16.0, "increasing", "linear scale from 6 to 16"),
        ("CALI", "Caliper QC", 4.0, 20.0, "increasing", "scale from 4 to 20"),
    ]

    # Three templates × 17 specs ≈ 51 admits (within ~40–60 aim)
    templates = [
        (
            "Create one new normal track titled {title} from the scalar source. "
            "Bind {curve} with a {scale}."
        ),
        (
            "Create one section with a normal track named {title} from the curve pack. "
            "Display {curve} with a {scale}."
        ),
        (
            "Build a single normal track called {title}. "
            "Plot {curve} on that track with a {scale}."
        ),
    ]

    rows: list[dict[str, Any]] = []
    for i, (curve, title, amin, amax, direction, scale) in enumerate(specs):
        ops = _composition_ops(curve, amin, amax, direction)
        gold = envelope_ok(ops)
        for j, tmpl in enumerate(templates):
            utt = tmpl.format(title=title, curve=curve, scale=scale)
            # Slight CM-style secondary-source variant for GR Selected only
            if title == "Selected Gamma Ray" and j == 0:
                utt = (
                    f"Create one new normal track titled {title} using the secondary source, "
                    f"not the primary source. Bind {curve} with a {scale}."
                )
            if title == "Resistivity Reverse" and j == 2:
                utt = (
                    f"Create a normal {title} track from the curve pack. "
                    f"Bind {curve} {scale} and enable reverse direction."
                )
            case_id = f"comp_para_{curve.lower()}_{i}_{j}"
            rows.append(
                _admit(
                    source_kind="para",
                    source_path="scripts/mine_cm_tw_d4_to_well_ir.py#expand_composition_paraphrases",
                    case_id=case_id,
                    utterance=utt,
                    semantic_family="composition",
                    fixture="d0_base",
                    gold=gold,
                    rationale=(
                        "Controlled CM-style paraphrase of admitted composition pattern "
                        f"(create_track+place_curve+configure; curve={curve})"
                    ),
                    tags=["composition", "controlled_paraphrase", f"curve_{curve}"],
                )
            )
    return rows


def _admit(
    *,
    source_kind: str,
    source_path: str,
    case_id: str,
    utterance: str,
    semantic_family: str,
    fixture: str,
    gold: dict[str, Any],
    rationale: str,
    tags: list[str],
) -> dict[str, Any]:
    return {
        "candidate_id": cand_id(source_kind, case_id, utterance),
        "decision": "admit",
        "reject_reason": None,
        "source": {"kind": source_kind, "path": source_path, "case_id": case_id},
        "utterance": utterance,
        "semantic_family": semantic_family,
        "fixture": fixture,
        "gold": gold,
        "map_rationale": rationale,
        "semantic_tags": tags,
        "split_hint": None,  # assigned later
    }


def load_d4_cases() -> list[dict[str, Any]]:
    try:
        raw = subprocess.check_output(
            [
                "git",
                "show",
                "origin/implementation/nlp-d4r1-semantic-worker-convergence:tests/fixtures/nlp_d4_live_cases.json",
            ],
            cwd=str(WELLPLOT),
        )
        return json.loads(raw).get("cases", [])
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: could not load D4 cases: {exc}")
        return []


def assign_split_hints(admits: list[dict[str, Any]]) -> None:
    """Prefer ambiguity/composition; aim ~80–120 development / ~20–30 validation."""
    admits.sort(key=lambda r: r["candidate_id"])
    amb = [r for r in admits if r["semantic_family"] == "ambiguity_unsupported"]
    comp = [r for r in admits if r["semantic_family"] == "composition"]
    other = [
        r
        for r in admits
        if r["semantic_family"] not in {"ambiguity_unsupported", "composition"}
    ]

    # Global val budget ~25; fill validation first within each priority family, rest → development
    val_budget = 25
    for bucket, val_share in ((amb, 12), (comp, 10), (other, 3)):
        n_val = min(val_share, val_budget, max(1, len(bucket) // 5) if bucket else 0)
        # Cap val so remaining can still feed development toward 80–120
        n_val = min(n_val, len(bucket))
        val_budget -= n_val
        for i, r in enumerate(bucket):
            if i < n_val:
                r["split_hint"] = "validation"
            else:
                r["split_hint"] = "development"


def ensure_d0_base_fixture() -> None:
    """Alias fixture name used in candidates → reuse default triple-combo fixture file."""
    fixtures = ROOT / "benchmark" / "fixtures"
    # Prefer an existing base-like fixture
    src = fixtures / "d0_with_rhob.json"
    # Actually composition create_track uses tracks without requiring RHOB; use first gold fixture pattern
    # Write d0_base from generate_gold default if missing
    dest = fixtures / "d0_base.json"
    if dest.exists():
        return
    # Build from lowerer defaults if importable
    import sys

    sys.path.insert(0, str(ROOT))
    from lowerer.context import default_triple_combo_d0, default_workspace_from_d0

    d0 = default_triple_combo_d0()
    ws = default_workspace_from_d0(d0)
    dest.write_text(
        json.dumps(
            {"d0": d0.model_dump(mode="json"), "workspace": ws.model_dump(mode="json")},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    # silence unused
    _ = src


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--summary", type=Path, default=SUMMARY_DEFAULT)
    args = parser.parse_args()

    ensure_d0_base_fixture()
    all_rows: list[dict[str, Any]] = []

    # CM
    if HIST_TW.is_dir():
        for path in sorted(HIST_TW.glob("cm*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            rel = f"wellplot-historical/tests/fixtures/typed_worker/{path.name}"
            for case in data.get("cases", []):
                all_rows.extend(map_cm_case(rel, case))
        # TW stubs
        for path in [
            HIST_TW / "exp_tw00_cbl" / "corpus.json",
            HIST_TW / "exp_tw01_cbl" / "golden_drafts.json",
            HIST_TW / "exp_tw02r_cbl" / "golden_drafts.json",
        ]:
            if path.exists():
                all_rows.extend(map_tw_stub(path))
    else:
        print(f"WARN: historical TW path missing: {HIST_TW}")

    # D4
    for case in load_d4_cases():
        all_rows.extend(map_d4_case(case))

    # Second pass: controlled composition paraphrases (CM-style NL, same gold ops)
    all_rows.extend(expand_composition_paraphrases())

    # Deduplicate by utterance+gold status signature
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for r in all_rows:
        key = sha(
            (r.get("utterance") or "")
            + "|"
            + json.dumps(r.get("gold"), sort_keys=True, default=str)
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    admits = [r for r in deduped if r["decision"] == "admit"]
    rejects = [r for r in deduped if r["decision"] == "reject"]
    assign_split_hints(admits)

    # Enrich rejects already in deduped with no split
    by_id = {r["candidate_id"]: r for r in admits}
    final_rows = []
    for r in deduped:
        if r["decision"] == "admit":
            final_rows.append(by_id[r["candidate_id"]])
        else:
            final_rows.append(r)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for r in final_rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")

    fam_counts = Counter(r["semantic_family"] for r in admits)
    split_counts = Counter(r.get("split_hint") for r in admits)
    source_counts = Counter(r["source"]["kind"] for r in admits)
    summary = {
        "n_total_rows": len(final_rows),
        "n_admit": len(admits),
        "n_reject": len(rejects),
        "admit_by_family": dict(fam_counts),
        "admit_by_split_hint": dict(split_counts),
        "admit_by_source": dict(source_counts),
        "targets": {
            "development_new_rows_aim": "80-120",
            "validation_new_rows_aim": "20-30",
            "priority_families": ["ambiguity_unsupported", "composition"],
        },
        "out": str(args.out),
        "notes": [
            "Held-out untouched.",
            "Candidates are mapped proposals; review before merging into gold/SFT v2.",
            "Fixture d0_base created if missing; d0_ambiguous_density reused for density alias.",
            "CM report/CBL/VDL mapped to unsupported; track+bind to composition.",
            "Second pass: controlled composition paraphrases (source=para) over frozen ops.",
        ],
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
