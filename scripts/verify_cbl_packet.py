"""Deterministic acceptance checks for the supported CBL/VDL packet."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from wellplot.authoring import load_authoring_document

_EXPECTED_SECTIONS = ("main_pass", "repeat_pass")
_EXPECTED_TRACKS = (
    ("combo", "normal", 50.0),
    ("depth", "reference", 10.0),
    ("cbl", "normal", 44.0),
    ("vdl", "array", 48.0),
)
_EXPECTED_CURVES = {
    "combo": (
        ("ECGR_STGC", "Gamma Ray (ECGR_STGC) QTGC-B", 0.0, 150.0, False, "#16a34a", "-", 0.8),
        ("TT", "Transit Time for CBL (TT) QSLT-B", 200.0, 400.0, True, "#2142ff", "-", 0.75),
        ("TENS", "Cable Tension (TENS)", 5000.0, 0.0, False, "#111111", "--", 0.65),
        ("MTEM", "Mud Temperature (MTEM) LEH-MT", 100.0, 500.0, False, "#111111", "-", 0.9),
    ),
    "depth": (
        ("STIT", "Stuck Tool Indicator, Total (STIT)", 0.0, 50.0, False, "#111111", "-", 0.65),
        ("TDSP", "Cable Drag", 0.0, 50.0, False, "#92400e", ":", 0.65),
        ("VSEC", "Tool_Tot. Drag", 0.0, 50.0, False, "#1d4ed8", "--", 0.65),
    ),
    "cbl": (
        ("CBL", "CBL Amplitude (CBL) QSLT-B", 0.0, 100.0, False, "#111111", "-", 0.75),
        ("CBL", "CBL Amplitude (CBL) QSLT-B", 0.0, 10.0, False, "#2563eb", "--", 0.65),
    ),
}
_EXPECTED_HEADER_VALUES = {
    "company": "University of Utah",
    "well": "FORGE 16B (78)-32",
    "field": "Utah Forge",
    "county": "Beaver",
    "state_or_country": "Utah",
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
    "fluid_type": "Fresh Water",
    "run_number": "ONE",
    "driller_depth": "4980.00 ft",
    "logged_depth": "TD Not Tag",
    "fluid_density": "8.4 lbm/gal",
    "bottom_temperature": "177.2 degF",
    "logged_by": "D. May / D. Jones",
    "witnessed_by": "Leroy Swearingen",
}
_EXPECTED_SERVICE_TITLES = (
    "Cement Bond Log",
    "Variable Density Log",
    "Gamma Ray - CCL",
)
_LINE_STYLE_ALIASES = {
    "-": "-",
    "solid": "-",
    "--": "--",
    "dashed": "--",
    ":": ":",
    "dotted": ":",
}


def _close(left: object, right: float) -> bool:
    try:
        return abs(float(left) - right) < 1e-9
    except (TypeError, ValueError):
        return False


def _line_style_matches(actual: object, expected: object) -> bool:
    """Treat Matplotlib shorthand and equivalent descriptive styles equally."""
    actual_style = str(actual)
    expected_style = str(expected)
    return _LINE_STYLE_ALIASES.get(actual_style, actual_style) == _LINE_STYLE_ALIASES.get(
        expected_style, expected_style
    )


def _values_for_header_key(header: Mapping[str, Any], key: str) -> list[str]:
    values: list[str] = []
    general_keys = {key}
    if key == "state_or_country":
        general_keys = {"state", "country"}
    for field in header.get("general_fields", []):
        if isinstance(field, Mapping) and field.get("key") in general_keys:
            value = field.get("value")
            if isinstance(value, Mapping) and value.get("value") is not None:
                values.append(str(value["value"]))

    for row in header.get("detail", {}).get("rows", []):
        if not isinstance(row, Mapping):
            continue
        row_keys = {row.get("key"), *row.get("keys", [])}
        if key not in row_keys:
            continue
        values.extend(_nested_slot_values(row))
    return values


def _nested_slot_values(value: object) -> list[str]:
    if isinstance(value, Mapping):
        if "slot_id" in value and isinstance(value.get("value"), Mapping):
            slot_value = value["value"].get("value")
            return [] if slot_value is None else [str(slot_value)]
        result: list[str] = []
        for child in value.values():
            result.extend(_nested_slot_values(child))
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result = []
        for child in value:
            result.extend(_nested_slot_values(child))
        return result
    return []


def _check_header(payload: Mapping[str, Any], errors: list[str]) -> None:
    header = payload.get("header")
    if not isinstance(header, Mapping):
        errors.append("header is missing")
        return
    service_titles = [
        item.get("value", {}).get("value")
        for item in header.get("service_titles", [])
        if isinstance(item, Mapping) and isinstance(item.get("value"), Mapping)
    ]
    if tuple(service_titles[:3]) != _EXPECTED_SERVICE_TITLES:
        errors.append(f"service titles mismatch: {service_titles[:3]!r}")
    for key, expected in _EXPECTED_HEADER_VALUES.items():
        if not any(value == expected for value in _values_for_header_key(header, key)):
            errors.append(f"header value {key!r} is not {expected!r}")


def _check_remarks(payload: Mapping[str, Any], errors: list[str]) -> None:
    remarks = {
        item.get("title"): " ".join(
            [str(item.get("text") or ""), *[str(line) for line in item.get("lines", [])]]
        )
        for item in payload.get("remarks", [])
        if isinstance(item, Mapping)
    }
    required = {
        "Supported Reconstruction Scope": "Reconstruct only the supported subset",
        "Data Sources": "staged DLIS files",
        "Public Data and IP Notice": "wellplot",
    }
    for title, phrase in required.items():
        if title not in remarks or phrase.lower() not in remarks[title].lower():
            errors.append(f"remark {title!r} does not contain {phrase!r}")


def _check_scale(
    binding: Mapping[str, Any],
    *,
    minimum: float,
    maximum: float,
    reverse: bool,
    requirement: str,
    errors: list[str],
) -> None:
    scale = binding.get("scale")
    if not isinstance(scale, Mapping):
        errors.append(f"{requirement}: scale is missing")
        return
    if scale.get("kind") != "linear":
        errors.append(f"{requirement}: scale kind is not linear")
    actual_minimum = scale.get("minimum")
    actual_maximum = scale.get("maximum")
    actual_reverse = bool(scale.get("reverse"))
    expected_left = maximum if reverse else minimum
    expected_right = minimum if reverse else maximum
    actual_left = actual_maximum if actual_reverse else actual_minimum
    actual_right = actual_minimum if actual_reverse else actual_maximum
    if not _close(actual_left, expected_left) or not _close(actual_right, expected_right):
        errors.append(
            f"{requirement}: scale endpoints are "
            f"{actual_left!r} to {actual_right!r}, expected {expected_left!r} to {expected_right!r}"
        )


def _check_curve(
    binding: Mapping[str, Any],
    expected: tuple[object, ...],
    *,
    section_id: str,
    track_id: str,
    index: int,
    errors: list[str],
) -> None:
    channel, label, minimum, maximum, reverse, color, line_style, line_width = expected
    requirement = f"{section_id}/{track_id}[{index}]"
    if binding.get("kind") != "curve" or binding.get("channel") != channel:
        errors.append(f"{requirement}: expected curve channel {channel!r}")
    if binding.get("label") != label:
        errors.append(f"{requirement}: label mismatch")
    _check_scale(
        binding,
        minimum=minimum,
        maximum=maximum,
        reverse=reverse,
        requirement=requirement,
        errors=errors,
    )
    style = binding.get("style")
    if not isinstance(style, Mapping):
        errors.append(f"{requirement}: style is missing")
        return
    if style.get("color") != color:
        errors.append(f"{requirement}: color is {style.get('color')!r}")
    if not _line_style_matches(style.get("line_style"), line_style):
        errors.append(f"{requirement}: line style is {style.get('line_style')!r}")
    if not _close(style.get("line_width"), float(line_width)):
        errors.append(f"{requirement}: line width is {style.get('line_width')!r}")


def _check_raster(track: Mapping[str, Any], *, section_id: str, errors: list[str]) -> None:
    requirement = f"{section_id}/vdl/VDL"
    x_scale = track.get("x_scale")
    if not isinstance(x_scale, Mapping) or x_scale.get("kind") != "linear":
        errors.append(f"{requirement}: track x-scale is not linear")
    elif not _close(x_scale.get("minimum"), 200.0) or not _close(x_scale.get("maximum"), 1200.0):
        errors.append(f"{requirement}: track x-scale bounds are {x_scale!r}")
    grid = track.get("grid")
    if not isinstance(grid, Mapping) or grid.get("vertical_main_visible") is not False:
        errors.append(f"{requirement}: main vertical grid must be hidden")
    if not isinstance(grid, Mapping) or grid.get("vertical_secondary_visible") is not False:
        errors.append(f"{requirement}: secondary vertical grid must be hidden")

    bindings = [item for item in track.get("bindings", []) if isinstance(item, Mapping)]
    if len(bindings) != 1:
        errors.append(f"{requirement}: expected one raster binding")
        return
    binding = bindings[0]
    if binding.get("kind") != "raster" or binding.get("channel") != "VDL":
        errors.append(f"{requirement}: raster channel is not VDL")
    if binding.get("label") != "VDL VariableDensity (VDL) QSLT-B":
        errors.append(f"{requirement}: raster label mismatch")
    if binding.get("profile") != "vdl":
        errors.append(f"{requirement}: raster profile is not vdl")
    style = binding.get("style")
    if not isinstance(style, Mapping) or style.get("colormap") != "gray_r":
        errors.append(f"{requirement}: raster colormap is not gray_r")
    colorbar = binding.get("colorbar")
    if colorbar != {"enabled": True, "label": "Amplitude", "position": "header"}:
        errors.append(f"{requirement}: colorbar settings are {colorbar!r}")
    sample_axis = binding.get("sample_axis")
    expected_sample_axis = {
        "enabled": True,
        "unit": "us",
        "minimum": 200.0,
        "maximum": 1200.0,
        "tick_count": 7,
        "source_origin": 40.0,
        "source_step": 10.0,
    }
    if not isinstance(sample_axis, Mapping):
        errors.append(f"{requirement}: sample axis is missing")
    else:
        for key, expected in expected_sample_axis.items():
            actual = sample_axis.get(key)
            matches = (
                _close(actual, expected) if isinstance(expected, float) else actual == expected
            )
            if not matches:
                errors.append(f"{requirement}: sample axis {key} is {actual!r}")


def _check_sections(payload: Mapping[str, Any], errors: list[str]) -> None:
    sections = payload.get("sections")
    if not isinstance(sections, list) or [item.get("id") for item in sections] != list(
        _EXPECTED_SECTIONS
    ):
        errors.append("sections must be ordered as main_pass, repeat_pass")
        return
    for section_id, section in zip(_EXPECTED_SECTIONS, sections, strict=True):
        if not isinstance(section, Mapping):
            errors.append(f"section {section_id!r} is not an object")
            continue
        source = section.get("data_source")
        if not isinstance(source, Mapping) or source.get("source_format") != "dlis":
            errors.append(f"section {section_id}: DLIS data source is missing")
        else:
            expected_source = "CBL_Main.dlis" if section_id == "main_pass" else "CBL_Repeat.dlis"
            if Path(str(source.get("source_path", ""))).name != expected_source:
                errors.append(f"section {section_id}: source is not {expected_source}")
        depth_range = section.get("depth_range")
        if depth_range is not None:
            try:
                invalid_depth_range = (
                    not isinstance(depth_range, Sequence)
                    or len(depth_range) != 2
                    or float(depth_range[0]) >= float(depth_range[1])
                )
            except (TypeError, ValueError):
                invalid_depth_range = True
            if invalid_depth_range:
                errors.append(f"section {section_id}: depth range is invalid")
        tracks = section.get("tracks")
        if not isinstance(tracks, list) or [item.get("id") for item in tracks] != [
            item[0] for item in _EXPECTED_TRACKS
        ]:
            errors.append(f"section {section_id}: track order is invalid")
            continue
        for track, expected_track in zip(tracks, _EXPECTED_TRACKS, strict=True):
            track_id, kind, width = expected_track
            if not isinstance(track, Mapping):
                errors.append(f"section {section_id}: track {track_id} is not an object")
                continue
            if track.get("kind") != kind or not _close(track.get("width_mm"), width):
                errors.append(f"{section_id}/{track_id}: kind or width mismatch")
            if track_id == "vdl":
                _check_raster(track, section_id=section_id, errors=errors)
                continue
            bindings = [item for item in track.get("bindings", []) if isinstance(item, Mapping)]
            expected_curves = _EXPECTED_CURVES[track_id]
            if len(bindings) != len(expected_curves):
                errors.append(
                    f"{section_id}/{track_id}: expected {len(expected_curves)} "
                    f"bindings, got {len(bindings)}"
                )
                continue
            for index, expected_curve in enumerate(expected_curves):
                _check_curve(
                    bindings[index],
                    expected_curve,
                    section_id=section_id,
                    track_id=track_id,
                    index=index,
                    errors=errors,
                )
            if track_id == "cbl" and len({item.get("binding_id") for item in bindings}) != 2:
                errors.append(f"{section_id}/cbl: duplicate CBL bindings need distinct ids")


def _check_report_settings(payload: Mapping[str, Any], errors: list[str]) -> None:
    page = payload.get("page")
    if not isinstance(page, Mapping):
        errors.append("page settings are missing")
    else:
        for key, expected in {"size": "A4", "orientation": "portrait", "continuous": False}.items():
            if page.get(key) != expected:
                errors.append(f"page {key} is {page.get(key)!r}, expected {expected!r}")
        for key, expected in {"width_mm": 210.0, "height_mm": 297.0}.items():
            if page.get(key) is not None and not _close(page[key], expected):
                errors.append(f"page {key} overrides the requested A4 geometry: {page[key]!r}")
    # This packet requests readable typography. This is an evaluation criterion,
    # not a new minimum imposed on the general authoring API; None keeps auto sizing.
    header = payload.get("header") or {}
    for title in header.get("service_titles", []):
        _check_readable_font(title, "font_size", title.get("slot_id"), errors)
    for remark in payload.get("remarks", []):
        for key in ("font_size", "title_font_size"):
            _check_readable_font(remark, key, remark.get("title"), errors)
    output = payload.get("output")
    if not isinstance(output, Mapping) or output.get("backend") != "matplotlib":
        errors.append("output backend must be matplotlib")
    if not isinstance(payload.get("tail"), Mapping) or payload["tail"].get("enabled") is not True:
        errors.append("tail must be enabled")


def _check_readable_font(
    item: Mapping[str, Any], key: str, target: object, errors: list[str]
) -> None:
    """Reject unreadable explicit sizes in the CBL acceptance packet."""
    value = item.get(key)
    if value is not None and float(value) < 6.0:
        errors.append(f"{target}: {key} must be automatic or at least 6 pt, got {value!r}")


def verify_cbl_packet(logfile_path: str | Path) -> dict[str, Any]:
    """Verify the final supported CBL packet without consulting the agent."""
    path = Path(logfile_path)
    result: dict[str, Any] = {
        "ok": False,
        "document_path": str(path),
        "document_sha256": hashlib.sha256(path.read_bytes()).hexdigest()
        if path.is_file()
        else None,
        "errors": [],
    }
    errors: list[str] = result["errors"]
    try:
        document = load_authoring_document(path)
    except Exception as exc:  # pragma: no cover - exact Pydantic errors vary by version
        errors.append(f"document validation failed: {exc}")
        return result
    payload = document.model_dump(mode="json")
    _check_header(payload, errors)
    _check_remarks(payload, errors)
    _check_sections(payload, errors)
    _check_report_settings(payload, errors)
    result["ok"] = not errors
    return result


def main() -> int:
    """Run the verifier as a JSON-producing command-line check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logfile_path", type=Path)
    args = parser.parse_args()
    result = verify_cbl_packet(args.logfile_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
