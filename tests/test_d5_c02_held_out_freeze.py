"""Provider-free integrity checks for the frozen D5-C02 population artifact."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from wellplot.io.dlis import load_dlis

ROOT = Path(__file__).resolve().parents[1]
REQUEST_PATH = ROOT / "tests/fixtures/d5_c02_held_out_request.json"
CONTRACT_PATH = ROOT / "tests/fixtures/d5_c02_held_out_contract.json"
CASES_PATH = ROOT / "tests/fixtures/nlp_d4_live_cases.json"

EXPECTED_CHECKPOINT = "abf5b5c7039fa6942cda076e6c47d780d600647b"
EXPECTED_SOURCE_HASHES = {
    "main_pass": "3ceb9100fd654d710155672a50a9e0f24ce9705db6ef8e424140f29bd02131f7",
    "repeat_pass": "a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640",
}
REQUIRED_CHANNELS = {
    "CBL",
    "VDL",
    "ECGR_STGC",
    "TT",
    "TENS",
    "MTEM",
    "STIT",
    "TDSP",
    "VSEC",
}


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_c02_is_outside_the_existing_d4_population() -> None:
    """Keep the held-out case out of the existing D4 population."""
    cases = _load(CASES_PATH)
    assert all(item.get("turn_id") != "D5-C02:C01" for item in cases["cases"])


def test_c02_request_and_contract_are_held_out_and_bound_to_checkpoint() -> None:
    """Bind the request and contract to the accepted freeze checkpoint."""
    request = _load(REQUEST_PATH)
    contract = _load(CONTRACT_PATH)

    assert request["turn_id"] == "D5-C02:C01"
    assert request["classification"] == "held_out_semantic_generalization"
    assert contract["turn_id"] == request["turn_id"]
    assert contract["model_unseen"] is True
    assert contract["execution_checkpoint"] == EXPECTED_CHECKPOINT


def test_c02_contract_covers_the_frozen_capability_envelope() -> None:
    """Require the same broad CBL/VDL capability envelope as C01."""
    contract = _load(CONTRACT_PATH)
    required = set(contract["required_capabilities"])
    expected = {
        "report_header_metadata",
        "ordered_service_titles",
        "multiple_semantic_remarks",
        "main_and_repeat_sections",
        "normal_reference_array_tracks",
        "explicit_track_widths",
        "multiple_scalar_curve_bindings",
        "repeated_channel_binding",
        "labels_scales_reverse_and_styles",
        "vdl_raster_presentation",
        "raster_profile_and_colormap",
        "colorbar",
        "sample_axis",
        "grid_visibility",
        "persistence_reload_render",
        "deterministic_contract_verification",
    }
    assert required == expected


def test_c02_source_inventory_matches_bytes_and_required_channels() -> None:
    """Verify source bytes, inventories, and required channels deterministically."""
    contract = _load(CONTRACT_PATH)
    inventory = contract["source_inventory"]
    for pass_name, expected_hash in EXPECTED_SOURCE_HASHES.items():
        item = inventory[pass_name]
        path = ROOT / item["path"]
        dataset = load_dlis(path)
        channels = set(dataset.channels)
        assert _sha256(path) == expected_hash
        assert len(channels) == item["channel_count"]
        assert channels == set(item["channels"])
        assert channels >= REQUIRED_CHANNELS


def test_c02_request_mentions_every_contract_identity_and_presentation_value() -> None:
    """Ensure every frozen contract value is represented in the request."""
    request = _load(REQUEST_PATH)["request"].casefold()
    contract = _load(CONTRACT_PATH)

    assert request.count("cbl") >= 4
    assert request.count("vdl") >= 2
    for metadata in contract["report"]["metadata"].values():
        fragment = f"{metadata['label']} {metadata['value']}".casefold()
        assert fragment in request
    for title in contract["report"]["service_titles"] + contract["report"]["remarks"]:
        assert title.casefold() in request
    for track in contract["sections"]["main_pass"]["tracks"]:
        assert f"{track['id']} = {track['kind']} {int(track['width_mm'])} mm" in request
    for binding_group in contract["bindings"].values():
        for binding in binding_group:
            assert binding["channel"].casefold() in request
            assert binding["label"].casefold() in request
    assert "secondary vertical grid lines visible" in request
    assert "source origin 35 and step 12" in request


def test_c02_contract_is_internally_consistent() -> None:
    """Check section, track, binding, and presentation structure without a model."""
    contract = _load(CONTRACT_PATH)
    for _section_id, section in contract["sections"].items():
        assert section["source"] in {"CBL_Main.dlis", "CBL_Repeat.dlis"}
        track_ids = [track["id"] for track in section["tracks"]]
        assert track_ids == ["combo", "depth", "cbl", "vdl"]
        assert [track["kind"] for track in section["tracks"]] == [
            "normal",
            "reference",
            "normal",
            "array",
        ]
        assert all(track["width_mm"] > 0 for track in section["tracks"])

    for group_name, bindings in contract["bindings"].items():
        if group_name == "vdl":
            assert len(bindings) == 1
            assert bindings[0]["kind"] == "raster"
            continue
        assert bindings
        for binding in bindings:
            scale = binding["scale"]
            assert scale["kind"] == "linear"
            assert scale["minimum"] != scale["maximum"]
            assert binding["style"]["line_width"] > 0
