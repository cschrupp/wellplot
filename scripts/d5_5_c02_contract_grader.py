"""Deterministic grader for the frozen D5-C02 construction contract."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from wellplot.authoring import load_authoring_document

_REQUIREMENT_NAMES = (
    ("C02-01", "report metadata"),
    ("C02-02", "service titles and remarks"),
    ("C02-03", "section sources and track structure"),
    ("C02-04", "scalar binding identity and presentation"),
    ("C02-05", "VDL raster presentation"),
    ("C02-06", "tail and end-to-end artifact state"),
)
_HEADER_KEYS = {
    "company": ("company",),
    "well": ("well",),
    "field": ("field",),
    "county": ("county",),
    "state": ("country", "state"),
    "section": ("section",),
    "township": ("township",),
    "range": ("range",),
    "footage": ("footage",),
    "latitude": ("latitude",),
    "longitude": ("longitude",),
    "logging_date": ("logging_date",),
    "kb": ("elevation_kb",),
    "gl": ("elevation_gl",),
    "df": ("elevation_df",),
    "drilling_log_datum": ("measured_from", "log_measured_from"),
    "top_interval": ("top_log_interval",),
    "bottom_interval": ("bottom_log_interval",),
    "fluid": ("fluid_type",),
    "run": ("run_number",),
    "driller_depth": ("driller_depth",),
    "logged_depth": ("logged_depth",),
    "density": ("fluid_density",),
    "maximum_temperature": ("bottom_temperature",),
    "logged_by": ("logged_by",),
    "witnessed_by": ("witnessed_by",),
}


def _close(actual: object, expected: object) -> bool:
    try:
        return math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-9)
    except (TypeError, ValueError):
        return actual == expected


def _matches_expected_fields(actual: object, expected: object) -> bool:
    """Match frozen fields while allowing canonical model default fields."""
    if isinstance(expected, Mapping):
        return isinstance(actual, Mapping) and all(
            key in actual and _matches_expected_fields(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes, bytearray)):
        return (
            isinstance(actual, Sequence)
            and not isinstance(actual, (str, bytes, bytearray))
            and len(actual) == len(expected)
            and all(
                _matches_expected_fields(left, right)
                for left, right in zip(actual, expected, strict=True)
            )
        )
    return _close(actual, expected)


def _slot_values(value: object) -> list[str]:
    values: list[str] = []
    if isinstance(value, Mapping):
        if (
            "value" in value
            and not isinstance(value["value"], Mapping)
            and value["value"] is not None
        ):
            values.append(str(value["value"]))
        for nested in value.values():
            values.extend(_slot_values(nested))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            values.extend(_slot_values(nested))
    return values


def _indexed_header_values(payload: Mapping[str, Any]) -> dict[str, list[str]]:
    indexed: dict[str, list[str]] = {}
    header = payload.get("header")
    if not isinstance(header, Mapping):
        return indexed
    for field in header.get("general_fields", []):
        if not isinstance(field, Mapping):
            continue
        names = [field.get("key"), field.get("label"), *field.get("aliases", [])]
        values = _slot_values(field.get("value"))
        for name in names:
            if name:
                indexed.setdefault(str(name).casefold(), []).extend(values)
    detail = header.get("detail")
    if isinstance(detail, Mapping):
        for row in detail.get("rows", []):
            if not isinstance(row, Mapping):
                continue
            names = [row.get("key"), row.get("label"), *row.get("keys", [])]
            values = _slot_values(row.get("values", [])) + _slot_values(row.get("columns", []))
            for name in names:
                if name:
                    indexed.setdefault(str(name).casefold(), []).extend(values)
    return indexed


def _check_metadata(payload: Mapping[str, Any], contract: Mapping[str, Any]) -> list[str]:
    metadata = contract.get("report", {}).get("metadata", {})
    indexed = _indexed_header_values(payload)
    errors: list[str] = []
    for field, expected in metadata.items():
        aliases = _HEADER_KEYS.get(field, (field,))
        actual_values = [value for alias in aliases for value in indexed.get(alias, [])]
        if str(expected.get("value")) not in actual_values:
            errors.append(f"metadata value missing: {field}")
    return errors


def _check_report(payload: Mapping[str, Any], contract: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    header = payload.get("header")
    titles = []
    if isinstance(header, Mapping):
        titles = [
            item.get("value", {}).get("value")
            for item in header.get("service_titles", [])
            if isinstance(item, Mapping) and isinstance(item.get("value"), Mapping)
        ]
    expected_titles = contract.get("report", {}).get("service_titles", [])
    if titles != expected_titles:
        errors.append("service title order or values mismatch")
    remarks = payload.get("remarks")
    actual_remarks = (
        [item.get("title") for item in remarks if isinstance(item, Mapping)]
        if isinstance(remarks, list)
        else []
    )
    expected_remarks = contract.get("report", {}).get("remarks", [])
    if actual_remarks != expected_remarks:
        errors.append("remark order or values mismatch")
    return errors


def _check_sections(payload: Mapping[str, Any], contract: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    sections = payload.get("sections")
    if not isinstance(sections, list):
        return ["sections missing"]
    expected_sections = contract.get("sections", {})
    actual_section_ids = [item.get("id") for item in sections if isinstance(item, Mapping)]
    expected_section_ids = list(expected_sections)
    if actual_section_ids != expected_section_ids:
        errors.append("section identity, order, or cardinality mismatch")
    actual_by_id = {item.get("id"): item for item in sections if isinstance(item, Mapping)}
    for section_id, expected_section in expected_sections.items():
        actual_section = actual_by_id.get(section_id)
        if not isinstance(actual_section, Mapping):
            errors.append(f"section missing: {section_id}")
            continue
        source = actual_section.get("data_source")
        expected_source = expected_section.get("source")
        if (
            not isinstance(source, Mapping)
            or Path(str(source.get("source_path", ""))).name != expected_source
        ):
            errors.append(f"section source mismatch: {section_id}")
        actual_tracks = actual_section.get("tracks", [])
        if not isinstance(actual_tracks, list):
            errors.append(f"tracks missing: {section_id}")
            continue
        expected_tracks = expected_section.get("tracks", [])
        expected_track_ids = [item["id"] for item in expected_tracks]
        actual_track_ids = [item.get("id") for item in actual_tracks if isinstance(item, Mapping)]
        if actual_track_ids != expected_track_ids:
            errors.append(f"track identity or order mismatch: {section_id}")
        tracks = {item.get("id"): item for item in actual_tracks if isinstance(item, Mapping)}
        for expected_track in expected_tracks:
            track_id = expected_track["id"]
            actual_track = tracks.get(track_id)
            if not isinstance(actual_track, Mapping):
                errors.append(f"track missing: {section_id}/{track_id}")
                continue
            if actual_track.get("kind") != expected_track["kind"] or not _close(
                actual_track.get("width_mm"), expected_track["width_mm"]
            ):
                errors.append(f"track identity or width mismatch: {section_id}/{track_id}")
    return errors


def _check_scalar_bindings(payload: Mapping[str, Any], contract: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_bindings = contract.get("bindings", {})
    for section in payload.get("sections", []):
        if not isinstance(section, Mapping):
            continue
        section_id = str(section.get("id"))
        for track in section.get("tracks", []):
            if not isinstance(track, Mapping):
                continue
            track_id = str(track.get("id"))
            if track_id == "vdl":
                continue
            expected = expected_bindings.get(track_id, [])
            actual = [item for item in track.get("bindings", []) if isinstance(item, Mapping)]
            if len(actual) != len(expected):
                errors.append(f"binding count mismatch: {section_id}/{track_id}")
                continue
            for index, (actual_binding, expected_binding) in enumerate(
                zip(actual, expected, strict=True)
            ):
                if actual_binding.get("channel") != expected_binding["channel"]:
                    errors.append(f"channel mismatch: {section_id}/{track_id}[{index}]")
                if actual_binding.get("label") != expected_binding["label"]:
                    errors.append(f"label mismatch: {section_id}/{track_id}[{index}]")
                for key in ("kind", "minimum", "maximum", "reverse"):
                    if not _close(
                        actual_binding.get("scale", {}).get(key),
                        expected_binding["scale"].get(key),
                    ):
                        errors.append(f"scale mismatch: {section_id}/{track_id}[{index}]")
                for key in ("color", "line_style"):
                    if actual_binding.get("style", {}).get(key) != expected_binding["style"][key]:
                        errors.append(f"style mismatch: {section_id}/{track_id}[{index}]")
                if not _close(
                    actual_binding.get("style", {}).get("line_width"),
                    expected_binding["style"]["line_width"],
                ):
                    errors.append(f"line width mismatch: {section_id}/{track_id}[{index}]")
    return errors


def _check_raster_binding(payload: Mapping[str, Any], contract: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = contract.get("bindings", {}).get("vdl", [])
    for section in payload.get("sections", []):
        if not isinstance(section, Mapping):
            continue
        section_id = str(section.get("id"))
        for track in section.get("tracks", []):
            if not isinstance(track, Mapping) or track.get("id") != "vdl":
                continue
            actual = [item for item in track.get("bindings", []) if isinstance(item, Mapping)]
            if len(actual) != len(expected):
                errors.append(f"binding count mismatch: {section_id}/vdl")
                continue
            item = actual[0]
            target = expected[0]
            if item.get("kind") != target["kind"] or item.get("channel") != target["channel"]:
                errors.append(f"raster identity mismatch: {section_id}/vdl")
            if item.get("label") != target["label"] or item.get("profile") != target["profile"]:
                errors.append(f"raster label or profile mismatch: {section_id}/vdl")
            x_scale = track.get("x_scale", {})
            expected_scale = target["track_scale"]
            for key in ("kind", "minimum", "maximum", "reverse"):
                if not _close(x_scale.get(key), expected_scale.get(key)):
                    errors.append(f"raster scale mismatch: {section_id}/vdl")
            style = item.get("style", {})
            if style.get("colormap") != target["colormap"]:
                errors.append(f"raster colormap mismatch: {section_id}/vdl")
            if item.get("colorbar") != target["colorbar"]:
                errors.append(f"raster colorbar mismatch: {section_id}/vdl")
            if not _matches_expected_fields(item.get("sample_axis"), target["sample_axis"]):
                errors.append(f"raster sample axis mismatch: {section_id}/vdl")
            grid = track.get("grid", {})
            if grid.get("vertical_main_visible") != target["grid"]["vertical_main_visible"]:
                errors.append(f"main grid mismatch: {section_id}/vdl")
            if (
                grid.get("vertical_secondary_visible")
                != target["grid"]["vertical_secondary_visible"]
            ):
                errors.append(f"secondary grid mismatch: {section_id}/vdl")
    return errors


def grade_c02_payload(payload: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    """Grade one canonical C02 document against the frozen contract."""
    tail = payload.get("tail")
    checks = [
        ("C02-01", _check_metadata(payload, contract)),
        ("C02-02", _check_report(payload, contract)),
        ("C02-03", _check_sections(payload, contract)),
        ("C02-04", _check_scalar_bindings(payload, contract)),
        ("C02-05", _check_raster_binding(payload, contract)),
        (
            "C02-06",
            [] if isinstance(tail, Mapping) and tail.get("enabled") is True else ["tail missing"],
        ),
    ]
    errors = [error for _, failures in checks for error in failures]
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "verifier_status": "PASS" if not errors else "FAIL",
        "verifier_requirements": [
            {"id": requirement_id, "status": "PASS" if not failures else "FAIL"}
            for requirement_id, failures in checks
        ],
    }


def grade_c02_artifact(actual: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    """Grade persisted/rendered C02 output without mutating the artifact."""
    errors: list[str] = []
    requirements: list[dict[str, str]] = []
    artifact_path = actual.get("artifact_path")
    artifact_state_ok = (
        actual.get("persisted") is True
        and actual.get("rendered") is True
        and actual.get("rendered_artifact_path") == artifact_path
        and bool(artifact_path)
    )
    if actual.get("persisted") is not True:
        errors.append("persistence_not_proven")
    if actual.get("rendered") is not True:
        errors.append("render_not_proven")
    if actual.get("rendered_artifact_path") != artifact_path:
        errors.append("rendered_wrong_artifact")
    if not artifact_path:
        errors.append("artifact_path_missing")
    else:
        try:
            payload = load_authoring_document(Path(str(artifact_path))).model_dump(mode="json")
        except Exception as error:
            errors.append(f"canonical_document_invalid: {type(error).__name__}")
        else:
            result = grade_c02_payload(payload, contract)
            errors.extend(result["errors"])
            requirements = result["verifier_requirements"]
    if requirements and not artifact_state_ok:
        for requirement in requirements:
            if requirement["id"] == "C02-06":
                requirement["status"] = "FAIL"
    if not requirements:
        requirements = [
            {"id": requirement_id, "status": "FAIL"} for requirement_id, _name in _REQUIREMENT_NAMES
        ]
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "verifier_status": "PASS" if not errors else "FAIL",
        "verifier_requirements": requirements,
    }
