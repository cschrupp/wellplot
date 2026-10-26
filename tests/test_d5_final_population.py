"""Provider-free tests for final D5 population assembly and C02 grading."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from scripts import d5_5_c02_contract_grader as c02_grader
from scripts import d5_5_final_population as final_population
from scripts import nlp_d5_live_semantic_qualification as d5

ROOT = Path(__file__).resolve().parents[1]


def _contract() -> dict[str, object]:
    return json.loads((ROOT / final_population.C02_CONTRACT_PATH).read_text(encoding="utf-8"))


def _value(value: object) -> dict[str, object]:
    return {"value": value}


def _valid_payload(contract: dict[str, object]) -> dict[str, object]:
    metadata = contract["report"]["metadata"]
    actual_keys = {
        "state": "country",
        "kb": "elevation_kb",
        "gl": "elevation_gl",
        "df": "elevation_df",
        "drilling_log_datum": "measured_from",
        "top_interval": "top_log_interval",
        "bottom_interval": "bottom_log_interval",
        "fluid": "fluid_type",
    }
    detail_keys = {
        "run": "run_number",
        "driller_depth": "driller_depth",
        "logged_depth": "logged_depth",
        "density": "fluid_density",
        "maximum_temperature": "bottom_temperature",
        "logged_by": "logged_by",
        "witnessed_by": "witnessed_by",
    }
    general_fields = []
    detail_rows = []
    for field, expected in metadata.items():
        key = actual_keys.get(field, field)
        if field in detail_keys:
            detail_rows.append(
                {
                    "key": detail_keys[field],
                    "label": expected["label"],
                    "values": [_value(expected["value"])],
                    "columns": [],
                    "keys": [],
                }
            )
        else:
            general_fields.append(
                {
                    "key": key,
                    "label": expected["label"],
                    "aliases": [],
                    "value": _value(expected["value"]),
                }
            )

    sections = []
    for section_id, expected_section in contract["sections"].items():
        tracks = []
        for expected_track in expected_section["tracks"]:
            track_id = expected_track["id"]
            track = {
                "id": track_id,
                "kind": expected_track["kind"],
                "width_mm": expected_track["width_mm"],
                "bindings": [],
            }
            if track_id == "vdl":
                expected_binding = contract["bindings"]["vdl"][0]
                track["x_scale"] = expected_binding["track_scale"]
                track["grid"] = expected_binding["grid"]
                track["bindings"] = [
                    {
                        "kind": "raster",
                        "channel": expected_binding["channel"],
                        "label": expected_binding["label"],
                        "profile": expected_binding["profile"],
                        "style": {"colormap": expected_binding["colormap"]},
                        "colorbar": expected_binding["colorbar"],
                        "sample_axis": expected_binding["sample_axis"],
                    }
                ]
            else:
                for expected_binding in contract["bindings"][track_id]:
                    track["bindings"].append(
                        {
                            "kind": "curve",
                            "channel": expected_binding["channel"],
                            "label": expected_binding["label"],
                            "scale": copy.deepcopy(expected_binding["scale"]),
                            "style": copy.deepcopy(expected_binding["style"]),
                        }
                    )
            tracks.append(track)
        sections.append(
            {
                "id": section_id,
                "data_source": {"source_path": expected_section["source"]},
                "tracks": tracks,
            }
        )

    return {
        "header": {
            "general_fields": general_fields,
            "service_titles": [
                {"value": _value(title)} for title in contract["report"]["service_titles"]
            ],
            "detail": {"rows": detail_rows},
        },
        "remarks": [{"title": title} for title in contract["report"]["remarks"]],
        "sections": sections,
        "tail": {"enabled": True},
    }


def test_final_population_has_nine_d4_turns_then_c02() -> None:
    """Assemble the final ten-turn population without changing D4 fixtures."""
    cases, gold = final_population.load_final_population(ROOT)
    assert len(cases) == 10
    assert len(gold["cases"]) == 10
    assert tuple(case["turn_id"] for case in cases) == final_population.FINAL_TURN_IDS
    assert cases[-1]["request_sha256"]
    assert gold["cases"][-1]["grader"] == "d5_c02_contract"


def test_c02_grader_passes_the_frozen_contract_shape() -> None:
    """Grade a provider-free canonical payload against the frozen C02 contract."""
    contract = _contract()
    result = c02_grader.grade_c02_payload(_valid_payload(contract), contract)
    assert result["status"] == "PASS", result["errors"]
    assert all(item["status"] == "PASS" for item in result["verifier_requirements"])


def test_c02_grader_rejects_metadata_and_presentation_drift() -> None:
    """Reject wrong frozen metadata and a wrong C02 presentation scale."""
    contract = _contract()
    payload = _valid_payload(contract)
    payload["header"]["general_fields"][0]["value"]["value"] = "Wrong Company"
    payload["sections"][0]["tracks"][0]["bindings"][0]["scale"]["maximum"] = 136.0
    result = c02_grader.grade_c02_payload(payload, contract)
    assert result["status"] == "FAIL"
    assert any("metadata value missing" in error for error in result["errors"])
    assert any("scale mismatch" in error for error in result["errors"])


def test_d5_grading_dispatches_c02_without_changing_d4_grading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route only the frozen C02 grader through the final-population seam."""
    called = {}

    def fake_grader(actual: dict[str, object], contract: dict[str, object]) -> dict[str, object]:
        del actual
        called["contract"] = contract
        return {"status": "PASS", "errors": [], "verifier_requirements": []}

    monkeypatch.setattr(d5, "grade_c02_artifact", fake_grader)
    expected = {"grader": "d5_c02_contract", "contract": {"case_id": "D5-C02"}}
    assert d5._grade_turn({}, expected)["status"] == "PASS"
    assert called["contract"]["case_id"] == "D5-C02"
