"""Deterministic canonical semantic responses for provider-free D4 tests."""

from __future__ import annotations

from typing import Any

from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan

_CBL_GENERAL_VALUES = {
    "company": "University of Utah",
    "well": "FORGE 16B (78)-32",
    "field": "Utah Forge",
    "county": "Beaver",
    "country": "Utah",
    "section": "NWSW 32",
    "township": "26",
    "range": "9",
    "footage": "972' FSL & 523' FWL",
    "latitude": "38.501242",
    "longitude": "-112.882661",
    "logging_date": "08-May-2023",
    "measured_from": "Kelly Bushing",
    "log_measured_from": "Kelly Bushing",
    "elevation_kb": "5445.50 ft",
    "elevation_gl": "5415.00 ft",
    "elevation_df": "5445.00 ft",
    "top_log_interval": "25.00 ft",
    "bottom_log_interval": "4845.00 ft",
    "service_company": "Halliburton",
    "run_number": "ONE",
    "fluid_type": "Fresh Water",
}

_CBL_DETAIL_VALUES = {
    "detail.row_2.column_1.cell_1": "ONE",
    "detail.row_4.column_1.cell_1": "4980.00 ft",
    "detail.row_5.column_1.cell_1": "TD Not Tag",
    "detail.row_12.value_1": "8.4 lbm/gal",
    "detail.row_19.column_1.cell_1": "177.2 degF",
    "detail.row_23.value_1": "D. May / D. Jones",
    "detail.row_24.value_1": "Leroy Swearingen",
}


def _scale(
    minimum: float, maximum: float, *, kind: str = "linear", reverse: bool = False
) -> dict[str, object]:
    """Build one canonical worker-owned scale mapping."""
    return {
        "kind": kind,
        "minimum": minimum,
        "maximum": maximum,
        "reverse": reverse,
    }


def _curve(
    semantic_id: str,
    channel: str,
    label: str,
    scale: dict[str, object],
    *,
    color: str,
    line_style: str,
    alpha: float,
) -> dict[str, object]:
    """Build one canonical scalar binding mapping."""
    return {
        "kind": "curve",
        "semantic_id": semantic_id,
        "channel": channel,
        "label": label,
        "scale": scale,
        "style": {
            "color": color,
            "line_style": line_style,
            "line_width": alpha,
            "alpha": alpha,
        },
    }


def _cbl_section_response(*, source_candidate: str, title: str) -> dict[str, object]:
    """Build the frozen CBL section as a canonical reconstruct action."""
    combo = {
        "semantic_id": "combo",
        "kind": "normal",
        "title": "Combo",
        "width_mm": 50,
        "bindings": [
            _curve(
                "ecgr",
                "ECGR_STGC",
                "Gamma Ray (ECGR_STGC) QTGC-B",
                _scale(0, 150),
                color="#16a34a",
                line_style="solid",
                alpha=0.8,
            ),
            _curve(
                "tt",
                "TT",
                "Transit Time for CBL (TT) QSLT-B",
                _scale(200, 400, reverse=True),
                color="#2142ff",
                line_style="solid",
                alpha=0.75,
            ),
            _curve(
                "tens",
                "TENS",
                "Cable Tension (TENS)",
                _scale(5000, 0),
                color="#111111",
                line_style="dashed",
                alpha=0.65,
            ),
            _curve(
                "mtem",
                "MTEM",
                "Mud Temperature (MTEM) LEH-MT",
                _scale(100, 500),
                color="#111111",
                line_style="solid",
                alpha=0.9,
            ),
        ],
    }
    depth = {
        "semantic_id": "depth",
        "kind": "reference",
        "title": "Depth",
        "width_mm": 10,
        "bindings": [
            _curve(
                "stit",
                "STIT",
                "Stuck Tool Indicator, Total (STIT)",
                _scale(0, 50),
                color="#111111",
                line_style="solid",
                alpha=0.65,
            ),
            _curve(
                "tdsp",
                "TDSP",
                "Cable Drag",
                _scale(0, 50),
                color="#92400e",
                line_style="dotted",
                alpha=0.65,
            ),
            _curve(
                "vsec",
                "VSEC",
                "Tool_Tot. Drag",
                _scale(0, 50),
                color="#1d4ed8",
                line_style="dashed",
                alpha=0.65,
            ),
        ],
    }
    cbl = {
        "semantic_id": "cbl",
        "kind": "normal",
        "title": "CBL",
        "width_mm": 44,
        "bindings": [
            _curve(
                "cbl-wide",
                "CBL",
                "CBL Amplitude (CBL) QSLT-B",
                _scale(0, 100),
                color="#111111",
                line_style="solid",
                alpha=0.75,
            ),
            _curve(
                "cbl-narrow",
                "CBL",
                "CBL Amplitude (CBL) QSLT-B",
                _scale(0, 10),
                color="#2563eb",
                line_style="dashed",
                alpha=0.65,
            ),
        ],
    }
    vdl = {
        "semantic_id": "vdl",
        "kind": "array",
        "title": "VDL",
        "width_mm": 48,
        "x_scale": _scale(200, 1200),
        "grid": {
            "vertical_main_visible": False,
            "vertical_secondary_visible": False,
        },
        "bindings": [
            {
                "kind": "raster",
                "semantic_id": "vdl",
                "channel": "VDL",
                "label": "VDL VariableDensity (VDL) QSLT-B",
                "profile": "vdl",
                "colormap": "gray_r",
                "colorbar_enabled": True,
                "colorbar_label": "Amplitude",
                "colorbar_position": "header",
                "sample_axis": {
                    "unit": "us",
                    "minimum": 200,
                    "maximum": 1200,
                    "tick_count": 7,
                    "source_origin": 40,
                    "source_step": 10,
                },
            }
        ],
    }
    return {
        "action": "reconstruct",
        "section": {
            "title": title,
            "source_candidate": source_candidate,
            "tracks": [combo, depth, cbl, vdl],
        },
    }


def _cbl_report_response(payload: dict[str, Any]) -> dict[str, object]:
    """Build the CBL report fragment from host-advertised slots."""
    general_fields: list[dict[str, object]] = []
    detail_fields: list[dict[str, object]] = []
    service_titles: list[dict[str, object]] = []
    for slot in payload["report_context"]["header_slots"]:
        slot_id = str(slot["slot_id"])
        key = slot.get("key")
        if slot_id.startswith("general.") and key in _CBL_GENERAL_VALUES:
            general_fields.append({"slot_id": slot_id, "value": _CBL_GENERAL_VALUES[key]})
        elif slot_id.startswith("detail.") and slot_id in _CBL_DETAIL_VALUES:
            detail_fields.append({"slot_id": slot_id, "value": _CBL_DETAIL_VALUES[slot_id]})
        elif slot_id.startswith("service_title."):
            service_titles.append(
                {
                    "slot_id": slot_id,
                    "value": ("Cement Bond Log", "Variable Density Log", "Gamma Ray - CCL")[
                        len(service_titles)
                    ],
                }
            )
    return {
        "general_fields": general_fields,
        "service_titles": service_titles,
        "detail_fields": detail_fields,
        "remarks": [
            {
                "semantic_id": "scope",
                "title": "Supported Reconstruction Scope",
                "lines": [
                    "Reconstruct only the supported heading, remarks, main pass, "
                    "repeat pass, and tail."
                ],
            },
            {
                "semantic_id": "sources",
                "title": "Data Sources",
                "lines": ["This packet uses staged DLIS files."],
            },
            {
                "semantic_id": "notice",
                "title": "Public Data and IP Notice",
                "lines": ["Rendered by wellplot for educational use."],
            },
        ],
    }


def _plan_for(request: str) -> SemanticPlan:
    """Return deterministic planner output for one frozen D4 request."""
    if request.startswith("Using CBL_Main.dlis"):
        capabilities = (
            "section.log_plot",
            "track.normal",
            "track.reference",
            "track.array",
            "binding.curve",
            "binding.raster",
        )
        return SemanticPlan(
            summary="Reconstruct the bounded CBL packet.",
            report_task=ReportTask(
                goal="Populate the supported CBL report metadata.",
                capability_ids=("report.standard",),
                requirements=(request,),
            ),
            section_tasks=(
                SectionTask(
                    goal="Reconstruct the main CBL pass.",
                    capability_ids=capabilities,
                    existing_section_hint="Main Pass",
                    source_hints=("CBL_Main.dlis",),
                    requirements=(request,),
                ),
                SectionTask(
                    goal="Reconstruct the repeat CBL pass.",
                    capability_ids=capabilities,
                    existing_section_hint="Repeat Pass",
                    source_hints=("CBL_Repeat.dlis",),
                    requirements=(request,),
                ),
            ),
        )
    if request.startswith("Rename this report"):
        return SemanticPlan(
            summary="Rename the report.",
            report_task=ReportTask(
                goal="Rename the report.",
                capability_ids=("report.standard",),
                requirements=(request,),
            ),
        )
    section_hint = "Main Log – Upper" if "Main Log – Upper" in request else "Main Log"
    source_hints = ("missing_neutron.las",) if "missing_neutron.las" in request else ()
    capabilities = ["section.log_plot", "track.normal", "binding.curve"]
    if "fill from" in request:
        capabilities.append("fill.curve")
    return SemanticPlan(
        summary="Apply the requested LAS change.",
        section_tasks=(
            SectionTask(
                goal="Apply the requested LAS change.",
                capability_ids=tuple(capabilities),
                existing_section_hint=section_hint,
                source_hints=source_hints,
                requirements=(request,),
            ),
        ),
    )


def _section_response(request: str, payload: dict[str, Any]) -> dict[str, object]:
    """Return one canonical section action for a frozen request."""
    if request.startswith("Using CBL_Main.dlis"):
        source = payload["section_context"]["sources"][0]["candidate_id"]
        title = (
            "Main Pass"
            if payload["section_task"]["existing_section_hint"] == "Main Pass"
            else "Repeat Pass"
        )
        response = _cbl_section_response(source_candidate=source, title=title)
    elif (
        "set the Gamma Ray curve" in request
        or "change the Gamma Ray curve" in request
        or "20–110" in request
    ):
        minimum, maximum = (20, 110) if "20–110" in request else (5, 125)
        handle = next(
            item["handle"]
            for item in payload["section_context"]["existing_curves"]
            if item["channel"] == "GR"
        )
        response = {
            "action": "update_curve_scale",
            "target": {"handle": handle},
            "scale": _scale(minimum, maximum),
        }
    elif "Append a 30 mm normal track" in request:
        response = {
            "action": "add_track",
            "track": {
                "semantic_id": "resistivity-qc",
                "kind": "normal",
                "title": "Resistivity QC",
                "width_mm": 30,
                "bindings": [
                    {
                        "kind": "curve",
                        "semantic_id": "ild",
                        "channel": "ILD",
                        "label": "Resistivity QC",
                        "scale": _scale(0.2, 2000, kind="log"),
                    }
                ],
            },
        }
    elif "fill from the Gamma Ray curve" in request:
        handle = next(
            item["handle"]
            for item in payload["section_context"]["existing_curves"]
            if item["channel"] == "GR"
        )
        response = {
            "action": "add_fill",
            "target": {"handle": handle},
            "fill": {
                "kind": "to_lower_limit",
                "semantic_id": "gr-fill",
                "target_binding": "GR",
                "color": "#f2e8a0",
                "alpha": 0.2,
            },
        }
    else:
        response = {
            "action": "add_track",
            "track": {
                "semantic_id": "resistivity-alias-qc",
                "kind": "normal",
                "title": "Resistivity Alias QC",
                "width_mm": 24,
                "bindings": [
                    {
                        "kind": "curve",
                        "semantic_id": "rt",
                        "channel": "RT",
                        "label": "Resistivity Alias QC",
                        "scale": _scale(0.2, 2000, kind="log"),
                    }
                ],
            },
        }
    return response


def _canonical_section_action(
    response: dict[str, object], payload: dict[str, Any]
) -> dict[str, object]:
    """Retain the already canonical action without a compatibility conversion."""
    del payload
    return response
